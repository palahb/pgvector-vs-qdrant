# Memory experiment: decision against the supervisor's criterion (26 November 2026)

The supervisor's answer of 17 November sets the criterion for the memory experiment for 1 December: the full query set, repetitions, an independent cold start; the
cgroup part stays. This note compares E10 (`data-manifests/e10_full_0b0b905.json`, commit `0b0b905`, analysis `results/derived/e10_full_0b0b905_summary.md`) with it.

| Criterion | Evidence in E10 | Met |
|---|---|---|
| Full query set | Each pass runs all 1,677 queries, one client, in a random order that differs per pass and per repetition (`bench/workload.py: pass_order`); the earlier 300-query set is gone. | yes |
| Repetitions | Three repetitions per system and limit, each a separate Slurm job (one job per system, limit and repetition); standard deviations over repetitions are in the summary. | yes, except the cells below |
| Independent cold start | Each limit restarts the server with its files evicted from the page cache (`evict_page_cache`), recorded as `resident_before_evict` and `resident_after_evict`. Pass 0 is the cold start (no warm-up); the later passes are the steady state; both are reported separately. A repetition is a new job on a new build. | yes |
| cgroup | The limit is a Slurm step cgroup (`srun --mem`, cgroup v2). `memory.current` of the server's cgroup is read after the passes and stored in every result (30 of 30 results; Qdrant at 4 GB reads 4.00 GiB, i.e. at the limit). | yes |
| Equal memory accounting | pgvector is run with two buffer settings (1 GB, and a quarter of the limit); Qdrant is memory-mapped. The page cache is inside the cgroup for both. | yes |
| NVMe | The cluster has none (`docs/STORAGE_CHECK.md`). Every result is labelled HDD, worst case. | not possible |

## What is missing, and the default

* **pgvector at 4 GB** (both buffer settings): the arms did not finish within the 3 h job limit (tasks 10 and 11 were killed at the limit, the other four were
  cancelled before they started). The paper reports them as "did not finish" and does not extrapolate. The cold start at 8 GB already takes about 2,000 s and the steady state about
  0.6 to 1.2 s per query, so a 4 GB arm needs more than the 3 h limit that killed tasks 10 and 11 (an estimate; it was not run).
* Default (recorded now, as the plan says): **the cells stay reported as not completed.** Running them is a single command
  (`manage.py` resubmit with a longer limit), roughly 3 repetitions x 2 arms x more than 3 h on a queue that currently waits many hours; it would only add a pgvector
  number below the size of its index, where it is already known to be unusable. The decision to run them anyway is the author's.

## Conclusion

The memory experiment meets the supervisor's criterion for 1 December on every point the cluster allows. The two things it does not have, NVMe and pgvector at 4 GB, are
stated in the paper where the results are (Section Memory Pressure, Threats to Validity).
