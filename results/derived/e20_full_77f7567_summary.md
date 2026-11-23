# E20 quantization

Verdict: **valid**; results: 12; issues: 0.

Mean ± standard deviation over independent builds. Latency and CPU are interpolated in recall to 0.95 for each build; recall is against exact float32 neighbors.

| Engine | Arm | Index/storage MB | Build s | ef@0.95 | Latency ms | Server CPU ms/q | Recall ceiling | share <0.8 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| pg | halfvec | 2727 | 160.3 ± 4.3 | 455 ± 36 | 6.280 ± 0.430 | 6.188 ± 0.429 | 0.9714 ± 0.0021 | 0.0600 ± 0.0057 |
| pg | vector | 8175 | 272.8 ± 14.6 | 439 ± 11 | 6.734 ± 0.148 | 6.637 ± 0.151 | 0.9722 ± 0.0005 | 0.0606 ± 0.0027 |
| qdrant | f32 | 5157 | 342.6 ± 53.8 | 338 ± 7 | 2.005 ± 0.022 | 4.494 ± 0.065 | 0.9754 ± 0.0006 | 0.0618 ± 0.0023 |
| qdrant | int8 | 6369 | 365.4 ± 39.0 | 339 ± 17 | 1.259 ± 0.038 | 2.467 ± 0.104 | 0.9730 ± 0.0030 | 0.0582 ± 0.0038 |

## Paired comparison with the float32 arm

| Engine | Arm | Metric | Kind | Mean | 95% CI |
|---|---|---|---|---:|---|
| pg | halfvec | build_total_s | ratio | 0.5887 | 0.493 to 0.684 |
| pg | halfvec | concurrency_matched_ef | ratio | 1.0000 | 1.000 to 1.000 |
| pg | halfvec | ef@0.9 | ratio | 1.0516 | 0.918 to 1.185 |
| pg | halfvec | ef@0.95 | ratio | 1.0360 | 0.789 to 1.283 |
| pg | halfvec | ef_at_target | ratio | 1.0000 | 1.000 to 1.000 |
| pg | halfvec | heap_bytes | ratio | 1.0000 | 1.000 to 1.000 |
| pg | halfvec | index_bytes | ratio | 0.3336 | 0.334 to 0.334 |
| pg | halfvec | mean | difference | -0.0001 | -0.008 to 0.008 |
| pg | halfvec | mean_ms@0.9 | ratio | 0.9776 | 0.904 to 1.052 |
| pg | halfvec | mean_ms@0.95 | ratio | 0.9335 | 0.733 to 1.134 |
| pg | halfvec | min | difference | 0.0000 | 0.000 to 0.000 |
| pg | halfvec | p01 | difference | 0.0000 | 0.000 to 0.000 |
| pg | halfvec | p05 | difference | 0.0000 | 0.000 to 0.000 |
| pg | halfvec | p50 | difference | 0.0000 | 0.000 to 0.000 |
| pg | halfvec | p99_ms@0.9 | ratio | 0.9653 | 0.913 to 1.018 |
| pg | halfvec | p99_ms@0.95 | ratio | 0.9330 | 0.767 to 1.099 |
| pg | halfvec | qps_c1_ef64 | ratio | 1.0164 | 0.964 to 1.069 |
| pg | halfvec | qps_c1_matched | ratio | 1.0964 | 1.055 to 1.138 |
| pg | halfvec | qps_c32_ef64 | ratio | 1.0396 | 1.000 to 1.079 |
| pg | halfvec | qps_c32_matched | ratio | 1.1025 | 1.072 to 1.133 |
| pg | halfvec | qps_c8_ef64 | ratio | 1.0224 | 0.974 to 1.070 |
| pg | halfvec | qps_c8_matched | ratio | 1.0877 | 1.058 to 1.118 |
| pg | halfvec | recall@ef128 | difference | -0.0012 | -0.008 to 0.006 |
| pg | halfvec | recall_at_concurrency_c1_matched | difference | 0.0009 | -0.007 to 0.009 |
| pg | halfvec | recall_at_concurrency_c32_matched | difference | -0.0001 | -0.006 to 0.006 |
| pg | halfvec | recall_at_concurrency_c8_matched | difference | -0.0002 | -0.007 to 0.007 |
| pg | halfvec | recall_ceiling | difference | -0.0009 | -0.007 to 0.005 |
| pg | halfvec | server_cpu_ms_per_query@0.9 | ratio | 0.9771 | 0.902 to 1.052 |
| pg | halfvec | server_cpu_ms_per_query@0.95 | ratio | 0.9333 | 0.729 to 1.137 |
| pg | halfvec | share_at_most_0_5 | difference | 0.0004 | -0.009 to 0.009 |
| pg | halfvec | share_below_0_8 | difference | -0.0006 | -0.014 to 0.012 |
| pg | halfvec | share_perfect | difference | -0.0032 | -0.032 to 0.026 |
| pg | halfvec | table_total_bytes | ratio | 0.4052 | 0.405 to 0.405 |
| pg | halfvec | toast_bytes | ratio | 0.5000 | 0.500 to 0.500 |
| qdrant | int8 | build_total_s | ratio | 1.0723 | 0.932 to 1.213 |
| qdrant | int8 | concurrency_matched_ef | ratio | 0.9444 | 0.705 to 1.183 |
| qdrant | int8 | ef@0.9 | ratio | 0.9921 | 0.823 to 1.161 |
| qdrant | int8 | ef@0.95 | ratio | 1.0062 | 0.837 to 1.176 |
| qdrant | int8 | ef_at_target | ratio | 0.9444 | 0.705 to 1.183 |
| qdrant | int8 | mean | difference | -0.0013 | -0.007 to 0.004 |
| qdrant | int8 | mean_ms@0.9 | ratio | 0.7053 | 0.671 to 0.739 |
| qdrant | int8 | mean_ms@0.95 | ratio | 0.6284 | 0.568 to 0.689 |
| qdrant | int8 | min | difference | 0.0000 | 0.000 to 0.000 |
| qdrant | int8 | p01 | difference | 0.0333 | -0.110 to 0.177 |
| qdrant | int8 | p05 | difference | 0.0000 | 0.000 to 0.000 |
| qdrant | int8 | p50 | difference | 0.0000 | 0.000 to 0.000 |
| qdrant | int8 | p99_ms@0.9 | ratio | 0.6424 | 0.564 to 0.721 |
| qdrant | int8 | p99_ms@0.95 | ratio | 0.5998 | 0.541 to 0.659 |
| qdrant | int8 | qps_c1_ef64 | ratio | 1.3300 | 1.319 to 1.341 |
| qdrant | int8 | qps_c1_matched | ratio | 1.6677 | 1.430 to 1.906 |
| qdrant | int8 | qps_c32_ef64 | ratio | 1.5856 | 1.576 to 1.595 |
| qdrant | int8 | qps_c32_matched | ratio | 1.9243 | 1.520 to 2.328 |
| qdrant | int8 | qps_c8_ef64 | ratio | 1.5267 | 1.514 to 1.540 |
| qdrant | int8 | qps_c8_matched | ratio | 1.9102 | 1.517 to 2.303 |
| qdrant | int8 | recall@ef128 | difference | -0.0009 | -0.011 to 0.010 |
| qdrant | int8 | recall_at_concurrency_c1_matched | difference | -0.0013 | -0.006 to 0.004 |
| qdrant | int8 | recall_at_concurrency_c32_matched | difference | -0.0014 | -0.007 to 0.004 |
| qdrant | int8 | recall_at_concurrency_c8_matched | difference | -0.0013 | -0.007 to 0.004 |
| qdrant | int8 | recall_ceiling | difference | -0.0024 | -0.009 to 0.004 |
| qdrant | int8 | server_cpu_ms_per_query@0.9 | ratio | 0.5718 | 0.515 to 0.628 |
| qdrant | int8 | server_cpu_ms_per_query@0.95 | ratio | 0.5493 | 0.477 to 0.621 |
| qdrant | int8 | share_at_most_0_5 | difference | -0.0026 | -0.008 to 0.003 |
| qdrant | int8 | share_below_0_8 | difference | -0.0036 | -0.017 to 0.010 |
| qdrant | int8 | share_perfect | difference | -0.0248 | -0.035 to -0.014 |
| qdrant | int8 | storage_bytes | ratio | 1.2678 | 0.401 to 2.135 |
