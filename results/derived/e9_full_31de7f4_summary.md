# E9 ingestion and build fairness

Verdict: **valid**; results: 36; issues: 0.

Mean ± standard deviation over independent builds on the same node, seconds unless noted.

## N = 500000

### PostgreSQL / pgvector

| Arm | Load | CREATE INDEX | Load + index | Checkpoint | WAL MB (load / index) | Disk write MB | Req. checkpoints |
|---|---:|---:|---:|---:|---:|---:|---:|
| pg_logged | 32.4 ± 2.8 | 74.4 ± 5.6 | 106.8 ± 7.5 | 49.6 ± 7.4 | 2300 ± 0 / 2233 ± 0 | 6909 ± 0 | 1.0 ± 0.0 |
| pg_unlogged | 11.2 ± 0.0 | 50.5 ± 0.2 | 61.7 ± 0.2 | 17.8 ± 0.5 | 0 ± 0 / 0 ± 0 | 15 ± 0 | 1.0 ± 0.0 |

### Qdrant

| Arm | Upload | Index wait | Total |
|---|---:|---:|---:|
| q_base | 143.2 ± 18.0 | 8.7 ± 1.3 | 151.9 ± 19.1 |
| q_batch4096 | 120.7 ± 7.5 | 12.1 ± 0.8 | 132.8 ± 8.3 |
| q_par4 | 97.8 ± 8.7 | 16.9 ± 5.9 | 114.7 ± 2.9 |
| q_tuned | 62.6 ± 1.4 | 36.4 ± 0.8 | 99.0 ± 1.5 |

## N = 1000000

### PostgreSQL / pgvector

| Arm | Load | CREATE INDEX | Load + index | Checkpoint | WAL MB (load / index) | Disk write MB | Req. checkpoints |
|---|---:|---:|---:|---:|---:|---:|---:|
| pg_logged | 93.0 ± 11.2 | 202.7 ± 17.6 | 295.8 ± 28.6 | 79.7 ± 13.2 | 4600 ± 0 / 4467 ± 0 | 13894 ± 0 | 2.0 ± 0.0 |
| pg_unlogged | 22.2 ± 0.1 | 103.6 ± 0.5 | 125.9 ± 0.6 | 35.5 ± 10.1 | 0 ± 0 / 0 ± 0 | 46 ± 0 | 1.0 ± 0.0 |

### Qdrant

| Arm | Upload | Index wait | Total |
|---|---:|---:|---:|
| q_base | 339.0 ± 42.5 | 16.9 ± 5.1 | 355.9 ± 47.4 |
| q_batch4096 | 271.1 ± 22.6 | 17.3 ± 4.6 | 288.4 ± 27.0 |
| q_par4 | 229.5 ± 30.4 | 20.0 ± 2.2 | 249.5 ± 32.5 |
| q_tuned | 130.3 ± 2.2 | 75.6 ± 2.6 | 205.9 ± 4.4 |
