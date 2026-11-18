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
                    resident_bytes, save_json, sha256, stable_id, git_state)
from engines import MODE, make_query_fn, make_server
from workload import (cgroup_memory_bytes, concurrency_run, latency_sweep, memory_passes,
                      proc_counters)


def ints(s):
    return [int(x) for x in s.split(",") if x]


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["pg", "qdrant"], required=True)
    ap.add_argument("--n", type=int, default=100_000)
    ap.add_argument("--dim", type=int, default=1024)
    ap.add_argument("--synthetic", action="store_true", help="random clustered vectors instead of MS MARCO (smoke tests)")
    ap.add_argument("--seed", type=int, default=42, help="seed for synthetic data generation")
    ap.add_argument("--warm-seed", type=int, default=7, help="seed for warm-up vector sampling")
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
    ap.add_argument("--pg-unlogged", action="store_true",
                    help="create the table UNLOGGED so the load and index build skip most WAL")
    ap.add_argument("--qdrant-upload-parallel", type=int, default=1,
                    help="parallel gRPC upload streams (1 reproduces the single-stream baseline)")
    ap.add_argument("--qdrant-upload-batch", type=int, default=512,
                    help="points per upload batch (512 reproduces the baseline)")
    ap.add_argument("--qdrant-defer-indexing", action="store_true",
                    help="disable indexing during the upload and restore the threshold afterwards")
    ap.add_argument("--qdrant-max-indexing-threads", type=int, default=0,
                    help="HNSW build threads for Qdrant; 0 keeps automatic selection")
    ap.add_argument("--memory-passes", type=int, default=0,
                    help="memory study: after every restart with an evicted page cache run this many full-query-set "
                         "passes (the first is the cold start, the rest are steady state); replaces the latency sweep")
    ap.add_argument("--memory-ef", type=int, default=128, help="ef used by the memory study")
    ap.add_argument("--memory-clients", type=int, default=0,
                    help="memory study: closed-loop clients for one window after the passes (0 = none)")
    ap.add_argument("--memory-conc-duration", type=float, default=60)
    ap.add_argument("--order-seed", type=int, default=None,
                    help="seed of the memory study query order; defaults to --seed")
    ap.add_argument("--qdrant-on-disk", action="store_true", help="mmap vectors and HNSW (needed for memory limits)")
    ap.add_argument("--qdrant-indexing-threshold-kb", type=int, default=None)
    ap.add_argument("--qdrant-segments", type=int, default=0,
                    help="target optimized segment count; 0 keeps Qdrant automatic selection")
    ap.add_argument("--qdrant-search-threads", type=int, default=0,
                    help="Qdrant search pool size; 0 keeps automatic selection")
    ap.add_argument("--qdrant-require-indexed", action="store_true",
                    help="fail if the final collection does not index every vector")
    ap.add_argument("--qdrant-control-grace-s", type=float, default=60,
                    help="maximum stable-green wait for requested segment/index controls")
    ap.add_argument("--perf", action="store_true", help="perf stat the server during concurrency windows")
    ap.add_argument("--tag", default="", help="suffix for the result folder name")
    ap.add_argument("--experiment-id", default=None,
                    help="globally unique run ID; defaults to config/job/engine-derived ID")
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
    base, queries, dtag = load_vectors(a.n, a.dim, a.synthetic, seed=a.seed)
    gt = ground_truth(base, queries, a.k, dtag)
    if a.nq:
        queries, gt = queries[:a.nq], gt[:a.nq]
    rng = np.random.default_rng(a.warm_seed)
    warm = base[rng.choice(len(base), size=min(a.warm, len(base)), replace=False)]
    log(f"data: {base.shape} base, {queries.shape} queries ({dtag})")

    config = {key: value for key, value in vars(a).items()
              if key not in {"out", "work", "keep", "experiment_id"}}
    config_id = stable_id(config)
    experiment_id = a.experiment_id or f"{config_id}-{job}-{name}"
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    revision = git_state(repo)
    result = {
        "schema_version": 2,
        "provenance_status": "native",
        "experiment_id": experiment_id,
        "config_id": config_id,
        "seed": a.seed,
        "warm_seed": a.warm_seed,
        "code_commit": revision["commit"],
        "code_dirty": revision["dirty"],
        "command": sys.argv,
        "engine": a.engine, "args": vars(a), "dataset": dtag, "n": len(base), "dim": base.shape[1],
        "n_queries": len(queries), "server_cores": server_cores, "client_cores": client_cores,
        "mode": MODE, "host": host_info(), "runs": [], "status": "running",
    }
    image = os.environ.get("PG_SIF" if a.engine == "pg" else "QDRANT_SIF")
    result["image_sha256"] = sha256(image) if MODE == "apptainer" else None
    rpath = os.path.join(out_dir, "result.json")
    if os.path.exists(rpath):
        sys.exit(f"refusing to overwrite existing raw result: {rpath}")
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
            # The memory study starts every limit, including "none", from the same state: the
            # server restarted with its files evicted from the page cache.
            if lim != "none" or a.memory_passes:
                srv.stop()
                data_dir = srv.data if a.engine == "pg" else srv.storage
                run["resident_before_evict"] = resident_bytes(data_dir)
                run["evicted_bytes"] = evict_page_cache(data_dir)
                run["resident_after_evict"] = resident_bytes(data_dir)
                srv.start(mem_limit=None if lim == "none" else lim)
            if a.memory_passes:
                proto = protocols[0]
                log(f"== {name} mem_limit={lim}: {a.memory_passes} passes over {len(queries)} queries, ef={a.memory_ef}")
                query = make_query_fn(srv.query_spec(a.memory_ef, proto, a.k))
                rows, r = memory_passes(
                    query, queries, gt, a.k, a.memory_passes,
                    a.seed if a.order_seed is None else a.order_seed,
                    counters_fn=lambda: proc_counters(srv.pids()),
                    stats_begin=lambda: srv.stats_begin(proto), stats_end=lambda: srv.stats_end(proto))
                run["memory_passes"] = [{"proto": proto, "ef": a.memory_ef, **row} for row in rows]
                run["resident_after_passes"] = resident_bytes(data_dir)
                server_pids = srv.pids()
                run["server_cgroup_memory_bytes"] = cgroup_memory_bytes(server_pids[0]) if server_pids else None
                raw.update({f"{lim}_{key}": v for key, v in r.items()})
                save_json(result | {"runs": result["runs"] + [run]}, rpath)
                if a.memory_clients:
                    row, r = concurrency_run(srv, proto, a.memory_ef, a.memory_clients, a.memory_conc_duration,
                                             0, queries, gt, a.k, None)
                    run["concurrency"] = [row]
                    raw.update({f"{lim}_{key}": v for key, v in r.items()})
                if a.engine == "qdrant":
                    run["collection_state"] = srv.collection_state()
                result["runs"].append(run)
                save_json(result, rpath)
                continue
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
