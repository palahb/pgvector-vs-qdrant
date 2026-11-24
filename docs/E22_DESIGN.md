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
