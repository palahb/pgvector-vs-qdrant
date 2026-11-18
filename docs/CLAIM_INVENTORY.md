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
| C06 | pgvector's 1024-d layout roughly doubles on-disk footprint | Abstract/Discussion; E1/E4 size fields | qualify | Explain TOAST/page byte budget, verify across scales and representation arms |
| C07 | Benchmark confounders reversed all three original laptop conclusions | Confounders/Discussion; E0 vs E1–E5 | qualify | Create explicit before/after table with identical metric definitions and provenance |
| C08 | Qdrant may report green while small segments remain unindexed because of indexing threshold | Confounders; E3 | retain | Confirm with collection telemetry and current Qdrant docs/version; state affected configurations |
| C09 | pgvector planner fallback can replace HNSW with an exact scan about 250× slower | Confounders/Discussion; observed E1 planner arm | rerun | E17 grid, minimum reproducer, upstream confirmation/issue; do not hide with forced index |
| C10 | Qdrant tolerates tighter memory limits / returns to in-memory speed at 4 GB | Abstract/Memory; E4 cap arm | rewritten from E10 | Full query set, 3 repetitions, cold and steady separated: Qdrant keeps in-memory latency down to 8 GB; at 4 GB (just below its data size) it settled in 2 of 3 repetitions; pgvector is at 636 ms per query at 8 GB; pgvector 4 GB arms did not finish in 3 h. The old 300-query claim is replaced, not retained. |
| C11 | The latency gap is robust across eight HNSW settings and dimensions 128–1024 | Abstract/Results; E2/E3 | rerun | E6 parallelism controls, E8 graph repetitions, E16 native second model |
| C12 | Both systems are CPU-bound under closed-loop load | Results/Discussion; E1 CPU and wait metrics | qualify | Repeat windows/builds, report server/client saturation and distinguish closed-loop scope |
| C13 | Qdrant indexing threshold explains the folklore 384-d anomaly/saw-tooth curve | Confounders/Dimensions; E3 default vs forced | qualify | Repeat graph builds and explicitly correlate indexed-vector/segment state with latency |
| C14 | The released artifact is fully reproducible with pinned containers and raw per-query data | Artifact statement; harness and archive | qualify | New schema/provenance fields, clean-environment reproduction, public immutable artifact and instructions |

## Claims forbidden until their gates pass

- Do not use “3–4× faster engine” before E6 and the CPU-efficiency analysis.
- Do not state build superiority before E9.
- Do not state memory-limit superiority from the existing E4 cap arm.
- Do not generalize truncation results to native embedding dimensions before E16.
- Do not claim RAG-workload coverage before E12–E14, or retitle if those experiments are
  explicitly removed with author approval.
