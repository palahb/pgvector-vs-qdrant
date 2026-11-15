# E7 perf counter probe

Verdict: **valid**; rows: 2; issues: 0.

| Engine | C | ef | Engine span ms/q | /proc CPU ms/q | perf task-clock ms/q | cycles/q | instructions/q | IPC | cache miss % | branch miss % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pg | 4 | 32 | 0.204 | 0.231 | 0.212 | 532404.995 | 715801.427 | 1.344 | 0.008 | 1.383 |
| qdrant | 4 | 32 | 0.190 | 0.504 | 0.484 | 1036706.775 | 1473615.573 | 1.421 | 0.008 | 1.270 |

The engine-reported spans are not treated as semantically interchangeable. The `/proc` and perf values are external process-level attribution over the same concurrency window.
