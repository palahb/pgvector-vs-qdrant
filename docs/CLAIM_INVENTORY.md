# Quantitative Claim Inventory

Status values:

- `retain`: supported as written after provenance/variance checks.
- `qualify`: evidence exists but wording or scope must narrow.
- `rerun`: new controlled evidence is required.
- `withdraw`: current evidence cannot support the claim.

No baseline claim below is considered final merely because the historical result audit
has zero schema errors; the audit identified missing commit/config/seed provenance and
the referee identified design confounders.

| ID | Current claim | Current location/evidence | Status | Required resolution |
|---|---|---|---|---|
| C01 | Qdrant's engine is 3.0–3.9× faster/lower latency at matched recall | Abstract, Discussion, Conclusion; E1 Table 4 | rerun | E6 controls segment and search parallelism; report latency and CPU-ms/query side by side; replace “engine faster” wording |
| C02 | Qdrant's end-to-end advantage shrinks to roughly 0.5–1.7× and pgvector can win against official REST | Abstract/Results; E1 protocol paths | qualify | Preserve exact client/protocol/version scope, repeat controlled builds, add CI |
| C03 | Qdrant plateau throughput is 19–68% higher and its overload tail is flatter | Abstract/Concurrency; E1 | rerun | Resolve Table 5/Figure 3 mismatch, E8 repetitions and E11 open-loop/core scaling |
| C04 | Tuned pgvector builds faster at 500K and 1M | Abstract/Build; E5 | rerun | E9 symmetric ingestion, deferred/parallel Qdrant, NVMe/tmpfs, WAL-separated phase times |
| C05 | Default/small shared_buffers increases pgvector engine time by about 2.7× without disk reads | Abstract/Memory; E4 buffer-pool arm | qualify | Repeat independent order/runs; retain only if buffer and OS-cache evidence reproduces |
| C06 | pgvector's 1024-d float32 layout needs about twice the bytes of Qdrant's storage | Section Memory Pressure; E5, E20 | rewritten from E20 | 1M, 3 builds: pgvector index 7.61 GiB (one element per 8 KiB page), table with TOAST 12.84 GiB; Qdrant float32 storage 3.94-5.24 GiB (varies between builds, cause not found). Index is 1.5-1.9x and whole table 2.4-3.3x Qdrant's storage. With halfvec: index 2.54 GiB (0.334x), table 5.20 GiB; index 0.48-0.65x and table 1.0-1.3x Qdrant float32. The 'twice' is a property of the 32-bit layout, not of pgvector at 1024 dimensions. Qdrant int8 does not shrink the storage directory (adds about 1 GB for the quantized copy). |
| C07 | Benchmark confounders reversed all three original laptop conclusions | Confounders/Discussion; E0 vs E1–E5 | qualify | Create explicit before/after table with identical metric definitions and provenance |
| C08 | Qdrant may report green while small segments remain unindexed because of indexing threshold | Confounders; E3 | retain | Confirm with collection telemetry and current Qdrant docs/version; state affected configurations |
| C09 | pgvector planner fallback can replace HNSW with an exact scan more than 200x slower | Confounders/Planner Exposure; E1 default-planner run; E17 | rewritten from E17 | Plan grid, 5 N x 4 dimensions x 18 ef = 360 cells: 9 (2.5%) choose a sequential scan, all at 768 and 1024 dimensions (9 of 180, 5.0%; 6 of 10 builds), none at 128 or 384. Narrow ef ranges that move with N. Latency of the scan plan measured only at 500K x 1024 (218x). Custom plans only; not reported upstream. |
| C10 | Qdrant tolerates tighter memory limits / returns to in-memory speed at 4 GB | Abstract/Memory; E4 cap arm | rewritten from E10 | Full query set, 3 repetitions, cold and steady separated: Qdrant keeps in-memory latency down to 8 GB; at 4 GB (just below its data size) it settled in 2 of 3 repetitions; pgvector is at 636 ms per query at 8 GB; pgvector 4 GB arms did not finish in 3 h. The old 300-query claim is replaced, not retained. |
| C11 | The latency gap is robust across eight HNSW settings and dimensions 128–1024 | Abstract/Results; E2/E3 | rerun | E6 parallelism controls, E8 graph repetitions, E16 native second model |
| C12 | Both systems are CPU-bound under closed-loop load | Results/Discussion; E1 CPU and wait metrics | qualify | Repeat windows/builds, report server/client saturation and distinguish closed-loop scope |
| C13 | Qdrant indexing threshold explains the folklore 384-d anomaly/saw-tooth curve | Confounders/Dimensions; E3 default vs forced | qualify | Repeat graph builds and explicitly correlate indexed-vector/segment state with latency |
| C14 | The released artifact is fully reproducible with pinned containers and raw per-query data | Artifact statement; harness and archive | qualify | New schema/provenance fields, clean-environment reproduction, public immutable artifact and instructions |
| C15 | Qdrant's latency gap is explained by intra-query parallelism rather than per-query work (new commitment) | Section Causal Decomposition; E19 (`data-manifests/e19_full_518a444.json`), E6 | retain, bounded | 1M, 3 builds each. pgvector needs 1.37x (1.31-1.52) the CPU of Qdrant with four segments and 1.75x (1.68-1.88) of one segment. It does not read more vectors (5.2K against 6.9K and 8.9K, estimated from cache misses and checked against pgvector's block counter, 1% apart) but spends 3342 cycles per read against 1410-1427: buffer manager 25%, unresolved postgres addresses 16% (largest next to buffer-table symbols), visited-set and heaps 6% of its cycles. Distance counts were not measured (no per-query counter, no root, no eBPF); proxies and upper bounds are stated. User-space only. |
| C16 | `halfvec` and `int8` change index size, latency and recall (new commitment) | Section Quantization; E20 (`data-manifests/e20_full_77f7567.json`) | retain | 3 builds each. halfvec: index 0.334x, build 0.59x (0.49-0.68), latency and CPU at matched recall 0.93x (0.73-1.13, no detectable change), recall unchanged, throughput 1.09-1.10x at the matched ef. int8: latency 0.63x (0.57-0.69), CPU 0.55x (0.48-0.62), throughput 1.67-1.92x at the matched ef, highest recall -0.0024 (-0.009 to 0.004), share of perfect queries -0.025. Reasons halfvec does not speed up search were not investigated. |
| C17 | A connection pooler (PgBouncer) changes pgvector concurrency behavior (new commitment) | none yet | rerun | E21 |
| C18 | Tail behavior under open-loop arrivals (new commitment) | none yet | rerun | E22, minimal; first to be cut when time is short |
| C19 | nDCG@10 can be reported with TREC DL qrels (the status mail said the qrels were at hand; this was not verified) | Section Ranking Quality; E23 (`data-manifests/e23_full_5276f14.json`), `docs/E23_GATE_RESULT.md` | rewritten from E23 | Qrels downloaded and read. The 1M corpus holds 0.72% of the judged-relevant documents (385 of 53,761); 63 of 214 judged queries have one. Rule fixed beforehand (`docs/E23_GATE.md`): sensitivity analysis only. Ratio of ANN to exact on the 63 queries, 3 builds each: at recall 0.95 pgvector keeps 97.9% of exact nDCG@10 (ef 512) and Qdrant 98.4% (ef 384), intervals of the difference contain zero. Not an absolute effectiveness number. v2 and v2.1 document ids are not comparable (byte offsets in different files); documents matched by url. |

## Claims forbidden until their gates pass

- Do not use “3–4× faster engine” before E6 and the CPU-efficiency analysis.
- Do not state build superiority before E9.
- Do not state memory-limit superiority from the existing E4 cap arm.
- Do not generalize truncation results to native embedding dimensions before E16.
- Do not claim RAG-workload coverage before E12–E14, or retitle if those experiments are
  explicitly removed with author approval.
- Do not present nDCG@10 as an absolute result before the qrels coverage of the 1M prefix is
  measured and found sufficient (E23 gate).
- Do not state a mechanism for the Qdrant latency gap as proven; E19 can only bound it.
- Do not state the distance count per query as measured; it is bounded by the block counter, the cache-miss proxy and the 248 ns kernel time (E19).
- Do not present nDCG@10, MRR@10 or Recall@10 of E23 as retrieval effectiveness; the corpus holds 0.72% of the judged-relevant documents (E23 gate).
