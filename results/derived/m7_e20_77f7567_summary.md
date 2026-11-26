# M7: throughput at exactly the matched recall

Target recall 0.95. Model: qps(target) = qps(matched ef) * cpu(matched ef) / cpu(target). Validation compares the model's prediction at the second measured ef with the measurement.

| Engine | Arm | Clients | recall at point | qps at point | qps at target | correction % | validation error % |
|---|---|---:|---:|---:|---:|---:|---:|
| pg | halfvec | 8 | 0.955 | 1069 | 1194 | 11.8 | 2.8 |
| pg | halfvec | 32 | 0.955 | 1003 | 1121 | 11.8 | -2.5 |
| pg | vector | 8 | 0.955 | 982 | 1119 | 13.9 | 3.3 |
| pg | vector | 32 | 0.955 | 910 | 1037 | 13.9 | -1.7 |
| qdrant | f32 | 8 | 0.953 | 1489 | 1647 | 10.6 | 14.5 |
| qdrant | f32 | 32 | 0.953 | 1492 | 1650 | 10.6 | -3.6 |
| qdrant | int8 | 8 | 0.952 | 2845 | 2977 | 4.9 | 22.2 |
| qdrant | int8 | 32 | 0.952 | 2872 | 3005 | 4.9 | -0.1 |
