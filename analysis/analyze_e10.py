#!/usr/bin/env python3
"""Aggregate E10: cold start and steady state under memory limits, per system and limit.

Only results with status "ok" and a complete set of passes enter the aggregates. Results that
were cut off (status "running" after a time limit) or failed are listed as excluded, never
silently dropped and never averaged in.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.analyze_e6 import interval

TAG = re.compile(r"^(rep\d+)_(.+)_(none|\d+G)$")
LIMIT_ORDER = {"none": 0, "16G": 1, "8G": 2, "4G": 3, "2G": 4}
EXPECTED_SYSTEMS = ("qdrant_mmap", "pg_sb1G", "pg_sbq")
EXPECTED_LIMITS = ("none", "16G", "8G", "4G")
PASS_METRICS = ("mean_ms", "p99_ms", "throughput_qps", "recall_at_k", "major_faults", "read_bytes", "wall_s")


def parse_tag(tag: str) -> tuple[str, str, str] | None:
    match = TAG.match(tag or "")
    return (match.group(1), match.group(2), match.group(3)) if match else None


def analyze(root: Path, expected_passes: int = 3, expected_cells=None) -> dict[str, Any]:
    if expected_cells is None:
        expected_cells = [(s, l) for l in EXPECTED_LIMITS for s in EXPECTED_SYSTEMS]
    results = [json.loads(path.read_text()) for path in sorted(root.glob("**/result.json"))]
    cells: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    included: dict[tuple[str, str], set[str]] = defaultdict(set)
    excluded: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for result in results:
        parsed = parse_tag(result["args"].get("tag", ""))
        experiment = result.get("experiment_id")
        if parsed is None:
            issues.append({"experiment_id": experiment, "problem": "unparseable_tag"})
            continue
        rep, system, limit = parsed
        run = next((r for r in result.get("runs", []) if r.get("mem_limit") == limit), None)
        passes = (run or {}).get("memory_passes", [])
        if result.get("status") != "ok" or run is None or len(passes) < expected_passes:
            excluded.append({"experiment_id": experiment, "system": system, "limit": limit, "rep": rep,
                             "status": result.get("status"), "passes_recorded": len(passes)})
            continue
        if result["engine"] == "qdrant" and not result.get("build", {}).get("fully_indexed"):
            issues.append({"experiment_id": experiment, "problem": "not_fully_indexed"})
        included[(system, limit)].add(rep)
        cold, steady = passes[0], passes[1:]
        for metric in PASS_METRICS:
            if isinstance(cold.get(metric), (int, float)):
                cells[(system, limit, "cold", metric)].append(float(cold[metric]))
            values = [p[metric] for p in steady if isinstance(p.get(metric), (int, float))]
            if values:
                cells[(system, limit, "steady_last", metric)].append(float(values[-1]))
                cells[(system, limit, "steady_first", metric)].append(float(values[0]))
        for row in (run or {}).get("concurrency", []):
            cells[(system, limit, "concurrency", f"qps_c{row['clients']}")].append(float(row["throughput_qps"]))
        if run.get("server_cgroup_memory_bytes") is not None:
            cells[(system, limit, "memory", "cgroup_gb")].append(run["server_cgroup_memory_bytes"] / 1e9)
    aggregates = []
    for key in sorted(cells, key=lambda k: (k[0], LIMIT_ORDER.get(k[1], 9), k[2], k[3])):
        system, limit, phase, metric = key
        values = cells[key]
        stats = interval(values)
        mean = statistics.mean(values)
        stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
        aggregates.append({"system": system, "limit": limit, "phase": phase, "metric": metric, "stats": stats})
    cell_list = [{"system": s, "limit": l, "reps": sorted(r)} for (s, l), r in sorted(
        included.items(), key=lambda kv: (kv[0][0], LIMIT_ORDER.get(kv[0][1], 9)))]
    for cell in cell_list:
        if len(cell["reps"]) < 3:
            issues.append({"cell": cell, "problem": "fewer_than_three_repetitions"})
    missing = [{"system": s, "limit": l} for s, l in expected_cells if (s, l) not in included]
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "verdict": "valid" if not issues else "incomplete", "result_count": len(results),
            "included_cells": cell_list, "excluded": excluded, "missing_cells": missing,
            "aggregates": aggregates, "issues": issues}


def get(report: dict[str, Any], system: str, limit: str, phase: str, metric: str) -> dict[str, Any] | None:
    for item in report["aggregates"]:
        if (item["system"], item["limit"], item["phase"], item["metric"]) == (system, limit, phase, metric):
            return item["stats"]
    return None


def cell(stats: dict[str, Any] | None, digits: int = 2) -> str:
    if not stats:
        return "n/a"
    sd = stats["sd"]
    text = f"{stats['mean']:.{digits}f}"
    return f"{text} ± {sd:.{digits}f} (n={stats['n']})" if sd is not None else f"{text} (n={stats['n']})"


def markdown_report(report: dict[str, Any], title: str = "E10 memory limits") -> str:
    lines = [f"# {title}", "",
             f"Verdict: **{report['verdict']}**; results read: {report['result_count']}; "
             f"cells with data: {len(report['included_cells'])}; excluded: {len(report['excluded'])}.", "",
             "Mean ± standard deviation over repetitions of whole-query-set passes (1,677 queries, one client, ef=128, "
             "random order per pass). Cold is the first pass after a restart with an evicted page cache; steady is the "
             "last of the later passes.", "",
             "| System | Limit | Cold mean ms | Cold wall s | Cold major faults | Steady mean ms | Steady p99 ms | Steady qps | Reps |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for item in report["included_cells"]:
        s, l = item["system"], item["limit"]
        g = lambda ph, m, d=2: cell(get(report, s, l, ph, m), d)  # noqa: E731
        lines.append(f"| {s} | {l} | {g('cold', 'mean_ms', 1)} | {g('cold', 'wall_s', 0)} | {g('cold', 'major_faults', 0)} | "
                     f"{g('steady_last', 'mean_ms')} | {g('steady_last', 'p99_ms')} | {g('steady_last', 'throughput_qps', 1)} | "
                     f"{','.join(r[3:] for r in item['reps'])} |")
    if report.get("missing_cells"):
        lines += ["", "## Cells with no completed repetition", "",
                  "These cells of the planned matrix have no usable result (time limit, failure or not run). "
                  "They are absent from the table above, not zero.", ""]
        lines += [f"- {m['system']} at {m['limit']}" for m in report["missing_cells"]]
    if report["excluded"]:
        lines += ["", "## Excluded results", "",
                  "These did not record a full set of passes (time limit or failure) and are not averaged in.", ""]
        lines += [f"- {e['system']} {e['limit']} {e['rep']}: status {e['status']}, "
                  f"{e['passes_recorded']} passes recorded ({e['experiment_id']})" for e in report["excluded"]]
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--passes", type=int, default=3)
    args = parser.parse_args()
    report = analyze(args.root, args.passes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} results={report['result_count']} cells={len(report['included_cells'])} "
          f"excluded={len(report['excluded'])} issues={len(report['issues'])}")
    return 0 if report["verdict"] in {"valid", "incomplete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
