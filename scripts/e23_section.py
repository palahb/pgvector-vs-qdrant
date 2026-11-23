#!/usr/bin/env python3
"""Print the LaTeX of the "Ranking Quality" subsection from the E23 gate and analysis JSON files, so every
number in it is read from them.

usage: e23_section.py results/derived/e23_gate.json results/derived/e23_full_<commit>_analysis.json > subsection.tex
"""
import json
import sys

gate = json.load(open(sys.argv[1]))
report = json.load(open(sys.argv[2]))
total, years = gate["total"], gate["years"]
by = {(x["engine"], x["ef"]): x for x in report["by_ef"]}
matched = report["matched"]
ex = report["exact"]


def pct(x, d=1):
    return f"{100 * x:.{d}f}"


def ci(x, key):
    lo, hi = x[key]
    return f"{lo:+.3f} to {hi:+.3f}"


def row(label, x):
    return (f"    {label} & {x['ef']} & {x['ann_recall_all_queries']:.3f} & {x['ndcg']:.3f} & {x['ndcg_ratio']:.3f} & "
            f"{ci(x, 'ndcg_minus_exact_ci95')} & {x['mrr_ratio']:.3f} & {x['recall_ratio']:.3f} \\\\")


low = {e: by[(e, 64)] for e in ("pg", "qdrant") if (e, 64) in by}
print(r"""\subsection{Ranking Quality}
\label{sec:ranking}

Recall@10 counts the neighbors that exact search would return. It does not say whether the lost neighbors would have
mattered to a user. Relevance judgments exist for the TREC Deep Learning queries, so we asked how much ranking quality
approximate search loses. The question has a limit that decides what can be claimed. Our corpus is the first million
rows of the MS MARCO v2.1 segment stream, about 0.9\,\%% of the collection the judgments were made against. We fixed a
rule before looking (the repository file \texttt{docs/E23\_GATE.md}): absolute nDCG only if at least half of the
relevant documents are in the corpus, a sensitivity analysis if at least 50 queries still have one.

\paragraph{Coverage.} The judgments name v2 documents (2021 and 2022) or v2 passages (2023), while the stream
holds v2.1 segments, and the numbers inside the two kinds of identifier are byte offsets in different files (the second
document is 4806 in v2 and 4810 in v2.1). Comparing the identifiers, as we first did, finds no judged document
in the corpus; that zero is a failed match, not a coverage. We matched documents by URL instead: all %s documents of the corpus
have exactly one v2 document with the same URL. Of %s relevant documents (grade 2 or 3) of %d judged queries, %d are in
the corpus, a coverage of %s\,\%%, and %d queries (%d, %d and %d of the years 2021, 2022 and 2023) have at least one. The
coverage is far below one half and the query count is above 50, so the rule allows a sensitivity analysis only.
""" % (f"{gate['prefix_documents']:,}".replace(",", "{,}"), f"{total['r_total']:,}".replace(",", "{,}"), total["q_judged"],
       total["r_in"], pct(total["coverage"], 2), total["q_cov"], years["2021"]["q_cov"], years["2022"]["q_cov"],
       years["2023"]["q_cov"]))

print(r"""\paragraph{Setup.} We score those %d queries. A segment takes the grade of its document, nDCG@10 uses the grades
as gains, and the ideal ranking is the best ten segments the corpus holds, so a query is scored on what the corpus can
contain. MRR@10 and Recall@10 count grades 2 and 3 as relevant. The reference is the exact top ten of the same corpus.
For each engine we built the index %d times (1M vectors, 1024 dimensions, $M=16$, $ef_{construction}=64$) and kept the
returned identifiers at ten $ef$ values; the numbers are means over builds, and the intervals are bootstrap intervals over
queries. Table~\ref{tab:ranking} gives the exact result and each engine at $ef=64$ and at the smallest swept $ef$ whose
recall against the exact neighbors reaches 0.95.
""" % (report["queries"], min(report["builds"].values())))

print(r"""\begin{table}[t]
  \caption{Ranking quality of approximate search against exact search on the same 1M corpus (sensitivity analysis,
  %d queries with a relevant document in the corpus). Recall is against the exact neighbors over all 1{,}677 queries.
  Ratios are the engine's value divided by the exact value; the interval is for the mean per-query difference in nDCG@10.}
  \label{tab:ranking}
  \small
  \begin{tabular}{@{}lrrrrrrr@{}}
    \toprule
    & $ef$ & recall & nDCG@10 & ratio & difference to exact & MRR ratio & R@10 ratio \\
    \midrule
    exact & -- & 1.000 & %.3f & 1.000 & -- & 1.000 & 1.000 \\""" % (report["queries"], ex["ndcg"]))
for engine, label in (("pg", "pgvector"), ("qdrant", "Qdrant")):
    if engine in low:
        print(row(label, low[engine]))
    if engine in matched:
        print(row(label + ", matched", matched[engine]))
print(r"""    \bottomrule
  \end{tabular}
\end{table}
""")

mp, mq = matched.get("pg"), matched.get("qdrant")
print(r"""\paragraph{Result.} The exact top ten has nDCG@10 of %.3f (95\,\%% interval %.3f to %.3f over the queries), MRR@10 of %.3f and
Recall@10 of %.3f on this corpus; these are not effectiveness numbers, because %s\,\%% of the relevant documents are
outside it.""" % (ex["ndcg"], ex["ndcg_ci95"][0], ex["ndcg_ci95"][1], ex["mrr"], ex["recall"], pct(1 - total["coverage"])))
if mp and mq:
    print(r"""At the smallest swept $ef$ reaching a recall of 0.95 against the exact neighbors, pgvector (at $ef=%d$) keeps %s\,\%% of
the exact nDCG@10 and Qdrant (at $ef=%d$) %s\,\%%. The 95\,\%% intervals of the mean difference to exact search, %s and %s, both contain
zero, so at this recall neither engine is distinguishable from exact search on these queries. MRR@10 keeps %s\,\%% and
%s\,\%%, Recall@10 %s\,\%% and %s\,\%%.""" % (
        mp["ef"], pct(mp["ndcg_ratio"]), mq["ef"], pct(mq["ndcg_ratio"]), ci(mp, "ndcg_minus_exact_ci95"),
        ci(mq, "ndcg_minus_exact_ci95"), pct(mp["mrr_ratio"]), pct(mq["mrr_ratio"]), pct(mp["recall_ratio"]),
        pct(mq["recall_ratio"])))
print()
points = report["by_ef"]
above = sum(1 for x in points if x["ndcg_ratio"] > x["ann_recall_judged_queries"])
low32 = [by[(e, 32)] for e in ("pg", "qdrant") if (e, 32) in by]
excl = sum(1 for x in points if x["ndcg_minus_exact_ci95"][1] < 0)
print(r"""\paragraph{Relation to recall.} Over the %d swept points the nDCG@10 ratio is higher than the recall of the same %d queries in %d of them (the
table's recall column is over all 1{,}677 queries and is lower). A missed neighbor therefore usually costs less ranking
quality than its share of the ten suggests. At $ef=32$, with recalls of %s, the engines keep %s of the exact nDCG@10 and the interval of the
difference excludes zero; across the grid the interval lies entirely below zero at %d of %d points, all at or below $ef=%d$.""" % (
    len(points), report["queries"], above, " and ".join(f"{x['ann_recall_all_queries']:.2f}" for x in low32),
    " and ".join(f"{pct(x['ndcg_ratio'], 0)}\\,\\%" for x in low32), excl, len(points),
    max([x["ef"] for x in points if x["ndcg_minus_exact_ci95"][1] < 0] or [0])))
print()
print(r"""\paragraph{What this does and does not show.} Only %d queries, uneven over the years, and a relevance
signal taken from documents and copied to their segments. The ratios describe how much ranking quality an approximation
at a given recall costs on a corpus that holds a small part of the relevant documents; they do not rank the two systems by
effectiveness, which would need a corpus that holds the judged documents. Extending to the full collection of 113 million
segments is outside this study.
""" % report["queries"])
