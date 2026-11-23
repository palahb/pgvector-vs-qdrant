#!/usr/bin/env python3
"""Print the LaTeX of the "Causal Decomposition" subsection from an E19 analysis JSON, so that
every number in it is computed from the analysis file and none is typed by hand.

usage: e19_section.py results/derived/e19_full_<commit>_analysis.json > subsection.tex
"""
import json
import sys

path = sys.argv[1]
report = json.load(open(path))
agg = {(a["engine"], a["arm"], a["metric"]): a["stats"] for a in report["aggregates"]}
cmp_ = {(c["arm"], c["metric"]): c for c in report["comparisons"]}


def mean(engine, arm, metric):
    return agg[(engine, arm, metric)]["mean"]


def sd(engine, arm, metric):
    return agg[(engine, arm, metric)]["sd"]


PG, AUTO, SEG1 = ("pg", "pg"), ("qdrant", "auto"), ("qdrant", "seg1")
M = 1e6


def ratio(arm, metric):
    c = cmp_[(arm, metric)]
    return c["ratio_of_means"], c["pairwise_min"], c["pairwise_max"]


def rr(arm, metric, digits=2):
    r, lo, hi = ratio(arm, metric)
    return f"{r:.{digits}f} ({lo:.{digits}f} to {hi:.{digits}f})"


def cyc(arm, cat):
    return mean(*arm, f"cycles_{cat}") / M


def pct(arm, cat):
    return 100 * mean(*arm, f"share_{cat}")


pg_touch = cyc(PG, "distance") + cyc(PG, "graph_and_element_access")
seg_touch = cyc(SEG1, "distance") + cyc(SEG1, "graph_and_element_access")
auto_touch = cyc(AUTO, "distance") + cyc(AUTO, "graph_and_element_access")
pg_rest = mean(*PG, "cycles") / M - pg_touch
seg_rest = mean(*SEG1, "cycles") / M - seg_touch
builds = {(c["engine"], c["arm"]): len(c["builds"]) for c in report["cells"]}


def row(label, arm, ef=True):
    cells = [label, f"{mean(*arm, 'ef'):.0f}", f"{mean(*arm, 'server_cpu_ms_per_query'):.2f}",
             f"{mean(*arm, 'cycles') / M:.1f}", f"{mean(*arm, 'ipc'):.2f}",
             f"{mean(*arm, 'vector_reads_proxy') / 1000:.1f}", f"{mean(*arm, 'cycles_per_vector_read'):.0f}"]
    cells += [f"{cyc(arm, c):.1f}" for c in ("distance", "graph_and_element_access", "queues_and_visited", "buffer_manager")]
    cells += [f"{(cyc(arm, 'unresolved') + cyc(arm, 'other') + cyc(arm, 'request_path')):.1f}"]
    return " & ".join(cells) + " \\\\"


print(r"""\subsection{Causal Decomposition}
\label{sec:causal}

Section~\ref{sec:cpu} shows that pgvector needs more CPU per query than Qdrant, and that Qdrant's
latency lead comes mostly from searching its segments in parallel. This section asks where a query's
CPU goes. One client queries 1M vectors of 1024 dimensions at the matched-recall $ef$ of each build (the
smallest swept $ef$ that reaches Recall@10 of 0.95). We built pgvector, Qdrant with its automatic segments
(four) and Qdrant with one segment, %d, %d and %d times. Timing uses repetitions one and two of the sweep; repetition
zero ran under \texttt{perf record} (user-space cycles of the server processes), and a separate
30\,s window gives user-space hardware counters per query. The profiles resolve function names only
after unpacking the images and pointing \texttt{perf report} at them, which we did for both. We sort the
functions into categories by name: the distance function, graph search with element loading, queues and
visited sets, the buffer manager (hash lookup, pinning, locks), and the rest. Inlining moves work between
categories, so a share is the share of samples whose top frame is in the category.
""" % (builds[PG], builds[AUTO], builds[SEG1]))

print(r"""\begin{table*}[t]
  \caption{CPU per query at matched recall 0.95, one client, 1M vectors, mean of the builds.
  Cycles are user-space; the category columns are millions of cycles per query (profile share times
  cycles). Vector reads are cache misses per query divided by the 64 cache lines of a vector, a proxy
  checked against pgvector's block counter (%.0f blocks per query). The last column sums the request path,
  the unresolved addresses and the rest.}
  \label{tab:causal}
  \small
  \begin{tabular}{@{}lrrrrrrrrrrr@{}}
    \toprule
    & & CPU & Mcyc. & & reads & cyc. per & \multicolumn{5}{c}{Mcycles per query in} \\
    arm & $ef$ & ms & per q. & IPC & $\times10^3$ & read & distance & elements & queues & buffers & other \\
    \midrule""" % mean(*PG, "blocks_per_query"))
print("    " + row("pgvector", PG))
print("    " + row("Qdrant, 4 segments", AUTO))
print("    " + row("Qdrant, 1 segment", SEG1))
print(r"""    \bottomrule
  \end{tabular}
\end{table*}
""")

r_auto, lo_a, hi_a = ratio("auto", "server_cpu_ms_per_query")
r_seg, lo_s, hi_s = ratio("seg1", "server_cpu_ms_per_query")
reads_pg = mean(*PG, "vector_reads_proxy")
print(r"""\paragraph{The gap is per-read cost, not the number of distances.}
pgvector uses %s times the CPU time per query of Qdrant with its automatic segments and %s times that of Qdrant with one
segment (ratio of means, with the range over all build pairs). It does not read more vectors. The vectors read per query,
estimated from cache misses, are %.1f thousand for pgvector (its block counter says %.1f thousand, so the proxy
is within %.0f\%%), %.1f thousand for Qdrant with one segment and %.1f thousand for four segments, so Qdrant reads %.2f and %.2f
times as many vectors. The cost per read reverses the order. pgvector spends %.0f cycles per vector read, Qdrant %.0f
and %.0f, a factor of %.1f (the range over build pairs is %.1f to %.1f). The CPU gap is the product of a smaller number of
reads and a larger cost per read, not of the distance work.""" % (
    rr("auto", "server_cpu_ms_per_query"), rr("seg1", "server_cpu_ms_per_query"),
    reads_pg / 1000, mean(*PG, "blocks_per_query") / 1000,
    100 * abs(reads_pg / mean(*PG, "blocks_per_query") - 1),
    mean(*SEG1, "vector_reads_proxy") / 1000, mean(*AUTO, "vector_reads_proxy") / 1000,
    mean(*SEG1, "vector_reads_proxy") / reads_pg, mean(*AUTO, "vector_reads_proxy") / reads_pg,
    mean(*PG, "cycles_per_vector_read"), mean(*AUTO, "cycles_per_vector_read"), mean(*SEG1, "cycles_per_vector_read"),
    mean(*PG, "cycles_per_vector_read") / mean(*SEG1, "cycles_per_vector_read"),
    *(lambda r: (r[1], r[2]))(ratio("seg1", "cycles_per_vector_read"))))
print()
print(r"""\paragraph{Where pgvector's cycles go.} The distance function and the loading of elements together take
%.1f million cycles per query in pgvector and %.1f million in Qdrant with one segment, which is the same work
(Qdrant's distance function takes %.0f\%% of its cycles because its memory waits are counted there, pgvector's
fall in the element loader). The difference is everything around it: %.1f million cycles
in pgvector, %.0f\%% of its total, against %.1f million in Qdrant. In pgvector the buffer manager takes %.0f\%% of the cycles
(mostly \texttt{hash\_search\_with\_hash\_value}, the buffer-mapping lookup, and lightweight locks), the
visited-set hash and the candidate heaps %.0f\%%, and a further %.0f\%% of the samples fall on addresses of the stripped
\texttt{postgres} binary that have no name. The largest of these lie next to buffer-table symbols
(\texttt{BufTableDelete}, \texttt{LockBufHdr}), so we read them as more buffer-manager work, but we did not attribute them.
Qdrant has no counterpart: its request path, scheduling and result merging take %.0f\%% of its cycles.
pgvector retires %.2f instructions per cycle against %.2f for Qdrant, which fits Qdrant's cycles being dominated by waiting
for vector data, and pgvector's by instructions around the data. The functions that carry the distance samples are
\texttt{VectorInnerProduct.fma} in pgvector and \texttt{dot\_similarity\_avx} in Qdrant, so both run AVX/FMA code, although
the processors also support AVX-512.""" % (
    pg_touch, seg_touch, pct(SEG1, "distance"), pg_rest, 100 * pg_rest / (mean(*PG, "cycles") / M), seg_rest,
    pct(PG, "buffer_manager"), pct(PG, "queues_and_visited"), pct(PG, "unresolved"),
    pct(SEG1, "request_path"), mean(*PG, "ipc"), mean(*SEG1, "ipc")))
print()
print(r"""\paragraph{What was not measured.} Neither engine reports how many distances a query computes, and
the nodes allow neither root nor eBPF, so the distance count is a proxy. Two upper bounds are consistent for pgvector. The time in distance
functions, divided by the 248\,ns of the fastest kernel in our pinned-core probe (E7), allows at most %.1f thousand distances per query;
the block counter gives %.1f thousand. For Qdrant the same time bound gives at most %.1f thousand (one segment) and %.1f thousand
(four segments), and the cache-miss proxy %.1f and %.1f thousand. User-space cycles only are profiled, so time in the kernel
(page-cache and system calls) is outside the table. Qdrant's matched $ef$ differs between builds (the grid is coarse), which moves
its means by up to the spread shown in the analysis file.
""" % (mean(*PG, "distances_upper_avx512") / 1000, mean(*PG, "blocks_per_query") / 1000,
       mean(*SEG1, "distances_upper_avx512") / 1000, mean(*AUTO, "distances_upper_avx512") / 1000,
       mean(*SEG1, "vector_reads_proxy") / 1000, mean(*AUTO, "vector_reads_proxy") / 1000))
