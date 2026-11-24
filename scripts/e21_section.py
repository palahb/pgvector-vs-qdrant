#!/usr/bin/env python3
"""Print the LaTeX of the "Connection Pooling" subsection from the E21 analysis JSON; no number is typed by hand.

usage: e21_section.py results/derived/e21_full_<commit>_analysis.json > subsection.tex
The template uses @NAME@ placeholders so that LaTeX braces and percent signs need no escaping.
"""
import json
import re
import sys

report = json.load(open(sys.argv[1]))
agg = {(a["mode"], a["ef_role"], a["clients"], a["metric"]): a["stats"] for a in report["aggregates"]}
cmp_ = {(c["baseline"], c["mode"], c["ef_role"], c["clients"], c["metric"]): c for c in report["comparisons"]}
matched_ef = next(a["ef"] for a in report["aggregates"] if a["ef_role"] == "matched")
fixed_ef = next(a["ef"] for a in report["aggregates"] if a["ef_role"] == "fixed")
builds = len(report["builds"])
pooler = report["pooler"]


def m(mode, role, c, metric):
    return agg[(mode, role, c, metric)]["mean"]


def ratio(base, mode, role, c, metric, d=2, interval=True):
    x = cmp_[(base, mode, role, c, metric)]
    s = x["stats"]
    text = f"{s['mean']:.{d}f}"
    if interval and s["ci95_low"] is not None:
        text += f" ({s['ci95_low']:.{d}f} to {s['ci95_high']:.{d}f})"
    return text


def rng(base, mode, role, c, metric, d=2):
    lo, hi = cmp_[(base, mode, role, c, metric)]["range"]
    return f"{lo:.{d}f} to {hi:.{d}f}"


V = {}
V["BUILDS"] = str(builds)
V["MATCHED"] = str(matched_ef)
V["FIXED"] = str(fixed_ef)
V["VERSION"] = pooler["version"].replace("PgBouncer ", "")
V["SIF"] = pooler["image_sha256"][:12]
rec = [m(mode, "matched", c, "recall_at_k") for mode in ("direct", "direct_txn", "pooled") for c in (1, 8, 32, 48)]
V["RECLO"], V["RECHI"] = f"{min(rec):.3f}", f"{max(rec):.3f}"

rows = []
for c in (1, 8, 32, 48):
    for mode, label in (("direct", "direct"), ("direct_txn", "transaction"), ("pooled", "PgBouncer")):
        rows.append(f"    {c if mode == 'direct' else ''} & {label} & {m(mode, 'matched', c, 'throughput_qps'):.0f} & "
                    f"{m(mode, 'matched', c, 'mean_ms'):.1f} & {m(mode, 'matched', c, 'p99_ms'):.1f} & "
                    f"{m(mode, 'matched', c, 'server_cpu_ms_per_query'):.2f} & {m(mode, 'matched', c, 'active_backends'):.1f} \\\\")
    if c != 48:
        rows.append("    \\addlinespace")
V["ROWS"] = "\n".join(rows)

for c in (1, 8, 32, 48):
    V[f"TPUT_PD_{c}"] = ratio("direct", "pooled", "matched", c, "throughput_qps")
    V[f"TPUT_TD_{c}"] = ratio("direct", "direct_txn", "matched", c, "throughput_qps")
    V[f"TPUT_PT_{c}"] = ratio("direct_txn", "pooled", "matched", c, "throughput_qps")
    V[f"MEAN_PD_{c}"] = ratio("direct", "pooled", "matched", c, "mean_ms")
    V[f"P99_PD_{c}"] = ratio("direct", "pooled", "matched", c, "p99_ms")
    V[f"P99_TD_{c}"] = ratio("direct", "direct_txn", "matched", c, "p99_ms")
    V[f"P99_PT_{c}"] = ratio("direct_txn", "pooled", "matched", c, "p99_ms")
    V[f"CPU_PD_{c}"] = ratio("direct", "pooled", "matched", c, "server_cpu_ms_per_query")
    V[f"P99ABS_D_{c}"] = f"{m('direct', 'matched', c, 'p99_ms'):.0f}"
    V[f"P99ABS_P_{c}"] = f"{m('pooled', 'matched', c, 'p99_ms'):.0f}"
    V[f"P99SD_D_{c}"] = f"{agg[('direct', 'matched', c, 'p99_ms')]['sd']:.0f}"
    V[f"POOLCORES_{c}"] = f"{m('pooled', 'matched', c, 'pooler_cores_busy'):.2f}"
    V[f"POOLMS_{c}"] = f"{m('pooled', 'matched', c, 'pooler_cpu_ms_per_query'):.3f}"
    V[f"POOLSHARE_{c}"] = f"{100 * m('pooled', 'matched', c, 'pooler_cpu_ms_per_query') / m('pooled', 'matched', c, 'server_cpu_ms_per_query'):.1f}"
    V[f"ACT_D_{c}"] = f"{m('direct', 'matched', c, 'active_backends'):.0f}"
    V[f"ACT_P_{c}"] = f"{m('pooled', 'matched', c, 'active_backends'):.1f}"
    V[f"LOCK_D_{c}"] = f"{100 * m('direct', 'matched', c, 'lockmanager_share'):.2f}"
    V[f"FIXED_TPUT_{c}"] = f"{cmp_[('direct', 'pooled', 'fixed', c, 'throughput_qps')]['stats']['mean']:.2f}"
    V[f"FIXED_RECALL_{c}"] = f"{m('direct', 'fixed', c, 'recall_at_k'):.2f}"
V["PLATEAU"] = f"{round(m('direct', 'matched', 32, 'throughput_qps'), -1):,.0f}".replace(",", "{,}")
V["CTX_D"] = f"{m('direct', 'matched', 48, 'ctx_voluntary_per_query'):.1f}"
V["CTX_T"] = f"{m('direct_txn', 'matched', 48, 'ctx_voluntary_per_query'):.1f}"
V["CTX_P"] = f"{m('pooled', 'matched', 48, 'ctx_voluntary_per_query'):.1f}"
V["FIXED_TPUT_LO"] = f"{min(float(V[f'FIXED_TPUT_{c}']) for c in (1, 8, 32, 48)):.2f}"
V["FIXED_TPUT_HI"] = f"{max(float(V[f'FIXED_TPUT_{c}']) for c in (1, 8, 32, 48)):.2f}"

TEMPLATE = r"""\subsection{Connection Pooling}
\label{sec:pooling}

A common recommendation for PostgreSQL with more clients than cores is to put a connection pooler in front of it. We tested
it for pgvector. The pooler is PgBouncer @VERSION@ from the project's container image, pulled by digest (the digest and the
image checksum are in the run record), in transaction pooling mode with a pool of 8 server connections, equal to the 8 cores of the server, and
pinned to those same cores, so that its CPU time competes with PostgreSQL's and is counted in the server CPU per query. The
index is the 1M $\times$ 1024 index of the other experiments, built @BUILDS@ times. Each build serves three connection modes one
after the other, so a comparison is within a build: \emph{direct}, the baseline of the rest of this paper (one session, settings
made once with \texttt{SET}); \emph{transaction}, where every query is a transaction of its own that starts with
\texttt{SET LOCAL hnsw.ef\_search} and \texttt{SET LOCAL enable\_seqscan}, without a pooler; and \emph{PgBouncer}, the same
transactions through the pooler. The transaction arm exists because a transaction pooler does not keep session settings: the
next statement may reach another server connection, and a session-level \texttt{SET} would silently run the query at the wrong
$ef$. It separates the cost of the per-query transaction from the cost of the pooler. We ran closed-loop windows of 30\,s with 1,
8, 32 and 48 clients at $ef=@MATCHED@$, the smallest swept value with Recall@10 of 0.95 on every build, and at $ef=@FIXED@$. Recall
in the three modes agrees ($@RECLO@$ to $@RECHI@$ at $ef=@MATCHED@$), which shows that the settings reached the queries.

\begin{table}[t]
  \caption{pgvector at $ef=@MATCHED@$ (Recall@10 about 0.95), 1M vectors, mean of @BUILDS@ builds. CPU is server CPU per query in ms,
  including the pooler. Active is the mean number of backends working at a sample of the wait-event sampler.}
  \label{tab:pooling}
  \small
  \begin{tabular}{@{}rlrrrrr@{}}
    \toprule
    clients & mode & qps & mean ms & p99 ms & CPU & active \\
    \midrule
@ROWS@
    \bottomrule
  \end{tabular}
\end{table}

\paragraph{With fewer clients than cores the pooler does not help.} With one client the throughput through the pooler is @TPUT_PD_1@
times the direct one, which is not distinguishable from 1, and with eight clients @TPUT_PD_8@ (ratios of the same build, mean of three, 95\,\% interval). The pooler
uses @POOLMS_8@\,ms of CPU per query at eight clients, @POOLSHARE_8@\,\% of the server CPU per query, and @POOLCORES_8@ of a core; at 32 and 48
clients it uses @POOLCORES_32@ and @POOLCORES_48@ of a core, so a single-threaded pooler is far from its own limit. The per-query
transaction accounts for part of the loss (throughput @TPUT_TD_1@ and @TPUT_TD_8@ of direct at one and eight clients).

\paragraph{With more clients than cores it cuts the tail, not the throughput.} At 32 and 48 clients, throughput through the pooler is
@TPUT_PD_32@ and @TPUT_PD_48@ times the direct one, so the plateau of about @PLATEAU@ queries per second is the server's and
hardly moves. Mean latency is @MEAN_PD_32@ and @MEAN_PD_48@ times the direct one, and p99 latency is @P99_PD_32@ and @P99_PD_48@
times, from @P99ABS_D_32@ to @P99ABS_P_32@\,ms at 32 clients and from @P99ABS_D_48@ to @P99ABS_P_48@\,ms at 48. The direct p99
at 48 clients is unstable across builds (standard deviation @P99SD_D_48@\,ms), which is why its interval is wide. Server CPU per query,
with the pooler's share included, is @CPU_PD_32@ and @CPU_PD_48@ times the direct one. The wait-event sampler shows what changes:
with direct connections @ACT_D_32@ and @ACT_D_48@ backends are active on average at 32 and 48 clients, with the
pooler @ACT_P_32@ and @ACT_P_48@. The lock manager takes @LOCK_D_32@\,\% and @LOCK_D_48@\,\% of the active-backend observations in the direct
runs and none behind the pooler, which is too little to explain the CPU difference; we did not isolate its cause. Voluntary context
switches per query rise from @CTX_D@ (direct) to @CTX_T@ (transaction) and @CTX_P@ (pooler) at 48 clients, so the pooler adds wake-ups
and does not save scheduler work.

\paragraph{Part of the tail effect is the per-query transaction.} Comparing the transaction arm with the direct one, p99 at 32 and
48 clients is @P99_TD_32@ and @P99_TD_48@ times the direct value; the pooler lowers it by a further @P99_PT_32@ and @P99_PT_48@
times, and throughput through the pooler is @TPUT_PT_32@ and @TPUT_PT_48@ times that of the transaction arm. The tail
improvement of the pooler alone is therefore smaller than the figures against direct connections suggest, and at 48 clients the
interval of the transaction arm is too wide to apportion it.

\paragraph{With short queries the overhead weighs more.} At $ef=@FIXED@$ (recall @FIXED_RECALL_1@), where a query is short, the throughput
through the pooler is @FIXED_TPUT_LO@ to @FIXED_TPUT_HI@ times the direct throughput across the four client counts: this
fits a fixed cost per query, from the extra statements and the extra hop, that weighs more when the query is short; we did not isolate it.

\paragraph{Reading.} For this workload, a pooler with a pool equal to the number of cores is a tail-latency control, not a
throughput gain. When clients outnumber cores it brings p99 latency to @P99_PD_32@ and @P99_PD_48@ times that of direct connections
at 32 and 48 clients (@P99_PT_32@ and @P99_PT_48@ times that of the same transactions without a pooler), costs about
@POOLMS_32@\,ms of CPU per query, and costs throughput when the system is not saturated or the queries are short. Using it also changes how the index must be configured, since
settings have to travel with each transaction. We did not test other pool sizes, session pooling, a pooler on separate cores
or a separate host (the pooler here is on the loopback interface and on the server's cores), open-loop load or other clients.
"""
text = TEMPLATE
for key, value in V.items():
    text = text.replace(f"@{key}@", value)
left = re.findall(r"@[A-Z0-9_]+@", text)
if left:
    raise SystemExit(f"unfilled placeholders: {sorted(set(left))}")
print(text)
