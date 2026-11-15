#!/usr/bin/env python3
"""Validate which external perf counters are usable in a benchmark result tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = {"cycles", "instructions"}
DESIRED = {"cache-references", "cache-misses", "branches", "branch-misses"}


def base_event(name: str) -> str:
    return name.split(":", 1)[0]


def validate(root: Path) -> dict:
    engines = {}
    issues = []
    for path in sorted(root.glob("**/result.json")):
        result = json.loads(path.read_text())
        rows = [
            row for run in result.get("runs", []) for row in run.get("concurrency", [])
            if row.get("perf") is not None
        ]
        numeric = set()
        unsupported = set()
        for row in rows:
            for name, value in row.get("perf", {}).items():
                (numeric if isinstance(value, (int, float)) else unsupported).add(base_event(name))
        missing_required = sorted(REQUIRED - numeric)
        if not rows:
            issues.append({"engine": result.get("engine"), "problem": "no_perf_rows"})
        if missing_required:
            issues.append({"engine": result.get("engine"), "problem": "missing_required", "events": missing_required})
        engines[result["engine"]] = {
            "result": str(path), "perf_rows": len(rows),
            "numeric_events": sorted(numeric), "unsupported_events": sorted(unsupported),
            "missing_desired_events": sorted(DESIRED - numeric),
            "derived_metrics_present": sum(row.get("perf_derived") is not None for row in rows),
        }
    if set(engines) != {"pg", "qdrant"}:
        issues.append({"problem": "both_engines_required", "found": sorted(engines)})
    return {
        "schema_version": 1,
        "verdict": "validated" if not issues else "invalid_or_incomplete",
        "engines": engines,
        "issues": issues,
        "interpretation": (
            "perf counters are external process-level on-CPU attribution; they are not "
            "semantically identical to pg_stat_statements or Qdrant request telemetry spans"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"verdict={report['verdict']} engines={len(report['engines'])} issues={len(report['issues'])}")
    return 0 if report["verdict"] == "validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
