#!/usr/bin/env python3
"""E23: what does approximate search cost in ranking quality? (sensitivity analysis, see docs/E23_GATE_RESULT.md)

Only the judged queries that have a relevant document inside the 1M-passage corpus are scored, 63 of them. nDCG@10, MRR@10 and
Recall@10 of the ids returned by each engine at each swept ef are compared with the same metrics of the exact (brute force)
top 10 of the same corpus. The ratio ANN / exact says how much of the achievable ranking quality the approximation keeps;
it is not an absolute effectiveness number, because 99.3% of the judged-relevant documents are outside the corpus.
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

from analysis.ranking_metrics import mrr_at_k, ndcg_at_k, recall_at_k

PRIMARY = {"pg": "pg", "qdrant": "grpc_raw"}
IDS = re.compile(r"^none_ids_(?P<proto>.+)_ef(?P<ef>\d+)_rep0$")
RELEVANT = 2


def query_metrics(ranked_rows: list[int], segments: dict[str, int], k: int = 10) -> dict[str, float | None]:
    grades = [segments.get(str(int(row)), 0) for row in ranked_rows[:k]]
    available = list(segments.values())
    relevant_available = sum(1 for g in available if g >= RELEVANT)
    return {"ndcg": ndcg_at_k(grades, available, k), "mrr": mrr_at_k(grades, k, RELEVANT),
            "recall": recall_at_k(grades, relevant_available, k, RELEVANT)}


def bootstrap_ci(values: np.ndarray, seed: int = 0, resamples: int = 10_000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = np.asarray(values, dtype=float)[rng.integers(0, len(values), size=(resamples, len(values)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def ann_recall(ids: np.ndarray, gt: np.ndarray, k: int) -> np.ndarray:
    return np.array([len(set(map(int, a[:k])) & set(map(int, b[:k]))) / k for a, b in zip(ids, gt)])


def analyze(root: Path, judgments_path: Path, gt_path: Path, k: int = 10, target: float = 0.95,
            seed: int = 0) -> dict[str, Any]:
    judged = json.loads(judgments_path.read_text())["queries"]
    gt = np.load(gt_path)
    qids = sorted(judged, key=lambda q: judged[q]["query_index"])
    index = [judged[q]["query_index"] for q in qids]
    exact = [query_metrics(list(gt[i]), judged[q]["segments"], k) for q, i in zip(qids, index)]
    exact_mean = {m: float(np.mean([e[m] for e in exact])) for m in ("ndcg", "mrr", "recall")}

    per: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    builds: dict[str, set[str]] = defaultdict(set)
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        if result.get("status") != "ok":
            continue
        engine = result["engine"]
        builds[engine].add(path.parent.name)
        with np.load(path.with_name("raw.npz")) as raw:
            for name in raw.files:
                match = IDS.match(name)
                if not match or match["proto"] != PRIMARY[engine]:
                    continue
                ids = raw[name]
                metrics = [query_metrics(list(ids[i]), judged[q]["segments"], k) for q, i in zip(qids, index)]
                recall_all = ann_recall(ids, gt, k)
                per[(engine, int(match["ef"]))].append({
                    "ndcg": np.array([m["ndcg"] for m in metrics]), "mrr": np.array([m["mrr"] for m in metrics]),
                    "recall": np.array([m["recall"] for m in metrics]),
                    "ann_recall_all": float(recall_all.mean()), "ann_recall_judged": float(recall_all[index].mean())})

    exact_arrays = {m: np.array([e[m] for e in exact]) for m in ("ndcg", "mrr", "recall")}
    by_ef = []
    for (engine, ef), builds_at_ef in sorted(per.items()):
        item: dict[str, Any] = {"engine": engine, "ef": ef, "builds": len(builds_at_ef),
                                "ann_recall_all_queries": float(np.mean([b["ann_recall_all"] for b in builds_at_ef])),
                                "ann_recall_judged_queries": float(np.mean([b["ann_recall_judged"] for b in builds_at_ef]))}
        for m in ("ndcg", "mrr", "recall"):
            per_query = np.mean([b[m] for b in builds_at_ef], axis=0)        # mean over builds, per query
            item[m] = float(per_query.mean())
            item[f"{m}_ratio"] = item[m] / exact_mean[m] if exact_mean[m] else None
            lo, hi = bootstrap_ci(per_query - exact_arrays[m], seed=seed)
            item[f"{m}_minus_exact_ci95"] = [lo, hi]
            item[f"{m}_ratio_sd_over_builds"] = (statistics.stdev([float(b[m].mean()) / exact_mean[m] for b in builds_at_ef])
                                                 if len(builds_at_ef) > 1 and exact_mean[m] else None)
        by_ef.append(item)

    matched = {}
    for engine in sorted(builds):
        points = sorted((x for x in by_ef if x["engine"] == engine), key=lambda x: x["ef"])
        reach = next((x for x in points if x["ann_recall_all_queries"] >= target), None)
        if reach:
            matched[engine] = reach
    years = defaultdict(int)
    for q in qids:
        years[judged[q]["year"]] += 1
    lo, hi = bootstrap_ci(exact_arrays["ndcg"], seed=seed)
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "k": k, "target_recall": target, "queries": len(qids), "queries_by_year": dict(years),
            "exact": {**exact_mean, "ndcg_ci95": [lo, hi]}, "builds": {e: len(b) for e, b in builds.items()},
            "by_ef": by_ef, "matched": matched,
            "note": "sensitivity analysis: ratios to exact search on the same 1M corpus, not absolute effectiveness"}


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# E23 ranking quality of approximate search (sensitivity analysis)", "",
             f"{report['queries']} judged queries with a relevant document in the 1M corpus {report['queries_by_year']}. "
             f"Exact top-{report['k']}: nDCG@10 {report['exact']['ndcg']:.3f}, MRR@10 {report['exact']['mrr']:.3f}, "
             f"Recall@10 {report['exact']['recall']:.3f}. Ratios are ANN divided by exact.", "",
             "| Engine | ef | ANN recall (all queries) | nDCG@10 | ratio | difference to exact (95% CI) | MRR ratio | Recall@10 ratio |",
             "|---|---:|---:|---:|---:|---|---:|---:|"]
    for x in report["by_ef"]:
        lo, hi = x["ndcg_minus_exact_ci95"]
        lines.append(f"| {x['engine']} | {x['ef']} | {x['ann_recall_all_queries']:.3f} | {x['ndcg']:.3f} | "
                     f"{x['ndcg_ratio']:.3f} | {lo:+.3f} to {hi:+.3f} | {x['mrr_ratio']:.3f} | {x['recall_ratio']:.3f} |")
    lines += ["", "## At the smallest swept ef reaching recall " + str(report["target_recall"]), ""]
    for engine, x in report["matched"].items():
        lo, hi = x["ndcg_minus_exact_ci95"]
        lines.append(f"- {engine}: ef {x['ef']}, nDCG@10 ratio {x['ndcg_ratio']:.3f} (difference {lo:+.3f} to {hi:+.3f}), "
                     f"MRR ratio {x['mrr_ratio']:.3f}, Recall@10 ratio {x['recall_ratio']:.3f}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = analyze(args.root, args.judgments, args.gt)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown_report(report))
    print(f"queries={report['queries']} builds={report['builds']} points={len(report['by_ef'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
