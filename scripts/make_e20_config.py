#!/usr/bin/env python3
"""Generate configs/examples/e20_quantization.json.

Arms: pgvector vector (float32) and halfvec (float16); Qdrant float32 and int8 scalar
quantization (always_ram, rescore on, Qdrant's default oversampling). Each job builds the two
arms of one system, one after the other on one node, three independent builds (jobs) per system
at 1M x 1024. Pilot: the same shape at 100K with one repetition and a short grid.
"""
import json
from pathlib import Path

EF_FULL = [48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 240, 256, 288, 320, 384, 512, 640, 768, 1000]
EF_PILOT = [32, 64, 96, 128, 192, 256, 384, 512]
# pgvector rejects ef_search above 1000, so the top of the grid is 1000, not 1024.
COMMON = {"dim": 1024, "seed": 42, "warm_seed": 7, "k": 10, "m": 16, "efc": 64, "warm": 500,
          "mem_limits": "none", "conc_ef": 64, "conc_recall": 0.95}
PG = {"pg_shared_buffers": "32GB", "pg_effective_cache": "64GB", "pg_maintenance_mem": "16GB",
      "pg_planner": "force-index"}
QDRANT = {"protocols": ["grpc_raw"], "qdrant_indexing_threshold_kb": 1, "qdrant_require_indexed": True,
          "qdrant_control_grace_s": 120}
ARMS = {"pg": [("vector", {}), ("halfvec", {"pg_vector_type": "halfvec"})],
        "qdrant": [("f32", {}), ("int8", {"qdrant_quantization": "int8"})]}


def job(stage, system, rep, n):
    pilot = stage == "pilot"
    runs = []
    for arm, extra in ARMS[system]:
        args = {**COMMON, "ef": EF_PILOT if pilot else EF_FULL, "reps": 1 if pilot else 3,
                "clients": [1, 8, 32], "conc_duration": 5 if pilot else 30, "conc_warmup": 2 if pilot else 5,
                **(PG if system == "pg" else QDRANT), **extra, "n": n, "tag": f"rep{rep}_{arm}"}
        runs.append({"engine": system, "args": args})
    return {"job_key": f"n-{n}_sys-{system}_tag-rep{rep}", "factors": {"n": n, "system": system, "tag": f"rep{rep}"},
            "runs": runs}


config = {
    "schema_version": 1, "experiment_id": "E20_quantization", "code_commit": "AUTO",
    "registry_root": "$BENCH_ROOT/orchestration", "requires_smoke": True, "max_retries": 1,
    "resources": {"partition": "hamsi", "cpus": 56, "memory": "170G", "time": "01:30:00",
                  "array_concurrency": 4, "exclude": ["hamsi20", "hamsi65"]},
    "storage": {"min_free_gb": 200, "min_inode_free_percent": 10},
    "stages": {
        "pilot": {"jobs": [job("pilot", s, 1, 100_000) for s in ("pg", "qdrant")]},
        "full": {"jobs": [job("full", s, r, 1_000_000) for r in (1, 2, 3) for s in ("pg", "qdrant")]},
    },
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "configs" / "examples" / "e20_quantization.json"
    out.write_text(json.dumps(config, indent=2) + "\n")
    print(out, len(config["stages"]["full"]["jobs"]), "full jobs")
