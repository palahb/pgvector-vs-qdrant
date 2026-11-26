#!/usr/bin/env python3
"""M7: closed-loop throughput at exactly the matched recall, instead of at the first swept ef that reaches it.

The concurrency windows run at the smallest swept ef whose recall reaches the target, so their recall overshoots it (0.951 to 0.957), and
a higher recall is a slower query. With clients >= cores both engines are CPU bound, so throughput is inversely proportional to the CPU time
of a query. The measured plateau of a build at its matched ef is therefore corrected to the target recall with the build's own
CPU-per-query curve:

    qps(target) = qps(matched ef) * cpu(matched ef) / cpu(target),   cpu(target) interpolated in recall as in E8.

The proportionality is not assumed: the same formula predicts the throughput at the second measured ef (ef=64) from the matched point,
and the difference to the measurement is reported per build (`validation_error_percent`).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.analyze_e6 import interval
from analysis.analyze_e8 import PRIMARY, interpolate, per_ef_curve

CLIENTS = (8, 32)


def correct_throughput(qps_at_point: float, cpu_at_point: float | None, cpu_at_target: float | None) -> float | None:
    if not cpu_at_point or not cpu_at_target or cpu_at_target <= 0:
        return None
    return qps_at_point * cpu_at_point / cpu_at_target


def analyze(root: Path, target: float = 0.95) -> dict[str, Any]:
    builds: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        if result.get("status") != "ok":
            continue
        engine, args = result["engine"], result["args"]
        proto = PRIMARY[engine]
        tag = args.get("tag", path.parent.name)
        rep, _, arm = tag.partition("_")
        for run in (r for r in result.get("runs", []) if r.get("mem_limit") == "none"):
            matched = run.get("conc_matched_ef")
            curve = per_ef_curve(run.get("latency", []), proto)
            point = next((p for p in curve if p["ef"] == matched), None)
            at_target = interpolate(curve, target)
            who = {"experiment_id": result.get("experiment_id"), "engine": engine, "arm": arm or "base", "rep": rep}
            if matched is None or point is None or "server_cpu_ms_per_query" not in point:
                issues.append({**who, "problem": "no_matched_point_or_cpu_curve"})
                continue
            if at_target is None or at_target.get("extrapolated_below_grid") or "server_cpu_ms_per_query" not in at_target:
                issues.append({**who, "problem": "target_not_reached"})
                continue
            for clients in CLIENTS:
                rows = {c["ef"]: c for c in run.get("concurrency", []) if c.get("proto") == proto and c.get("clients") == clients}
                if matched not in rows:
                    issues.append({**who, "problem": "no_concurrency_row", "clients": clients})
                    continue
                qps_point = rows[matched]["throughput_qps"]
                qps_target = correct_throughput(qps_point, point["server_cpu_ms_per_query"], at_target["server_cpu_ms_per_query"])
                row = {**who, "clients": clients, "matched_ef": matched, "recall_at_point": point["recall_at_k"],
                       "overshoot": point["recall_at_k"] - target, "qps_at_point": qps_point,
                       "cpu_ms_at_point": point["server_cpu_ms_per_query"],
                       "cpu_ms_at_target": at_target["server_cpu_ms_per_query"], "qps_at_target": qps_target,
                       "correction_percent": 100 * (qps_target / qps_point - 1)}
                other = [(ef, c) for ef, c in rows.items() if ef != matched]
                if other:
                    ef2, c2 = min(other, key=lambda t: t[0])
                    cpu2 = next((p["server_cpu_ms_per_query"] for p in curve if p["ef"] == ef2), None)
                    predicted = correct_throughput(qps_point, point["server_cpu_ms_per_query"], cpu2)
                    if predicted:
                        row.update({"validation_ef": ef2, "validation_cores_busy": c2.get("server_cores_busy"),
                                    "validation_predicted_qps": predicted,
                                    "validation_measured_qps": c2["throughput_qps"],
                                    "validation_error_percent": 100 * (predicted / c2["throughput_qps"] - 1)})
                builds.append(row)

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for b in builds:
        groups[(b["engine"], b["arm"], b["clients"])].append(b)
    aggregates = []
    for (engine, arm, clients), rows in sorted(groups.items()):
        for metric in ("overshoot", "qps_at_point", "qps_at_target", "correction_percent", "validation_error_percent"):
            values = [r[metric] for r in rows if isinstance(r.get(metric), (int, float))]
            if values:
                aggregates.append({"engine": engine, "arm": arm, "clients": clients, "metric": metric, "stats": interval(values)})
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root), "target": target,
            "model": "qps(target) = qps(matched ef) * cpu(matched ef) / cpu(target)", "builds": builds,
            "aggregates": aggregates, "issues": issues, "verdict": "valid" if builds and not issues else "invalid"}


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# M7: throughput at exactly the matched recall", "", f"Target recall {report['target']}. Model: {report['model']}. "
             "Validation compares the model's prediction at the second measured ef with the measurement.", "",
             "| Engine | Arm | Clients | recall at point | qps at point | qps at target | correction % | validation error % |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    agg = {(a["engine"], a["arm"], a["clients"], a["metric"]): a["stats"] for a in report["aggregates"]}
    for engine, arm, clients in sorted({(a["engine"], a["arm"], a["clients"]) for a in report["aggregates"]}):
        def m(metric, d):
            s = agg.get((engine, arm, clients, metric))
            return "n/a" if not s else f"{s['mean']:.{d}f}"
        lines.append(f"| {engine} | {arm} | {clients} | {0.95 + (agg[(engine, arm, clients, 'overshoot')]['mean']):.3f} | "
                     f"{m('qps_at_point', 0)} | {m('qps_at_target', 0)} | {m('correction_percent', 1)} | {m('validation_error_percent', 1)} |")
    if report["issues"]:
        lines += ["", "## Issues", ""] + [f"- {json.dumps(i)}" for i in report["issues"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--target", type=float, default=0.95)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = analyze(args.root, args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown_report(report))
    print(f"verdict={report['verdict']} builds={len(report['builds'])} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
