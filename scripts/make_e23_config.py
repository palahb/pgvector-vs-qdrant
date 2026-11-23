#!/usr/bin/env python3
"""Generate configs/examples/e23_ranking_quality.json.

The ids that each engine returns for every query at every swept ef, for the nDCG sensitivity analysis (E23).
1M x 1024, M=16, efc=64, three builds per system, one job per system and build; no concurrency windows, one repetition
(the ids of repetition 0 are what is analysed). Pilot: 100K, one build.
"""
import json
from pathlib import Path

EF = [32, 64, 96, 128, 192, 256, 384, 512, 768, 1000]
COMMON = {"dim": 1024, "seed": 42, "warm_seed": 7, "k": 10, "m": 16, "efc": 64, "warm": 100, "reps": 1, "ef": EF,
          "mem_limits": "none", "clients": [], "conc_recall": 0, "store_ids": True}
PG = {"pg_shared_buffers": "32GB", "pg_effective_cache": "64GB", "pg_maintenance_mem": "16GB",
      "pg_planner": "force-index"}
QDRANT = {"protocols": ["grpc_raw"], "qdrant_indexing_threshold_kb": 1, "qdrant_require_indexed": True,
          "qdrant_control_grace_s": 120}


def job(system, rep, n):
    args = {**COMMON, **(PG if system == "pg" else QDRANT), "n": n, "tag": f"rep{rep}"}
    return {"job_key": f"n-{n}_sys-{system}_tag-rep{rep}", "factors": {"n": n, "system": system, "tag": f"rep{rep}"},
            "runs": [{"engine": system, "args": args}]}


config = {
    "schema_version": 1, "experiment_id": "E23_ranking_quality", "code_commit": "AUTO",
    "registry_root": "$BENCH_ROOT/orchestration", "requires_smoke": True, "max_retries": 1,
    "resources": {"partition": "hamsi", "cpus": 56, "memory": "170G", "time": "01:30:00",
                  "array_concurrency": 4, "exclude": ["hamsi20", "hamsi65"]},
    "storage": {"min_free_gb": 200, "min_inode_free_percent": 10},
    "stages": {
        "pilot": {"jobs": [job(s, 1, 100_000) for s in ("pg", "qdrant")]},
        "full": {"jobs": [job(s, r, 1_000_000) for r in (1, 2, 3) for s in ("pg", "qdrant")]},
    },
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "configs" / "examples" / "e23_ranking_quality.json"
    out.write_text(json.dumps(config, indent=2) + "\n")
    print(out, len(config["stages"]["full"]["jobs"]), "full jobs")
