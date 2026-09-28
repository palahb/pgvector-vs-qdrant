"""Prints compact tables for every result.json under a folder. Paste this output back for review.
Usage: python summarize.py $BENCH_RESULTS/e1_scale
"""
import glob
import json
import os
import sys


def fmt(v, w=9):
    if v is None:
        return "-".rjust(w)
    if isinstance(v, float):
        return f"{v:.3f}".rjust(w) if abs(v) < 1000 else f"{v:.0f}".rjust(w)
    return str(v).rjust(w)


def main(root):
    files = sorted(glob.glob(os.path.join(root, "**", "result.json"), recursive=True))
    if not files:
        sys.exit(f"no result.json under {root}")
    for path in files:
        r = json.load(open(path))
        h = r.get("host", {})
        print(f"\n### {os.path.relpath(os.path.dirname(path), root)}  [{r['status']}]  "
              f"n={r['n']} dim={r['dim']} m={r['args']['m']} efc={r['args']['efc']}  "
              f"node={h.get('hostname')} srv_cores={len(r['server_cores'])} cli_cores={len(r['client_cores'])}")
        if r.get("error"):
            print("ERROR:", r["error"].strip().splitlines()[-1])
        b = r.get("build")
        if b:
            keys = ["load_s", "index_s", "upload_s", "index_wait_s", "total_s", "index_bytes", "storage_bytes",
                    "fully_indexed", "final_state"]
            print("build:", ", ".join(f"{k}={b[k]}" for k in keys if k in b))
            if b.get("notices"):
                print("pg notices:", [n for n in b["notices"] if "does not exist" not in n])
        si = r.get("server_info", {})
        if si:
            print("server:", si.get("version", "")[:60], "pgvector", si.get("pgvector", "")) if r["engine"] == "pg" \
                else print("server: qdrant", si.get("version"))
        for run in r.get("runs", []):
            lim = run["mem_limit"]
            extra = ""
            if "evicted_bytes" in run:
                extra = f"  evicted={run['evicted_bytes'] / 2**30:.2f}GB resident_after={run.get('resident_after_evict')}"
            print(f"-- mem_limit={lim}{extra}")
            print("   proto        ef rep  recall   mean_ms    p99_ms  srv_mean  hit_ratio  rd/query")
            for x in run.get("latency", []):
                print(f"   {x['proto']:9s}{x['ef']:5d}{x['rep']:4d} {x['recall_at_k']:.4f}{fmt(x.get('mean_ms'))}{fmt(x.get('p99_ms'))}"
                      f"{fmt(x.get('server_mean_ms'))}{fmt(x.get('buffer_hit_ratio'), 11)}{fmt(x.get('blks_read_per_query'), 10)}"
                      + ("" if not x.get("plan") or all(p["uses_index"] for p in x["plan"].values())
                         else "  NO INDEX: " + x["plan"]["custom"]["nodes"]))
            if run.get("concurrency"):
                if "conc_matched_ef" in run:
                    print(f"   matched-recall ef for concurrency: {run['conc_matched_ef']}")
                print("   proto      ef   C       qps   mean_ms    p99_ms  srv_mean  srv_busy  cli_busy  top wait events"
                      "   (! = client near saturation, row measures the client)")
                for x in run["concurrency"]:
                    we = x.get("pg_wait_events", {}).get("share", {})
                    top = ", ".join(f"{k}={v}" for k, v in list(we.items())[:3])
                    if x["client_cores_busy"] > 0.8 * x.get("client_cores_allotted", 1e9):
                        top = "! " + top
                    print(f"   {x['proto']:9s}{x['ef']:4d}{x['clients']:4d}{fmt(x['throughput_qps'], 10)}{fmt(x.get('mean_ms'))}"
                          f"{fmt(x.get('p99_ms'))}{fmt(x.get('server_mean_ms'))}{fmt(x['server_cores_busy'], 10)}"
                          f"{fmt(x['client_cores_busy'], 10)}  {top}")
                perf = [x for x in run["concurrency"] if x.get("perf")]
                if perf:
                    p = perf[-1]["perf"]
                    print(f"   perf (C={perf[-1]['clients']}):", ", ".join(f"{k}={v}" for k, v in list(p.items())[:8]))
            if "collection_state" in run:
                print("   collection:", run["collection_state"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
