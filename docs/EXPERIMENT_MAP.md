# Experiment and Research-Question Map

This map gives every historical and planned experiment a stable identifier. An ID does
not imply that the experiment is complete or that its result is paper-ready.

## Research questions

| ID | Research question |
|---|---|
| RQ1 | Which benchmark-design choices can reverse or materially distort a pgvector–Qdrant comparison, and how can each confounder be detected? |
| RQ2 | At matched retrieval quality, how do single-query latency, CPU-ms/query and multi-core throughput differ after controlling Qdrant segment/search parallelism? |
| RQ3 | How do ingestion, index construction and durability costs compare under symmetric, production-relevant tuning and storage? |
| RQ4 | How do buffer management, page layout, cache state and memory limits affect steady-state and cold-start behavior? |
| RQ5 | How do the systems behave on filtered, hybrid and mixed read/write workloads that exercise their RAG-relevant features? |
| RQ6 | Do the conclusions generalize to 10M vectors, a native lower-dimensional embedding model, quantization and PostgreSQL-native alternatives? |
| RQ7 | Given quality, client stack, load, freshness and memory constraints, which configuration minimizes latency or CPU/cost per query? |

## Stable experiment IDs

| ID | State | Scope | Primary RQs | Referee items | Planned evidence |
|---|---|---|---|---|---|
| E0 | Historical | Original laptop/Docker course benchmark | RQ1 | Minor 13 | Preserved scripts, JSON and before/after confounder table |
| E1 | Baseline complete; audit gaps | 100K/500K/1M scale, protocol, recall/latency and closed-loop concurrency | RQ1, RQ2 | M1, M6, M7, M8, M11 | Existing 9 active results; reruns where build/variance controls require them |
| E2 | Baseline complete; audit gaps | Eight HNSW construction settings at 500K | RQ2 | M3, M6 | Existing 16 results plus independent-build repetitions |
| E3 | Baseline complete; audit gaps | Dimension 128–1024 and Qdrant indexing threshold | RQ1, RQ6 | M2, M6, M10, Minor 10 | Existing 24 results; repeat outliers and replace/augment truncation with native model |
| E4 | Baseline complete but method invalid for main claim | Buffer pool and cgroup memory limits at 1M | RQ4 | M5 | Existing 6 diagnostic results; corrected design is E10 |
| E5 | Baseline complete; storage-limited | Three interleaved builds per engine/scale and disk probe | RQ3 | M3, M4, M6 | Existing 18 results; fair tuned/NVMe build design is E9 |
| E6 | Planned | Qdrant segment count 1/2/4/8, search threads 1/default, CPU-ms/query | RQ2 | M1, M2 | Matched-recall latency, CPU time, distance work, segment state |
| E7 | Planned | Causal engine decomposition and microbenchmarks | RQ2 | M1, M11 | perf counters/profiles, IPC/cache misses, distance kernels, pg buffer/executor costs |
| E8 | Planned | Independent HNSW builds, fine ef grid and recall distributions | RQ2 | M6, M7 | At least three builds, confidence intervals, per-query recall and interpolated throughput |
| E9 | Planned | Symmetric ingestion/index construction on NVMe/tmpfs | RQ3 | M3, M4 | Qdrant parallel/deferred indexing arms, pg logged/unlogged arms, WAL and phase timing |
| E10 | Planned | Corrected memory and out-of-core experiment | RQ4 | M5 | Full/held-out queries, disjoint warm-up, repeated cold and steady state, equalized accounting, NVMe |
| E11 | Planned | Open-loop offered load and 8/16/28/56-core scaling | RQ2, RQ7 | M8 | p99/p99.9 versus offered load, CI, NUMA, PgBouncer arm |
| E12 | Planned | Filtered ANN selectivity sweep | RQ5 | M9 | 0.1–50% selectivity, iterative scan/payload index diagnostics, recall/latency |
| E13 | Planned | Mixed reads/inserts/updates/deletes and freshness | RQ5 | M9 | Throughput, tail latency, visibility/freshness lag and consistency behavior |
| E14 | Planned | Lexical+dense hybrid retrieval and TREC qrels | RQ5 | M9 | nDCG@10, MRR/Recall, fusion variants and system cost |
| E15 | Planned | Quantization and PostgreSQL-native alternatives | RQ6 | M3, freshness | pgvector halfvec/binary, Qdrant scalar/binary, pgvectorscale and VectorChord feasibility/results |
| E16 | Planned | 10M scale and native lower-dimensional second model/dataset | RQ6 | M10 | Resource-qualified 10M matrix; native 384/768-d model and quality controls |
| E17 | Planned | Default pgvector planner fallback exposure | RQ1 | M12 | N×ef×dimension plan grid, predicted/actual cost, minimum reproducer and upstream reference |

## Naming rules

- New result paths begin with the stable experiment ID, for example `e6_segments/...`.
- Every result records `schema_version`, `config_id`, `code_commit`, seed, Slurm job ID,
  node, image digest and complete engine settings.
- Pilot and smoke results are not silently promoted to paper evidence.
- A changed design receives a new config ID; raw output is never overwritten.
