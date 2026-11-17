#!/usr/bin/env python3
"""Aggregate E8: build-to-build variance of HNSW graphs at interpolated matched recall.

Each (engine, N, M, ef_construction) cell has independent builds. For every build the
latency and CPU curves are interpolated to the recall target instead of taking the first
swept ef above it, so engines are compared at the same recall (referee M7).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.analyze_e6 import interval

METRICS = ("mean_ms", "p99_ms", "server_cpu_ms_per_query")
PRIMARY = {"pg": "pg", "qdrant": "grpc_raw"}
FIXED_EF = 128


def per_ef_curve(latency: list[dict[str, Any]], proto: str) -> list[dict[str, float]]:
    """Mean over repetitions at each swept ef, sorted by ef."""
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in latency:
        if row.get("proto") == proto and "recall_at_k" in row:
            grouped[row["ef"]].append(row)
    curve = []
    for ef in sorted(grouped):
        rows = grouped[ef]
        point = {"ef": float(ef), "recall_at_k": statistics.mean(r["recall_at_k"] for r in rows)}
        for metric in METRICS:
            values = [r[metric] for r in rows if isinstance(r.get(metric), (int, float))]
            if values:
                point[metric] = statistics.mean(values)
        curve.append(point)
    return curve


def interpolate(curve: list[dict[str, float]], target: float) -> dict[str, Any] | None:
    """Linear interpolation of each metric in recall; ef is interpolated in log space.

    Returns None when the target is never reached. When the first swept point already
    reaches the target, that point is returned and flagged, because nothing below it
    was measured.
    """
    for index, point in enumerate(curve):
        if point["recall_at_k"] >= target:
            break
    else:
        return None
    if index == 0:
        out = dict(point)
        out["extrapolated_below_grid"] = True
        return out
    low, high = curve[index - 1], point
    span = high["recall_at_k"] - low["recall_at_k"]
    weight = (target - low["recall_at_k"]) / span if span > 0 else 1.0
    out: dict[str, Any] = {"recall_at_k": target, "extrapolated_below_grid": False}
    out["ef"] = math.exp(math.log(low["ef"]) + weight * (math.log(high["ef"]) - math.log(low["ef"])))
    for metric in METRICS:
        if metric in low and metric in high:
            out[metric] = low[metric] + weight * (high[metric] - low[metric])
    return out


def analyze(root: Path, targets: list[float]) -> dict[str, Any]:
    results = [json.loads(path.read_text()) for path in sorted(root.glob("**/result.json"))]
    issues: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    cells: dict[tuple[Any, ...], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    tags: dict[tuple[Any, ...], set[str]] = defaultdict(set)

    for result in results:
        args, engine = result["args"], result["engine"]
        cell = (engine, result["n"], args["m"], args["efc"])
        tags[cell].add(args.get("tag", ""))
        runs = [run for run in result.get("runs", []) if run.get("mem_limit") == "none"]
        latency = [row for run in runs for row in run.get("latency", [])]
        curve = per_ef_curve(latency, PRIMARY[engine])
        for target in targets:
            point = interpolate(curve, target)
            if point is None:
                issues.append({"experiment_id": result.get("experiment_id"), "problem": "recall_target_not_reached", "target": target})
                continue
            if point.get("extrapolated_below_grid"):
                # The target lies below the lowest swept ef, so nothing can be interpolated.
                # Keep it out of the aggregates instead of reporting a clamped value as matched.
                observations.append({
                    "experiment_id": result.get("experiment_id"), "engine": engine, "n": result["n"],
                    "m": args["m"], "efc": args["efc"], "tag": args.get("tag"),
                    "observation": "target_below_swept_ef_grid", "target": target,
                    "first_ef": point["ef"], "recall_at_first_ef": round(point["recall_at_k"], 5),
                })
                continue
            for metric in ("ef", *METRICS):
                if isinstance(point.get(metric), (int, float)):
                    cells[(*cell, f"{metric}@{target}")]["values"].append(float(point[metric]))
        fixed = next((p for p in curve if p["ef"] == FIXED_EF), None)
        if fixed:
            cells[(*cell, f"recall@ef{FIXED_EF}")]["values"].append(fixed["recall_at_k"])
        build = result.get("build", {})
        if isinstance(build.get("total_s"), (int, float)):
            cells[(*cell, "build_total_s")]["values"].append(float(build["total_s"]))
        for run in runs:
            for row in run.get("concurrency", []):
                if row.get("proto") == PRIMARY[engine] and row.get("clients") in (1, 8, 32):
                    clients = row["clients"]
                    cells[(*cell, f"qps_c{clients}")]["values"].append(float(row["throughput_qps"]))
                    cells[(*cell, f"recall_at_concurrency_ef_c{clients}")]["values"].append(float(row["recall_at_k"]))

    aggregates = []
    for key in sorted(cells, key=str):
        engine, n, m, efc, metric = key
        values = cells[key]["values"]
        stats = interval(values)
        stats["cv_percent"] = round(100 * statistics.stdev(values) / statistics.mean(values), 3) if len(values) > 1 and statistics.mean(values) else None
        stats["range"] = round(max(values) - min(values), 6)
        aggregates.append({"engine": engine, "n": n, "m": m, "efc": efc, "metric": metric, "stats": stats})

    cell_tags = [
        {"engine": e, "n": n, "m": m, "efc": efc, "builds": sorted(t)}
        for (e, n, m, efc), t in sorted(tags.items(), key=str)
    ]
    for cell in cell_tags:
        if len(cell["builds"]) < 3:
            issues.append({"cell": cell, "problem": "fewer_than_three_builds"})
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "verdict": "valid" if not issues else "invalid",
        "result_count": len(results),
        "cells": cell_tags,
        "aggregates": aggregates,
        "observations": observations,
        "issues": issues,
    }


def lookup(report: dict[str, Any], engine: str, m: int, efc: int, metric: str) -> dict[str, Any] | None:
    for item in report["aggregates"]:
        if (item["engine"], item["m"], item["efc"], item["metric"]) == (engine, m, efc, metric):
            return item["stats"]
    return None


def fmt(stats: dict[str, Any] | None, digits: int = 3) -> str:
    if not stats:
        return "n/a"
    sd = stats["sd"]
    return f"{stats['mean']:.{digits}f} ± {sd:.{digits}f}" if sd is not None else f"{stats['mean']:.{digits}f}"


def markdown_report(report: dict[str, Any], target: float = 0.95, title: str = "E8 HNSW build variance") -> str:
    lines = [
        f"# {title}",
        "",
        f"Verdict: **{report['verdict']}**; results: {report['result_count']}; issues: {len(report['issues'])}.",
        "",
        "Mean ± standard deviation across independent builds. Latency and CPU are linearly "
        f"interpolated in recall to {target} for each build.",
        "",
        f"| Engine | M | efc | ef@{target} | Latency ms | CV % | Server CPU ms/q | Recall@ef{FIXED_EF} | Build s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    seen = sorted({(c["engine"], c["m"], c["efc"]) for c in report["cells"]}, key=lambda x: (x[0], x[1], x[2]))
    for engine, m, efc in seen:
        lat = lookup(report, engine, m, efc, f"mean_ms@{target}")
        lines.append(
            f"| {engine} | {m} | {efc} | {fmt(lookup(report, engine, m, efc, f'ef@{target}'), 1)} | {fmt(lat)} | "
            f"{lat['cv_percent'] if lat else 'n/a'} | {fmt(lookup(report, engine, m, efc, f'server_cpu_ms_per_query@{target}'))} | "
            f"{fmt(lookup(report, engine, m, efc, f'recall@ef{FIXED_EF}'), 4)} | "
            f"{fmt(lookup(report, engine, m, efc, 'build_total_s'), 1)} |"
        )
    below = [o for o in report.get("observations", []) if o["observation"] == "target_below_swept_ef_grid"]
    if below:
        by_target: dict[Any, int] = defaultdict(int)
        for item in below:
            by_target[item["target"]] += 1
        lines += ["", "## Targets below the swept ef grid", ""]
        for target_value, count in sorted(by_target.items()):
            lines.append(
                f"- Recall@10 = {target_value}: {count} builds already reach it at the smallest swept ef, "
                "so those builds have no interpolated value at this target and are excluded from its aggregates."
            )
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(issue)}" for issue in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--targets", default="0.90,0.95")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--markdown-target", type=float, default=0.95)
    args = parser.parse_args()
    report = analyze(args.root, [float(v) for v in args.targets.split(",")])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report, args.markdown_target))
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
