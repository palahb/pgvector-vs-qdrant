# Response to Referee — Working Draft

Internal document. It becomes the point-by-point response after the author and the referee
have agreed on the scope. Do not send it externally in its current form. Every number below
is taken from a validated result set (strict audit, zero errors and warnings); the source
manifest is named next to each response. A comment marked **open** has no new evidence yet.

## Overall response

We thank the referee for identifying the distinction between single-query latency and CPU
efficiency, the uncontrolled segment parallelism, the asymmetric ingestion tuning and the
memory-study design. The revision is reorganized around quantified benchmark confounders
(Section 4, with a detection and avoidance checklist) instead of a "which system is faster"
ranking. The headline "Qdrant's engine is 3-4x faster" has been replaced by separate
latency and CPU-per-query results. Filtered, mixed read/write, hybrid, open-loop, quantization,
10M-scale and second-model work (M8, M9, M10 and the freshness items) is not part of this
revision; the proposed scope reduction (title and framing limited to unfiltered ANN search)
is subject to the author's and the referee's agreement.

## Major comments

### M1 — Latency versus CPU efficiency: addressed

- Evidence: E6 (`data-manifests/e6_full_9050d65.json`, 54 results, three builds per cell) and
  E8 (`data-manifests/e8_full_fe88da1.json`, 48 results).
- Qdrant was run with 1, 2, 4 and 8 target segments and with the search pool limited to one
  thread or left automatic. Server CPU milliseconds per query are reported next to latency
  at matched Recall@10 = 0.95.
- At 1M, pgvector: 7.63 ms latency, 7.53 ms CPU. Qdrant with one segment: 2.62 ms and
  4.32 ms (ratios 2.9x and 1.7x). Four segments (the default): 2.25 ms and 5.20 ms (3.4x and
  1.4x). Eight segments: 1.72 ms and 7.43 ms (4.4x and 1.0x). At 500K the eight-segment CPU
  ratio is 0.9x. Across the eight HNSW settings of E8 at 500K, latency is 2.4-3.2x lower and
  CPU 1.3-1.6x lower.
- This agrees with the referee's estimate from saturation throughput (1.2-1.7x) and shows
  that the latency ratio mostly measures intra-query parallelism.
- Manuscript: Abstract, new subsection "Latency Versus CPU Cost" (Table `tab:cpu`),
  HNSW Parameters (Table `tab:hnsw`), Discussion, Conclusion. The phrase "3-4x faster
  engine" now reads "lower single-client latency" and is paired with the CPU result.

### M2 — Segment count: addressed

- Evidence: E6, as above.
- The segment sweep is in Table `tab:cpu`. Setting `default_segment_number=1` yields two
  public segments (one non-empty indexed segment plus an empty appendable one); the
  requested target, the public count and the per-segment state are all recorded, and a run
  fails if any vector is unindexed.
- Not done: pgvector parallel index scans or partitioning to emulate segmentation. The
  asymmetry (one graph against several) is stated in the text.

### M3 — Asymmetric tuning: partly addressed

- Evidence: E9 (`data-manifests/e9_full_31de7f4.json`, 36 results, three interleaved builds
  per arm on one node).
- Qdrant ingestion was tuned with larger batches, parallel upload streams and deferred
  indexing. Total build time falls from 152 s to 99 s at 500K and from 356 s to 206 s at 1M.
  Ingestion and index-wait are reported separately.
- The build claim is withdrawn and rewritten: logged pgvector is 1.2x faster than Qdrant's
  baseline upload at 1M, but Qdrant with tuned ingestion is 1.4x faster than logged pgvector.
- Not done: pgvector search-side levers named by the referee (huge pages, halfvec storage,
  a connection pooler) were not measured.

### M4 — Rotational disk and WAL: partly addressed

- Evidence: E9.
- WAL, checkpoint and write volume are recorded per phase. At 1M the load writes 4.6 GB of
  WAL and the final checkpoint writes 13.9 GB in 80 s (about 175 MB/s, matching the measured
  167 MB/s of the disk). With an unlogged table the load takes 22 s instead of 93 s and
  scales linearly. The 1M load is therefore limited by logging to the spinning disk.
- Not done: builds on NVMe or tmpfs. Build times are labelled as specific to this disk.

### M5 — Memory working set: pending E10

- The superiority claim from the 300-query study is still in the draft (the Memory Pressure
  section and one Conclusion sentence, now marked as preliminary) and is withdrawn from the
  Abstract; it will be replaced, not kept, once E10 is final. The corrected study (E10) uses the full 1,677-query set in a random order
  per pass, separates the cold pass from steady-state passes, restarts every limit
  (including "none") from an evicted page cache, runs three repetitions with their own
  order seeds, and adds a pgvector arm with `shared_buffers` equal to a quarter of the limit.
- Status: the array is running. Early rows (not final) show that Qdrant's behaviour at the
  4 GB limit is borderline and varies between repetitions. pgvector's 4 GB arms did not
  finish within the 3 h job limit.
- Not done: NVMe.

### M6 — Internal inconsistencies: addressed

- Evidence: `docs/M6_THROUGHPUT_RECONCILIATION.md`, E8.
- The Table 5 and Figure 3 difference is not a transcription error: the E1 concurrency run
  used the matched-recall `ef=384` while the sparser E2 grid reached the target at
  `ef=512`, which has about 0.009 higher recall and 19-21% lower throughput for both engines.
- Every row of the new HNSW table is the mean of three independent builds, interpolated to
  the recall target. Build-to-build standard deviation of the interpolated latency is
  0.2-4.5% of the mean.
- The non-monotonic pgvector latency over graph density is not build-to-build noise
  (3.6 and 4.9 standard errors of the difference); it is systematic and its cause is open.

### M7 — Matched recall: partly addressed

- Evidence: E6 and E8 use per-build linear interpolation of latency and CPU in recall.
- Not done: interpolation of throughput (concurrency still runs at the first swept `ef`
  reaching the target), and per-query recall distributions (the baseline stores latency
  arrays only; new runs would have to store retrieved identifiers).

### M8 — Closed loop and eight cores: open

- No new evidence. Proposed as future work.

### M9 — RAG workload scope: open, scope reduction proposed

- No new evidence. The proposal is to limit the title and framing to unfiltered ANN search.
  nDCG@10 with the TREC qrels is possible but not done.

### M10 — Scale and model generality: partly addressed

- The Cohere embed-v3 statement was checked against documentation: v3 is not trained with a
  Matryoshka objective, so the manuscript now calls the dimensionality experiment "prefix
  truncation" and states that it does not transfer to native low-dimensional models.
- Not done: 10M scale and a second model.

### M11 — Engine-time boundaries: partly addressed

- Evidence: E1 server-side counters (single build per scale) and the E7 pilot.
- The manuscript compares engine-side times only at one client and uses server CPU time per
  query, measured from outside, for the efficiency comparison. User-space instruction and
  cycle counts per query are reported by client path.
- Not done: eBPF attribution (no privileges on the cluster); a real-data repetition of the
  perf measurement (the E7 pilot used synthetic data and only checks that counters work).

### M12 — Planner fallback exposure: open

- No new evidence. The default-planner grid and the upstream report are not done.

## Minor comments

1. TODOs and references: done. No `\todo` remains; Zhang et al. (the case study is PASE,
   not pgvector, and is described accordingly), Pan et al., VectorDBBench, the TRUBA
   acknowledgement and the Cohere statement were checked against primary sources.
2. Experiment map: done (Table `tab:expmap`, E1-E6, E8, E9).
3. Expanded confounder section: done as a table with measured effects plus a
   detection-and-avoidance checklist (`tab:checklist`).
4. Table splitting: done (mechanism/effect table and checklist table).
5. Dataset statistics: partly done (passage length 161.7 mean, 155 median words). Qrels
   coverage and ground-truth precision and tie handling are not done.
6. Qdrant response flags: partly done (`with_payload=False` is set in the query path;
   the manuscript statement and a `with_vectors` assertion are pending).
7. pgvector `hnsw.iterative_scan`, compile flags, ISA: partly done (the CPU supports AVX2
   and AVX-512 per the kernel probe); the setting and compile flags are not yet recorded.
8. Per-page byte budget of the index size: open.
9. Fixed-`ef` figure: open.
10. d=768 outlier: open (no repeated builds yet).
11. Wording: done for the three headline sentences; REST statement scoped to the official
    Python REST client.
12. Abstract: done (about 240 words, three findings).
13. Old-harness table: open.
