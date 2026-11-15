# E6 — Qdrant segment and search-thread protocol

## Question

E6 separates Qdrant's intra-query parallelism from engine efficiency. The primary
comparison reports end-to-end latency and server CPU milliseconds per completed query at
matched recall. It does not interpret lower latency from additional parallel work as lower
computational cost.

## Controlled variables

- Qdrant target segment count: 1, 2, 4 and 8.
- Search pool: one thread and Qdrant automatic selection.
- Dataset sizes: 100K pilot, followed by 500K and 1M only after the pilot gate.
- Three independent clean builds per cell.
- HNSW baseline: `m=16`, `ef_construct=64`; fine search-ef grid around recall targets.
- Primary client: persistent lean gRPC, with payload and vectors disabled.
- Server allocation: eight isolated server cores; clients use a disjoint NUMA/core set.

`default_segment_number` is a target rather than an assumption. Every result records the
requested and actual segment counts, indexed/total vectors and collection configuration;
the run fails if the requested target is not reached or all vectors are not indexed.

The single-search-thread arm is applied at process startup through
`QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS=1`. Qdrant documents environment
variables as highest-precedence configuration and `storage.performance.max_search_threads`
as the parallel search pool size:

- https://qdrant.tech/documentation/operations/configuration/
- https://github.com/qdrant/qdrant/blob/master/config/config.yaml

## Gates

1. Unit tests must show the exact environment key and optimizer config emitted by the
   harness.
2. A real synthetic ARF smoke must pass for the exact commit.
3. The 100K pilot must have three valid builds per cell, exact segment targets, fully
   indexed vectors, no schema/provenance warnings and no node anomaly.
4. Only then may the 500K/1M full deployment be rendered and submitted.

The pgvector one-graph reference is a separate three-build deployment so it is not
needlessly rebuilt for every Qdrant segment/thread cell.
