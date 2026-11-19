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

### E10 time-limit finding (2026-11-18)

- Task 10 (`pg_rep1_pg_sb1G_4G`) hit the 3 h limit without finishing its first pass set, and
  task 11 (`pg_rep1_pg_sbq_4G`) is about to. At the 8 GB cap the completed pgvector arms
  already need 770-1,020 s per steady pass (459-610 ms/query, `shared_buffers=1GB`) and
  1,940-1,960 s (about 1,160 ms/query, equalized arm), so one 4 GB pass is longer still.
  The job limit of 3 h is too short for the pgvector 4 GB arms; this is a design limit of
  the array, not a transient failure.
- Pending 4 GB pgvector tasks 22, 23, 34 and 35 of array 7008319 were cancelled before they
  started (no data lost) so they would not each occupy a node for 3 h and delay the rest.
  Tasks 10 and 11 have partial directories (`status: running`) that must be excluded from
  the analysis and listed as superseded in the E10 manifest.
- Open decision for the author: rerun the six pgvector 4 GB arms with a longer limit (each
  likely several hours) or report them as not completing within 3 h per task.

### E10 result (2026-11-18)

- E10 full array 7008319 finished: 30 usable results, strict audit clean
  (`data-manifests/e10_full_0b0b905.json`). Excluded: tasks 10 and 11 (3 h limit), task 14
  first attempt (port collision; manual retry 7008845 completed). Cancelled before start:
  tasks 22, 23, 34, 35. The pgvector 4 GB cells therefore have no completed repetition.
- Memory section, methodology, discussion, threats and conclusion rewritten from E10; the
  old 300-query claim is gone. The analyzer now lists planned cells with no result.
- Open for the author: whether to rerun the pgvector 4 GB arms with a longer job limit.

### Measurement bug found by the E17 pilot (2026-11-18)

- pgvector accepts `hnsw.ef_search` only from 1 to 1000. For a larger value the server logs
  `WARNING: ... outside the valid range (1 .. 1000)` and keeps the previous value (40 by
  default); the `SET` does not fail. The harness did not check, so pgvector rows labelled
  `ef=1024` were measured at `ef=40` (E8 example: 1.1 ms and recall 0.79 against 10.3 ms and
  0.974 at `ef=768`).
- Affected: only the pgvector rows with `ef=1024` in E6 full (18 rows, 6 files) and E8 full
  (72 rows, 24 files). E1-E4, E9, E10 and all pilots never exceeded `ef=1000`.
- Reported numbers are unchanged. The matched-recall values come from the smallest `ef`
  reaching the recall target, which was at most 512 in every pgvector build, so the invalid
  1024 point was never selected or interpolated. Re-running both analyzers with those rows
  excluded gives aggregates identical to the committed ones. The raw files keep the mislabeled
  rows; the analyzers now exclude them explicitly and E6 lists each exclusion as an observation.
- Fix: `set_ef_search` confirms the value with `SHOW` and raises on a mismatch; it is used at
  all three call sites. The E17 grid now stops at `ef=1000`. E6/E8 example configs still list
  1024 because they describe what ran.

### Week 4 items done early (2026-11-18/19)

- Related work: ten sources (Milvus, VBase, DiskANN, SPANN, Starling, Big-ANN NeurIPS'21,
  Filtered-DiskANN, ACORN, pgvectorscale, VectorChord with RaBitQ) checked against primary
  listings and positioned in a new Related Work subsection. Pages are given only where verified
  (Milvus, DiskANN, Big-ANN, Filtered-DiskANN); VBase, SPANN, Starling, ACORN and RaBitQ have no
  page range in the reference because none was confirmed. The vendor performance claims for
  pgvectorscale and VectorChord are described as unreproduced.
- E17 (planner exposure): pilot 7011941 reproduced the E1 fallback with recorded plans (500K,
  ef=256: default plan Seq Scan, index cost 13,323 against scan cost 11,819; ef=192 index cost
  10,516 and ef=384 3,787 match the paper's earlier figures). Full array 7013754 (20 jobs) submitted.
- AI-use statement drafted (`paper/ai_use_statement.md`) with the facts that can be stated and the
  points the authors must confirm; not inserted into the manuscript because the target journal's
  wording and placement are not fixed.

### E17 result (2026-11-19)

- E17 full array 7013754: 20 builds, 360 plan cells, one attempt each, strict audit clean
  (`data-manifests/e17_full_a5bb141.json`). 9 cells (2.5%) take a sequential scan, all at 768
  and 1024 dimensions; none at 128 or 384. Paper subsection "Planner Exposure" rewritten from
  the grid. The upstream report is not sent and needs the author's approval.

### Second port collision and its fix (2026-11-19)

- E18 pilot task 0 (`qdrant_rep1_d128`) failed after 48 s on hamsi54: Qdrant logged `Error while
  starting gRPC server: transport error` right after `gRPC listening on 56334`. The same class
  of fault as E10 task 14 (PostgreSQL on 55432): the previous job on the node still held its
  port. Task 1 ran on the same node a minute later and completed. That is two collisions in
  roughly 150 task starts of this session.
- Fix (the follow-up noted for E10): both servers now wait for their ports to be free before
  starting (`wait_for_free_ports`, up to 120 s, polling by trying to bind, which is what the
  server does; connecting is not used because a full accept queue made it look free). A wait
  is logged. The earlier failed attempt's directory is excluded from analysis.
- This changes the code commit, so smoke and pilot were run again for it.
- Also found in the E18 smoke: `hnsw.iterative_scan` is `off` in the main experiments
  (recorded in `server_info`), which answers referee minor comment 7.

### E18 result (2026-11-19)

- E18 full array 7014911: 24 tasks (8 dimensions x 3 builds, both engines), one attempt each, strict
  audit clean (`data-manifests/e18_full_7d1b1c4.json`). The harness now stores the number of true
  neighbors found per query and records pgvector's `hnsw.*` scan settings.
- Per-query recall: ~80% of queries perfect at mean recall 0.95; ~6% below 0.8 at 768/1024 dims;
  tails equal across engines. d=768: the E3 dip to 0.871 shrinks to 0.877 +/- 0.001 over three
  builds. Paper: new subsection "Per-Query Recall", extended Dimensionality, Environment and
  experiment map. Referee M7 mostly, m7 partly, m10 done.

## Month 1 status (2026-11-19)

Written to say plainly what is finished, what is blocked and on whom. The plan's own week 4 row
(results, abstract, section 4, referee response, AI-use statement, journal template) is met except
the journal template. Nothing below is marked done unless a validated result set, a manifest or a
commit backs it.

**Done and backed by validated results** (strict audit zero errors and zero warnings; manifests under
`data-manifests/`): E6 (segments, threads, CPU per query), E7 (counters pilot on synthetic data; real-data
counters recomputed from E1), E8 (HNSW build variance), E9 (ingestion fairness, WAL), E10 (memory limits,
without the pgvector 4 GB arms), E17 (planner plan grid, 360 cells), E18 (per-query recall, eight
dimensions, three builds). Paper: no `\todo`, Related Work, Per-Query Recall, Planner Exposure,
laptop-versus-controlled table, byte budget, experiment map E1-E18, abstract of about 240 words.
Referee response drafted for all twelve major and thirteen minor comments.

**Corrections found along the way** (all recorded above): Zhang et al. studied PASE, not pgvector; the
`ef_search` range problem (reported numbers unchanged); the "250x" slowdown restated as 218x like for
like; the 300-query memory claim replaced; "pgvector about 3x faster" restated as 1.6-3.7x at equal ef.

**Not done, and why**
- LaTeX compile check: no TeX on this machine and installing one was declined. The structural checks
  (environments, labels, references, citations) pass; the real build has to be done in Overleaf.
- Journal template: depends on the supervisor's journal decision, which has not arrived. The draft is
  in the ACM sigconf class.
- Scope items M8 (open loop, 16/28/56 cores, PgBouncer), M9 (filtered, mixed read/write, hybrid, nDCG)
  and M10 (10M scale, second embedding model) were proposed as future work and need the supervisor's
  agreement. qrels are not in the repository, so nDCG@10 was not computed.
- pgvector 4 GB memory arms: did not finish in the 3 h job limit; reported as not completed. Rerunning
  with a longer limit is the author's decision.
- Throughput interpolation at matched recall (M7) and compile flags of the engine binaries (m7) were not
  done.
- Upstream report to the pgvector maintainers: not sent, needs the author's approval. A draft issue and
  a reproducer script are written (`docs/PGVECTOR_ISSUE_DRAFT.md`); the reproducer has not been run.
  The cost-estimator mechanism in it was checked against pgvector's source and reproduces the observed
  threshold in 20 of 20 builds.

**Needs the author or supervisor** (nothing here is blocked on tooling): journal and deadline, the
scope reduction, the AI-use statement wording and its attestation, the 4 GB decision, the upstream
report. A draft of the second status mail to the supervisor is in `docs/MAIL_HOCA_DURUM_2.md`.
