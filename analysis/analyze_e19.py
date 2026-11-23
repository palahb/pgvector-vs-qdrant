#!/usr/bin/env python3
"""Aggregate E19: where the CPU of one query goes, for pgvector and Qdrant.

Per build, at the matched-recall ef of that build (the smallest swept ef whose rep-0 recall
reaches 0.95, as chosen by the harness):

* CPU per query, latency and shared-buffer blocks per query come from the latency sweep, using
  repetitions 1 and 2 only, because repetition 0 carries the profiler;
* cycles, instructions and cache misses per query are user-space hardware counters over a
  one-client window at that ef;
* the share of samples per function category comes from a `perf record` profile of rep 0 at that
  ef (see perf_profile.py). Cycles per category = share x cycles per query.

Neither engine reports how many distances a query computes, and the nodes allow neither root nor
eBPF. The distance count is therefore bounded, not measured: the CPU time spent in distance
functions divided by the fastest per-distance time of a pinned-core kernel probe (E7) is an upper
bound on the count, because a distance in a graph search costs at least as much as in the probe.
For pgvector the shared-buffer blocks per query are a second, independent upper-bound proxy.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

from analysis.analyze_e6 import interval
from analysis.perf_profile import CATEGORIES

PRIMARY = {"pg": "pg", "qdrant": "grpc_raw"}
# ns per 1024-d distance, in-cache streaming probe on one pinned core (E7 job 6985664, mean of 3).
KERNEL_NS = {"scalar": 1504.333682, "avx2_fma": 282.214804, "avx512f_fma": 248.19019}
BASELINE = "pg"


def distance_upper_bound(distance_ms: float, kernel: str) -> float:
    return distance_ms * 1e6 / KERNEL_NS[kernel]


def event(row: dict[str, Any], wanted: str) -> float | None:
    for name, value in ((row.get("perf_derived") or {}).get("events_per_query") or {}).items():
        if name.split(":", 1)[0] == wanted and isinstance(value, (int, float)):
            return float(value)
    return None


def load_profiles(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    path = root / "perf_profiles.json"
    if not path.exists():
        return {}
    out = {}
    for profile in json.loads(path.read_text()).get("profiles", []):
        parts = Path(profile["file"]).parts
        out[(parts[-2], parts[-1])] = profile
    return out


def build_metrics(result: dict[str, Any], directory: str, profiles: dict[tuple[str, str], dict[str, Any]],
                  issues: list[dict[str, Any]]) -> dict[str, float]:
    engine, proto = result["engine"], PRIMARY[result["engine"]]
    who = {"experiment_id": result.get("experiment_id")}
    out: dict[str, float] = {}
    for run in (r for r in result.get("runs", []) if r.get("mem_limit") == "none"):
        ef = run.get("conc_matched_ef")
        if ef is None:
            issues.append({**who, "problem": "no_matched_ef"})
            continue
        out["ef"] = float(ef)
        rows = [r for r in run.get("latency", []) if r.get("proto") == proto and r["ef"] == ef and r["rep"] >= 1]
        if not rows:
            issues.append({**who, "problem": "no_timed_reps_at_matched_ef"})
            continue
        for key, name in (("server_cpu_ms_per_query", "server_cpu_ms_per_query"), ("mean_ms", "mean_ms"),
                          ("blks_hit_per_query", "blocks_per_query"), ("recall_at_k", "recall_at_k")):
            values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
            if values:
                out[name] = statistics.mean(values)
        counters = next((r for r in run.get("concurrency", []) if r.get("proto") == proto
                         and r.get("clients") == 1 and r.get("ef") == ef and r.get("perf_derived")), None)
        cycles = instructions = None
        if counters:
            cycles, instructions = event(counters, "cycles"), event(counters, "instructions")
            misses, refs = event(counters, "cache-misses"), event(counters, "cache-references")
            if cycles:
                out["cycles"] = cycles
            if instructions:
                out["instructions"] = instructions
            if cycles and instructions:
                out["ipc"] = instructions / cycles
            if misses is not None:
                out["cache_misses_per_query"] = misses
            if misses is not None and refs:
                out["cache_miss_ratio"] = misses / refs
        else:
            issues.append({**who, "problem": "no_counter_window_at_matched_ef"})
        profile = profiles.get((directory, f"perfrec_{proto}_ef{int(ef)}.data"))
        if profile is None:
            issues.append({**who, "problem": "no_profile", "ef": ef})
            continue
        for name in CATEGORIES:
            out[f"share_{name}"] = profile["shares"][name]
            if cycles:
                out[f"cycles_{name}"] = profile["shares"][name] * cycles
        if "server_cpu_ms_per_query" in out:
            distance_ms = profile["shares"]["distance"] * out["server_cpu_ms_per_query"]
            out["distance_ms"] = distance_ms
            out["distances_upper_avx2"] = distance_upper_bound(distance_ms, "avx2_fma")
            out["distances_upper_avx512"] = distance_upper_bound(distance_ms, "avx512f_fma")
    return out


def analyze(root: Path) -> dict[str, Any]:
    profiles = load_profiles(root)
    issues: list[dict[str, Any]] = []
    table: dict[tuple[str, str], dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    reps: dict[tuple[str, str], set[str]] = defaultdict(set)
    count = 0
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        count += 1
        if result.get("status") != "ok":
            issues.append({"experiment_id": result.get("experiment_id"), "problem": "result_not_ok"})
            continue
        rep, _, arm = result["args"].get("tag", "").partition("_")
        key = (result["engine"], arm)
        reps[key].add(rep)
        for metric, value in build_metrics(result, path.parent.name, profiles, issues).items():
            table[key][metric][rep] = value

    aggregates = []
    for (engine, arm), metrics in sorted(table.items()):
        for metric, by_rep in sorted(metrics.items()):
            stats = interval(list(by_rep.values()))
            values = list(by_rep.values())
            mean = statistics.mean(values)
            stats["cv_percent"] = round(100 * statistics.stdev(values) / mean, 3) if len(values) > 1 and mean else None
            aggregates.append({"engine": engine, "arm": arm, "metric": metric, "stats": stats})

    comparisons = []
    base_key = next((k for k in table if k[0] == BASELINE), None)
    for key, metrics in sorted(table.items()):
        if key[0] == BASELINE or base_key is None:
            continue
        for metric, by_rep in sorted(metrics.items()):
            base = table[base_key].get(metric)
            if not base:
                continue
            ratios = [b / v for b, v in product(base.values(), by_rep.values()) if v]
            if ratios:
                comparisons.append({
                    "baseline": f"{base_key[0]}/{base_key[1]}", "engine": key[0], "arm": key[1], "metric": metric,
                    "ratio_of_means": statistics.mean(base.values()) / statistics.mean(by_rep.values())
                    if statistics.mean(by_rep.values()) else None,
                    "pairwise_min": min(ratios), "pairwise_max": max(ratios), "pairs": len(ratios)})

    cells = [{"engine": e, "arm": a, "builds": sorted(r)} for (e, a), r in sorted(reps.items())]
    for cell in cells:
        if len(cell["builds"]) < 3:
            issues.append({"cell": cell, "problem": "fewer_than_three_builds"})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "kernel_ns_per_distance": KERNEL_NS, "verdict": "valid" if not issues else "invalid",
            "result_count": count, "cells": cells, "aggregates": aggregates, "comparisons": comparisons,
            "issues": issues}


def get(report: dict[str, Any], engine: str, arm: str, metric: str) -> dict[str, Any] | None:
    for item in report["aggregates"]:
        if (item["engine"], item["arm"], item["metric"]) == (engine, arm, metric):
            return item["stats"]
    return None


def fmt(stats: dict[str, Any] | None, scale: float = 1.0, digits: int = 2) -> str:
    if not stats:
        return "n/a"
    sd = stats["sd"]
    text = f"{stats['mean'] / scale:.{digits}f}"
    return f"{text} ± {sd / scale:.{digits}f}" if sd is not None else text


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# E19 causal decomposition", "",
             f"Verdict: **{report['verdict']}**; results: {report['result_count']}; issues: {len(report['issues'])}.", "",
             "One client, 1M x 1024, matched-recall ef of each build. Mean ± standard deviation over builds. "
             "Cycles are user-space counters per query; category cycles = profile share x cycles.", "",
             "| Engine | Arm | ef | CPU ms/q | Mcycles/q | Minstr/q | IPC | blocks/q |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for cell in report["cells"]:
        e, a = cell["engine"], cell["arm"]
        lines.append(f"| {e} | {a} | {fmt(get(report, e, a, 'ef'), 1, 0)} | {fmt(get(report, e, a, 'server_cpu_ms_per_query'))} | "
                     f"{fmt(get(report, e, a, 'cycles'), 1e6, 1)} | {fmt(get(report, e, a, 'instructions'), 1e6, 1)} | "
                     f"{fmt(get(report, e, a, 'ipc'), 1, 2)} | {fmt(get(report, e, a, 'blocks_per_query'), 1, 0)} |")
    lines += ["", "## Mcycles per query by category", "",
              "| Engine | Arm | " + " | ".join(CATEGORIES) + " |", "|---|---|" + "---:|" * len(CATEGORIES)]
    for cell in report["cells"]:
        e, a = cell["engine"], cell["arm"]
        lines.append(f"| {e} | {a} | " + " | ".join(fmt(get(report, e, a, f'cycles_{c}'), 1e6, 2) for c in CATEGORIES) + " |")
    lines += ["", "## Distance work (upper bounds)", "",
              "| Engine | Arm | distance ms/q | at most (AVX2 ns/dist) | at most (AVX-512 ns/dist) |", "|---|---|---:|---:|---:|"]
    for cell in report["cells"]:
        e, a = cell["engine"], cell["arm"]
        lines.append(f"| {e} | {a} | {fmt(get(report, e, a, 'distance_ms'), 1, 3)} | "
                     f"{fmt(get(report, e, a, 'distances_upper_avx2'), 1, 0)} | {fmt(get(report, e, a, 'distances_upper_avx512'), 1, 0)} |")
    lines += ["", "## pgvector against Qdrant (ratio of means, range over all build pairs)", "",
              "| Arm | Metric | Ratio | Min | Max |", "|---|---|---:|---:|---:|"]
    for c in report["comparisons"]:
        if c["metric"] in {"server_cpu_ms_per_query", "cycles", "instructions", "ipc", "blocks_per_query", "distance_ms",
                           *[f"cycles_{x}" for x in CATEGORIES]}:
            lines.append(f"| {c['arm']} | {c['metric']} | {c['ratio_of_means']:.3f} | {c['pairwise_min']:.3f} | {c['pairwise_max']:.3f} |")
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
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
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} results={report['result_count']} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
