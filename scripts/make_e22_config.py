#!/usr/bin/env python3
"""Generate configs/examples/e22_open_loop.json (design: docs/E22_DESIGN.md).

1M x 1024, M=16, efc=64, pgvector (direct connection) and Qdrant (four segments, lean gRPC), three builds each. After the
one-repetition sweep fixes the matched-recall ef, a closed-loop window at 32 clients measures the capacity of the build, then
Poisson-arrival windows run at 50%, 80%, 95% and 110% of it, 60 s each. Pilot: 100K, one build per engine.
"""
import json
from pathlib import Path

EF = [64, 128, 192, 256, 320, 384, 448, 512, 640]
COMMON = {"dim": 1024, "seed": 42, "warm_seed": 7, "k": 10, "m": 16, "efc": 64, "warm": 200, "reps": 1, "ef": EF,
          "mem_limits": "none", "conc_ef": 64, "conc_recall": 0.95, "clients": [32],
          "open_loop_fractions": [0.5, 0.8, 0.95, 1.1], "open_loop_capacity_clients": 32, "open_loop_workers": 64}
PG = {"pg_shared_buffers": "32GB", "pg_effective_cache": "64GB", "pg_maintenance_mem": "16GB", "pg_planner": "force-index"}
QDRANT = {"protocols": ["grpc_raw"], "qdrant_indexing_threshold_kb": 1, "qdrant_require_indexed": True,
          "qdrant_control_grace_s": 120}


def job(system, rep, n, pilot):
    args = {**COMMON, **(PG if system == "pg" else QDRANT), "n": n, "tag": f"rep{rep}",
            "conc_duration": 5 if pilot else 30, "conc_warmup": 2 if pilot else 5,
            "open_loop_duration": 10 if pilot else 60}
    if pilot:
        args["ef"] = [64, 128, 192, 256, 384, 512]
    return {"job_key": f"n-{n}_sys-{system}_tag-rep{rep}", "factors": {"n": n, "system": system, "tag": f"rep{rep}"},
            "runs": [{"engine": system, "args": args}]}


config = {
    "schema_version": 1, "experiment_id": "E22_open_loop", "code_commit": "AUTO",
    "registry_root": "$BENCH_ROOT/orchestration", "requires_smoke": True, "max_retries": 1,
    "resources": {"partition": "hamsi", "cpus": 56, "memory": "170G", "time": "01:30:00",
                  "array_concurrency": 4, "exclude": ["hamsi20", "hamsi65"]},
    "storage": {"min_free_gb": 200, "min_inode_free_percent": 10},
    "stages": {"pilot": {"jobs": [job(s, 1, 100_000, True) for s in ("pg", "qdrant")]},
               "full": {"jobs": [job(s, r, 1_000_000, False) for r in (1, 2, 3) for s in ("pg", "qdrant")]}},
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "configs" / "examples" / "e22_open_loop.json"
    out.write_text(json.dumps(config, indent=2) + "\n")
    print(out, len(config["stages"]["full"]["jobs"]), "full jobs")
