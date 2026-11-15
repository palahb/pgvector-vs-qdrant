# E6 pilot operations log

## Superseded pilot (commit `66c01ae`)

- Smoke: job `6984048`, hamsi51, `COMPLETED 0:0`, strict audit clean.
- Qdrant array: job `6984055`; pgvector reference array: job `6984056`.
- Tasks 0–3 of the Qdrant array failed non-retryably and independently on hamsi51,
  hamsi101, hamsi103 and hamsi112. Each configured
  `default_segment_number=1`, indexed 100000/100000 vectors, and reported public
  `segments_count=2`.
- Root cause: the harness incorrectly treated Qdrant's optimizer segment target as an
  exact public segment-count contract. Qdrant can keep an additional appendable segment.
- The orchestrator correctly did not retry a scientific-control failure. After the common
  cause was confirmed, the remaining Qdrant tasks and old pgvector reference were
  cancelled to prevent resource waste and cross-commit comparison.
- No failed output is eligible for analysis. It remains isolated by the superseded
  submission IDs for auditability.

## Corrected pilot (commit `9050d65`)

- Fix: requested optimizer target, public actual count and detailed per-segment telemetry
  are now distinct fields. A difference is an explicit observation; fully indexed vectors
  remain a hard gate.
- Smoke: job `6985140`, hamsi29, `COMPLETED 0:0` in 37 seconds, two schema-v2 results,
  strict audit with zero errors and zero warnings.
- Qdrant array: job `6985152`, 24 tasks, array concurrency cap 4.
- pgvector reference array: job `6985153`, 3 tasks, array concurrency cap 2.
- Submission IDs:
  - `E6_qdrant_segment_threads-pilot-9050d65f-9889be25`
  - `E6_pg_reference-pilot-9050d65f-a9e1d09b`
- Qdrant final registry: 24/24 completed and validated, zero consistency issues, zero
  failed tasks, median task duration 154.5795 s and no slow-node anomaly.
- pgvector final registry: 3/3 completed and validated, zero consistency issues, median
  task duration 169.416 s and no slow-node anomaly.
- Combined strict audit: 27 results, zero errors and zero warnings. All nine control
  cells contain three independent build tags.
- Level-10 telemetry resolved the earlier count observation: target-1 runs contain one
  non-empty indexed segment with all 100K vectors plus one empty appendable segment.
- Derived evidence is tracked in `results/derived/e6_pilot_9050d65_analysis.json`,
  `results/derived/e6_pilot_9050d65_summary.md` and
  `paper/figures/e6_pilot_segment_threads.{pdf,png}`.
- Pilot data shows the one-search-thread arm saturating near 0.46–1.10K QPS at C=32,
  while automatic threads reach roughly 3.05–6.96K QPS depending on segment target.
  CPU-ms/query rises as the number of non-empty indexed segments rises, so latency and
  work efficiency are reported separately.

Both pilot summaries are complete, all expected build tags are present, control telemetry
passes and node diagnostics are clean. The full 500K/1M configuration uses the pilot-
informed finer ef grid; it still requires the normal smoke and full-stage submission gates.
