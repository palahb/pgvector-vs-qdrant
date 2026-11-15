#!/usr/bin/env python3
"""Summarize external perf attribution and reconcile it with benchmark timing spans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _event(row: dict[str, Any], wanted: str) -> float | None:
    derived = row.get("perf_derived") or {}
    for name, value in derived.get("events_per_query", {}).items():
        if name.split(":", 1)[0] == wanted and isinstance(value, (int, float)):
            return float(value)
    return None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def summarize(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        engine = result.get("engine")
        for run in result.get("runs", []):
            if run.get("mem_limit") != "none":
                continue
            for row in run.get("concurrency", []):
                if row.get("perf_derived") is None:
                    continue
                cycles = _event(row, "cycles")
                instructions = _event(row, "instructions")
                task_clock = _event(row, "task-clock")
                refs = _event(row, "cache-references")
                misses = _event(row, "cache-misses")
                branches = _event(row, "branches")
                branch_misses = _event(row, "branch-misses")
                proc_cpu = row.get("server_cpu_ms_per_query")
                rows.append({
                    "engine": engine,
                    "result": str(path),
                    "ef": row.get("ef"),
                    "clients": row.get("clients"),
                    "query_count": (row.get("perf_derived") or {}).get("query_count"),
                    "server_mean_ms": row.get("server_mean_ms"),
                    "proc_server_cpu_ms_per_query": proc_cpu,
                    # perf's task-clock CSV unit is milliseconds; division by query count
                    # therefore produces an independently attributed CPU-ms/query value.
                    "perf_task_clock_ms_per_query": _round(task_clock),
                    "task_clock_to_proc_cpu_ratio": _round(task_clock / proc_cpu)
                    if task_clock is not None and isinstance(proc_cpu, (int, float)) and proc_cpu else None,
                    "cycles_per_query": _round(cycles),
                    "instructions_per_query": _round(instructions),
                    "instructions_per_cycle": _round(instructions / cycles)
                    if instructions is not None and cycles else None,
                    "cache_references_per_query": _round(refs),
                    "cache_misses_per_query": _round(misses),
                    "cache_miss_ratio": _round(misses / refs) if misses is not None and refs else None,
                    "branches_per_query": _round(branches),
                    "branch_misses_per_query": _round(branch_misses),
                    "branch_miss_ratio": _round(branch_misses / branches)
                    if branch_misses is not None and branches else None,
                })
                missing = [name for name, value in (("cycles", cycles), ("instructions", instructions)) if value is None]
                if missing:
                    issues.append({"engine": engine, "problem": "missing_required_events", "events": missing})
    found = {row["engine"] for row in rows}
    if found != {"pg", "qdrant"}:
        issues.append({"problem": "both_engines_required", "found": sorted(found)})
    return {
        "schema_version": 1,
        "verdict": "valid" if not issues else "invalid_or_incomplete",
        "rows": rows,
        "issues": issues,
        "measurement_boundaries": {
            "server_mean_ms": "engine self-reported request/execution span; definitions differ by engine",
            "proc_server_cpu_ms_per_query": "delta of server-process CPU time from /proc over the wall-clock window",
            "perf_task_clock_ms_per_query": "external perf process attribution over the same window",
            "hardware_events": "user-space process-level perf events divided by completed queries",
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# E7 perf counter probe",
        "",
        f"Verdict: **{report['verdict']}**; rows: {len(report['rows'])}; issues: {len(report['issues'])}.",
        "",
        "| Engine | C | ef | Engine span ms/q | /proc CPU ms/q | perf task-clock ms/q | cycles/q | instructions/q | IPC | cache miss % | branch miss % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        def value(key: str, scale: float = 1.0) -> str:
            item = row.get(key)
            return "—" if item is None else f"{item * scale:.3f}"
        lines.append(
            f"| {row['engine']} | {row['clients']} | {row['ef']} | {value('server_mean_ms')} | "
            f"{value('proc_server_cpu_ms_per_query')} | {value('perf_task_clock_ms_per_query')} | "
            f"{value('cycles_per_query')} | {value('instructions_per_query')} | "
            f"{value('instructions_per_cycle')} | {value('cache_miss_ratio', 100)} | "
            f"{value('branch_miss_ratio', 100)} |"
        )
    lines += [
        "",
        "The engine-reported spans are not treated as semantically interchangeable. The `/proc` and perf values are external process-level attribution over the same concurrency window.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = summarize(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown(report))
    print(f"verdict={report['verdict']} rows={len(report['rows'])} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
