# E22 open-loop load

Verdict: **valid**; builds: {'pg': ['rep1', 'rep2', 'rep3'], 'qdrant': ['rep1', 'rep2', 'rep3']}.

Mean ± sd over builds; mean and tail leave out the first 30 s of each window (the ramp). A level is steady if >= 98% of the measured queries finished inside the window and latency is not growing; overload levels are shown for completeness and carry no tail claim.

| Engine | Load | Offered qps | Finished in window qps | steady builds | settled builds | mean ms | p99 ms | p99.9 ms | max send lag ms | CPU ms/q |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pg | 0.50 | 514 ± 6 | 513 ± 7 | 3/3 | 3/3 | 8.1 ± 0.1 | 16.2 ± 0.3 | 22.8 ± 1.0 | 0 ± 0 | 7.92 ± 0.10 |
| pg | 0.80 | 823 ± 10 | 820 ± 10 | 3/3 | 3/3 | 11.9 ± 0.2 | 54.5 ± 1.1 | 86.8 ± 0.4 | 1910 ± 152 | 7.95 ± 0.09 |
| pg | 0.95 | 977 ± 12 | 974 ± 13 | 3/3 | 0/3 | 573.9 ± 131.0 | 4019.5 ± 520.9 | 5593.3 ± 833.1 | 6118 ± 981 | 8.13 ± 0.09 |
| pg | 1.10 | 1131 ± 13 | 890 ± 11 | 0/3 | 0/3 | 10097.0 ± 57.2 | 19686.2 ± 900.0 | 21572.0 ± 415.4 | 22082 ± 477 | 8.15 ± 0.10 |
| qdrant | 0.50 | 783 ± 67 | 781 ± 66 | 3/3 | 3/3 | 3.0 ± 0.2 | 7.4 ± 0.6 | 11.2 ± 1.1 | 1 ± 0 | 5.05 ± 0.41 |
| qdrant | 0.80 | 1253 ± 107 | 1247 ± 109 | 3/3 | 3/3 | 5.5 ± 0.4 | 25.7 ± 1.4 | 36.1 ± 1.6 | 20 ± 3 | 5.13 ± 0.41 |
| qdrant | 0.95 | 1488 ± 127 | 1485 ± 127 | 3/3 | 3/3 | 8.6 ± 0.8 | 30.2 ± 3.5 | 45.3 ± 4.9 | 28 ± 5 | 5.09 ± 0.42 |
| qdrant | 1.10 | 1723 ± 148 | 1486 ± 127 | 0/3 | 0/3 | 5935.4 ± 20.4 | 8907.4 ± 67.0 | 9026.9 ± 84.1 | 9086 ± 99 | 5.10 ± 0.42 |

## Closed loop (32 clients) against the highest settled open-loop level, same builds

| Engine | closed p99 ms | highest settled load | open p99 ms | ratio |
|---|---:|---:|---:|---:|
| pg | 71.1 | 0.80 | 54.5 | 0.77 |
| qdrant | 22.4 | 0.95 | 30.2 | 1.35 |
