# E22 (minimal open-loop) design, written before any measurement (24 November 2026)

Question: the paper's concurrency results are closed loop (a fixed number of clients, each sends its next query when the
last one returns), so a slow server slows the load down and the tail looks better than under real traffic. What do the two
engines do when queries arrive at a fixed rate whatever the server does?

## Method

Arrivals are a Poisson process (`bench/features.py: poisson_arrivals`, tests in `tests/test_g1_features.py`), served by a pool
of client processes; latency is measured from the **planned** send time, so a server that falls behind shows up as queueing
delay instead of being hidden (`open_loop_summary`). The pool is 64 processes, which bounds the queries in flight at 64
(PostgreSQL has `max_connections` 300; Qdrant uses one gRPC channel per worker). Because every worker handles its own
slice of the arrivals in order, a saturated server makes the send lag grow, which is recorded.

## Load levels (decided now)

Capacity of a build is its closed-loop throughput at 32 clients at the matched-recall `ef` (the smallest swept `ef` with recall
>= 0.95), measured in the same job before the open-loop windows. The offered rates are 50%, 80%, 95% and 110% of that
capacity, rounded to whole queries per second, 60 s each, after a 2 s start-up where the connections are made and the
first query is sent. 110% is above the measured plateau by construction.

## Start-up and CPU accounting (added after the pilot, before any full measurement)

The pilot (100K) showed a start-up transient for pgvector only: in the first seconds of a window the p99 was about ten times
that of the rest (95 ms against 7 ms at 50% load), which is the first queries of 64 new backends. Two measures: every worker
runs 20 untimed queries on its connection before the window (harness), and the tail statistics leave out the first 5 s of the
planned arrivals (analysis; `p99_ms_all` keeps the whole window). The pilot also showed an impossible server CPU per query for
pgvector: the backends exit when the client workers exit, and the CPU time of an exited process is not visible. The workers now
stay connected until the parent has read the CPU time.

## What the first full run showed, and the second protocol (written 25 November 2026, before the second run)

The first full run (job 7060149, commit `6e94ecd`, 60 s windows, first 5 s left out) is kept as **run 1**
(`results/derived/e22_run1_6e94ecd_*`). Its pgvector rows are not usable as steady-state results: at 80% of the closed-loop
capacity the latency over time was a start-up backlog followed by a flat 9 ms median (median latency 210 ms in the first seconds and
9 ms after the tenth second, in build 1), and a 5 s trim does not cover it. At 50% load, where the backlog drains within a second, the
tail is flat. Qdrant has no such effect. In 200 ms bins the pgvector latency is above 100 ms from the first bin, so the server falls behind
at the start, not later.

Our reading, not verified directly: connections that are new to the experiment start with backends whose page tables
have not yet mapped the shared buffers they will touch (the hot index is about 8 GB and a query touches about 5,000 blocks, so a
backend needs a few hundred queries to map most of it), which makes the first seconds slow at any load that leaves little spare capacity. The
closed-loop windows of the other experiments do not show it because their backends have been alive for a long time. A deployment with
long-lived connections would not see it either. What can be checked in the second run: the latency over time during the ramp.

**Run 2** keeps the harness and the load levels (50, 80, 95, 110% of the closed-loop capacity of the same build) and changes only two
parameters: the window is 90 s long and the first 30 s of planned arrivals, at the same rate, are a ramp that is left out of every
statistic. The steady rule no longer uses the largest send lag (which the ramp inflates). A level is **steady** if (a) at least 98% of the
queries planned in the measured part finished by the end of the window, and (b) the median latency in the last quarter of the measured
part is at most 2 times the median in its first quarter plus 10 ms, that is, latency is not growing. Otherwise it is **overload**: its
tail is shown but is not a claim. Run 2 uses the same code commit as run 1 (the smoke and the pilot of that commit stand); the
configuration differs only in `open_loop_duration`, 90 instead of 60.

## Interpretation rules (decided now)

* A level is **steady** if the rate of queries finished inside the window is at least 98% of the offered rate and the largest send lag is below 1 s. (Counting every completion over the window would equal the offered rate even for a server that is behind, because all queries finish eventually; the smoke test showed this. The wording was sharpened before any E22 measurement; the thresholds are unchanged.) For steady
  levels p99 and p99.9 describe the system at that load.
* A level that is not steady is **overload**. Its latency depends on the length of the window (the queue grows as long as the
  overload lasts), so no p99 is claimed from it; the achieved rate and the growth of the lag are reported.
* The comparison with the closed loop is made on the same build: the closed-loop p99 at 32 clients against the open-loop p99 at
  95% of capacity.
* Recall must agree between the closed-loop window and each open-loop window within 0.01 (the same ef reached the queries).

## Scope

1M x 1024, M=16, efc=64, pgvector (direct connection, session settings) and Qdrant (four segments, lean gRPC), three builds
per engine, one job per engine and build; client on the cores of the other socket as in the other experiments. One matched-recall
`ef` per build. No filters, no mixed writes, no other core counts.

## Outcome rule

(a) measured: manifest, audit, analysis, paper subsection with the difference to the closed loop. (b) if time runs out, the cut is
recorded in `docs/` and the paper says that open-loop load was not measured.
