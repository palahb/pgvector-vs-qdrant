#!/usr/bin/env python3
"""Aggregate E6 independent builds and audit Qdrant segment/thread controls."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}


def interval(values: list[float]) -> dict[str, Any]:
    mean = statistics.mean(values)
    if len(values) < 2:
        half = None
    else:
        critical = T95.get(len(values), 1.96)
        half = critical * statistics.stdev(values) / math.sqrt(len(values))
    return {
        "n": len(values),
        "mean": round(mean, 6),
        "sd": round(statistics.stdev(values), 6) if len(values) > 1 else None,
        "ci95_low": round(mean - half, 6) if half is not None else None,
        "ci95_high": round(mean + half, 6) if half is not None else None,
    }


def run_rows(result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    latency, concurrency = [], []
    for run in result.get("runs", []):
        if run.get("mem_limit") != "none":
            continue
        latency.extend(run.get("latency", []))
        concurrency.extend(run.get("concurrency", []))
    return latency, concurrency


def analyze(root: Path, targets: list[float]) -> dict[str, Any]:
    results = [json.loads(path.read_text()) for path in sorted(root.glob("**/result.json"))]
    issues: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    matched: dict[tuple[Any, ...], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    concurrency_matched: dict[tuple[Any, ...], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    control_cells: dict[tuple[Any, ...], set[str]] = defaultdict(set)

    for result in results:
        args = result["args"]
        engine = result["engine"]
        build = result.get("build", {})
        tag = args.get("tag", "")
        if engine == "qdrant":
            requested = args.get("qdrant_segments", 0)
            actual = build.get("actual_segments")
            if requested and actual != requested:
                observations.append({
                    "experiment_id": result.get("experiment_id"),
                    "observation": "actual_segment_count_differs_from_optimizer_target",
                    "requested": requested, "actual": actual,
                })
            if args.get("qdrant_require_indexed") and not build.get("fully_indexed"):
                issues.append({"experiment_id": result.get("experiment_id"), "problem": "not_fully_indexed"})
            segments = requested or "auto"
            threads = args.get("qdrant_search_threads", 0) or "auto"
        else:
            segments, threads = "one_graph", "n/a"
        cell = (engine, result["n"], segments, threads)
        control_cells[cell].add(tag)

        latency, concurrency = run_rows(result)
        primary = "pg" if engine == "pg" else "grpc_raw"
        latency = [row for row in latency if row.get("proto") == primary]
        for target in targets:
            candidates = sorted(
                (row for row in latency if row.get("recall_at_k", 0) >= target),
                key=lambda row: (row["ef"], row.get("rep", 0)),
            )
            if not candidates:
                issues.append({"experiment_id": result.get("experiment_id"), "problem": "recall_target_not_reached", "target": target})
                continue
            # One row per independent build: use the first measured repetition at the
            # smallest observed ef reaching the target.
            chosen_ef = candidates[0]["ef"]
            chosen = next(row for row in candidates if row["ef"] == chosen_ef)
            key = (*cell, target)
            for metric in ("ef", "recall_at_k", "mean_ms", "p99_ms", "server_cpu_ms_per_query", "client_cpu_ms_per_query"):
                value = chosen.get(metric)
                if isinstance(value, (int, float)):
                    matched[key][metric].append(float(value))

        for run in result.get("runs", []):
            if run.get("mem_limit") != "none" or run.get("conc_matched_ef") is None:
                continue
            matched_ef = run["conc_matched_ef"]
            for row in run.get("concurrency", []):
                if row.get("proto") != primary or row.get("ef") != matched_ef:
                    continue
                key = (*cell, args.get("conc_recall", 0.95), row["clients"])
                for metric in (
                    "ef", "recall_at_k", "throughput_qps", "mean_ms", "p99_ms",
                    "server_cpu_ms_per_query", "client_cpu_ms_per_query",
                    "server_cores_busy", "client_cores_busy",
                ):
                    value = row.get(metric)
                    if isinstance(value, (int, float)):
                        concurrency_matched[key][metric].append(float(value))

    aggregates = []
    for key, metrics in sorted(matched.items(), key=lambda item: tuple(map(str, item[0]))):
        engine, n, segments, threads, target = key
        aggregates.append({
            "engine": engine, "n": n, "segments": segments, "search_threads": threads,
            "recall_target": target,
            "metrics": {name: interval(values) for name, values in sorted(metrics.items())},
        })

    concurrency_aggregates = []
    for key, metrics in sorted(concurrency_matched.items(), key=lambda item: tuple(map(str, item[0]))):
        engine, n, segments, threads, target, clients = key
        concurrency_aggregates.append({
            "engine": engine, "n": n, "segments": segments, "search_threads": threads,
            "recall_target": target, "clients": clients,
            "metrics": {name: interval(values) for name, values in sorted(metrics.items())},
        })

    cells = []
    for key, tags in sorted(control_cells.items(), key=lambda item: tuple(map(str, item[0]))):
        engine, n, segments, threads = key
        cells.append({
            "engine": engine, "n": n, "segments": segments, "search_threads": threads,
            "independent_build_tags": sorted(tags), "build_count": len(tags),
        })
        if len(tags) < 3:
            issues.append({"problem": "fewer_than_three_builds", "cell": list(key), "count": len(tags)})

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "verdict": "valid" if not issues else "incomplete_or_invalid",
        "result_count": len(results),
        "control_cells": cells,
        "matched_recall_aggregates": aggregates,
        "matched_concurrency_aggregates": concurrency_aggregates,
        "observations": observations,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--targets", default="0.90,0.95")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.root, [float(value) for value in args.targets.split(",")])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
