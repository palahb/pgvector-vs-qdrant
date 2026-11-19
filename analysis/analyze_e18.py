#!/usr/bin/env python3
"""Aggregate E18: per-query recall distribution and recall across dimensions, over repeated builds.

Reads each result's result.json and its sibling raw.npz. For every (engine, dimension, build) the
per-query neighbor counts at each swept ef give the recall distribution; the summary at the
target is taken at the smallest swept ef whose mean recall reaches it, so the distribution
belongs to a real setting and is not an interpolation.
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

KEY = re.compile(r"^none_hits_(?P<proto>.+)_ef(?P<ef>\d+)_rep(?P<rep>\d+)$")
PRIMARY = {"pg": "pg", "qdrant": "grpc_raw"}
K = 10


def per_query_recall(hits: np.ndarray, k: int = K) -> np.ndarray:
    return np.asarray(hits, dtype=np.float64) / k


def distribution(recall: np.ndarray) -> dict[str, float]:
    return {
        "mean": float(recall.mean()),
        "p01": float(np.percentile(recall, 1)), "p05": float(np.percentile(recall, 5)),
        "p50": float(np.percentile(recall, 50)),
        "min": float(recall.min()),
        "share_perfect": float((recall >= 1.0).mean()),
        "share_below_0_8": float((recall < 0.8).mean()),
        "share_at_most_0_5": float((recall <= 0.5).mean()),
    }


def load_hits(raw_path: Path, proto: str) -> dict[int, np.ndarray]:
    """ef -> per-query neighbor counts of the first repetition."""
    out: dict[int, np.ndarray] = {}
    with np.load(raw_path) as raw:
        for name in raw.files:
            match = KEY.match(name)
            if match and match["proto"] == proto and int(match["rep"]) == 0:
                out[int(match["ef"])] = raw[name]
    return out


def analyze(root: Path, target: float = 0.95) -> dict[str, Any]:
    cells: dict[tuple[Any, ...], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    builds: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    issues: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        experiment = result.get("experiment_id")
        engine, dim, tag = result["engine"], result["dim"], result["args"].get("tag", "")
        rep = tag.split("_", 1)[0] if tag else ""
        raw_path = path.with_name("raw.npz")
        if result.get("status") != "ok" or not raw_path.exists():
            issues.append({"experiment_id": experiment, "problem": "missing_raw_or_not_ok"})
            continue
        hits_by_ef = load_hits(raw_path, PRIMARY[engine])
        if not hits_by_ef:
            issues.append({"experiment_id": experiment, "problem": "no_per_query_hits"})
            continue
        builds[(engine, dim)].add(rep)
        means = {ef: float(per_query_recall(h).mean()) for ef, h in hits_by_ef.items()}
        for ef in (64, 128):
            if ef in means:
                cells[(engine, dim, f"recall@ef{ef}")]["value"].append(means[ef])
        reaching = sorted(ef for ef, m in means.items() if m >= target)
        if not reaching:
            issues.append({"experiment_id": experiment, "problem": "target_not_reached", "target": target})
            continue
        ef = reaching[0]
        cells[(engine, dim, "ef_at_target")]["value"].append(float(ef))
        for name, value in distribution(per_query_recall(hits_by_ef[ef])).items():
            cells[(engine, dim, name)]["value"].append(value)
    aggregates = []
    for key in sorted(cells, key=str):
        engine, dim, metric = key
        values = cells[key]["value"]
        stats = interval(values)
        mean = statistics.mean(values)
        stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
        aggregates.append({"engine": engine, "dim": dim, "metric": metric, "stats": stats})
    cell_list = [{"engine": e, "dim": d, "builds": sorted(r)} for (e, d), r in sorted(builds.items(), key=str)]
    for cell in cell_list:
        if len(cell["builds"]) < 3:
            issues.append({"cell": cell, "problem": "fewer_than_three_builds"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "target": target, "verdict": "valid" if not issues else "invalid", "cells": cell_list,
            "aggregates": aggregates, "issues": issues}


def get(report: dict[str, Any], engine: str, dim: int, metric: str) -> dict[str, Any] | None:
    for item in report["aggregates"]:
        if (item["engine"], item["dim"], item["metric"]) == (engine, dim, metric):
            return item["stats"]
    return None


def fmt(stats: dict[str, Any] | None, digits: int = 3) -> str:
    if not stats:
        return "n/a"
    sd = stats["sd"]
    return f"{stats['mean']:.{digits}f} ± {sd:.{digits}f}" if sd is not None else f"{stats['mean']:.{digits}f}"


def markdown_report(report: dict[str, Any], title: str = "E18 per-query recall and dimensions") -> str:
    lines = [f"# {title}", "", f"Verdict: **{report['verdict']}**; target mean recall {report['target']}.", "",
             "Mean ± standard deviation over independent builds. The distribution is taken at the smallest swept ef "
             "whose mean recall reaches the target.", "",
             "| Engine | Dim | Recall@ef64 | Recall@ef128 | ef at target | p05 | min | share perfect | share <0.8 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for cell in report["cells"]:
        e, d = cell["engine"], cell["dim"]
        lines.append(f"| {e} | {d} | {fmt(get(report, e, d, 'recall@ef64'))} | {fmt(get(report, e, d, 'recall@ef128'))} | "
                     f"{fmt(get(report, e, d, 'ef_at_target'), 0)} | {fmt(get(report, e, d, 'p05'), 2)} | "
                     f"{fmt(get(report, e, d, 'min'), 2)} | {fmt(get(report, e, d, 'share_perfect'), 3)} | "
                     f"{fmt(get(report, e, d, 'share_below_0_8'), 4)} |")
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--target", type=float, default=0.95)
    args = parser.parse_args()
    report = analyze(args.root, args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} cells={len(report['cells'])} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
