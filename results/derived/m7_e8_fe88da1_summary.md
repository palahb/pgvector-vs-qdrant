# M7: throughput at exactly the matched recall

Target recall 0.95. Model: qps(target) = qps(matched ef) * cpu(matched ef) / cpu(target). Validation compares the model's prediction at the second measured ef with the measurement.

| Engine | Arm | Clients | recall at point | qps at point | qps at target | correction % | validation error % |
|---|---|---:|---:|---:|---:|---:|---:|
| pg | base | 8 | 0.953 | 1976 | 2099 | 6.2 | 1.4 |
| pg | base | 32 | 0.953 | 1893 | 2011 | 6.2 | -0.3 |
| qdrant | base | 8 | 0.954 | 2816 | 3003 | 6.7 | 5.9 |
| qdrant | base | 32 | 0.954 | 2848 | 3037 | 6.7 | -2.3 |
