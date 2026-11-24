# E21 PgBouncer

Verdict: **valid**; builds: ['rep1', 'rep2', 'rep3']; pooler: {'image': '/arf/scratch/endemir/rag_bench/images/pgbouncer-1.25.1.sif', 'image_sha256': '8b00cbdebc078eaa2b216f5791263743f4e5009149863b49681d48d22d8582bb', 'pool_mode': 'transaction', 'pool_size': 8, 'max_client_conn': 200, 'pinned_cores': [0, 1, 2, 3, 4, 5, 6, 7], 'version': 'PgBouncer 1.25.1'}.

Mean ± sd over builds, at the matched-recall ef.

| Clients | Mode | qps | mean ms | p99 ms | server CPU ms/q | recall | pooler cores | pooler ms/q |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | direct | 151 ± 2 | 6.60 ± 0.09 | 10.08 ± 0.18 | 6.53 ± 0.09 | 0.952 ± 0.001 | n/a | n/a |
| 1 | direct_txn | 145 ± 2 | 6.87 ± 0.08 | 10.35 ± 0.12 | 6.66 ± 0.08 | 0.952 ± 0.001 | n/a | n/a |
| 1 | pooled | 147 ± 1 | 6.80 ± 0.05 | 10.30 ± 0.01 | 6.58 ± 0.05 | 0.952 ± 0.001 | 0.01 ± 0.00 | 0.078 ± 0.003 |
| 8 | direct | 1125 ± 10 | 7.11 ± 0.06 | 10.89 ± 0.15 | 7.00 ± 0.06 | 0.951 ± 0.001 | n/a | n/a |
| 8 | direct_txn | 1092 ± 10 | 7.32 ± 0.06 | 11.12 ± 0.15 | 7.07 ± 0.07 | 0.951 ± 0.001 | n/a | n/a |
| 8 | pooled | 1065 ± 14 | 7.50 ± 0.10 | 12.30 ± 0.67 | 7.09 ± 0.05 | 0.951 ± 0.001 | 0.09 ± 0.00 | 0.088 ± 0.001 |
| 32 | direct | 1052 ± 9 | 30.39 ± 0.27 | 76.39 ± 3.98 | 7.56 ± 0.07 | 0.951 ± 0.001 | n/a | n/a |
| 32 | direct_txn | 1038 ± 9 | 30.82 ± 0.27 | 52.78 ± 0.27 | 7.65 ± 0.07 | 0.951 ± 0.001 | n/a | n/a |
| 32 | pooled | 1058 ± 23 | 30.23 ± 0.65 | 36.67 ± 1.45 | 7.09 ± 0.06 | 0.951 ± 0.001 | 0.10 ± 0.00 | 0.091 ± 0.001 |
| 48 | direct | 1014 ± 15 | 47.30 ± 0.72 | 130.98 ± 39.81 | 7.85 ± 0.12 | 0.951 ± 0.001 | n/a | n/a |
| 48 | direct_txn | 998 ± 7 | 48.09 ± 0.35 | 99.17 ± 9.36 | 7.96 ± 0.06 | 0.951 ± 0.001 | n/a | n/a |
| 48 | pooled | 1059 ± 10 | 45.31 ± 0.44 | 52.00 ± 0.66 | 7.09 ± 0.06 | 0.951 ± 0.001 | 0.10 ± 0.00 | 0.092 ± 0.000 |

## Paired ratios per build (matched ef)

| Clients | Comparison | Metric | Ratio | 95% CI | range |
|---:|---|---|---:|---|---|
| 1 | direct_txn / direct | mean_ms | 1.041 | 1.019 to 1.063 | 1.033 to 1.051 |
| 1 | direct_txn / direct | p99_ms | 1.027 | 1.001 to 1.052 | 1.017 to 1.038 |
| 1 | direct_txn / direct | server_cpu_ms_per_query | 1.019 | 0.995 to 1.042 | 1.010 to 1.028 |
| 1 | direct_txn / direct | throughput_qps | 0.961 | 0.940 to 0.981 | 0.951 to 0.968 |
| 8 | direct_txn / direct | mean_ms | 1.030 | 1.028 to 1.032 | 1.029 to 1.031 |
| 8 | direct_txn / direct | p99_ms | 1.021 | 1.020 to 1.022 | 1.021 to 1.021 |
| 8 | direct_txn / direct | server_cpu_ms_per_query | 1.009 | 1.006 to 1.012 | 1.008 to 1.010 |
| 8 | direct_txn / direct | throughput_qps | 0.971 | 0.969 to 0.973 | 0.970 to 0.972 |
| 32 | direct_txn / direct | mean_ms | 1.014 | 1.012 to 1.016 | 1.014 to 1.015 |
| 32 | direct_txn / direct | p99_ms | 0.692 | 0.598 to 0.787 | 0.659 to 0.734 |
| 32 | direct_txn / direct | server_cpu_ms_per_query | 1.011 | 1.009 to 1.013 | 1.010 to 1.012 |
| 32 | direct_txn / direct | throughput_qps | 0.986 | 0.984 to 0.988 | 0.985 to 0.987 |
| 48 | direct_txn / direct | mean_ms | 1.017 | 0.983 to 1.051 | 1.008 to 1.033 |
| 48 | direct_txn / direct | p99_ms | 0.816 | 0.053 to 1.580 | 0.533 to 1.143 |
| 48 | direct_txn / direct | server_cpu_ms_per_query | 1.013 | 0.980 to 1.047 | 1.005 to 1.029 |
| 48 | direct_txn / direct | throughput_qps | 0.984 | 0.952 to 1.017 | 0.969 to 0.992 |
| 1 | pooled / direct_txn | mean_ms | 0.990 | 0.960 to 1.020 | 0.978 to 1.002 |
| 1 | pooled / direct_txn | p99_ms | 0.995 | 0.967 to 1.024 | 0.983 to 1.006 |
| 1 | pooled / direct_txn | server_cpu_ms_per_query | 0.989 | 0.958 to 1.021 | 0.976 to 1.001 |
| 1 | pooled / direct_txn | throughput_qps | 1.010 | 0.979 to 1.040 | 0.998 to 1.023 |
| 8 | pooled / direct_txn | mean_ms | 1.025 | 1.006 to 1.044 | 1.017 to 1.031 |
| 8 | pooled / direct_txn | p99_ms | 1.107 | 0.957 to 1.257 | 1.037 to 1.145 |
| 8 | pooled / direct_txn | server_cpu_ms_per_query | 1.003 | 0.997 to 1.008 | 1.001 to 1.005 |
| 8 | pooled / direct_txn | throughput_qps | 0.976 | 0.958 to 0.993 | 0.970 to 0.984 |
| 32 | pooled / direct_txn | mean_ms | 0.981 | 0.945 to 1.016 | 0.969 to 0.997 |
| 32 | pooled / direct_txn | p99_ms | 0.695 | 0.629 to 0.760 | 0.679 to 0.725 |
| 32 | pooled / direct_txn | server_cpu_ms_per_query | 0.927 | 0.922 to 0.932 | 0.925 to 0.929 |
| 32 | pooled / direct_txn | throughput_qps | 1.020 | 0.983 to 1.057 | 1.003 to 1.033 |
| 48 | pooled / direct_txn | mean_ms | 0.942 | 0.936 to 0.948 | 0.939 to 0.944 |
| 48 | pooled / direct_txn | p99_ms | 0.527 | 0.416 to 0.638 | 0.477 to 0.563 |
| 48 | pooled / direct_txn | server_cpu_ms_per_query | 0.891 | 0.885 to 0.897 | 0.888 to 0.893 |
| 48 | pooled / direct_txn | throughput_qps | 1.062 | 1.056 to 1.068 | 1.060 to 1.064 |
| 1 | pooled / direct | mean_ms | 1.031 | 0.983 to 1.079 | 1.016 to 1.053 |
| 1 | pooled / direct | p99_ms | 1.022 | 0.973 to 1.070 | 1.008 to 1.044 |
| 1 | pooled / direct | server_cpu_ms_per_query | 1.008 | 0.959 to 1.056 | 0.993 to 1.030 |
| 1 | pooled / direct | throughput_qps | 0.970 | 0.925 to 1.015 | 0.949 to 0.984 |
| 8 | pooled / direct | mean_ms | 1.056 | 1.035 to 1.077 | 1.046 to 1.062 |
| 8 | pooled / direct | p99_ms | 1.130 | 0.977 to 1.283 | 1.059 to 1.169 |
| 8 | pooled / direct | server_cpu_ms_per_query | 1.012 | 1.005 to 1.019 | 1.010 to 1.015 |
| 8 | pooled / direct | throughput_qps | 0.947 | 0.928 to 0.966 | 0.941 to 0.956 |
| 32 | pooled / direct | mean_ms | 0.995 | 0.960 to 1.029 | 0.983 to 1.010 |
| 32 | pooled / direct | p99_ms | 0.480 | 0.438 to 0.523 | 0.465 to 0.499 |
| 32 | pooled / direct | server_cpu_ms_per_query | 0.937 | 0.933 to 0.941 | 0.936 to 0.939 |
| 32 | pooled / direct | throughput_qps | 1.006 | 0.971 to 1.041 | 0.990 to 1.017 |
| 48 | pooled / direct | mean_ms | 0.958 | 0.922 to 0.994 | 0.949 to 0.974 |
| 48 | pooled / direct | p99_ms | 0.421 | 0.117 to 0.726 | 0.300 to 0.545 |
| 48 | pooled / direct | server_cpu_ms_per_query | 0.903 | 0.879 to 0.926 | 0.897 to 0.914 |
| 48 | pooled / direct | throughput_qps | 1.045 | 1.007 to 1.083 | 1.027 to 1.055 |
