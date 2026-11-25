# E22 open-loop load

Verdict: **valid**; builds: {'pg': ['rep1', 'rep2', 'rep3'], 'qdrant': ['rep1', 'rep2', 'rep3']}.

Mean ± sd over builds; mean and tail leave out the first 5 s of each window. A level is steady if the queries finished inside the window are >= 98% of offered and the largest send lag is < 1 s; overload levels are shown for completeness and carry no tail claim.

| Engine | Load | Offered qps | Finished in window qps | steady builds | mean ms | p99 ms | p99.9 ms | max send lag ms | CPU ms/q |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pg | 0.50 | 500 ± 83 | 500 ± 83 | 3/3 | 8.6 ± 1.2 | 18.0 ± 2.6 | 26.0 ± 2.9 | 8 ± 14 | 8.37 ± 1.19 |
| pg | 0.80 | 799 ± 134 | 798 ± 135 | 0/3 | 38.2 ± 6.1 | 759.7 ± 232.0 | 1397.8 ± 129.5 | 1746 ± 323 | 8.40 ± 1.23 |
| pg | 0.95 | 949 ± 159 | 935 ± 158 | 0/3 | 1275.3 ± 55.5 | 5089.7 ± 397.4 | 6039.5 ± 474.3 | 6141 ± 361 | 8.64 ± 1.33 |
| pg | 1.10 | 1099 ± 184 | 930 ± 158 | 0/3 | 6490.2 ± 82.2 | 15144.4 ± 1405.0 | 16958.6 ± 1918.7 | 17192 ± 2049 | 8.63 ± 1.33 |
| qdrant | 0.50 | 786 ± 68 | 784 ± 68 | 3/3 | 3.0 ± 0.2 | 7.1 ± 0.6 | 10.8 ± 0.8 | 0 ± 0 | 5.04 ± 0.41 |
| qdrant | 0.80 | 1257 ± 108 | 1255 ± 107 | 3/3 | 5.5 ± 0.4 | 25.7 ± 1.8 | 37.9 ± 1.1 | 20 ± 2 | 5.12 ± 0.41 |
| qdrant | 0.95 | 1493 ± 128 | 1488 ± 128 | 3/3 | 8.2 ± 0.6 | 30.8 ± 3.1 | 45.3 ± 4.4 | 29 ± 12 | 5.08 ± 0.42 |
| qdrant | 1.10 | 1728 ± 149 | 1569 ± 136 | 0/3 | 3254.6 ± 34.9 | 5835.0 ± 59.1 | 5960.4 ± 37.5 | 6008 ± 18 | 5.08 ± 0.42 |

## Closed loop (32 clients) against open loop at 95% of capacity, same builds

| Engine | closed p99 ms | open p99 ms at 95% | ratio | builds steady at 95% |
|---|---:|---:|---:|---:|
| pg | 73.6 | n/a | n/a | 0 |
| qdrant | 22.3 | 30.8 | 1.38 | 3 |
