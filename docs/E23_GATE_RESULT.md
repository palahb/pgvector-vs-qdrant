# E23 gate result (measured 23 November 2026, rule in `docs/E23_GATE.md`)

Data: `results/derived/e23_gate.json`. Computation: `analysis/e23_gate.py` (14 tests).

## What was read

* The ids and urls of the first 1,000,000 rows of the MS MARCO v2.1 stream (`bench/prepare_ids.py`,
  `bench/prepare_urls.py`). The first 2,000 rows were streamed again with their embeddings and are identical to
  `embeddings_1m.npy` (maximum absolute difference 0). The prefix holds 105,546 documents, all from document
  shard 00 (`msmarco_v2.1_doc_00_0` to `msmarco_v2.1_doc_00_877289672`), about 0.9% of the 11.96 million documents.
* TREC DL document qrels for 2021 (`2021.qrels.docs.final.txt`) and 2022 (`2022.qrels.docs.inferred.txt`, inferred
  by NIST from the passage judgments) and passage qrels for 2023 (`2023.qrels.pass.withDupes.txt`); there is no
  document qrels file for 2023. Hashes are in the data manifest of the experiment.

## The ids of v2 and v2.1 cannot be compared

The numbers in `msmarco_doc_00_N` (v2) and `msmarco_v2.1_doc_00_N` (v2.1) are byte offsets in different files:
the second document is 4806 in v2 and 4810 in v2.1. A first attempt that compared the ids as the rule says
found zero judged documents in the prefix. That zero is not a coverage, it is a failed id match, and it was
discarded. Documents are matched by url instead: the v2 collection shard 00 was read from the public tar
(`bench/map_v2_docs.py`, 200,000 documents), and all 105,546 prefix documents have exactly one v2 document with the
same url, none ambiguous. The passages of the 2023 judgments were linked to their documents with the first two
v2 passage shards (`bench/map_v2_passages.py`): shard 0 holds 2,000,000 passages, all of documents of shard 00;
shard 1 holds 15,119 such passages; shard 2 holds none, so no later shard can contribute.

## Measured quantities (relevance grade 2 or 3)

| Year | judged queries | relevant documents | in the 1M prefix | coverage | queries with at least one in the prefix |
|---|---:|---:|---:|---:|---:|
| 2021 | 56 | 4,025 | 49 | 1.22% | 25 |
| 2022 | 76 | 45,651 | 305 | 0.67% | 17 |
| 2023 | 82 | 4,085 | 31 | 0.76% | 21 |
| all | 214 | 53,761 | 385 | **0.72%** | **63** |

An earlier pass with only the two years that have document qrels gave 42 queries (below 50) before the 2023 judgments
could be linked to documents; the rule names no year, so the decision is taken on all three. The 2023 relevant
count is of documents of linked passages, an unlinked passage counts as a document of its own, which can only
overstate the total.

## Decision

`coverage = 0.72% < 0.50`, `Q_cov = 63 >= 50`: rule 2, **sensitivity analysis only**. nDCG@10 is reported as the ratio
of the ANN result to the exact result on the same 1M corpus and the 63 queries, and is not a statement about
retrieval effectiveness: 99.3% of the judged-relevant documents are outside the corpus.

## Choices of the sensitivity analysis (fixed before running it)

* A segment takes the grade its document has for the query (the judgments are per document or per passage, the
  corpus is segments). Several segments of one relevant document all count as relevant items.
* Gains are the grades (0 to 3), discount `1/log2(rank+1)`; the ideal ranking is the best ten items available in the
  corpus, so a query is only scored on what the corpus can contain.
* MRR@10 and Recall@10 count grade 2 or 3 as relevant; Recall@10 divides by min(10, relevant segments available).
* The exact result is the brute-force top 10 of the benchmark itself (the cached ground truth).
* 63 queries is small and uneven (25 / 17 / 21). Differences between systems are reported with intervals over queries.
