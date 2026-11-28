# E10, pgvector at 4 GB: rerun on hamsi (G13)

Submitted 28 November 2026 (after the author's `/goal ... G13 ve G14 başlasın`). Records what was run so the result can be bound to it.

* Code: commit `0b0b905c9fca9aa0350d4a392440394aa7a9a066`, the same checkout as E10 (`/arf/scratch/endemir/rag_bench/revisions/0b0b905`), so the harness is identical to the other E10 cells.
* Gates: the smoke manifest and the pilot summary of commit `0b0b905` (`orchestration/gates/smoke_0b0b905...json`, `submissions/E10_memory_limits-pilot-0b0b905c-0b300a95/summary.json`) were found by `manage.py submit --dry-run` and reused; the experiment id is unchanged.
* Config: `configs/examples/e10_hamsi_4g_rerun.json`, written by `scripts/make_e10_4g_config.py` from `e10_memory_limits.json`: the six `pg_*` cells at 4 GB (two buffer settings x three repetitions) with the same job keys, tags and seeds as in E10; only
  `resources.time` (48:00:00 instead of 03:00:00) and `array_concurrency` (6) differ.
* Submission id `E10_memory_limits-4g-rerun-48h`, Slurm job `7085866` (array 0-5), partition `hamsi`, whole node (`-c 56 --mem=170G`), excluded nodes `hamsi20,hamsi65` as before.
* Slurm estimate at submission (`--test-only`): first start 4 December 13:13. A pass at 8 GB takes about 33 min (steady, 1/4 buffers); the 4 GB estimate is in `docs/E10_NVME_PLAN.md` (3 h to 35 h per job, not measured).
* If a task hits the 48 h limit it is recorded as "did not finish within 48 h" in the manifest and the paper; nothing is extrapolated.
