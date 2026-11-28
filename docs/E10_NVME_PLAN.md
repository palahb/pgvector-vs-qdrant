# E10 on HDD (set 1) and on NVMe (set 2): cost and schedule (G12, 28 November 2026)

Read-only calculation. No job was submitted (the `sbatch --test-only` calls below only ask Slurm for an estimate). Numbers come from `data-manifests/e10_full_0b0b905.json`,
`sacct` for job 7008319, the per-task results in `../artifacts/truba-experiments/E10/0b0b905/full/` and `docs/STORAGE_CHECK.md`. Estimates are labelled.

## 1. What E10 cost on `hamsi` (measured)

E10 planned 36 tasks, 12 arms (3 systems/buffer settings x limits) x 3 repetitions; each task is one Slurm job on a whole node (`-c 56 --mem=170G`): build, evict page cache, three whole-query-set passes
(cold, then steady), a short concurrency step. Elapsed time per task, mean over repetitions (`sacct`):

| Arm | Mean elapsed |
|---|---|
| Qdrant, none / 16G / 8G / 4G | 22 / 24 / 22 / 28 min |
| pgvector (buffers 1 GB), none / 16G / 8G | 40 / 38 / 74 min |
| pgvector (buffers 1/4 of limit), none / 16G / 8G | 34 / 37 / 116 min |
| pgvector, 4G (both settings) | **killed at the 3 h limit** (tasks 10 and 11); tasks 22, 23, 34, 35 cancelled before they started |

The 29 completed tasks (the manual retry of task 14, job 7008845, is not in this sum) add up to **21.1 h** of node time, about 22 h with the retry. A pass at 8 GB takes 2,521 s cold and
1,964 s steady for the 1/4-buffer setting (1,171 ms per query, `results/derived/e10_full_0b0b905_summary.md`); 3 passes plus 450 s of build explain the 1 h 56 min.

## 2. pgvector at 4 GB on `hamsi` (estimate, not measured)

The 3 h limit that killed tasks 10 and 11 was **our choice**: the partition allows 3 days (`scontrol show partition hamsi`: `MaxTime=3-00:00:00`). A job is about 450 s of build plus three passes. Killed at 10,800 s
means a pass above about 3,400 s, i.e. above about 2 s per query, so the job needs **more than 3 h** (lower bound, from the data). An upper bound: pgvector reads about 5,000 vectors per query (E19; the order of magnitude
is what matters) and a random read on this disk takes 4.8 ms, so with nothing cached a query costs at most about 25 s, a pass about 11.6 h and a job about 35 h. Real values lie between the two bounds. **So a limit of 48 h should
be enough for every 4G arm, and 24 h may not be.** The 72 h and the 12 h request get the same estimated start (section 4), so the long limit costs no waiting.

Six jobs: two buffer settings x three repetitions, the same commit `0b0b905` and the same configs as the other cells. If a job still hits the limit, the manifest and the paper say "did not finish within 48 h".

## 3. E10 on `orfoz` (NVMe), a separate set

* `orfoz183` has an NVMe device (`/dev/nvme0n1`, Micron 7450, 894 GB) and `/tmp` is on it (`docs/STORAGE_CHECK.md`). Its processor differs from hamsi (112 cores and 256 GB per node, Xeon Platinum 8480+ according to the documentation, not measured
  here), so the results form their own table; nothing is mixed with hamsi results.
* Cost: the matrix is the same 36 tasks. As an upper bound take the hamsi time, about 22 h of node time plus the six 4G tasks of section 2. On NVMe a cold read costs far less than the 4.8 ms of the disk, so passes at 8 GB
  and 4 GB should be much shorter; this is expected, **not measured**.
* Work before the first run: (a) the pinning (`server_cores auto:8`, `client_cores auto`) was written for 2 x 28 cores and must be checked on a 2 x 56 node (`lscpu` topology); (b) the queue accepts only whole nodes of 56 or 112 cores
  (`orfoz: -c 112` accepted, smaller refused), and a limit of 3 days at most; (c) a smoke task per arm family and the pilot gate as in `ORCHESTRATION.md`; (d) every result records `lsblk`/`findmnt` of the node so the platform is in the data.

## 4. Schedule (Slurm estimates, 28 November; they move with the queue)

`sbatch --test-only` with the real script (`-N 1 -n 1`; the first attempts with `--wrap` were refused for an unrelated reason):

| Request | Estimated start of the first job |
|---|---|
| hamsi, `-c 56 --mem=170G`, 12 h | 4 Dec 13:13 (hamsi34) |
| hamsi, same, 72 h | 4 Dec 13:13 |
| orfoz, `-c 112`, 12 h | 6 Dec 07:21 (orfoz188) |
| orfoz, same, 72 h | 6 Dec 07:21 |

Both partitions are full (140 of 156 orfoz nodes allocated); our priority is low, and the estimate is for the **first** job only. A job of 12 h or longer cannot use backfill, so the waiting is a few days, not hours.

Reading against the plan (G13 and G14 due 12 December, G15 writing 9 to 14 December, draft 15 December):

* Set 1 (hamsi, six 4G jobs): the first start about 4 December; if the six jobs run side by side the last ends around 6 to 8 December in the lower-bound case and later if they are slow. Fits, with little slack.
* Set 2 (orfoz): the first start about 6 December; 36 tasks of mostly well under an hour each. Fits only if several nodes become free; a sequential run of 22 h would end around 7 to 8 December at best. **Uncertain**, because it depends on the queue we cannot control.

## 5. Recommendation and cut line

1. Run set 1 (G13) first: small, the same platform as everything else, and it removes the weakest sentence of the memory section ("did not finish within our own limit").
2. Prepare set 2 (G14) in parallel (pinning check, smoke); submit it as soon as the smoke passes. Smoke and pilot gates are short and can backfill.
3. **Cut line (the supervisor's own fallback):** if by 9 December set 2 has fewer than the planned cells, the paper reports the cells that finished as "NVMe, orfoz" and keeps every other storage-dependent result labelled "HDD, worst case". Set 1 and the writing are not cut.
