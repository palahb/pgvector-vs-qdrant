#!/usr/bin/env python3
"""Generate configs/examples/e21_pgbouncer.json (design: docs/E21_DESIGN.md).

pgvector at 1M x 1024, M=16, efc=64. One build per job, three jobs. After a one-repetition sweep that fixes the matched-recall ef,
closed-loop windows at 1, 8, 32 and 48 clients run in three connection modes on that build: direct, direct_txn, pooled
(PgBouncer, transaction pooling, pool size 8 = server cores). Pilot: 100K, one job.
"""
import json
from pathlib import Path

EF = [64, 128, 192, 256, 320, 384, 448, 512, 640]
COMMON = {"dim": 1024, "seed": 42, "warm_seed": 7, "k": 10, "m": 16, "efc": 64, "warm": 200, "reps": 1, "ef": EF,
          "mem_limits": "none", "conc_ef": 64, "conc_recall": 0.95, "clients": [1, 8, 32, 48],
          "pg_shared_buffers": "32GB", "pg_effective_cache": "64GB", "pg_maintenance_mem": "16GB",
          "pg_planner": "force-index", "pg_conn_modes": ["direct", "direct_txn", "pooled"],
          "pg_pooler_pool_size": 8, "pg_pooler_max_client_conn": 200}


def job(stage, rep, n):
    pilot = stage == "pilot"
    args = {**COMMON, "n": n, "tag": f"rep{rep}", "conc_duration": 5 if pilot else 30, "conc_warmup": 2 if pilot else 5}
    if pilot:
        args["ef"] = [64, 128, 192, 256, 384, 512]
    return {"job_key": f"n-{n}_tag-rep{rep}", "factors": {"n": n, "tag": f"rep{rep}"}, "runs": [{"engine": "pg", "args": args}]}


config = {
    "schema_version": 1, "experiment_id": "E21_pgbouncer", "code_commit": "AUTO",
    "registry_root": "$BENCH_ROOT/orchestration", "requires_smoke": True, "max_retries": 1,
    "resources": {"partition": "hamsi", "cpus": 56, "memory": "170G", "time": "01:30:00",
                  "array_concurrency": 3, "exclude": ["hamsi20", "hamsi65"]},
    "storage": {"min_free_gb": 200, "min_inode_free_percent": 10},
    "stages": {"pilot": {"jobs": [job("pilot", 1, 100_000)]},
               "full": {"jobs": [job("full", r, 1_000_000) for r in (1, 2, 3)]}},
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "configs" / "examples" / "e21_pgbouncer.json"
    out.write_text(json.dumps(config, indent=2) + "\n")
    print(out, len(config["stages"]["full"]["jobs"]), "full jobs")
