"""Prints the numbers and LaTeX table rows used in the paper, straight from result.json.
Usage: python paper_numbers.py $BENCH_RESULTS
Nothing in the paper's tables should be typed by hand; rerun this after new results.
"""
import glob
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict


def load(path):
    r = json.load(open(path))
    return r if r.get("status") == "ok" else None


def sweep(r, proto):
    """ef -> dict(recall, mean, p99, eng), averaged over reps; rows without the ANN index dropped."""
    g = defaultdict(list)
    for x in r["runs"][0]["latency"]:
        plan = x.get("plan")
        if x["proto"] == proto and (plan is None or all(p["uses_index"] for p in plan.values())):
            g[x["ef"]].append(x)
    return {ef: {"recall": xs[0]["recall_at_k"], "mean": st.mean(x["mean_ms"] for x in xs),
                 "p99": st.mean(x["p99_ms"] for x in xs), "eng": st.mean(x["server_mean_ms"] for x in xs),
                 "cv": st.pstdev(x["mean_ms"] for x in xs) / st.mean(x["mean_ms"] for x in xs)}
            for ef, xs in sorted(g.items())}


def at_recall(sw, target, field):
    """Log-linear interpolation of a latency field at a recall target; None if out of range."""
    efs = sorted(sw)
    for a, b in zip(efs, efs[1:]):
        ra, rb = sw[a]["recall"], sw[b]["recall"]
        if ra <= target <= rb and rb > ra:
            f = (target - ra) / (rb - ra)
            return math.exp(math.log(sw[a][field]) + f * (math.log(sw[b][field]) - math.log(sw[a][field])))
    return None


def plateau(r, protos):
    run = r["runs"][0]
    ef = run.get("conc_matched_ef")
    rows = [c for c in run.get("concurrency", []) if c["ef"] == ef and c["proto"] in protos]
    if not rows:
        return None
    best = max(rows, key=lambda c: c["throughput_qps"])
    last = max(rows, key=lambda c: c["clients"])
    return {"ef": ef, "recall": best["recall_at_k"], "qps": best["throughput_qps"], "at_c": best["clients"],
            "qps_maxc": last["throughput_qps"], "p99_maxc": last["p99_ms"], "mean_maxc": last["mean_ms"],
            "cpu_ms_peak": best["server_cores_busy"] / best["throughput_qps"] * 1000,
            "cpu_ms_maxc": last["server_cores_busy"] / last["throughput_qps"] * 1000}


def fmt(x, d=2):
    return "--" if x is None else f"{x:.{d}f}"


def scale(n):
    return f"{n // 1_000_000}M" if n >= 1_000_000 else f"{n // 1000}K"


def e1(root):
    print("% ---- E1: build (Table build)")
    data = {}
    for d in sorted(glob.glob(os.path.join(root, "e1_scale", "n*"))):
        pg, qd = load(os.path.join(d, "pg", "result.json")), load(os.path.join(d, "qdrant", "result.json"))
        if pg and qd:
            data[pg["n"]] = (pg, qd)
    if not data:
        print("%   no E1 results")
        return
    for n, (pg, qd) in sorted(data.items()):
        b, q = pg["build"], qd["build"]
        print(f"    {scale(n)} & {b['load_s']:.1f} & {b['index_s']:.1f} & {b['total_s']:.1f} & "
              f"{b['index_bytes'] / 2**30:.2f} & {q['upload_s']:.1f} & {q['index_wait_s']:.1f} & {q['total_s']:.1f} \\\\"
              f"   % pg on {pg['host']['hostname']}, qdrant on {qd['host']['hostname']}")

    print("\n% ---- E1: matched recall (Table matched)")
    ratios = defaultdict(list)
    for n, (pg, qd) in sorted(data.items()):
        s = {"pg": sweep(pg, "pg"), "lean": sweep(qd, "grpc_raw"), "grpc": sweep(qd, "grpc"), "rest": sweep(qd, "rest")}
        for t in (0.90, 0.95):
            v = {k: {f: at_recall(sw, t, f) for f in ("mean", "p99", "eng")} for k, sw in s.items()}
            if any(v[k]["mean"] is None for k in v):
                t = max(x["recall"] for x in s["pg"].values()) - 0.005
                t = math.floor(t * 100) / 100
                v = {k: {f: at_recall(sw, t, f) for f in ("mean", "p99", "eng")} for k, sw in s.items()}
            eng = v["pg"]["eng"] / v["lean"]["eng"]
            for k in ("lean", "grpc", "rest"):
                ratios[k].append(v["pg"]["mean"] / v[k]["mean"])
            ratios["eng"].append(eng)
            print(f"    {scale(n)} & {t:.2f} & {fmt(v['pg']['mean'])} & {fmt(v['pg']['p99'])} & {fmt(v['pg']['eng'])} & "
                  f"{fmt(v['lean']['mean'])} & {fmt(v['lean']['p99'])} & {fmt(v['lean']['eng'])} & {fmt(v['grpc']['mean'])} & "
                  f"{fmt(v['rest']['mean'])} & {fmt(v['rest']['eng'])} & {eng:.1f}$\\times$ \\\\")
    for k, xs in ratios.items():
        print(f"%   pg/{k} ratio range: {min(xs):.2f}-{max(xs):.2f}")
    cvs = [x["cv"] for pg, qd in data.values() for sw in (sweep(pg, "pg"), sweep(qd, "grpc_raw")) for x in sw.values()]
    print(f"%   max coefficient of variation of the mean across reps: {max(cvs):.3f}")

    print("\n% ---- E1: throughput plateau at matched recall")
    for n, (pg, qd) in sorted(data.items()):
        a, b = plateau(pg, ("pg",)), plateau(qd, ("grpc_raw",))
        r = plateau(qd, ("rest",))
        print(f"%   {scale(n)}: pg ef{a['ef']} R{a['recall']:.3f} peak {a['qps']:.0f}@C{a['at_c']} -> {a['qps_maxc']:.0f} "
              f"(p99 {a['p99_maxc']:.1f}, p99/mean {a['p99_maxc'] / a['mean_maxc']:.2f}, cpu {a['cpu_ms_peak']:.2f}->{a['cpu_ms_maxc']:.2f} ms) | "
              f"qd ef{b['ef']} R{b['recall']:.3f} peak {b['qps']:.0f}@C{b['at_c']} -> {b['qps_maxc']:.0f} "
              f"(p99 {b['p99_maxc']:.1f}, p99/mean {b['p99_maxc'] / b['mean_maxc']:.2f}, cpu {b['cpu_ms_peak']:.2f} ms) | "
              f"rest peak {r['qps']:.0f} | qd/pg {b['qps'] / a['qps']:.2f}, pg drop {1 - a['qps_maxc'] / a['qps']:.1%}")


def e2(root):
    print("\n% ---- E2: HNSW parameters (Table hnsw)")
    rows = []
    for d in glob.glob(os.path.join(root, "e2_hnsw", "*")):
        pg, qd = load(os.path.join(d, "pg", "result.json")), load(os.path.join(d, "qdrant", "result.json"))
        if not (pg and qd):
            print(f"%   missing or failed: {os.path.basename(d)}")
            continue
        a, b = sweep(pg, "pg"), sweep(qd, "grpc_raw")
        pa, pb = plateau(pg, ("pg",)), plateau(qd, ("grpc_raw",))
        rows.append((pg["args"]["m"], pg["args"]["efc"], pg, qd, at_recall(a, .95, "eng"), at_recall(b, .95, "eng"), pa, pb,
                     max(x["recall"] for x in a.values()), max(x["recall"] for x in b.values())))
    for m, efc, pg, qd, ea, eb, pa, pb, ra, rb in sorted(rows, key=lambda x: (x[0], x[1])):
        print(f"    {m} & {efc} & {pg['build']['index_s']:.0f} & {fmt(ea)} & {pa['qps']:.0f} & {qd['build']['total_s']:.0f} & "
              f"{fmt(eb)} & {pb['qps']:.0f} \\\\   % engine x{fmt(ea / eb if ea and eb else None, 1)}, qps x{pb['qps'] / pa['qps']:.2f}, "
              f"max recall {ra:.3f}/{rb:.3f}, matched R {pa['recall']:.3f}/{pb['recall']:.3f}, index {pg['build']['index_bytes'] / 2**30:.2f} GiB")


def e3(root):
    print("\n% ---- E3: dimensionality")
    for d in sorted(glob.glob(os.path.join(root, "e3_dims", "*")), key=lambda p: int(p.rsplit("_d", 1)[1])):
        pg = load(os.path.join(d, "pg", "result.json"))
        qd, qf = load(os.path.join(d, "qdrant_default", "result.json")), load(os.path.join(d, "qdrant_forced", "result.json"))
        if not (pg and qd and qf):
            continue
        s = qd["build"]["final_state"]
        a, b, c = sweep(pg, "pg"), sweep(qd, "grpc_raw"), sweep(qf, "grpc_raw")
        g90 = at_recall(a, .90, "eng") / at_recall(c, .90, "eng")
        print(f"%   d={pg['dim']:4d} unindexed {1 - s['indexed'] / s['points']:.1%} default/forced eng@64 {b[64]['eng'] / c[64]['eng']:.2f} "
              f"(ef16 {b[16]['eng'] / c[16]['eng']:.2f}) dRecall@64 {b[64]['recall'] - c[64]['recall']:+.3f} | eng@64 pg {a[64]['eng']:.2f} "
              f"forced {c[64]['eng']:.2f} | gap@R.90 {g90:.1f}x | pg build {pg['build']['load_s']:.1f}+{pg['build']['index_s']:.1f}s")


def e5(root):
    print("\n% ---- E5: build repeats on one node (mean +- sd over reps)")
    for probe in glob.glob(os.path.join(root, "e5_builds", "disk_probe_*.json")):
        print(f"%   disk: {json.dumps(json.load(open(probe)))[:300]}")
    for d in sorted(glob.glob(os.path.join(root, "e5_builds", "n*")), key=lambda p: int(p.rsplit("n", 1)[1])):
        row = {}
        for eng, keys in (("pg", ("load_s", "index_s", "total_s")), ("qdrant", ("upload_s", "index_wait_s", "total_s"))):
            rs = [r for r in (load(p) for p in glob.glob(os.path.join(d, f"{eng}_r*", "result.json"))) if r]
            if len(rs) >= 2:
                row[eng] = {k: (st.mean(r["build"][k] for r in rs), st.stdev(r["build"][k] for r in rs)) for k in keys}
                row[eng]["n_reps"] = len(rs)
        if "pg" in row and "qdrant" in row:
            p, q = row["pg"], row["qdrant"]
            cell = lambda m: f"{m[0]:.1f} $\\pm$ {m[1]:.1f}"
            print(f"    {scale(int(os.path.basename(d)[1:]))} & {cell(p['load_s'])} & {cell(p['index_s'])} & {cell(p['total_s'])} & "
                  f"{cell(q['upload_s'])} & {cell(q['index_wait_s'])} & {cell(q['total_s'])} \\\\   "
                  f"% reps {p['n_reps']}/{q['n_reps']}, pg/qdrant total {p['total_s'][0] / q['total_s'][0]:.2f}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    e1(root)
    e2(root)
    e3(root)
    e5(root)
