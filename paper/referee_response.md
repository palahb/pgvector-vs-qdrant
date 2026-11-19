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

### M5 — Memory working set: addressed, with one incomplete cell group

- Evidence: E10 (`data-manifests/e10_full_0b0b905.json`), 30 usable results (strict audit
  clean), 1M vectors, ef=128.
- Each system and limit (including "none") starts from a restarted server with an evicted
  page cache; one client runs three passes over all 1,677 queries, each in its own random
  order; the first pass is the cold start and the later passes are the steady state. Three
  repetitions with their own order seeds. pgvector also has an arm with `shared_buffers`
  equal to a quarter of the limit. Page faults, bytes read, resident memory and cgroup
  memory are recorded per pass.
- The referee's suspicion is confirmed. With the 300-query subset pgvector was back to
  3.6 ms at 8 GB; with the full query set it is at 636 ms (1,171 ms for the equalized arm).
  Qdrant stays at 1.2 ms down to 8 GB. At 4 GB, just below Qdrant's data size, Qdrant
  settled to 1.2-1.4 ms in two of three repetitions and was still at 35 ms in the third.
- The "Qdrant tolerates tighter limits" claim is replaced by these results in the Memory
  section, Discussion, Threats and Conclusion.
- Not done: NVMe. pgvector's 4 GB arms did not finish within the 3 h job limit (tasks 10
  and 11 killed; the other four 4 GB pgvector tasks were cancelled before they started), so
  that comparison is incomplete and is reported as such.

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

### M7 — Matched recall: mostly addressed

- Evidence: E6 and E8 (per-build linear interpolation of latency and CPU in recall) and E18
  (`data-manifests/e18_full_7d1b1c4.json`, per-query recall).
- Per-query recall distributions are now stored and reported (new subsection "Per-Query
  Recall"). At the smallest swept ef reaching a mean of 0.95, about 80% of queries return all
  ten neighbors; at 768 and 1024 dimensions about 6% of queries have a recall below 0.8 and
  about 2% find at most five neighbors, and the worst query finds none. The two engines have
  almost the same tails at each dimension, so matching on the mean does not hide a
  difference in the worst queries.
- Not done: interpolation of throughput (concurrency still runs at the first swept ef reaching
  the target).

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

### M12 — Planner fallback exposure: addressed, upstream report open

- Evidence: E17 (`data-manifests/e17_full_a5bb141.json`, 20 builds, 360 cells, strict audit
  clean) and the E1 default-planner run.
- The default planner's plan was recorded for every combination of 100K-1M vectors,
  128/384/768/1024 dimensions and 18 values of ef (16-1000), with the best index and scan
  plan costs. 9 of 360 cells (2.5%) use a sequential scan; all are at 768 or 1024 dimensions
  (9 of 180, 5.0%, in 6 of 10 builds) and none at 128 or 384. The affected ef values form
  narrow ranges that move with N (for example only ef=256 at 500K and only ef=512 at 1M, at
  1024 dimensions). The scan plan costs the same at 768 and 1024 dimensions because the heap
  holds only pointers, and 3.0-3.8x less than at 128 dimensions.
- The earlier "about 250x" wording is replaced by the like-for-like 218x measured at 500K,
  1024 dimensions, ef=256, and "more than 200x" in the abstract. The latency of the scan plan
  was not measured in the other eight affected cells.
- Not done: a minimal reproducer and the upstream report. Nothing has been sent to the
  pgvector maintainers; that needs the author's approval. The manuscript says so.

## Minor comments

1. TODOs and references: done. No `\todo` remains; Zhang et al. (the case study is PASE,
   not pgvector, and is described accordingly), Pan et al., VectorDBBench, the TRUBA
   acknowledgement and the Cohere statement were checked against primary sources.
2. Experiment map: done (Table `tab:expmap`, E1-E6, E8, E9).
3. Expanded confounder section: done as a table with measured effects plus a
   detection-and-avoidance checklist (`tab:checklist`).
4. Table splitting: done (mechanism/effect table and checklist table).
5. Dataset statistics: partly done. Passage length is in Table 1 (161.7 mean, 155 median
   words). The ground-truth method is now stated from the code: exact inner product over the
   whole corpus in float32 with batched matrix products, corpus norms 0.99994-1.00007, and no
   rule for ties at rank 10 (not counted, so a tied neighbor may count as a miss). Qrels
   coverage is not done: the TREC DL qrels are not in the repository.
6. Qdrant response flags: done in the text. All three Qdrant paths set the payload off
   explicitly; no path requests vectors (client default `False` checked in qdrant-client 1.19.1,
   and the raw gRPC request leaves the field unset). The server's response was not inspected,
   and the harness does not set `with_vectors=False` explicitly; doing so would be a code
   change with new gates.
7. pgvector `hnsw.iterative_scan`, compile flags, ISA: partly done. The scan settings are now
   recorded in every result (`iterative_scan` off, `max_scan_tuples` 20,000, `scan_mem_multiplier`
   1) and stated in the manuscript; the CPU supports AVX2 and AVX-512 (kernel probe). The
   compile flags and which instruction sets the binaries use were not recorded.
8. Per-page byte budget of the index size: done. The tuple layout was read from pgvector's
   `hnsw.h` (v0.8.0, tuple structs identical in v0.8.6): at 1024 dimensions an element tuple
   takes 4,176 bytes, so two do not fit on a page; level-0 neighbor tuples of 200, 392 and 776
   bytes (M=16, 32, 64) fit beside it. The same budget predicts the measured half page per vector
   at 768 dimensions (E17: 249,433 pages for 500K vectors).
9. Fixed-`ef` figure: open.
10. d=768 outlier: done (E18, three builds per dimension). The single-build drop to 0.871 shrinks
    to 0.877 +/- 0.001 over three builds, 0.008 below 640 dimensions and 0.002 below 896; pgvector's
    recall at ef=64 lies between 0.870 and 0.885 across all dimensions. A dip of about 0.008
    remains and its cause was not found.
11. Wording: done for the three headline sentences; REST statement scoped to the official
    Python REST client.
12. Abstract: done (about 240 words, three findings).
13. Old-harness table: done (Table `tab:laptop`): latency at four `ef` values, recall,
    build times at three scales, throughput and p99, each from the archived course result files
    next to the controlled-harness value. The "pgvector about three times faster" wording was
    corrected: in the archive the ratio is 3.7x at ef=16, 2.6x at 32, 2.2x at 64 and 1.6x at 128.
