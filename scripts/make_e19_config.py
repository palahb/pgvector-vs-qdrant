#!/usr/bin/env python3
"""Generate configs/examples/e19_causal_decomposition.json.

Where does a query's CPU go? One client, 1M x 1024, M=16, efc=64. Per build we record the sweep
(CPU, latency, blocks per query), user-space hardware counters over a one-client window at the
matched-recall ef, and a `perf record` profile of rep 0 at every swept ef. Arms: pgvector (float32,
the default planner-forcing setup of the other experiments), Qdrant with automatic segments, and
Qdrant with one segment (one graph, like pgvector). Three builds each, one job per system.
Rep 0 of every ef carries the profiler, so analysis timing uses reps 1 and 2.
"""
import json
from pathlib import Path

EF = [128, 192, 256, 320, 384, 448, 512, 640]
EF_PILOT = [64, 128, 192, 256, 384, 512]
COMMON = {"dim": 1024, "seed": 42, "warm_seed": 7, "k": 10, "m": 16, "efc": 64, "warm": 500,
          "mem_limits": "none", "clients": [1], "conc_recall": 0.95, "perf": True, "perf_record": True}
PG = {"pg_shared_buffers": "32GB", "pg_effective_cache": "64GB", "pg_maintenance_mem": "16GB",
      "pg_planner": "force-index"}
QDRANT = {"protocols": ["grpc_raw"], "qdrant_indexing_threshold_kb": 1, "qdrant_require_indexed": True,
          "qdrant_control_grace_s": 120}
ARMS = {"pg": [("pg", {})], "qdrant": [("auto", {}), ("seg1", {"qdrant_segments": 1})]}


def job(stage, system, rep, n):
    pilot = stage == "pilot"
    runs = []
    for arm, extra in ARMS[system]:
        args = {**COMMON, "ef": EF_PILOT if pilot else EF, "reps": 3, "conc_ef": 256 if pilot else 384,
                "conc_duration": 10 if pilot else 30, "conc_warmup": 2 if pilot else 5,
                **(PG if system == "pg" else QDRANT), **extra, "n": n, "tag": f"rep{rep}_{arm}"}
        runs.append({"engine": system, "args": args})
    return {"job_key": f"n-{n}_sys-{system}_tag-rep{rep}", "factors": {"n": n, "system": system, "tag": f"rep{rep}"},
            "runs": runs}


config = {
    "schema_version": 1, "experiment_id": "E19_causal_decomposition", "code_commit": "AUTO",
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
    out = Path(__file__).resolve().parents[1] / "configs" / "examples" / "e19_causal_decomposition.json"
    out.write_text(json.dumps(config, indent=2) + "\n")
    print(out, len(config["stages"]["full"]["jobs"]), "full jobs")
