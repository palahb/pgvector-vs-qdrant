# E21 (PgBouncer) design, written before any measurement (24 November 2026)

Question (Discussion of the paper): is "use a connection pooler" good advice for pgvector under concurrent load?

## Feasibility (done)

The image `pgbouncer/pgbouncer` (the PgBouncer project's own repository on Docker Hub), version 1.25.1, was pulled by
digest `sha256:b718b48d66ddb3896da0a539c395cf7cf6da4587c733825d8983b66b27112a72` into
`$BENCH_ROOT/images/pgbouncer-1.25.1.sif` (sha256 of the SIF `8b00cbdebc07...`). It runs under Apptainer 1.3.3 on the login
node; the binary is `/opt/pgbouncer/pgbouncer` (PgBouncer 1.25.1, libevent 2.1.13, OpenSSL 3.5.8). Version 1.21 or later is
needed for protocol-level prepared statements in transaction mode, which the client uses.

## Two defects of the G1 hook, found while reading it before use

1. Transaction pooling does not keep session settings. The harness sets `hnsw.ef_search` and `enable_seqscan` with a
   session-level `SET`. Through a transaction pooler the next query may reach another server connection that has
   different values, so a measurement would silently use the wrong `ef`. In the pooled arms every query therefore runs in
   its own transaction that starts with `SET LOCAL hnsw.ef_search` (and `SET LOCAL enable_seqscan = off`).
2. The CPU of the pooler was taken from the pid of the process the harness started, which is the Apptainer wrapper; the
   pooler is its child. The pooler's pids are now the wrapper and its descendants.

## Arms (all on the same pgvector build, one build per job, three jobs)

| Arm | Connection | Per-query statements | What a comparison with the arm above it isolates |
|---|---|---|---|
| `direct` | straight to PostgreSQL | session `SET` once, then the query | (the baseline used everywhere else in the paper) |
| `direct_txn` | straight to PostgreSQL | `BEGIN; SET LOCAL ...; query; COMMIT` | the cost of the per-query transaction |
| `pooled` | through PgBouncer, transaction pooling, pool size 8 = server cores | same as `direct_txn` | the cost or gain of the pooler |

The pooler is pinned to the server's 8 cores, so its CPU competes with PostgreSQL and is counted in the server CPU per query.
Pool size 8 equals the cores; `max_client_conn` 200; `min_pool_size` 8 so server connections exist before the window.

## Measurement

1M x 1024, M=16, efc=64, three jobs (three builds). After the latency sweep (one client, ten `ef` values, one repetition;
it fixes the matched-recall `ef`, the smallest with recall >= 0.95) each arm runs closed-loop windows at 1, 8, 32 and 48
clients (30 s, 5 s warm-up) at the matched `ef` and at `ef=64`. The counts 32 and 48 are the ones where connections exceed
the 8 server cores.

## Checks that make a result usable (decided now)

* Recall in all three arms at the same `ef` must agree within 0.002. If a pooled arm differs, its `ef` did not take effect and
  that arm is invalid.
* A window counts only if every worker connected and received a reply.
* Report throughput, mean and p99 latency, server CPU per query (with the pooler's share), per arm, plus the paired ratios
  `direct_txn / direct` and `pooled / direct_txn` per build with the range over the three builds.

## Outcome rule

(a) measured: manifest, audit, analysis, paper text. (b) if the pooled arm cannot be made valid, the reason is written and the advice
to use a pooler is removed from the Discussion.
