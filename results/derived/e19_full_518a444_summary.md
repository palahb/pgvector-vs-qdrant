# E19 causal decomposition

Verdict: **valid**; results: 9; issues: 0.

One client, 1M x 1024, matched-recall ef of each build. Mean ± standard deviation over builds. Cycles are user-space counters per query; category cycles = profile share x cycles.

| Engine | Arm | ef | CPU ms/q | Mcycles/q | Minstr/q | IPC | blocks/q | vector reads/q (proxy) | cycles per read |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pg | pg | 448 ± 0 | 6.54 ± 0.01 | 17.2 ± 0.2 | 11.5 ± 0.0 | 0.66 ± 0.01 | 5107 ± 8 | 5160 ± 17 | 3342 ± 27 |
| qdrant | auto | 363 ± 37 | 4.76 ± 0.39 | 12.5 ± 1.0 | 6.4 ± 0.5 | 0.51 ± 0.00 | n/a | 8889 ± 750 | 1410 ± 4 |
| qdrant | seg1 | 427 ± 37 | 3.75 ± 0.24 | 9.9 ± 0.7 | 5.1 ± 0.3 | 0.51 ± 0.00 | n/a | 6919 ± 441 | 1427 ± 6 |

## Mcycles per query by category

| Engine | Arm | distance | graph_and_element_access | queues_and_visited | buffer_manager | request_path | other | unresolved |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| pg | pg | 4.52 ± 0.24 | 4.34 ± 0.13 | 1.02 ± 0.03 | 4.37 ± 0.11 | 0.08 ± 0.01 | 0.19 ± 0.03 | 2.73 ± 0.10 |
| qdrant | auto | 9.64 ± 0.72 | 1.71 ± 0.23 | 0.31 ± 0.05 | 0.00 ± 0.00 | 0.33 ± 0.07 | 0.37 ± 0.02 | 0.16 ± 0.06 |
| qdrant | seg1 | 7.51 ± 0.51 | 1.41 ± 0.09 | 0.26 ± 0.03 | 0.00 ± 0.00 | 0.28 ± 0.03 | 0.27 ± 0.04 | 0.15 ± 0.04 |

## Distance work (upper bounds)

| Engine | Arm | distance ms/q | at most (AVX2 ns/dist) | at most (AVX-512 ns/dist) |
|---|---|---:|---:|---:|
| pg | pg | 1.712 ± 0.085 | 6068 ± 302 | 6900 ± 343 |
| qdrant | auto | 3.664 ± 0.270 | 12984 ± 956 | 14764 ± 1087 |
| qdrant | seg1 | 2.848 ± 0.182 | 10093 ± 643 | 11477 ± 731 |

## pgvector against Qdrant (ratio of means, range over all build pairs)

| Arm | Metric | Ratio | Min | Max |
|---|---|---:|---:|---:|
| auto | cache_misses_per_query | 0.581 | 0.551 | 0.645 |
| auto | cycles | 1.376 | 1.296 | 1.535 |
| auto | cycles_distance | 0.469 | 0.430 | 0.544 |
| auto | cycles_graph_and_element_access | 2.532 | 2.256 | 3.041 |
| auto | cycles_other | 0.525 | 0.409 | 0.611 |
| auto | cycles_per_vector_read | 2.371 | 2.343 | 2.393 |
| auto | cycles_queues_and_visited | 3.262 | 2.874 | 4.234 |
| auto | cycles_request_path | 0.229 | 0.186 | 0.332 |
| auto | cycles_unresolved | 17.050 | 11.850 | 26.705 |
| auto | distance_ms | 0.467 | 0.433 | 0.540 |
| auto | instructions | 1.792 | 1.706 | 1.984 |
| auto | ipc | 1.302 | 1.292 | 1.316 |
| auto | server_cpu_ms_per_query | 1.373 | 1.310 | 1.517 |
| auto | vector_reads_proxy | 0.581 | 0.551 | 0.645 |
| seg1 | cache_misses_per_query | 0.746 | 0.714 | 0.807 |
| seg1 | cycles | 1.746 | 1.659 | 1.910 |
| seg1 | cycles_distance | 0.601 | 0.554 | 0.692 |
| seg1 | cycles_graph_and_element_access | 3.085 | 2.851 | 3.396 |
| seg1 | cycles_other | 0.733 | 0.519 | 0.938 |
| seg1 | cycles_per_vector_read | 2.341 | 2.310 | 2.367 |
| seg1 | cycles_queues_and_visited | 3.904 | 3.444 | 4.708 |
| seg1 | cycles_request_path | 0.268 | 0.225 | 0.329 |
| seg1 | cycles_unresolved | 18.497 | 13.680 | 23.069 |
| seg1 | distance_ms | 0.601 | 0.562 | 0.686 |
| seg1 | instructions | 2.265 | 2.176 | 2.451 |
| seg1 | ipc | 1.297 | 1.283 | 1.315 |
| seg1 | server_cpu_ms_per_query | 1.746 | 1.678 | 1.885 |
| seg1 | vector_reads_proxy | 0.746 | 0.714 | 0.807 |
