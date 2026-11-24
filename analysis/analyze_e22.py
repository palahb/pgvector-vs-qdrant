#!/usr/bin/env python3
"""Aggregate E22: open-loop (Poisson arrivals) load levels as fractions of each build's closed-loop capacity.

Design and the rules used here are in docs/E22_DESIGN.md. A level is steady if the achieved rate is at least 98% of the offered rate
and the largest send lag is under 1 s; otherwise it is overload, where latency depends on the length of the window, so its tail is
recorded but not used for claims (the aggregate carries `steady: false`).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.analyze_e6 import interval

STEADY_ACHIEVED = 0.98
STEADY_LAG_MS = 1000.0
# The first seconds of a window are left out of the tail statistics. A fresh PostgreSQL backend is slow for its first queries;
# the harness warms each connection up, and this is the second line of defence. Qdrant showed no such effect in the pilot.
TRIM_S = 5.0
RECALL_TOLERANCE = 0.01
METRICS = ("offered_qps", "achieved_qps", "achieved_in_window_qps", "mean_ms", "p99_ms", "p999_ms", "p99_ms_all", "p999_ms_all", "max_send_lag_ms", "mean_send_lag_ms",
           "service_mean_ms", "recall_at_k", "server_cpu_ms_per_query", "server_cores_busy")
CAPACITY_CLIENTS = 32


def is_steady(row: dict[str, Any]) -> bool:
    achieved = row.get("achieved_in_window_qps", row["achieved_qps"])
    return achieved >= STEADY_ACHIEVED * row["offered_qps"] and row["max_send_lag_ms"] < STEADY_LAG_MS


def achieved_in_window(planned_ns, latency_ns, window_s: float) -> float:
    """Queries that finished inside the window per second. Every query eventually completes, so the harness's own
    `achieved_qps` (all completions over the window length) equals the offered rate even when the server is behind;
    this counts only those finished by the end of the window."""
    import numpy as np
    finished = np.asarray(planned_ns, dtype=float) + np.asarray(latency_ns, dtype=float)
    return float((finished <= window_s * 1e9).sum()) / window_s


def trimmed_latency(planned_ns, latency_ns, trim_s: float, window_s: float) -> dict[str, float]:
    """Mean and tail of the latency (from the planned send time) of queries planned between trim_s and window_s."""
    import numpy as np
    planned = np.asarray(planned_ns, dtype=float)
    lat = np.asarray(latency_ns, dtype=float)[(planned >= trim_s * 1e9) & (planned < window_s * 1e9)] / 1e6
    if len(lat) == 0:
        return {"count": 0}
    p = np.percentile(lat, [50, 99, 99.9])
    return {"count": int(len(lat)), "mean_ms": float(lat.mean()), "p50_ms": float(p[0]), "p99_ms": float(p[1]),
            "p999_ms": float(p[2])}


def level_arrays(raw_path: Path, row: dict[str, Any]):
    import numpy as np
    if not raw_path.exists():
        return None
    suffix = f"{row['proto']}_ef{row['ef']}_r{row['offered_qps']}"
    with np.load(raw_path) as raw:
        lat, planned = raw.get(f"none_open_{suffix}_lat"), raw.get(f"none_open_{suffix}_planned")
        return None if lat is None or planned is None else (planned.copy(), lat.copy())


def load_in_window(raw_path: Path, row: dict[str, Any], window_s: float) -> float | None:
    arrays = level_arrays(raw_path, row)
    return None if arrays is None else achieved_in_window(arrays[0], arrays[1], window_s)


def analyze(root: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    # (engine, fraction, metric) -> rep -> value
    table: dict[tuple[Any, ...], dict[str, float]] = defaultdict(dict)
    steady: dict[tuple[Any, ...], dict[str, bool]] = defaultdict(dict)
    closed: dict[str, dict[str, float]] = defaultdict(dict)
    open95: dict[str, dict[str, float]] = defaultdict(dict)
    reps: dict[str, set[str]] = defaultdict(set)
    count = 0
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        count += 1
        if result.get("status") != "ok":
            issues.append({"experiment_id": result.get("experiment_id"), "problem": "result_not_ok"})
            continue
        engine, rep = result["engine"], result["args"].get("tag", path.parent.name)
        reps[engine].add(rep)
        for run in (r for r in result.get("runs", []) if r.get("mem_limit") == "none"):
            ef = run.get("conc_matched_ef")
            ref = next((c for c in run.get("concurrency", []) if c.get("ef") == ef and c.get("clients") == CAPACITY_CLIENTS), None)
            if ref:
                closed[engine][rep] = ref["p99_ms"]
            else:
                issues.append({"experiment_id": result.get("experiment_id"), "problem": "no_closed_loop_reference"})
            for row in run.get("open_loop", []):
                fraction = row.get("load_fraction")
                if fraction is None:
                    continue
                window_s = float(result["args"].get("open_loop_duration", 30))
                arrays = level_arrays(path.with_name("raw.npz"), row)
                if arrays is not None:
                    trimmed = trimmed_latency(arrays[0], arrays[1], TRIM_S, window_s)
                    row = {**row, "achieved_in_window_qps": achieved_in_window(arrays[0], arrays[1], window_s),
                           "mean_ms_all": row["mean_ms"], "p99_ms_all": row["p99_ms"], "p999_ms_all": row["p999_ms"],
                           "mean_ms": trimmed["mean_ms"], "p99_ms": trimmed["p99_ms"], "p999_ms": trimmed["p999_ms"]}
                if ref and abs(row["recall_at_k"] - ref["recall_at_k"]) > RECALL_TOLERANCE:
                    issues.append({"experiment_id": result.get("experiment_id"), "problem": "recall_disagrees_with_closed_loop",
                                   "load_fraction": fraction, "open": row["recall_at_k"], "closed": ref["recall_at_k"]})
                for metric in METRICS:
                    if isinstance(row.get(metric), (int, float)):
                        table[(engine, fraction, metric)][rep] = float(row[metric])
                steady[(engine, fraction)][rep] = is_steady(row)
                if abs(fraction - 0.95) < 1e-9 and is_steady(row):
                    open95[engine][rep] = row["p99_ms"]

    aggregates = []
    for (engine, fraction, metric), by_rep in sorted(table.items()):
        values = list(by_rep.values())
        stats = interval(values)
        mean = statistics.mean(values)
        stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
        flags = steady[(engine, fraction)]
        aggregates.append({"engine": engine, "load_fraction": fraction, "metric": metric, "stats": stats,
                           "steady": bool(flags) and all(flags.values())})
    status = [{"engine": e, "load_fraction": f, "builds": len(flags), "steady_builds": sum(flags.values())}
              for (e, f), flags in sorted(steady.items())]

    comparison = []
    for engine in sorted(closed):
        shared = sorted(set(closed[engine]) & set(open95[engine]))
        entry = {"engine": engine, "closed_p99_ms": statistics.mean(closed[engine].values()),
                 "open_p99_ms_at_95": statistics.mean(open95[engine][r] for r in shared) if shared else None,
                 "builds_with_steady_95": len(shared)}
        entry["ratio_open_to_closed"] = (statistics.mean(open95[engine][r] / closed[engine][r] for r in shared)
                                         if shared else None)
        comparison.append(entry)
    for engine, found in reps.items():
        if len(found) < 3:
            issues.append({"cell": {"engine": engine, "builds": sorted(found)}, "problem": "fewer_than_three_builds"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "steady_rule": {"achieved_at_least": STEADY_ACHIEVED, "max_send_lag_ms_below": STEADY_LAG_MS},
            "verdict": "valid" if not issues else "invalid", "result_count": count,
            "builds": {e: sorted(r) for e, r in reps.items()}, "aggregates": aggregates, "status": status,
            "closed_loop_comparison": comparison, "issues": issues}


def get(report: dict[str, Any], engine: str, fraction: float, metric: str) -> dict[str, Any] | None:
    for a in report["aggregates"]:
        if (a["engine"], a["load_fraction"], a["metric"]) == (engine, fraction, metric):
            return a["stats"]
    return None


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# E22 open-loop load", "", f"Verdict: **{report['verdict']}**; builds: {report['builds']}.", "",
             "Mean ± sd over builds; mean and tail leave out the first 5 s of each window. A level is steady if the queries finished inside the window are >= 98% of offered and the largest send lag is < 1 s; "
             "overload levels are shown for completeness and carry no tail claim.", "",
             "| Engine | Load | Offered qps | Finished in window qps | steady builds | mean ms | p99 ms | p99.9 ms | max send lag ms | CPU ms/q |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]

    def cell(e, f, m, d):
        s = get(report, e, f, m)
        return "n/a" if not s else (f"{s['mean']:.{d}f} ± {s['sd']:.{d}f}" if s["sd"] is not None else f"{s['mean']:.{d}f}")
    for st in report["status"]:
        e, f = st["engine"], st["load_fraction"]
        lines.append(f"| {e} | {f:.2f} | {cell(e, f, 'offered_qps', 0)} | {cell(e, f, 'achieved_in_window_qps', 0)} | "
                     f"{st['steady_builds']}/{st['builds']} | {cell(e, f, 'mean_ms', 1)} | {cell(e, f, 'p99_ms', 1)} | "
                     f"{cell(e, f, 'p999_ms', 1)} | {cell(e, f, 'max_send_lag_ms', 0)} | {cell(e, f, 'server_cpu_ms_per_query', 2)} |")
    lines += ["", "## Closed loop (32 clients) against open loop at 95% of capacity, same builds", "",
              "| Engine | closed p99 ms | open p99 ms at 95% | ratio | builds steady at 95% |", "|---|---:|---:|---:|---:|"]
    for c in report["closed_loop_comparison"]:
        op = "n/a" if c["open_p99_ms_at_95"] is None else f"{c['open_p99_ms_at_95']:.1f}"
        ra = "n/a" if c["ratio_open_to_closed"] is None else f"{c['ratio_open_to_closed']:.2f}"
        lines.append(f"| {c['engine']} | {c['closed_p99_ms']:.1f} | {op} | {ra} | {c['builds_with_steady_95']} |")
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--allow-fewer-builds", action="store_true")
    args = parser.parse_args()
    report = analyze(args.root)
    if args.allow_fewer_builds:
        report["issues"] = [i for i in report["issues"] if i["problem"] != "fewer_than_three_builds"]
        report["verdict"] = "valid" if not report["issues"] else "invalid"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
