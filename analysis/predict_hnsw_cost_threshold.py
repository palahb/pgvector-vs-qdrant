#!/usr/bin/env python3
"""Predict where pgvector's HNSW cost estimate lowers the index cost, and compare with E17.

The formulas are those of hnswcostestimate in pgvector 0.8.6 (src/hnsw.c):

    entryLevel      = int(ln(tuples) * ml),  ml = 1 / ln(m)
    layer0TuplesMax = 2 * m * ef_search
    layer0Selectivity = 0.55 * ln(tuples) / (ln(m) * (1 + ln(ef_search)))
    ratio           = min((entryLevel * m + layer0TuplesMax * layer0Selectivity) / tuples, 1)
    startupPages    = index_pages * ratio
    the startup cost is lowered when startupPages > table_pages and ratio < 0.5

Only the condition is reproduced, not the cost values.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def scan_ratio(tuples: int, ef: int, m: int = 16) -> float:
    entry_level = int(math.log(tuples) * (1 / math.log(m)))
    layer0_tuples_max = 2 * m * ef
    layer0_selectivity = 0.55 * math.log(tuples) / (math.log(m) * (1 + math.log(ef)))
    return min((entry_level * m + layer0_tuples_max * layer0_selectivity) / tuples, 1.0)


def correction_applies(tuples: int, ef: int, table_pages: int, index_pages: int, m: int = 16) -> bool:
    ratio = scan_ratio(tuples, ef, m)
    return index_pages * ratio > table_pages and ratio < 0.5


def predicted_threshold(tuples: int, table_pages: int, index_pages: int, efs: list[int], m: int = 16) -> int | None:
    """Smallest ef in the grid at which the correction applies, or None."""
    return next((ef for ef in sorted(efs) if correction_applies(tuples, ef, table_pages, index_pages, m)), None)


def observed_drop(cells: list[dict]) -> int | None:
    """First ef at which the index plan's cost is lower than at the previous ef."""
    ordered = sorted(cells, key=lambda c: c["ef"])
    for previous, current in zip(ordered, ordered[1:]):
        if current["index_cost"] < previous["index_cost"] - 1e-6:
            return current["ef"]
    return None


def compare(analysis: dict) -> list[dict]:
    builds = {(b["dim"], b["n"]): b for b in analysis["builds"]}
    grouped: dict[tuple[int, int], list[dict]] = {}
    for cell in analysis["cells"]:
        grouped.setdefault((cell["dim"], cell["n"]), []).append(cell)
    rows = []
    for key in sorted(grouped):
        dim, n = key
        build, cells = builds[key], grouped[key]
        efs = [c["ef"] for c in cells]
        predicted = predicted_threshold(n, build["heap_pages"], build["index_pages"], efs)
        observed = observed_drop(cells)
        rows.append({"dim": dim, "n": n, "heap_pages": build["heap_pages"], "predicted_ef": predicted,
                     "observed_ef": observed, "match": predicted == observed,
                     "exposed_ef": sorted(c["ef"] for c in cells if not c["default_uses_index"])})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path, help="E17 analysis JSON")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = compare(json.loads(args.analysis.read_text()))
    matches = sum(r["match"] for r in rows)
    for r in rows:
        print(f"d={r['dim']:4d} N={r['n']:8d} heap={r['heap_pages']:7d} predicted={r['predicted_ef']} "
              f"observed={r['observed_ef']} exposed={r['exposed_ef']}")
    print(f"predicted threshold equals the observed cost drop in {matches} of {len(rows)} builds")
    if args.output:
        args.output.write_text(json.dumps({"matches": matches, "builds": len(rows), "rows": rows}, indent=2) + "\n")
    return 0 if matches == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
