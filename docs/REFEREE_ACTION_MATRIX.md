# Referee Action Matrix

Source: referee report dated 4 November 2026. This is the execution checklist; the
response letter must cite the eventual evidence, not merely this plan.

## Major comments

| ID | Priority | Type | Affected manuscript area | Required work and acceptance gate | Experiment/plan | State |
|---|---:|---|---|---|---|---|
| M1 | 1 | experiment + analysis + writing | Abstract; Metrics; Latency; Concurrency; Discussion; Conclusion | Report matched-recall CPU-ms/query as primary beside latency; Qdrant 1 segment and 1 search-thread arms; ≥3 repetitions/CI; headline distinguishes parallel latency from efficiency | E6/E7; phases 5–6 | open |
| M2 | 1 | experiment + discussion | Configuration; Latency; Threats | Sweep Qdrant segments 1/2/4/8, record actual segments/indexed vectors and work; discuss pgvector one-graph asymmetry and partitioning boundary | E6; phase 5 | open |
| M3 | 2 | experiment + writing | Configuration; Build; Discussion | Symmetric tuning matrix; Qdrant parallel upload, batch and deferred indexing; separate ingestion/index phases; measure relevant pg search/build levers and label defaults vs tuned | E9/E15; phases 8/15 | open |
| M4 | 2 | experiment | Environment; Build; Threats | Repeat build arms on verified NVMe/tmpfs; logged/unlogged pg arms; record WAL/checkpoints/storage; no headline from rotational-disk-only result | E9; phase 8 | open |
| M5 | 1 | experiment + analysis | Memory Pressure; Abstract; Discussion; Conclusion | Full or held-out queries disjoint from warm-up; ≥3 runs; randomized/counterbalanced order; cold and steady-state separated; NVMe; equal memory accounting; remove current superiority claim | E10; phase 9 | open |
| M6 | 1 | provenance + experiment | HNSW Table; Concurrency Figure/Table | Resolve 500K throughput mismatch by tracing exact files/config/node/build/ef; ≥3 independent builds; every table row carries source IDs; CI/variance reported | E8; phases 3/7 | open |
| M7 | 1 | experiment + statistics | Matched-recall protocol; Latency; Concurrency | Fine ef near targets or model/interpolate both latency and throughput; compare equal recall; report per-query recall distribution and uncertainty | E8; phase 7 | open |
| M8 | 2 | experiment | Methodology; Concurrency; Threats | Open-loop Poisson offered loads; p99/p99.9 vs offered load; 8/16/28/56 cores with NUMA; PgBouncer arm; repeated windows/CI | E11; phase 10 | open |
| M9 | 1 | scope + experiment + writing | Title; Introduction; Methodology; Results | Complete filtered, mixed read/write/freshness, hybrid and qrels/nDCG experiments; otherwise title/scope reduction requires author approval | E12–E14; phases 11–14 | open |
| M10 | 2 | experiment + literature | Dataset; Dimensions; Threats | At least 10M; resource record; verify Cohere training claim; native lower-dimensional second model/dataset; no generality claim from truncation alone | E16; phase 16 | open |
| M11 | 1 | measurement definition + experiment | Metrics; Engine-side telemetry; Threats | Precisely define both self-reported spans; external on-CPU/perf attribution; avoid treating spans as identical; reconcile with CPU-ms/query | E7; phase 6 | open |
| M12 | 2 | experiment + upstream | Protocol; Confounders; Discussion | Default-planner N×ef×dimension exposure matrix; predicted/actual cost; minimum reproducer; upstream issue/response citation after user approval | E17; phase 17 | open |

## Minor comments

| ID | Type | Required action | Acceptance gate | State |
|---|---|---|---|---|
| m1 | writing/reference | Remove all unresolved `\todo{}` markers, including related-work verification, dataset stats, build I/O, counters, variance, acknowledgment and bibliography | Release-mode LaTeX fails on zero TODOs; source/reference checks recorded | open |
| m2 | presentation | Define E0–E17 early in Methodology | Experiment-map table agrees with `docs/EXPERIMENT_MAP.md` | planned |
| m3 | structure | Expand Measurement Confounders into mechanism/detection/mitigation subsections | Every confounder has evidence and actionable mitigation | open |
| m4 | presentation | Split dense confounder table or separate mechanism/effect; add result cross-references | Readable rendered table and valid references | open |
| m5 | data/quality | Add passage length, qrels coverage, exact-ground-truth precision and tie handling | Values generated from versioned data-analysis script | open |
| m6 | implementation/writing | Verify and state Qdrant `with_payload=false`, `with_vectors=false` | Code test/inspection plus manuscript statement | open |
| m7 | environment | Record pgvector iterative-scan setting, compile flags and ISA/SIMD availability for both engines | Result manifest/probe output and manuscript table | open |
| m8 | causal analysis | Explain M-independent index size with per-page byte budget and measured sizes | Calculation and engine-format citation/verification | open |
| m9 | figure/protocol | Show fixed-ef=64 curves or remove that protocol arm from claims | Figure/protocol are consistent | open |
| m10 | anomaly | Repeat pgvector d=768 builds and discuss recall drop | ≥3 builds and anomaly decision logged | open |
| m11 | wording | Replace broad speed claims; scope REST statement to official Python REST client | Claim-lint/search finds no forbidden wording | open |
| m12 | writing | Shorten abstract to surviving 3–4 findings | Final abstract meets target journal guidance | open |
| m13 | provenance/presentation | Publish old-harness vs controlled-harness numeric table | Same definitions and traceable E0/current sources | open |

## Reviewer priority order mapped to execution

1. E6 segment/thread and CPU efficiency.
2. E7 causal decomposition.
3. E10 corrected memory study.
4. E8 inconsistency, build variance and matched recall.
5. E9 symmetric build/ingestion.
6. E15 quantization and PostgreSQL-native alternatives.
7. E12–E14 RAG workloads and retrieval quality.
8. E16 10M and second model.
9. E11 open-loop and core scaling.
10. E17 planner exposure and upstream report.

The paper will be reframed around quantified benchmark confounders and a conditional
decision model. This framing does not waive any experiment above.
