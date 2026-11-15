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
