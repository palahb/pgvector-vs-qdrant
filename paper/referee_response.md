# Response to Referee — Working Skeleton

This internal document will become the point-by-point response after new evidence is
available. Do not send it externally in its current form.

## Overall response

We thank the referee for identifying the distinction between single-query latency and
CPU efficiency, the uncontrolled segment parallelism, and the scope gap between
unfiltered ANN and RAG workloads. The revision is being reorganized around quantified
benchmark confounders and a conditional system-selection model. Each response below
must cite a result/config ID, manuscript location and reproducible artifact before it is
marked complete.

## Major comments

### M1 — Latency versus CPU efficiency

- Response: pending E6/E7.
- Required evidence: Qdrant segment/thread controls, CPU-ms/query, CI.
- Manuscript changes: Abstract, Metrics, Results, Discussion, Conclusion.

### M2 — Segment count

- Response: pending E6.
- Required evidence: segment sweep and actual collection state.
- Manuscript changes: Configuration, Results, Threats to Validity.

### M3 — Asymmetric tuning

- Response: pending E9/E15.
- Required evidence: symmetric ingestion and search configuration matrix.
- Manuscript changes: Methodology, Build Results, Discussion.

### M4 — Rotational disk and WAL

- Response: pending E9.
- Required evidence: verified NVMe/tmpfs and WAL/checkpoint accounting.
- Manuscript changes: Environment, Build Results, Threats.

### M5 — Memory working set

- Response: the existing cap-arm conclusion is withdrawn pending E10.
- Required evidence: full/held-out queries, repetitions, cold vs steady state, NVMe.
- Manuscript changes: Abstract, Memory Results, Discussion, Conclusion.

### M6 — Internal inconsistencies

- Response: pending provenance trace and E8.
- Required evidence: source-file reconciliation and independent-build variance.
- Manuscript changes: affected tables/figures and provenance notes.

### M7 — Matched recall

- Response: pending E8.
- Required evidence: fine ef grid/interpolation for both latency and throughput plus
  per-query recall distributions.
- Manuscript changes: Measurement Protocol and matched-quality results.

### M8 — Closed loop and eight cores

- Response: pending E11.
- Required evidence: open-loop offered-load curves, core scaling, NUMA and PgBouncer.
- Manuscript changes: Methodology, Concurrency Results, Threats.

### M9 — RAG workload scope

- Response: pending E12–E14.
- Required evidence: filtered ANN, mixed writes/freshness, hybrid retrieval and qrels.
- Manuscript changes: title/scope, Methodology and new Results sections.

### M10 — Scale/model generality

- Response: pending E16.
- Required evidence: 10M and a native lower-dimensional second model/dataset.
- Manuscript changes: Dataset, Results, Threats.

### M11 — Engine-time boundaries

- Response: pending E7.
- Required evidence: precise span definitions and external CPU/perf attribution.
- Manuscript changes: Metrics, Telemetry, Results, Threats.

### M12 — Planner fallback exposure

- Response: pending E17 and author-approved upstream contact.
- Required evidence: default-plan grid, reproducer and upstream reference.
- Manuscript changes: Protocol, Confounders, Results, Discussion.

## Minor comments

1. TODO and reference verification — pending.
2. Experiment map — source map created; manuscript insertion pending.
3. Expand confounder section — pending.
4. Split/cross-reference confounder table — pending.
5. Dataset/qrels/ground-truth statistics — pending script and table.
6. Qdrant payload/vector response flags — pending code verification.
7. pgvector iterative scan, compile flags and ISA — pending probe/manifest.
8. HNSW page byte budget — pending calculation.
9. Fixed-ef figure/protocol consistency — pending figure revision.
10. d=768 outlier — pending E8 repetitions.
11. Wording corrections — pending claim rewrite.
12. Abstract shortening — final-writing phase.
13. Historical-vs-controlled numeric table — pending E0 provenance table.
