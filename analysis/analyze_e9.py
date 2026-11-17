#!/usr/bin/env python3
"""Aggregate E9: ingestion and build time per arm, with PostgreSQL write activity.

Each job builds every arm once on one node (interleaved, order rotated per repetition), so
arms are compared within a node and the spread across repetitions is the build variance.
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

TAG = re.compile(r"^(rep\d+)_(.+)$")
PG_METRICS = ("load_s", "index_s", "total_s", "vacuum_checkpoint_s")
QDRANT_METRICS = ("upload_s", "index_wait_s", "total_s")


def split_tag(tag: str) -> tuple[str, str] | None:
    match = TAG.match(tag or "")
    return (match.group(1), match.group(2)) if match else None


def activity_total(build: dict[str, Any], key: str, phases=("copy", "index", "vacuum_checkpoint")) -> float | None:
    activity = build.get("write_activity") or {}
    values = [activity[p][key] for p in phases if p in activity and key in activity[p]]
    return float(sum(values)) if values else None


def analyze(root: Path) -> dict[str, Any]:
    results = [json.loads(path.read_text()) for path in sorted(root.glob("**/result.json"))]
    issues: list[dict[str, Any]] = []
    cells: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    builds: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for result in results:
        parsed = split_tag(result["args"].get("tag", ""))
        if parsed is None:
            issues.append({"experiment_id": result.get("experiment_id"), "problem": "tag_without_arm"})
            continue
        rep, arm = parsed
        engine, n, build = result["engine"], result["n"], result.get("build", {})
        builds[(engine, n, arm)].add(rep)
        if engine == "qdrant" and not build.get("fully_indexed"):
            issues.append({"experiment_id": result.get("experiment_id"), "problem": "not_fully_indexed"})
        metrics: dict[str, float | None] = {}
        for key in (PG_METRICS if engine == "pg" else QDRANT_METRICS):
            metrics[key] = build.get(key)
        if engine == "pg":
            metrics["wal_mb_copy"] = (build.get("write_activity", {}).get("copy", {}).get("wal_bytes") or 0) / 1e6
            metrics["wal_mb_index"] = (build.get("write_activity", {}).get("index", {}).get("wal_bytes") or 0) / 1e6
            written = activity_total(build, "io_write_bytes")
            metrics["io_write_mb"] = written / 1e6 if written is not None else None
            metrics["checkpoints_requested"] = activity_total(build, "checkpoints_requested")
            metrics["checkpoints_timed"] = activity_total(build, "checkpoints_timed")
            metrics["checkpoint_write_s"] = (lambda v: v / 1000 if v is not None else None)(
                activity_total(build, "checkpoint_write_ms"))
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                cells[(engine, n, arm, key)].append(float(value))
    aggregates = []
    for key in sorted(cells, key=str):
        engine, n, arm, metric = key
        values = cells[key]
        stats = interval(values)
        mean = statistics.mean(values)
        stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
        aggregates.append({"engine": engine, "n": n, "arm": arm, "metric": metric, "stats": stats})
    arms = [{"engine": e, "n": n, "arm": a, "builds": sorted(r)} for (e, n, a), r in sorted(builds.items(), key=str)]
    for item in arms:
        if len(item["builds"]) < 3:
            issues.append({"cell": item, "problem": "fewer_than_three_builds"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "verdict": "valid" if not issues else "invalid", "result_count": len(results),
            "arms": arms, "aggregates": aggregates, "issues": issues}


def get(report: dict[str, Any], engine: str, n: int, arm: str, metric: str) -> dict[str, Any] | None:
    for item in report["aggregates"]:
        if (item["engine"], item["n"], item["arm"], item["metric"]) == (engine, n, arm, metric):
            return item["stats"]
    return None


def cell(stats: dict[str, Any] | None, digits: int = 1) -> str:
    if not stats:
        return "n/a"
    sd = stats["sd"]
    return f"{stats['mean']:.{digits}f} ± {sd:.{digits}f}" if sd is not None else f"{stats['mean']:.{digits}f}"


def markdown_report(report: dict[str, Any], title: str = "E9 ingestion and build fairness") -> str:
    lines = [f"# {title}", "",
             f"Verdict: **{report['verdict']}**; results: {report['result_count']}; issues: {len(report['issues'])}.", "",
             "Mean ± standard deviation over independent builds on the same node, seconds unless noted.", ""]
    sizes = sorted({a["n"] for a in report["arms"]})
    for n in sizes:
        lines += [f"## N = {n}", "", "### PostgreSQL / pgvector", "",
                  "| Arm | Load | CREATE INDEX | Load + index | Checkpoint | WAL MB (load / index) | Disk write MB | Req. checkpoints |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for arm in sorted({a["arm"] for a in report["arms"] if a["engine"] == "pg" and a["n"] == n}):
            g = lambda m, d=1: cell(get(report, "pg", n, arm, m), d)  # noqa: E731
            lines.append(f"| {arm} | {g('load_s')} | {g('index_s')} | {g('total_s')} | {g('vacuum_checkpoint_s')} | "
                         f"{g('wal_mb_copy', 0)} / {g('wal_mb_index', 0)} | {g('io_write_mb', 0)} | {g('checkpoints_requested', 1)} |")
        lines += ["", "### Qdrant", "", "| Arm | Upload | Index wait | Total |", "|---|---:|---:|---:|"]
        for arm in sorted({a["arm"] for a in report["arms"] if a["engine"] == "qdrant" and a["n"] == n}):
            g = lambda m: cell(get(report, "qdrant", n, arm, m))  # noqa: E731
            lines.append(f"| {arm} | {g('upload_s')} | {g('index_wait_s')} | {g('total_s')} |")
        lines.append("")
    if report["issues"]:
        lines += ["## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]] + [""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = analyze(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
