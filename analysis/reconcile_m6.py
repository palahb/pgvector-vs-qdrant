#!/usr/bin/env python3
"""Reproduce and explain the referee's E1-vs-E2 throughput discrepancy (M6)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def matched_plateau(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text())
    run = result["runs"][0]
    matched_ef = run["conc_matched_ef"]
    proto = "pg" if result["engine"] == "pg" else "grpc_raw"
    rows = [
        row
        for row in run["concurrency"]
        if row["ef"] == matched_ef and row["proto"] == proto
    ]
    best = max(rows, key=lambda row: row["throughput_qps"])
    return {
        "source": path.as_posix(),
        "source_sha256": sha256_file(path),
        "engine": result["engine"],
        "slurm_job_id": result["host"]["slurm"]["SLURM_JOB_ID"],
        "node": result["host"]["hostname"],
        "measurement_time_utc": result["host"]["time_utc"],
        "ef_grid": result["args"]["ef"],
        "matched_ef": matched_ef,
        "matched_recall": best["recall_at_k"],
        "peak_qps": best["throughput_qps"],
        "peak_clients": best["clients"],
        "server_cores_busy": best["server_cores_busy"],
        "cpu_ms_per_query": round(best["server_cores_busy"] / best["throughput_qps"] * 1000, 5),
        "build_total_s": result["build"]["total_s"],
    }


def reconcile(root: Path) -> dict[str, Any]:
    paths = {
        "e1_pg": root / "e1_scale/n500000/pg/result.json",
        "e1_qdrant": root / "e1_scale/n500000/qdrant/result.json",
        "e2_pg": root / "e2_hnsw/n500000_m16_efc64/pg/result.json",
        "e2_qdrant": root / "e2_hnsw/n500000_m16_efc64/qdrant/result.json",
    }
    rows = {name: matched_plateau(path) for name, path in paths.items()}
    differences = {}
    for engine in ("pg", "qdrant"):
        e1 = rows[f"e1_{engine}"]
        e2 = rows[f"e2_{engine}"]
        differences[engine] = {
            "e2_vs_e1_qps_percent": round((e2["peak_qps"] / e1["peak_qps"] - 1) * 100, 2),
            "recall_delta": round(e2["matched_recall"] - e1["matched_recall"], 5),
            "ef_delta": e2["matched_ef"] - e1["matched_ef"],
        }
    return {
        "schema_version": 1,
        "referee_item": "M6",
        "paper_locations": ["Table tab:hnsw (reviewer Table 5)", "Figure fig:throughput (reviewer Figure 3)"],
        "verdict": "resolved_methodological_mismatch_not_transcription_error",
        "cause": [
            "E1 includes ef=384 and selects it as the first swept point at or above Recall@10 0.95.",
            "E2 omits ef=384; ef=256 remains below target, so it selects ef=512.",
            "E2 therefore measures throughput at materially higher recall and search effort for both engines.",
            "E1 pgvector and Qdrant came from different jobs/nodes/builds; E2 measured both in one job/node.",
            "Throughput was not interpolated to exactly equal recall, unlike the engine-latency table.",
        ],
        "measurements": rows,
        "differences": differences,
        "required_fix": [
            "Do not compare the current E1 and E2 throughput cells as the same condition.",
            "Use a fine common ef grid near the recall target and interpolate/model throughput at equal recall.",
            "Repeat independent builds and report confidence intervals with job/node/config IDs.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Baseline results root")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = reconcile(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "pg E1/E2 qps",
        report["measurements"]["e1_pg"]["peak_qps"],
        report["measurements"]["e2_pg"]["peak_qps"],
        "qdrant E1/E2 qps",
        report["measurements"]["e1_qdrant"]["peak_qps"],
        report["measurements"]["e2_qdrant"]["peak_qps"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
