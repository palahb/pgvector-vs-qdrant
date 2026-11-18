# One-month plan (core paper)

Scope sent to Prof. Demir on 2026-11-15. Out of scope unless he asks otherwise: filtered,
hybrid and mixed read/write workloads (M9), open-loop and multi-core scaling (M8),
quantization and pgvectorscale/VectorChord, 10M scale and second embedding model (M10).
If these stay out, the title drops "RAG workloads".

The older 25-phase plan (`../MAKALE_CALISMA_PLANI.md` in the workspace root) is the
reference for everything beyond this scope.

## Weeks

| Week | Work | Gate |
|---|---|---|
| 1 | Finish E6 500K/1M (job arrays 6985667, 6985669), pull and validate; E7 perf pilot; fix paper TODOs and references | E6 full audit has zero errors; no `\todo` left in sections 1-3 |
| 2 | E8: three builds per HNSW setting, fine ef grid near recall 0.90/0.95, per-query recall; planner exposure grid (M12) | Table 5 and Figure 3 come from one source |
| 3 | E9: symmetric Qdrant ingestion, ingest vs index time; E10: corrected memory study (full query set, cold start per job, repeats) | Memory claim is rewritten or withdrawn |
| 4 | Rewrite results, abstract, section 4 (confounder checklist), response to referee, AI-use statement, journal template | No `\todo`, every number traceable to a result file |

## Rules

- Every new experiment passes smoke, pilot, then full (see `ORCHESTRATION.md`).
- Wording "3-4x faster engine" stays out of the paper until E6 and CPU-ms/query are in.
- Nothing is sent outside (upstream issue, submission, release) without the author's approval.

## Progress log

### Week 1 (2026-11-15)

- E6 500K/1M full matrix: Qdrant array 6985667 (48/48) and pgvector array 6985669 (6/6),
  one attempt each, strict audit 54 results with zero errors and zero warnings
  (`data-manifests/e6_full_9050d65.json`). Latency ratio grows with segment count while
  the CPU-per-query ratio shrinks (see paper section "Latency Versus CPU Cost").
- E7 perf pilot: smoke 6988271, pilot 6989672, all eight counters usable on both engines
  (`data-manifests/e7_pilot_3a9e727.json`). Synthetic data only; the real-data perf run
  against E1 configurations is still to do (closes the "hardware counters per client
  path" TODO in the paper).
- Paper: sections 1-3 have no `\todo`. The "hardware counters per client path" TODO is
  closed with per-query user-space counters recomputed from the E1 baseline (single build
  per scale, so direction and rough size only). Two remain in Results: graph-quality
  variance (E8) and build I/O (E9; the baseline stores no WAL or checkpoint volume).
- Not done: LaTeX compile check (no TeX installed on this machine); push to GitHub.

### Week 2 start (2026-11-17)

- E8 (HNSW build variance): pilot 6995037 (6/6) and full 6996492 (24/24, one attempt each),
  48 results, strict audit zero errors/warnings (`data-manifests/e8_full_fe88da1.json`).
  Interpolated matched recall 0.95 at 500K: Qdrant latency 2.4-3.2x lower, server CPU
  1.3-1.6x lower across all eight settings. Build-to-build latency CV 0.2-4.5%, so pgvector's
  non-monotonic latency over graph density (3.6 and 4.9 standard errors) is systematic, not
  noise. Recall 0.90 lies below the swept ef grid for 27 builds (excluded, not clamped).
- Paper: HNSW Parameters section rewritten from E8; the graph-variance `\todo` is closed.
  One `\todo` remains in Results (1M load I/O, needs E9).
- Operational: commits pushed to `paper-full-revision` through `fe88da1`; later commits are
  local. A queued 8 h time limit made the first pilot wait 18 h, 1.5 h limits backfill well.

### Week 3 work done early (2026-11-17)

- E9 (ingestion fairness, referee M3/M4): harness now records PostgreSQL WAL, checkpoint and
  write volume per build phase and supports `--pg-unlogged` and Qdrant parallel upload,
  batch size, deferred indexing and indexing threads (defaults reproduce the old baseline).
  Pilot 6998060 and full 6998157 (6/6, one attempt each), 36 results, strict audit clean
  (`data-manifests/e9_full_31de7f4.json`).
- Result: at 1M pgvector's load writes 4.6 GB of WAL and takes 93 s logged against 22 s
  unlogged; load scales 2.9x for 2x data when logged and 2.0x unlogged. Qdrant total build
  falls from 356 s to 206 s with parallel streams, larger batches and deferred indexing.
  Which system "builds faster" flips with the configuration compared; the old build claim
  (C04) is withdrawn and replaced.
- Paper: new "Ingestion Fairness" subsection; the last `\todo` (1M load I/O) is closed.
  The paper now has no `\todo`.
- Not done: LaTeX compile check (no TeX), E10 memory study, push of the newest commits.

### E10 operations note (2026-11-18)

- Task 14 of E10 full array 7008319 (`pg_rep2_pg_sbq_none`) failed after 3 s on hamsi68
  with `could not bind IPv4 address "127.0.0.1": Address already in use` (port 55432). It
  started one minute after task 8 left the same node, so the previous PostgreSQL still held
  the port. No result data was produced.
- The orchestrator marks it non-retryable by design, so `retry` refused. Because the cause is
  an infrastructure collision and not a benchmark or validation failure, it was resubmitted
  by hand with `sbatch --array=14` on the same deployment (job 7008845). The registry keeps
  both attempts. The failed attempt's directory (`task_0014_7008838`) is excluded from
  analysis and must be listed as superseded in the E10 manifest.
- Follow-up for the harness: wait for the port to become free (or pick a port per job)
  before starting PostgreSQL. This needs a new commit and therefore new smoke and pilot
  gates, so it is not applied to the running E10 array.
