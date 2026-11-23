# E23 (nDCG@10) gate: rule written before any coverage was measured

Written 23 November 2026, before the qrels were downloaded or the passage IDs were read.

## Why a gate

The benchmark corpus is the first 1,000,000 rows of the MS MARCO v2.1 segmented-passage stream
(Cohere embed-english-v3), not the whole collection of about 113 million segments. The TREC Deep
Learning judgments were made against the whole collection. The 1M prefix is one contiguous slice of
the stream and was not chosen for relevance. If most judged-relevant passages are outside it, an
nDCG@10 computed on it would measure how well the engines find the few relevant passages that happen
to be inside, and would say nothing about retrieval effectiveness. The gate decides what, if
anything, can honestly be reported.

## Quantities (all measured on the judged queries only, relevance grade 2 or 3 counts as relevant)

* `Q_judged`: queries that have judgments and whose embedding is in our 1,677-query set.
* `R_total`: judged-relevant passages of those queries, in the whole collection.
* `R_in`: those among them whose passage ID lies in the first 1M stream rows.
* `coverage = R_in / R_total`.
* `Q_cov`: judged queries with at least one relevant passage in the 1M prefix.

Passage IDs of the qrels are compared with the IDs of the stream rows as they are, by exact string
match. A qrels file whose IDs belong to a different segmentation (TREC DL 2021 and 2022 judged
MS MARCO v2 passages, the stream holds v2.1 segments) is only used if a document-level or text
mapping exists in files we can obtain; otherwise its queries are reported as not mappable and
counted neither in `R_in` nor in `R_total`.

## Decision rule

1. **Absolute nDCG.** If `coverage >= 0.50` and `Q_cov >= 50`: report nDCG@10, MRR@10 and
   Recall@10 as retrieval effectiveness of the benchmark corpus, for exact search and for each
   engine, with the ANN recall-to-nDCG relation.
2. **Sensitivity analysis only.** Otherwise, if `Q_cov >= 50`: report nDCG@10 only as the ratio of
   the ANN result to the exact (brute-force) result on the same 1M corpus and the same queries,
   labeled as a sensitivity analysis that says how much ranking quality ANN approximation costs.
   It is not an absolute effectiveness number and the text says so.
3. **Not measured.** Otherwise: nDCG is not reported. The measured coverage and this decision are
   written to the paper as the reason.

The thresholds are fixed here and are not changed after the measurement. 50 queries is the smallest
set for which we are willing to read a paired difference between two systems per query.
