#!/usr/bin/env python3
"""Aggregate E17: how often PostgreSQL's default planner leaves the HNSW index.

Each result holds, for one (N, dimension) build, the plan grid over ef: the planner's own
choice plus the best index plan and the best scan plan with their costs. Exposure is the
share of (N, dimension, ef) cells in which the default plan does not use the index.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def analyze(root: Path) -> dict[str, Any]:
    results = [json.loads(path.read_text()) for path in sorted(root.glob("**/result.json"))]
    cells: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for result in results:
        experiment = result.get("experiment_id")
        grid_runs = [r for r in result.get("runs", []) if "plan_grid" in r]
        if result.get("status") != "ok" or not grid_runs:
            issues.append({"experiment_id": experiment, "problem": "no_plan_grid", "status": result.get("status")})
            continue
        plan_grid = grid_runs[0]["plan_grid"]
        for row in plan_grid["grid"]:
            default = row["default"]
            cells.append({
                "n": result["n"], "dim": result["dim"], "ef": row["ef"],
                "default_uses_index": bool(default["uses_index"]),
                "default_nodes": default["nodes"], "default_cost": default["cost"],
                "index_cost": row["forced_index"]["cost"], "scan_cost": row["forced_scan"]["cost"],
                "index_to_scan_cost_ratio": row["index_to_scan_cost_ratio"],
            })
        sizes = plan_grid["table_pages"]
        for cell in cells[-len(plan_grid["grid"]):]:
            cell["heap_pages"], cell["toast_pages"], cell["index_pages"] = sizes["heap"], sizes["toast"], sizes["index"]
    exposed = [c for c in cells if not c["default_uses_index"]]
    by_build: dict[tuple[int, int], dict[str, Any]] = {}
    for cell in cells:
        key = (cell["n"], cell["dim"])
        entry = by_build.setdefault(key, {"n": key[0], "dim": key[1], "cells": 0, "exposed": 0, "exposed_ef": [],
                                          "heap_pages": cell["heap_pages"], "toast_pages": cell["toast_pages"],
                                          "index_pages": cell["index_pages"]})
        entry["cells"] += 1
        if not cell["default_uses_index"]:
            entry["exposed"] += 1
            entry["exposed_ef"].append(cell["ef"])
    builds = sorted(by_build.values(), key=lambda e: (e["dim"], e["n"]))
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "verdict": "valid" if not issues else "incomplete", "result_count": len(results),
            "cells": cells, "builds": builds,
            "summary": {"cells": len(cells), "exposed_cells": len(exposed),
                        "exposure": round(len(exposed) / len(cells), 4) if cells else None,
                        "builds_with_exposure": sum(1 for b in builds if b["exposed"]), "builds": len(builds)},
            "issues": issues}


def markdown_report(report: dict[str, Any], title: str = "E17 planner exposure") -> str:
    s = report["summary"]
    lines = [f"# {title}", "",
             f"Verdict: **{report['verdict']}**; builds: {s['builds']}; cells (N x dimension x ef): {s['cells']}; "
             f"cells where the default plan avoids the index: {s['exposed_cells']} "
             f"({100 * s['exposure']:.1f}%)." if s["cells"] else f"# {title}\n\nNo cells.", "",
             "No query is executed in this experiment: plans come from EXPLAIN. The planner's own choice is "
             "compared with the best index plan and the best scan plan.", "",
             "| Dim | N | Heap pages | TOAST pages | Index pages | Cells | Exposed | ef values using a scan |",
             "|---:|---:|---:|---:|---:|---:|---:|---|"]
    for b in report["builds"]:
        lines.append(f"| {b['dim']} | {b['n']} | {b['heap_pages']} | {b['toast_pages']} | {b['index_pages']} | "
                     f"{b['cells']} | {b['exposed']} | {', '.join(map(str, b['exposed_ef'])) or '-'} |")
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
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report))
    s = report["summary"]
    print(f"verdict={report['verdict']} builds={s['builds']} cells={s['cells']} exposed={s['exposed_cells']}")
    return 0 if report["verdict"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
