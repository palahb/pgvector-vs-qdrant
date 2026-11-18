# E10 memory limits

Verdict: **valid**; results read: 33; cells with data: 10; excluded: 3.

Mean ± standard deviation over repetitions of whole-query-set passes (1,677 queries, one client, ef=128, random order per pass). Cold is the first pass after a restart with an evicted page cache; steady is the last of the later passes.

| System | Limit | Cold mean ms | Cold wall s | Cold major faults | Steady mean ms | Steady p99 ms | Steady qps | Reps |
|---|---|---:|---:|---:|---:|---:|---:|---|
| pg_sb1G | none | 1131.9 ± 85.0 (n=3) | 1898 ± 142 (n=3) | 261678 ± 1 (n=3) | 6.56 ± 0.04 (n=3) | 13.15 ± 0.81 (n=3) | 152.3 ± 0.9 (n=3) | 1,2,3 |
| pg_sb1G | 16G | 1064.7 ± 49.4 (n=3) | 1786 ± 83 (n=3) | 261679 ± 1 (n=3) | 6.52 ± 0.09 (n=3) | 13.02 ± 0.40 (n=3) | 153.2 ± 2.2 (n=3) | 1,2,3 |
| pg_sb1G | 8G | 1245.9 ± 94.3 (n=3) | 2089 ± 158 (n=3) | 261680 ± 2 (n=3) | 635.62 ± 40.87 (n=3) | 1889.99 ± 71.13 (n=3) | 1.6 ± 0.1 (n=3) | 1,2,3 |
| pg_sbq | none | 971.5 ± 23.7 (n=3) | 1629 ± 40 (n=3) | 1659623 ± 2995 (n=3) | 2.29 ± 0.01 (n=3) | 3.96 ± 0.09 (n=3) | 435.3 ± 1.6 (n=3) | 1,2,3 |
| pg_sbq | 16G | 1050.6 ± 24.8 (n=3) | 1762 ± 42 (n=3) | 1048107 ± 2 (n=3) | 4.21 ± 0.08 (n=3) | 9.88 ± 0.56 (n=3) | 237.3 ± 4.3 (n=3) | 1,2,3 |
| pg_sbq | 8G | 1503.1 ± 106.7 (n=3) | 2521 ± 179 (n=3) | 523829 ± 1 (n=3) | 1171.08 ± 4.75 (n=3) | 2737.42 ± 20.69 (n=3) | 0.9 ± 0.0 (n=3) | 1,2,3 |
| qdrant_mmap | none | 610.8 ± 91.6 (n=3) | 1024 ± 154 (n=3) | 937049 ± 14273 (n=3) | 1.19 ± 0.04 (n=3) | 1.64 ± 0.02 (n=3) | 834.6 ± 26.2 (n=3) | 1,2,3 |
| qdrant_mmap | 16G | 655.9 ± 99.4 (n=3) | 1100 ± 167 (n=3) | 933957 ± 10339 (n=3) | 1.24 ± 0.00 (n=3) | 1.70 ± 0.02 (n=3) | 800.7 ± 2.3 (n=3) | 1,2,3 |
| qdrant_mmap | 8G | 570.5 ± 24.7 (n=3) | 957 ± 41 (n=3) | 929547 ± 4942 (n=3) | 1.22 ± 0.02 (n=3) | 1.68 ± 0.02 (n=3) | 815.0 ± 11.7 (n=3) | 1,2,3 |
| qdrant_mmap | 4G | 765.6 ± 61.4 (n=3) | 1284 ± 103 (n=3) | 933272 ± 8257 (n=3) | 12.39 ± 19.19 (n=3) | 113.75 ± 188.86 (n=3) | 518.0 ± 428.7 (n=3) | 1,2,3 |

## Cells with no completed repetition

These cells of the planned matrix have no usable result (time limit, failure or not run). They are absent from the table above, not zero.

- pg_sb1G at 4G
- pg_sbq at 4G

## Excluded results

These did not record a full set of passes (time limit or failure) and are not averaged in.

- pg_sb1G 4G rep1: status running, 0 passes recorded (E10_memory_limits-full-0b0b905c-0b300a95-t0010-a1-r00-pg)
- pg_sbq 4G rep1: status running, 0 passes recorded (E10_memory_limits-full-0b0b905c-0b300a95-t0011-a1-r00-pg)
- pg_sbq none rep2: status failed, 0 passes recorded (E10_memory_limits-full-0b0b905c-0b300a95-t0014-a1-r00-pg)
