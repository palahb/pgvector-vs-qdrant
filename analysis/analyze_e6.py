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


# pgvector rejects hnsw.ef_search above 1000 with a warning and keeps the default of 40, so any
# pgvector row labelled with a larger ef was not measured at that ef and must not be used.
PG_EF_MAX = 1000

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


def segment_summary(result: dict[str, Any]) -> dict[str, int]:
    existing = result.get("server_info", {}).get("segment_summary")
    if existing:
        return existing
    telemetry = result.get("server_info", {}).get("collection_segment_telemetry") or {}
    segments = []
    for collection in telemetry.get("collections", []):
        for shard in collection.get("shards", []):
            segments.extend((shard.get("local") or {}).get("segments", []))
    infos = [segment.get("info", {}) for segment in segments]
    return {
        "public_segment_count": len(infos),
        "nonempty_segment_count": sum(info.get("num_vectors", 0) > 0 for info in infos),
        "indexed_nonempty_segment_count": sum(
            info.get("num_vectors", 0) > 0 and info.get("segment_type") == "indexed" for info in infos
        ),
        "empty_appendable_segment_count": sum(
            info.get("num_vectors", 0) == 0 and info.get("is_appendable") is True for info in infos
        ),
    }


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
            segment_counts = segment_summary(result)
            if requested and actual != requested:
                observations.append({
                    "experiment_id": result.get("experiment_id"),
                    "observation": "actual_segment_count_differs_from_optimizer_target",
                    "requested": requested, "actual": actual, **segment_counts,
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
        if engine == "pg":
            invalid = [row for row in latency if row["ef"] > PG_EF_MAX]
            if invalid:
                observations.append({"experiment_id": result.get("experiment_id"),
                                     "observation": "pg_rows_above_ef_search_limit_excluded",
                                     "ef": sorted({row["ef"] for row in invalid}), "rows": len(invalid)})
            latency = [row for row in latency if row["ef"] <= PG_EF_MAX]
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


def metric_text(metric: dict[str, Any] | None) -> str:
    if not metric:
        return "—"
    if metric.get("ci95_low") is None:
        return f"{metric['mean']:.3f}"
    return f"{metric['mean']:.3f} [{metric['ci95_low']:.3f}, {metric['ci95_high']:.3f}]"


PILOT_NOTE = "This is pilot evidence only. The 500K/1M gate remains closed until the full deployment is separately validated."


def markdown_report(
    report: dict[str, Any],
    target: float = 0.95,
    title: str = "E6 100K pilot summary",
    note: str = PILOT_NOTE,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"Verdict: **{report['verdict']}**; results: {report['result_count']}; "
        f"issues: {len(report['issues'])}.",
        "",
        "Values are means with 95% t-intervals across three independent clean builds.",
        "Segment values are Qdrant optimizer targets; public and non-empty actual counts are audited separately.",
        "",
        "## Matched-recall single-client latency and efficiency",
        "",
        "| N | Engine | Segment target | Search threads | ef | Recall | Mean latency ms | Server CPU ms/query |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["matched_recall_aggregates"]:
        if item["recall_target"] != target:
            continue
        metrics = item["metrics"]
        lines.append(
            f"| {item['n']} | {item['engine']} | {item['segments']} | {item['search_threads']} | "
            f"{metric_text(metrics.get('ef'))} | {metric_text(metrics.get('recall_at_k'))} | "
            f"{metric_text(metrics.get('mean_ms'))} | {metric_text(metrics.get('server_cpu_ms_per_query'))} |"
        )
    lines += [
        "",
        "## Matched-recall concurrency endpoints",
        "",
        "| N | Engine | Segment target | Search threads | Clients | QPS | Mean latency ms | Server CPU ms/query |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["matched_concurrency_aggregates"]:
        if item["recall_target"] != target or item["clients"] not in {1, 32}:
            continue
        metrics = item["metrics"]
        lines.append(
            f"| {item['n']} | {item['engine']} | {item['segments']} | {item['search_threads']} | {item['clients']} | "
            f"{metric_text(metrics.get('throughput_qps'))} | {metric_text(metrics.get('mean_ms'))} | "
            f"{metric_text(metrics.get('server_cpu_ms_per_query'))} |"
        )
    differing = [item for item in report["observations"] if item.get("observation") == "actual_segment_count_differs_from_optimizer_target"]
    if differing:
        exemplar = differing[0]
        lines += [
            "",
            "## Segment telemetry observation",
            "",
            f"All {len(differing)} builds with optimizer target 1 reported "
            f"{exemplar.get('public_segment_count')} public segments: "
            f"{exemplar.get('indexed_nonempty_segment_count')} non-empty indexed segment and "
            f"{exemplar.get('empty_appendable_segment_count')} empty appendable segment. "
            "The experiment therefore reports both target and actual composition and does not relabel the public count.",
        ]
    lines += [
        "",
        note,
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--targets", default="0.90,0.95")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--title", default="E6 100K pilot summary")
    parser.add_argument("--note", default=PILOT_NOTE)
    args = parser.parse_args()
    report = analyze(args.root, [float(value) for value in args.targets.split(",")])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report, title=args.title, note=args.note))
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
