#!/usr/bin/env python3
"""Build a checksummed index from manuscript tables/figures to raw result files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


ARTIFACT_PATTERNS = {
    "tab:build": ["e5_builds/n*/pg_r*/result.json", "e5_builds/n*/qdrant_r*/result.json"],
    "fig:build": ["e5_builds/n*/pg_r*/result.json", "e5_builds/n*/qdrant_r*/result.json"],
    "tab:matched": ["e1_scale/n*/pg/result.json", "e1_scale/n*/qdrant/result.json"],
    "fig:recall": ["e1_scale/n*/pg/result.json", "e1_scale/n*/qdrant/result.json"],
    "fig:throughput": ["e1_scale/n*/pg/result.json", "e1_scale/n*/qdrant/result.json"],
    "tab:hnsw": ["e2_hnsw/*/pg/result.json", "e2_hnsw/*/qdrant/result.json"],
    "fig:dims": ["e3_dims/*/pg/result.json", "e3_dims/*/qdrant_*/result.json"],
    "tab:sb": ["e4_memory/n*/pg_sb*/result.json"],
    "tab:caps": ["e4_memory/n*/pg_capped/result.json", "e4_memory/n*/qdrant_capped_ondisk/result.json"],
    "confounder:planner_fallback": ["e1_scale/n*/pg_*planner*/result.json"],
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matching(root: Path, patterns: Iterable[str]) -> list[Path]:
    return sorted({path for pattern in patterns for path in root.glob(pattern)})


def source_entry(root: Path, path: Path) -> dict:
    result = json.loads(path.read_text())
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "engine": result.get("engine"),
        "status": result.get("status"),
        "n": result.get("n"),
        "dim": result.get("dim"),
        "slurm_job_id": result.get("host", {}).get("slurm", {}).get("SLURM_JOB_ID"),
        "node": result.get("host", {}).get("hostname"),
        "image_sha256": result.get("image_sha256"),
    }


def build_index(root: Path, repo: Path) -> dict:
    artifacts = {}
    for artifact, patterns in ARTIFACT_PATTERNS.items():
        entries = [source_entry(root, path) for path in matching(root, patterns)]
        canonical = "".join(f"{item['sha256']}  {item['path']}\n" for item in entries).encode()
        artifacts[artifact] = {
            "source_count": len(entries),
            "source_set_sha256": hashlib.sha256(canonical).hexdigest(),
            "sources": entries,
        }
    generators = {}
    for relative in ("bench/paper_numbers.py", "bench/make_figures.py"):
        path = repo / relative
        generators[relative] = sha256_file(path)
    return {
        "schema_version": 1,
        "results_root": root.as_posix(),
        "generators": generators,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    report = build_index(args.root, repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    counts = {key: value["source_count"] for key, value in report["artifacts"].items()}
    print(json.dumps(counts, sort_keys=True))
    return 0 if all(counts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
