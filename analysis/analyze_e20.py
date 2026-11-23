#!/usr/bin/env python3
"""Aggregate E20: float32 against quantized storage, at matched recall.

Arms: pgvector `vector` (float32) and `halfvec` (float16); Qdrant `f32` and `int8` scalar
quantization. Every build is one job on one node that builds both arms of a system, so each
quantized build has a baseline build of the same repetition on the same node and the
comparison is a paired ratio per repetition.

Recall is always measured against the exact float32 neighbors, so a recall below the baseline
is the accuracy lost to quantization. A target that an arm never reaches on the swept grid is
reported as an observation with the highest recall it did reach, not as an error.
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

import numpy as np

from analysis.analyze_e6 import interval
from analysis.analyze_e8 import METRICS, PRIMARY, interpolate, per_ef_curve
from analysis.analyze_e18 import distribution, per_query_recall

BASELINE = {"pg": "vector", "qdrant": "f32"}
SIZE_KEYS = ("index_bytes", "heap_bytes", "toast_bytes", "table_total_bytes", "storage_bytes")
HITS = re.compile(r"^none_hits_(?P<proto>.+)_ef(?P<ef>\d+)_rep(?P<rep>\d+)$")
FIXED_EF = 128


def arm_of(tag: str) -> tuple[str, str]:
    rep, _, arm = tag.partition("_")
    return rep, arm


def paired_ratio(value: dict[str, float], base: dict[str, float]) -> list[float]:
    return [value[rep] / base[rep] for rep in sorted(value) if rep in base and base[rep]]


def paired_diff(value: dict[str, float], base: dict[str, float]) -> list[float]:
    return [value[rep] - base[rep] for rep in sorted(value) if rep in base]


def load_hits(raw_path: Path, proto: str) -> dict[int, np.ndarray]:
    out: dict[int, np.ndarray] = {}
    with np.load(raw_path) as raw:
        for name in raw.files:
            match = HITS.match(name)
            if match and match["proto"] == proto and int(match["rep"]) == 0:
                out[int(match["ef"])] = raw[name]
    return out


def build_metrics(result: dict[str, Any], raw_path: Path, targets: list[float], dist_target: float,
                  observations: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, float]:
    engine, args = result["engine"], result["args"]
    rep, arm = arm_of(args.get("tag", ""))
    proto = PRIMARY[engine]
    runs = [run for run in result.get("runs", []) if run.get("mem_limit") == "none"]
    curve = per_ef_curve([row for run in runs for row in run.get("latency", [])], proto)
    out: dict[str, float] = {}
    who = {"experiment_id": result.get("experiment_id"), "engine": engine, "arm": arm, "rep": rep}
    for target in targets:
        point = interpolate(curve, target)
        if point is None:
            observations.append({**who, "observation": "target_not_reached", "target": target,
                                 "max_recall": max((p["recall_at_k"] for p in curve), default=None)})
            continue
        if point.get("extrapolated_below_grid"):
            observations.append({**who, "observation": "target_below_swept_ef_grid", "target": target,
                                 "first_ef": point["ef"]})
            continue
        for metric in ("ef", *METRICS):
            if isinstance(point.get(metric), (int, float)):
                out[f"{metric}@{target}"] = float(point[metric])
    if curve:
        out["recall_ceiling"] = curve[-1]["recall_at_k"]
        fixed = next((p for p in curve if p["ef"] == FIXED_EF), None)
        if fixed:
            out[f"recall@ef{FIXED_EF}"] = fixed["recall_at_k"]
    build = result.get("build", {})
    for key in ("total_s", *SIZE_KEYS):
        if isinstance(build.get(key), (int, float)):
            out["build_total_s" if key == "total_s" else key] = float(build[key])
    for run in runs:
        matched = run.get("conc_matched_ef")
        for row in run.get("concurrency", []):
            if row.get("proto") == proto and row.get("clients") in (1, 8, 32):
                # Two ef values run: the fixed one and the smallest swept ef reaching the recall
                # target. They are kept apart so one never overwrites the other.
                role = "matched" if row["ef"] == matched else f"ef{row['ef']}"
                out[f"qps_c{row['clients']}_{role}"] = float(row["throughput_qps"])
                if role == "matched":
                    out[f"recall_at_concurrency_c{row['clients']}_matched"] = float(row["recall_at_k"])
                    out["concurrency_matched_ef"] = float(row["ef"])
    if raw_path.exists():
        hits = load_hits(raw_path, proto)
        means = {ef: float(per_query_recall(h).mean()) for ef, h in hits.items()}
        reaching = sorted(ef for ef, mean in means.items() if mean >= dist_target)
        if reaching:
            out["ef_at_target"] = float(reaching[0])
            out.update(distribution(per_query_recall(hits[reaching[0]])))
    else:
        issues.append({**who, "problem": "missing_raw"})
    return out


def analyze(root: Path, targets: list[float], dist_target: float = 0.95) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    # (engine, arm) -> metric -> rep -> value
    table: dict[tuple[str, str], dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    reps: dict[tuple[str, str], set[str]] = defaultdict(set)
    count = 0
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        count += 1
        if result.get("status") != "ok":
            issues.append({"experiment_id": result.get("experiment_id"), "problem": "result_not_ok"})
            continue
        rep, arm = arm_of(result["args"].get("tag", ""))
        key = (result["engine"], arm)
        reps[key].add(rep)
        for metric, value in build_metrics(result, path.with_name("raw.npz"), targets, dist_target,
                                           observations, issues).items():
            table[key][metric][rep] = value

    aggregates = []
    for (engine, arm), metrics in sorted(table.items()):
        for metric, by_rep in sorted(metrics.items()):
            values = list(by_rep.values())
            stats = interval(values)
            mean = statistics.mean(values)
            stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
            aggregates.append({"engine": engine, "arm": arm, "metric": metric, "stats": stats})

    comparisons = []
    for (engine, arm), metrics in sorted(table.items()):
        base = table.get((engine, BASELINE[engine]))
        if arm == BASELINE[engine] or base is None:
            continue
        for metric, by_rep in sorted(metrics.items()):
            if metric not in base:
                continue
            recallish = metric.startswith("recall") or metric in {"mean", "p01", "p05", "p50", "min"} \
                or metric.startswith("share_")
            values = (paired_diff if recallish else paired_ratio)(by_rep, base[metric])
            if values:
                comparisons.append({"engine": engine, "arm": arm, "baseline": BASELINE[engine], "metric": metric,
                                    "kind": "difference" if recallish else "ratio", "stats": interval(values)})

    cells = [{"engine": e, "arm": a, "builds": sorted(r)} for (e, a), r in sorted(reps.items())]
    for cell in cells:
        if len(cell["builds"]) < 3:
            issues.append({"cell": cell, "problem": "fewer_than_three_builds"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "targets": targets, "distribution_target": dist_target,
            "verdict": "valid" if not issues else "invalid", "result_count": count, "cells": cells,
            "aggregates": aggregates, "comparisons": comparisons, "observations": observations, "issues": issues}


def get(report: dict[str, Any], engine: str, arm: str, metric: str) -> dict[str, Any] | None:
    for item in report["aggregates"]:
        if (item["engine"], item["arm"], item["metric"]) == (engine, arm, metric):
            return item["stats"]
    return None


def fmt(stats: dict[str, Any] | None, digits: int = 3) -> str:
    if not stats:
        return "n/a"
    sd = stats["sd"]
    return f"{stats['mean']:.{digits}f} ± {sd:.{digits}f}" if sd is not None else f"{stats['mean']:.{digits}f}"


def markdown_report(report: dict[str, Any], target: float = 0.95, title: str = "E20 quantization") -> str:
    lines = [f"# {title}", "",
             f"Verdict: **{report['verdict']}**; results: {report['result_count']}; issues: {len(report['issues'])}.", "",
             "Mean ± standard deviation over independent builds. Latency and CPU are interpolated in recall "
             f"to {target} for each build; recall is against exact float32 neighbors.", "",
             f"| Engine | Arm | Index/storage MB | Build s | ef@{target} | Latency ms | Server CPU ms/q | "
             f"Recall ceiling | share <0.8 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cell in report["cells"]:
        e, a = cell["engine"], cell["arm"]
        size = get(report, e, a, "index_bytes") or get(report, e, a, "storage_bytes")
        size_txt = f"{size['mean'] / 1e6:.0f}" if size else "n/a"
        lines.append(f"| {e} | {a} | {size_txt} | {fmt(get(report, e, a, 'build_total_s'), 1)} | "
                     f"{fmt(get(report, e, a, f'ef@{target}'), 0)} | {fmt(get(report, e, a, f'mean_ms@{target}'))} | "
                     f"{fmt(get(report, e, a, f'server_cpu_ms_per_query@{target}'))} | "
                     f"{fmt(get(report, e, a, 'recall_ceiling'), 4)} | {fmt(get(report, e, a, 'share_below_0_8'), 4)} |")
    lines += ["", "## Paired comparison with the float32 arm", "",
              "| Engine | Arm | Metric | Kind | Mean | 95% CI |", "|---|---|---|---|---:|---|"]
    for c in report["comparisons"]:
        s = c["stats"]
        ci = f"{s['ci95_low']:.3f} to {s['ci95_high']:.3f}" if s["ci95_low"] is not None else "n/a"
        lines.append(f"| {c['engine']} | {c['arm']} | {c['metric']} | {c['kind']} | {s['mean']:.4f} | {ci} |")
    if report["observations"]:
        lines += ["", "## Observations", ""] + [f"- {json.dumps(o)}" for o in report["observations"]]
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--targets", default="0.90,0.95")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = analyze(args.root, [float(v) for v in args.targets.split(",")])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
