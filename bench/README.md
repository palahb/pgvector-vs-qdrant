# bench: pgvector vs Qdrant on ARF (TRUBA)

The v2 harness for the journal version. The course scripts in `milestone/` and `final/` stay as they were, for the record. Everything here runs on a bare-metal ARF compute node. Servers run from Apptainer images and the client runs from a Python 3.11 venv.

## What changed from the course harness, and why

| Old harness | Effect on the old results | v2 |
|---|---|---|
| Qdrant "build time" = upsert time only. The HNSW graph is built asynchronously afterwards. | Qdrant's 3.5-4.7x build advantage is overstated. Early query passes ran while the optimizer was still indexing. | Build = upload + wait until the collection is `green` and stays green. The state trace is recorded. |
| pgvector built with `maintenance_work_mem = 64MB` (the default) | The graph didn't fit in memory, so pgvector's build time was inflated | `maintenance_work_mem` and parallel workers are set explicitly and reported. pgvector's own NOTICEs are captured. |
| Small Qdrant segments stay unindexed below `indexing_threshold` (20 MB) and are brute-forced | Most likely cause of the 384-dim "anomaly": slower, but recall highest (0.998) | `indexed_vectors_count` is recorded for every run. E3 reruns every dimension with indexing forced. |
| Concurrency: a new `QdrantClient` per query, REST, Python threads (GIL) | Connection setup was inside the timed region. The client was probably the bottleneck, not Qdrant. | One persistent connection per worker **process**, closed loop, 30 s window after warm-up. Client CPU use is reported. |
| Qdrant over REST, pgvector over its binary wire protocol | Protocol asymmetry (the reviewer's main point) | Qdrant is measured three ways: `grpc_raw` (protobuf stub, lean like psycopg), `grpc` (official client), `rest`. |
| End-to-end latency only | No way to separate engine time from client/network time | Server-side time per query: `pg_stat_statements` for pg, the `/telemetry` counters for Qdrant |
| Queries = the first 1000 corpus vectors (each one is in the index) | Known-item search, recall inflated | 1,677 real TREC-DL 2021-2023 query embeddings. Warm-up uses a separate set. |
| macOS Docker VM, both engines sharing CPUs with the client | Virtualization noise, CPU contention | Full hamsi node. Server pinned to 8 cores on socket 0, client on the 28 cores of socket 1. |
| No evidence for the buffer pool explanation | Hypothesis only | Buffer hit ratio and blocks read per query (pg), wait-event sampling (LWLock / IO), `perf stat`, and memory-capped cold runs (E4) |

In a quick local test (1 server core, synthetic data), Qdrant's server-side time was about 0.2 ms, while end-to-end latency was 0.75 ms (lean gRPC), 0.9 ms (official gRPC client) and 1.4 ms (REST). At 4 clients the client core was at 100%. Expect the concurrency story to change on ARF.

## Setup on ARF (once)

ARF rules that shape the scripts: jobs must be submitted from under `/arf/scratch/`, barbun wants
20 cores per node and hamsi wants all 56. We use **hamsi, full node** (2 x 28-core Xeon Gold 6258R,
HT off, ~187 GB): no other job shares the machine, the server gets 8 cores on socket 0 and the client
gets all 28 cores of socket 1. Jobs ask for `--mem=170G` (the default on some partitions is 2 GB/core).
Everything lives in `/arf/scratch/$USER/rag_bench`.

```bash
# on arf-ui1 (login node)
mkdir -p /arf/scratch/$USER/rag_bench && cd /arf/scratch/$USER/rag_bench
git clone https://github.com/palahb/pgvector-vs-qdrant.git   # or git pull if already there
cd pgvector-vs-qdrant/bench
bash setup_login.sh          # pulls qdrant v1.19.1 + pgvector 0.8.6-pg17, builds the venv
sbatch slurm/probe.sbatch    # ~10 min on a hamsi node, then:  cat logs/rb_probe_<jobid>.out

source env.sh
nohup $VENV/bin/python prepare_data.py > logs/prepare_data.log 2>&1 &   # ~1 h, 1M passages + queries
```

The probe answers everything that must be true before real runs. Send its output back before launching E1-E4:
- is `/tmp` a local SSD, not tmpfs? (the out-of-core experiment depends on it)
- does `srun --mem` actually cap a step? (look for the OOM kill)
- `perf_event_paranoid` and whether `perf stat` counts anything
- NUMA layout, used to place server and client cores
- a full end-to-end run of both engines on synthetic data, including a memory-capped restart

Always submit from the `bench/` folder, because the scripts find `env.sh` through `$SLURM_SUBMIT_DIR`.

## Experiments

| Job | What | Addresses |
|---|---|---|
| `sbatch slurm/e1_scale.sbatch 100000` (also 500000, 1000000) | Build, ef sweep 16-256 x 3 reps, concurrency 1-64 clients, all protocols | Protocol parity, ingestion standardization, virtualization, scale |
| `sbatch slurm/e2_hnsw.sbatch` | 8 (M, ef_construction) configs at 500K, array job | "Black box, default parameters" |
| `sbatch slurm/e3_dims.sbatch` | 128-1024 dims step 128, Qdrant default vs forced indexing | 384-dim anomaly (SIMD vs indexing threshold) |
| `sbatch slurm/e5_builds.sbatch` | Disk check (O_DIRECT random reads), then 3 interleaved builds per engine and scale on one node | Build-time variance; disk type for E4 |
| `sbatch slurm/e4_memory.sbatch` | pg shared_buffers 128MB-32GB. pg and Qdrant(on_disk) capped at 16/8/4/2 GB, cold cache | Buffer pool causality, out-of-core |

Run E1 at 100K first and look at it before submitting the rest. Hybrid filtering and mixed read/write workloads (items 7 and 8 of the plan) are the next harness extension, once E1 looks right.

Check progress with `squeue -u $USER` and `tail -f logs/<name>_<jobid>.out`. Summarize with:

```bash
$VENV/bin/python summarize.py $BENCH_RESULTS/e1_scale
```

Paper figures come straight from the result files (never from hand-copied numbers):

```bash
$VENV/bin/python make_figures.py $BENCH_RESULTS paper/figures
$VENV/bin/python paper_numbers.py $BENCH_RESULTS      # every table row and headline range
```

## Outputs

`$BENCH_RESULTS/<experiment>/<config>/<engine>[_tag]/`
- `result.json`: config, host metadata (CPU, kernel, NUMA, Slurm job, node), image sha256, engine versions and settings, build breakdown, every latency and concurrency row
- `raw.npz`: every per-query latency, for CIs and distributions later
- `*_server_*.log`: server logs
- `perf_*.csv`: `perf stat` output when `--perf` is on

`result.json` is rewritten after every step, so a job killed by the time limit still leaves everything it measured.

## Running a single configuration by hand

```bash
source env.sh
salloc -p hamsi -N1 -c56 --mem=170G -t 2:00:00
bench --engine qdrant --n 100000 --ef 64 --clients 1,8 --out $BENCH_RESULTS/scratch
bench --help    # every knob: --m --efc --dim --mem-limits --pg-shared-buffers --qdrant-on-disk ...
```

Local development works too: `BENCH_MODE=local PG_BIN=/usr/lib/postgresql/16/bin QDRANT_BIN=qdrant python run.py --synthetic ...` (Postgres needs a non-root user).
