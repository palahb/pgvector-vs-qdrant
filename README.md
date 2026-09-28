# pgvector vs. Qdrant: Vector Search Benchmarking for RAG Workloads

**CMP653 — Database Management Systems**
Hacettepe University, Spring 2026
Halil Burak Pala

This repository contains the benchmarking pipeline used to compare **pgvector** (PostgreSQL extension) and **Qdrant** (purpose-built vector database) under RAG-style workloads. Both systems run locally in Docker on the same machine so that network latency does not skew the comparison.

The study measures index build time, query latency, Recall@10, and throughput under concurrent load across dataset scales from 100K to 1M vectors.

---

## Repository Layout

```
pgvector-vs-qdrant/
│
├── milestone/                      # Scripts and results from the milestone report (100K only)
│   ├── 01_load_data.py             # Download MS MARCO and Cohere embeddings from HuggingFace
│   ├── 02_setup_pgvector.py        # Create the pgvector table and HNSW index
│   ├── 03_insert_vectors.py        # Insert 100K vectors into both systems
│   ├── 04_benchmark.py             # Run the latency and recall benchmark
│   └── results/                    # Raw JSON outputs from the milestone runs
│
├── final/                          # Scripts and results from the final report
│   ├── 05_load_data_1m.py          # Download up to 1M passages (used for scale experiments)
│   ├── 06_scale_benchmark.py       # Full benchmark at 100K / 500K / 1M
│   ├── 07_dim_benchmark.py         # Dimensionality experiment (384 / 512 / 1024)
│   ├── 08_concurrency_benchmark.py # Concurrency experiment (1 / 10 / 50 clients)
│   ├── 09_generate_charts.py       # Produces the charts used in the paper
│   ├── results/                    # Raw JSON outputs from all final experiments
│   └── charts/                     # Generated PNG charts
│
├── requirements.txt                # Python dependencies
└── README.md
```

> The actual vector data (`embeddings_*.npy`, `texts_*.json`) is not stored in the repo. It is downloaded by the data-loading scripts.

---

## Setup

You need Python 3.11 and Docker.

**Start the databases:**

```bash
docker run -d --name pgvector_db -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=vectordb -p 5432:5432 pgvector/pgvector:pg16

docker run -d --name qdrant_db -p 6333:6333 qdrant/qdrant
```

**Install Python dependencies:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## How to Reproduce

The `milestone/` scripts reproduce the 100K-vector experiment from the milestone report and are kept here for historical reference. The `final/` scripts reproduce everything used in the final report and are self-contained: a single data-loading step produces all three vector slices used by the benchmarks.

To rerun the full final pipeline:

```bash
cd final/

# Download MS MARCO and save the 100K / 500K / 1M slices plus dataset stats
# (takes 30-60 minutes on first run, downloads about 4 GB)
python 05_load_data_1m.py

# Scale experiments (each takes longer at larger sizes)
python 06_scale_benchmark.py 100000
python 06_scale_benchmark.py 500000
python 06_scale_benchmark.py 1000000

# Dimensionality experiment (uses the 100K slice)
python 07_dim_benchmark.py

# Concurrency experiment (relies on the database state left by the 100K scale run)
python 08_concurrency_benchmark.py

# Generate all charts from the JSON results
python 09_generate_charts.py
```

The 06 script saves progress to a checkpoint file after each phase, so if it crashes you can just rerun the same command and it will resume from where it left off.

---

## Results Files

Each result file under `final/results/` contains the raw numbers used to write the paper:

| File | Contains |
|---|---|
| `results_100K.json` / `results_500K.json` / `results_1M.json` | Build times and per-ef latency/recall at each scale |
| `results_concurrency.json` | Throughput and latency under 1, 10, 50 concurrent clients |
| `results_dimensionality.json` | Performance at 384, 512, 1024 dimensions |
| `dataset_stats.json` | Word counts and corpus properties for the 100K sample |

The chart files in `final/charts/` are generated from these JSON files by `09_generate_charts.py`.

---

## Notes

- All Cohere embeddings are 1024-dimensional and L2-normalized. The dimensionality experiment uses Matryoshka truncation (cutting the trailing dimensions and re-normalizing) to test smaller sizes.
- The 1M Qdrant build time was measured with a smaller upsert batch size (100 instead of 500) to avoid HTTP timeouts. This is documented in the paper.
- Hardware: a single commodity laptop (Intel x86_64, macOS). The absolute numbers are tied to this hardware, but the relative comparisons should hold on similar machines.