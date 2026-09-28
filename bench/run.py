"""Runs one engine through build, latency sweeps and concurrency, and writes result.json + raw.npz.

Typical use inside a Slurm job (pg and qdrant back to back on the same node):
  python run.py --engine pg     --n 1000000 --out $RES/scale_1M
  python run.py --engine qdrant --n 1000000 --out $RES/scale_1M
"""
import argparse
import os
import sys
import time
import traceback

import numpy as np

from common import (evict_page_cache, ground_truth, host_info, load_vectors, log, pick_cores,
                    resident_bytes, save_json, sha256)
from engines import MODE, make_server
from workload import concurrency_run, latency_sweep


def ints(s):
    return [int(x) for x in s.split(",") if x]


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["pg", "qdrant"], required=True)
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--dim", type=int, default=1024)
    ap.add_argument("--synthetic", action="store_true", help="random clustered vectors instead of MS MARCO (smoke tests)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--m", type=int, default=16)
    ap.add_argument("--efc", type=int, default=64)
    ap.add_argument("--ef", type=ints, default=[16, 32, 64, 96, 128, 192, 256, 384, 512, 768])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--warm", type=int, default=500, help="untimed warm-up queries per (protocol, ef)")
    ap.add_argument("--nq", type=int, default=0,
                    help="measure only the first nq queries (0 = all); for slow out-of-core runs on a spinning disk")
    ap.add_argument("--protocols", default="grpc_raw,grpc,rest",
                    help="qdrant only: grpc_raw (protobuf stub), grpc (qdrant-client), rest. pg uses its wire protocol")
    ap.add_argument("--clients", type=ints, default=[1, 2, 4, 8, 16, 32, 48])
    ap.add_argument("--conc-ef", type=int, default=64)
    ap.add_argument("--conc-recall", type=float, default=0.95,
                    help="also run concurrency at the smallest swept ef reaching this recall (0 disables)")
    ap.add_argument("--conc-duration", type=float, default=30)
    ap.add_argument("--conc-warmup", type=float, default=5)
    ap.add_argument("--conc-all-limits", action="store_true", help="also run concurrency under memory limits")
    ap.add_argument("--mem-limits", default="none", help="e.g. none,8G,4G,2G; each one restarts the server cold")
    ap.add_argument("--server-cores", default="auto:8")
    ap.add_argument("--client-cores", default="auto")
    ap.add_argument("--pg-shared-buffers", default="32GB")
    ap.add_argument("--pg-effective-cache", default="64GB")
    ap.add_argument("--pg-maintenance-mem", default="16GB")
    ap.add_argument("--pg-planner", choices=["force-index", "default"], default="force-index",
                    help="force-index sets enable_seqscan=off; default leaves the choice to the planner, "
                         "which falls back to an exact parallel scan for some ef values (TOAST costing)")
    ap.add_argument("--qdrant-on-disk", action="store_true", help="mmap vectors and HNSW (needed for memory limits)")
    ap.add_argument("--qdrant-indexing-threshold-kb", type=int, default=None)
    ap.add_argument("--perf", action="store_true", help="perf stat the server during concurrency windows")
    ap.add_argument("--tag", default="", help="suffix for the result folder name")
    ap.add_argument("--work", default=None, help="node-local scratch; defaults to $TMPDIR or /tmp")
    ap.add_argument("--keep", action="store_true", help="keep the database files after the run")
    ap.add_argument("--out", required=True)
    return ap.parse_args()


def main():
    a = parse()
    protocols = ["pg"] if a.engine == "pg" else [p for p in a.protocols.split(",") if p]
    server_cores, client_cores = pick_cores(a.server_cores, a.client_cores)
    os.sched_setaffinity(0, client_cores)  # this process, its BLAS threads and all client workers

    job = os.environ.get("SLURM_JOB_ID", str(int(time.time())))
    work = a.work or os.path.join(os.environ.get("TMPDIR") or "/tmp", f"bench_{os.getuid()}_{job}")
    name = f"{a.engine}{('_' + a.tag) if a.tag else ''}"
    out_dir = os.path.join(a.out, name)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work, exist_ok=True)

    log(f"{name}: server cores {server_cores}, client cores {client_cores}, work {work}")
    base, queries, dtag = load_vectors(a.n, a.dim, a.synthetic)
    gt = ground_truth(base, queries, a.k, dtag)
    if a.nq:
        queries, gt = queries[:a.nq], gt[:a.nq]
    rng = np.random.default_rng(7)
    warm = base[rng.choice(len(base), size=min(a.warm, len(base)), replace=False)]
    log(f"data: {base.shape} base, {queries.shape} queries ({dtag})")

    result = {
        "engine": a.engine, "args": vars(a), "dataset": dtag, "n": len(base), "dim": base.shape[1],
        "n_queries": len(queries), "server_cores": server_cores, "client_cores": client_cores,
        "mode": MODE, "host": host_info(), "runs": [], "status": "running",
    }
    image = os.environ.get("PG_SIF" if a.engine == "pg" else "QDRANT_SIF")
    result["image_sha256"] = sha256(image) if MODE == "apptainer" else None
    rpath = os.path.join(out_dir, "result.json")
    raw = {}

    srv = make_server(a.engine, work, server_cores, a)
    srv.log_dir = out_dir
    try:
        srv.init()
        srv.start()
        result["build"] = srv.build(base, a.m, a.efc)
        result["server_info"] = srv.info()
        save_json(result, rpath)

        for lim in [x for x in a.mem_limits.split(",") if x]:
            run = {"mem_limit": lim}
            if lim != "none":
                srv.stop()
                data_dir = srv.data if a.engine == "pg" else srv.storage
                run["resident_before_evict"] = resident_bytes(data_dir)
                run["evicted_bytes"] = evict_page_cache(data_dir)
                run["resident_after_evict"] = resident_bytes(data_dir)
                srv.start(mem_limit=lim)
            log(f"== {name} mem_limit={lim}: latency sweep")
            run["latency"], r = latency_sweep(srv, protocols, a.ef, a.reps, queries, warm, gt, a.k)
            raw.update({f"{lim}_{key}": v for key, v in r.items()})
            save_json(result | {"runs": result["runs"] + [run]}, rpath)

            if a.clients and (lim == "none" or a.conc_all_limits):
                # Fixed ef is not a fair comparison when the engines reach different recall at the
                # same ef, so concurrency also runs at the ef that reaches the target recall.
                conc_efs = [a.conc_ef]
                if a.conc_recall:
                    rows = sorted((x for x in run["latency"] if x["proto"] == protocols[0] and x["rep"] == 0),
                                  key=lambda x: x["ef"])
                    ok = [x["ef"] for x in rows if x["recall_at_k"] >= a.conc_recall]
                    run["conc_matched_ef"] = ok[0] if ok else rows[-1]["ef"]
                    conc_efs = sorted({a.conc_ef, run["conc_matched_ef"]})
                run["concurrency"] = []
                for ef, proto, c in [(e, p, c) for e in conc_efs for p in protocols for c in a.clients]:
                    perf_path = os.path.join(out_dir, f"perf_{lim}_{proto}_ef{ef}_c{c}.csv") if a.perf else None
                    row, r = concurrency_run(srv, proto, ef, c, a.conc_duration, a.conc_warmup,
                                             queries, gt, a.k, perf_path)
                    run["concurrency"].append(row)
                    raw.update({f"{lim}_{key}": v for key, v in r.items()})
                    save_json(result | {"runs": result["runs"] + [run]}, rpath)
            if a.engine == "qdrant":
                run["collection_state"] = srv.collection_state()
            result["runs"].append(run)
            save_json(result, rpath)
        result["status"] = "ok"
    except Exception:
        result["status"] = "failed"
        result["error"] = traceback.format_exc()
        log(result["error"])
    finally:
        srv.stop()
        save_json(result, rpath)
        np.savez_compressed(os.path.join(out_dir, "raw.npz"), **raw)
        if not a.keep:
            import shutil
            shutil.rmtree(srv.work, ignore_errors=True)
    log(f"{name}: {result['status']}, results in {out_dir}")
    sys.exit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
