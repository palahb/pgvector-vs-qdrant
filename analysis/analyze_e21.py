#!/usr/bin/env python3
"""Aggregate E21: pgvector through PgBouncer against a direct connection, on one build per job.

Each job builds pgvector once and runs the same closed-loop windows in three connection modes
(docs/E21_DESIGN.md): `direct` (session SET, the paper's baseline), `direct_txn` (a transaction per query with SET LOCAL)
and `pooled` (the same through PgBouncer in transaction mode, pool size equal to the server cores). Comparisons are paired
per build: direct_txn / direct isolates the per-query transaction, pooled / direct_txn isolates the pooler.

A pooled window is only usable if its recall agrees with the direct window at the same ef: a pooler that dropped the ef setting
would run at pgvector's default ef of 40 and show a recall that is far lower.
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

BASELINES = (("direct", "direct_txn"), ("direct_txn", "pooled"), ("direct", "pooled"))
METRICS = ("throughput_qps", "mean_ms", "p99_ms", "server_cpu_ms_per_query", "recall_at_k")
POOLER_METRICS = ("pooler_cores_busy", "pooler_cpu_ms_per_query")
# Two windows of one mode pair see different subsets of the 1,677 queries; with a per-query recall spread of about 0.15 the
# means of a few thousand queries differ by up to about 0.004. A wrong ef moves recall by more than 0.05.
RECALL_TOLERANCE = 0.01


def mode_of(row: dict[str, Any]) -> str:
    return row.get("conn_mode", "direct")


def recall_disagreements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base: dict[tuple[int, int], float] = {}
    for r in rows:
        if mode_of(r) == "direct":
            base[(r["ef"], r["clients"])] = r["recall_at_k"]
    out = []
    for r in rows:
        key = (r["ef"], r["clients"])
        if mode_of(r) != "direct" and key in base and abs(r["recall_at_k"] - base[key]) > RECALL_TOLERANCE:
            out.append({"mode": mode_of(r), "ef": r["ef"], "clients": r["clients"], "recall": r["recall_at_k"],
                        "direct_recall": base[key]})
    return out


def extra_measurements(row: dict[str, Any]) -> dict[str, float]:
    """Context switches per query and, from the wait-event sampler, the mean number of active backends per sample and the
    share of active-backend observations waiting on the lock manager."""
    out: dict[str, float] = {}
    cs = row.get("server_ctx_switches_per_query") or {}
    for key, name in (("voluntary", "ctx_voluntary_per_query"), ("involuntary", "ctx_involuntary_per_query")):
        if isinstance(cs.get(key), (int, float)):
            out[name] = float(cs[key])
    wait = row.get("pg_wait_events") or {}
    if wait.get("samples") and isinstance(wait.get("active_backend_observations"), (int, float)):
        out["active_backends"] = wait["active_backend_observations"] / wait["samples"]
        out["lockmanager_share"] = float((wait.get("share") or {}).get("LWLock:LockManager", 0.0))
    return out


def analyze(root: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    # (mode, ef_role, ef, clients, metric) -> rep -> value
    table: dict[tuple[Any, ...], dict[str, float]] = defaultdict(dict)
    reps: set[str] = set()
    pooler: dict[str, Any] | None = None
    count = 0
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        count += 1
        if result.get("status") != "ok":
            issues.append({"experiment_id": result.get("experiment_id"), "problem": "result_not_ok"})
            continue
        rep = result["args"].get("tag", path.parent.name)
        reps.add(rep)
        for run in (r for r in result.get("runs", []) if r.get("mem_limit") == "none"):
            rows = [r for r in run.get("concurrency", []) if r.get("proto") == "pg"]
            matched = run.get("conc_matched_ef")
            pooler = run.get("pooler") or pooler
            for bad in recall_disagreements(rows):
                issues.append({"experiment_id": result.get("experiment_id"), "problem": "recall_disagrees_between_modes", **bad})
            for r in rows:
                role = "matched" if r["ef"] == matched else "fixed"
                for metric in METRICS + POOLER_METRICS:
                    if isinstance(r.get(metric), (int, float)):
                        table[(mode_of(r), role, r["ef"], r["clients"], metric)][rep] = float(r[metric])
                for metric, value in extra_measurements(r).items():
                    table[(mode_of(r), role, r["ef"], r["clients"], metric)][rep] = value

    aggregates = []
    for (mode, role, ef, clients, metric), by_rep in sorted(table.items()):
        values = list(by_rep.values())
        stats = interval(values)
        mean = statistics.mean(values)
        stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
        aggregates.append({"mode": mode, "ef_role": role, "ef": ef, "clients": clients, "metric": metric, "stats": stats})

    comparisons = []
    for base, mode in BASELINES:
        for (m, role, ef, clients, metric), by_rep in sorted(table.items()):
            if m != mode or metric in POOLER_METRICS or metric == "recall_at_k" or metric not in METRICS:
                continue
            ref = table.get((base, role, ef, clients, metric))
            if not ref:
                continue
            ratios = [by_rep[rep] / ref[rep] for rep in sorted(by_rep) if rep in ref and ref[rep]]
            if ratios:
                comparisons.append({"baseline": base, "mode": mode, "ef_role": role, "ef": ef, "clients": clients,
                                    "metric": metric, "stats": interval(ratios), "range": [min(ratios), max(ratios)]})
    if len(reps) < 3:
        issues.append({"cell": sorted(reps), "problem": "fewer_than_three_builds"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "recall_tolerance": RECALL_TOLERANCE, "verdict": "valid" if not issues else "invalid", "result_count": count,
            "builds": sorted(reps), "pooler": pooler, "aggregates": aggregates, "comparisons": comparisons, "issues": issues}


def get(report: dict[str, Any], mode: str, role: str, clients: int, metric: str) -> dict[str, Any] | None:
    for a in report["aggregates"]:
        if (a["mode"], a["ef_role"], a["clients"], a["metric"]) == (mode, role, clients, metric):
            return a["stats"]
    return None


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# E21 PgBouncer", "",
             f"Verdict: **{report['verdict']}**; builds: {report['builds']}; pooler: {report['pooler']}.", "",
             "Mean ± sd over builds, at the matched-recall ef.", "",
             "| Clients | Mode | qps | mean ms | p99 ms | server CPU ms/q | recall | pooler cores | pooler ms/q |",
             "|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    clients = sorted({a["clients"] for a in report["aggregates"]})

    def cell(mode, c, metric, digits):
        s = get(report, mode, "matched", c, metric)
        return "n/a" if not s else (f"{s['mean']:.{digits}f} ± {s['sd']:.{digits}f}" if s["sd"] is not None else f"{s['mean']:.{digits}f}")
    for c in clients:
        for mode in ("direct", "direct_txn", "pooled"):
            lines.append(f"| {c} | {mode} | {cell(mode, c, 'throughput_qps', 0)} | {cell(mode, c, 'mean_ms', 2)} | "
                         f"{cell(mode, c, 'p99_ms', 2)} | {cell(mode, c, 'server_cpu_ms_per_query', 2)} | "
                         f"{cell(mode, c, 'recall_at_k', 3)} | {cell(mode, c, 'pooler_cores_busy', 2)} | "
                         f"{cell(mode, c, 'pooler_cpu_ms_per_query', 3)} |")
    lines += ["", "## Paired ratios per build (matched ef)", "",
              "| Clients | Comparison | Metric | Ratio | 95% CI | range |", "|---:|---|---|---:|---|---|"]
    for c in report["comparisons"]:
        if c["ef_role"] != "matched" or c["metric"] not in ("throughput_qps", "p99_ms", "mean_ms", "server_cpu_ms_per_query"):
            continue
        s = c["stats"]
        ci = f"{s['ci95_low']:.3f} to {s['ci95_high']:.3f}" if s["ci95_low"] is not None else "n/a"
        lines.append(f"| {c['clients']} | {c['mode']} / {c['baseline']} | {c['metric']} | {s['mean']:.3f} | {ci} | "
                     f"{c['range'][0]:.3f} to {c['range'][1]:.3f} |")
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--allow-fewer-builds", action="store_true", help="smoke and pilot runs have one build")
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
