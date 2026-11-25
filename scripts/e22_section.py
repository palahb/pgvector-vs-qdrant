#!/usr/bin/env python3
"""Print the LaTeX of the "Open-Loop Load" subsection from the E22 analysis JSON; no number is typed by hand.

usage: e22_section.py results/derived/e22_full_<commit>_analysis.json > subsection.tex
Placeholders @NAME@ avoid escaping LaTeX braces and percent signs.
"""
import json
import re
import sys

report = json.load(open(sys.argv[1]))
g = {(a["engine"], a["load_fraction"], a["metric"]): a for a in report["aggregates"]}
status = {(s["engine"], s["load_fraction"]): s for s in report["status"]}
cmp_ = {c["engine"]: c for c in report["closed_loop_comparison"]}
FR = (0.5, 0.8, 0.95, 1.1)


def m(e, f, metric):
    return g[(e, f, metric)]["stats"]["mean"]


def sd(e, f, metric):
    return g[(e, f, metric)]["stats"]["sd"]


V = {"BUILDS": str(len(report["builds"]["pg"])),
     "EF_PG": f"{m('pg', 0.5, 'ef'):.0f}",
     "EF_QD": f"{m('qdrant', 0.5, 'ef'):.0f}",
     "CAP_PG": f"{m('pg', 0.5, 'capacity_qps'):,.0f}".replace(",", "{,}"),
     "CAP_QD": f"{m('qdrant', 0.5, 'capacity_qps'):,.0f}".replace(",", "{,}")}

rows = []
for e, label in (("pg", "pgvector"), ("qdrant", "Qdrant")):
    for f in FR:
        s = status[(e, f)]
        tag = "yes" if s["settled_builds"] == s["builds"] else ("no" if f < 1.0 else "overload")
        done = 100 * m(e, f, "achieved_in_window_qps") / m(e, f, "offered_qps")
        if tag == "yes":
            tail = f"{m(e, f, 'mean_ms'):.1f} & {m(e, f, 'p99_ms'):.1f} & {m(e, f, 'p999_ms'):.1f}"
        else:
            tail = "\\multicolumn{3}{c}{not a steady state}"
        rows.append(f"    {label if f == 0.5 else ''} & {int(round(f * 100))}\\,\\% & {m(e, f, 'offered_qps'):.0f} & "
                    f"{done:.0f}\\,\\% & {tag} & {tail} \\\\")
    if e == "pg":
        rows.append("    \\addlinespace")
V["ROWS"] = "\n".join(rows)

pg80, qd80, qd95 = ("pg", 0.8), ("qdrant", 0.8), ("qdrant", 0.95)
V["P99_PG80"], V["P999_PG80"], V["MEAN_PG80"] = (f"{m('pg', 0.8, k):.1f}" for k in ("p99_ms", "p999_ms", "mean_ms"))
V["P99_QD80"], V["P999_QD80"], V["MEAN_QD80"] = (f"{m('qdrant', 0.8, k):.1f}" for k in ("p99_ms", "p999_ms", "mean_ms"))
V["P99_QD95"], V["P999_QD95"] = (f"{m('qdrant', 0.95, k):.1f}" for k in ("p99_ms", "p999_ms"))
V["P99_RATIO80"] = f"{m('pg', 0.8, 'p99_ms') / m('qdrant', 0.8, 'p99_ms'):.1f}"
V["P99_PG50"], V["P99_QD50"] = f"{m('pg', 0.5, 'p99_ms'):.1f}", f"{m('qdrant', 0.5, 'p99_ms'):.1f}"
V["OFF_PG80"], V["OFF_QD80"] = f"{m('pg', 0.8, 'offered_qps'):.0f}", f"{m('qdrant', 0.8, 'offered_qps'):.0f}"
V["CLOSED_PG"], V["CLOSED_QD"] = f"{cmp_['pg']['closed_p99_ms']:.1f}", f"{cmp_['qdrant']['closed_p99_ms']:.1f}"
V["RATIO_PG"] = f"{cmp_['pg']['ratio_open_to_closed']:.2f}"
V["RATIO_QD"] = f"{cmp_['qdrant']['ratio_open_to_closed']:.2f}"
assert cmp_["pg"]["highest_settled_fraction"] == 0.8 and cmp_["qdrant"]["highest_settled_fraction"] == 0.95
V["FIRST_PG95"], V["LAST_PG95"] = (f"{m('pg', 0.95, k):.0f}" for k in ("median_first_quarter_ms", "median_last_quarter_ms"))
V["MEAN_PG95"], V["P99_PG95"] = f"{m('pg', 0.95, 'mean_ms'):.0f}", f"{m('pg', 0.95, 'p99_ms') / 1000:.1f}"
V["MED_PG80"] = f"{m('pg', 0.8, 'median_last_quarter_ms'):.0f}"
V["DONE_PG110"] = f"{100 * m('pg', 1.1, 'achieved_in_window_qps') / m('pg', 1.1, 'offered_qps'):.0f}"
V["DONE_QD110"] = f"{100 * m('qdrant', 1.1, 'achieved_in_window_qps') / m('qdrant', 1.1, 'offered_qps'):.0f}"
V["LAST_PG110"] = f"{m('pg', 1.1, 'median_last_quarter_ms') / 1000:.1f}"
V["LAST_QD110"] = f"{m('qdrant', 1.1, 'median_last_quarter_ms') / 1000:.1f}"
V["FIRST_PG110"] = f"{m('pg', 1.1, 'median_first_quarter_ms') / 1000:.1f}"
V["FIRST_QD110"] = f"{m('qdrant', 1.1, 'median_first_quarter_ms') / 1000:.1f}"
V["CPU_PG"], V["CPU_QD"] = f"{m('pg', 0.8, 'server_cpu_ms_per_query'):.1f}", f"{m('qdrant', 0.8, 'server_cpu_ms_per_query'):.1f}"

TEMPLATE = r"""\subsection{Open-Loop Load}
\label{sec:openloop}

The concurrency results above are closed loop: a client sends its next query when the last one returns, so a server that slows
down also slows the load. Real traffic arrives whether or not the server keeps up. We therefore sent Poisson arrivals at fixed rates,
and measured latency from the planned send time, so that a server that falls behind shows its queue as latency. The load levels are
fractions of each build's own closed-loop throughput at 32 clients at its matched-recall $ef$ ($ef=@EF_PG@$ and a mean of $@EF_QD@$ for
pgvector and Qdrant; capacity @CAP_PG@ and @CAP_QD@ queries per second), so the two engines are compared at the same relative load and
not at the same absolute rate. A level is a window of 90\,s after the connections have been made and warmed up; the first 30\,s are a ramp at the
target rate and are left out of every statistic. @BUILDS@ builds per engine, 1M $\times$ 1024, 64 client processes (which bounds the
queries in flight at 64). A level is \emph{settled} if at least 98\,\% of the measured queries finish inside the window and the median
latency of the last quarter of the measured part is within a factor of two (plus 10\,ms) of that of the first quarter in both directions. The
rule, its history and the data it was fixed on are in \texttt{docs/E22\_DESIGN.md}; we state in the next paragraphs where it changed.

\begin{table}[t]
  \caption{Poisson arrivals at fractions of the closed-loop capacity of each build, mean of @BUILDS@ builds. Done is the
  share of the queries planned in the measured part that finished before the window ended. Latency is given only for settled levels.}
  \label{tab:openloop}
  \small
  \begin{tabular}{@{}llrrlrrr@{}}
    \toprule
    & load & qps & done & settled & mean ms & p99 ms & p99.9 ms \\
    \midrule
@ROWS@
    \bottomrule
  \end{tabular}
\end{table}

\paragraph{Where both systems are settled, pgvector's tail is wider.} At 50\,\% of capacity the p99 latency is @P99_PG50@\,ms for pgvector and
@P99_QD50@\,ms for Qdrant. At 80\,\% (@OFF_PG80@ and @OFF_QD80@ queries per second, so pgvector is at a lower absolute rate) it is @P99_PG80@
and @P99_QD80@\,ms, a factor of @P99_RATIO80@, and the p99.9 latency is @P999_PG80@ and @P999_QD80@\,ms. Server CPU per query is
@CPU_PG@ and @CPU_QD@\,ms at that load, the pattern of the closed-loop measurements (Section~\ref{sec:cpu}). Qdrant is still settled at
95\,\%, with a p99 of @P99_QD95@\,ms and a p99.9 of @P999_QD95@\,ms.

\paragraph{The closed loop shows a different tail.} The closed-loop p99 at 32 clients is @CLOSED_PG@\,ms for pgvector and @CLOSED_QD@\,ms for Qdrant. A closed loop bounds the
queue at the number of clients and an open loop does not. For Qdrant the open-loop p99 at the highest settled level, 95\,\%, is @RATIO_QD@ times the closed-loop value, so
although the closed loop keeps the server saturated, its tail is the smaller one. For pgvector the open-loop p99 at its highest settled level, 80\,\%, is
@RATIO_PG@ times the closed-loop value, which is not a contradiction: its 95\,\% level did not settle (next paragraph), so the highest level we can compare is a lighter one than for Qdrant.
The closed-loop tail of Section~\ref{sec:concurrency} should be read as that of a server held at saturation by a fixed number of clients, not as the tail at a given load.

\paragraph{pgvector did not settle at 95\,\%.} The first reading of the data labelled this level steady, because the rule then asked only that latency
not grow. The median latency in the first quarter of the measured part is @FIRST_PG95@\,ms and in the last quarter @LAST_PG95@\,ms:
a backlog that built up during the ramp was still draining throughout the window (mean @MEAN_PG95@\,ms, p99 @P99_PG95@\,s over the whole measured part).
With 5\,\% spare capacity a backlog of a second takes a long time to go. We therefore added the second direction to the rule (after seeing these
data, which is why it is described here) and do not give a tail for this level. What it does show is slow recovery: at 95\,\% load pgvector had not returned to the median latency of its 80\,\% level
(@MED_PG80@\,ms) by the end of the 90\,s window, while Qdrant's windows at the same relative load carried no backlog. The backlog builds in the first
seconds of a window (a first run with 60\,s windows and a 5\,s ramp showed it already at 80\,\%, and is kept as a record in the repository).
Our reading is that new PostgreSQL backends are slow for their first queries; we did not establish why, and a deployment with long-lived connections
may not see it, as the closed-loop windows of the other experiments, whose backends have been running for a long time, do not.

\paragraph{Beyond capacity.} At 110\,\% neither engine settles, as expected. Of the queries planned in the measured part, @DONE_PG110@\,\% (pgvector) and @DONE_QD110@\,\% (Qdrant)
finished before the window ended, and the median latency grows from @FIRST_PG110@\,s to @LAST_PG110@\,s and from @FIRST_QD110@\,s to @LAST_QD110@\,s over the
measured part. Those numbers depend on the length of the window and carry no tail claim.

\paragraph{Limits.} One $ef$ per build, one query mix, Poisson arrivals only, at most 64 queries in flight, a client on the other socket of the same node, 90\,s windows. The
engines ran on different nodes. We did not vary the number of cores, and we did not test long-lived connections that had been warmed for minutes before the window.
"""
text = TEMPLATE
for key, value in V.items():
    text = text.replace(f"@{key}@", value)
left = re.findall(r"@[A-Z0-9_]+@", text)
if left:
    raise SystemExit(f"unfilled placeholders: {sorted(set(left))}")
print(text)
