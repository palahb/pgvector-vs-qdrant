# pgvector vs. Qdrant for RAG Workloads

This repository contains the reproducible benchmark and paper sources for a
systems-oriented comparison of pgvector and Qdrant. The work started as a CMP653
course project and is being revised into a full paper using bare-metal TRUBA/ARF
experiments.

The active pipeline is the ARF harness under `bench/`. The original course code and
results are retained under `legacy/course-project/` for provenance; they are not the
source of new paper claims.

## Repository map

```text
.
├── bench/                  # active Python benchmark harness and Slurm jobs
├── docs/                   # operational and handover notes
├── legacy/course-project/  # preserved milestone/final course implementation
└── paper/                  # active LaTeX manuscript and generated figures
```

Additional experiment manifests, validation, analysis and artifact directories are
introduced as the revision progresses. Large datasets, container images and raw TRUBA
results are intentionally not committed to Git.

## Current experimental baseline

The archived baseline contains five experiment families:

| ID | Scope |
|---|---|
| E1 | Scale, recall/latency sweeps, protocols and concurrency |
| E2 | HNSW parameter sweep |
| E3 | Embedding dimensionality and Qdrant indexing threshold |
| E4 | Buffer pool, memory limits and out-of-core behavior |
| E5 | Interleaved build-time measurements and disk probe |

The active harness records configuration, host and Slurm metadata, engine versions,
container identities, build phases, latency samples and engine-specific diagnostics.
See [`bench/README.md`](bench/README.md) for the experiment commands and output schema.

## TRUBA/ARF quick start

Run experiments from a compute node through Slurm, not directly on a login node.
The current deployment root is `/arf/scratch/$USER/rag_bench`.

```bash
mkdir -p /arf/scratch/$USER/rag_bench
cd /arf/scratch/$USER/rag_bench
git clone https://github.com/palahb/pgvector-vs-qdrant.git
cd pgvector-vs-qdrant/bench

bash setup_login.sh
sbatch slurm/probe.sbatch
```

After the probe is validated, prepare the corpus and submit a small pilot before larger
arrays:

```bash
source env.sh
nohup "$VENV/bin/python" prepare_data.py > logs/prepare_data.log 2>&1 &
sbatch slurm/e1_scale.sbatch 100000
```

Do not launch the full matrix until the pilot output passes the provenance and result
schema checks.

## Local static checks

The benchmark package can be syntax-checked without database services:

```bash
python3 -m compileall -q bench
```

Run the complete frozen-baseline audit with one command after the external archive has
been restored at the workspace path recorded in its manifest:

```bash
make PYTHON_BIN=env/bin/python verify-baseline
```

This runs unit tests, syntax checks, the result validator, the lossless legacy adapter,
paper source indexing, the M6 reconciliation and pixel/render figure reproduction.

Full local execution requires compatible PostgreSQL/pgvector and Qdrant binaries. The
supported paper environment is the version-pinned ARF setup documented in
`bench/README.md` and the result manifests.

## Paper and figures

`paper/main.tex` is the active manuscript. Quantitative tables and figures must be
generated from validated result files rather than copied by hand.

From `bench/`:

```bash
"$VENV/bin/python" summarize.py "$BENCH_RESULTS/e1_scale"
"$VENV/bin/python" make_figures.py "$BENCH_RESULTS" ../paper/figures
"$VENV/bin/python" paper_numbers.py "$BENCH_RESULTS"
```

Every paper number should remain traceable to an immutable raw result, experiment
configuration, commit SHA, Slurm job ID and container digest.

## Historical course project

The original Docker/laptop scripts and their JSON/PNG outputs are available in:

```text
legacy/course-project/milestone/
legacy/course-project/final/
```

They are preserved to explain the evolution of the methodology. Known limitations of
that harness include protocol asymmetry, asynchronous Qdrant indexing, constrained
pgvector build memory, known-item queries and a client-limited concurrency test. New
paper claims must use the active ARF harness or explicitly identify historical evidence.

## Data and result policy

- Do not commit corpus embeddings, query matrices, container images or credentials.
- Never overwrite raw experiment output; create a new experiment/run identifier.
- Treat partial output from a failed job as incomplete until validation says otherwise.
- Keep at least commit SHA, config, seed, node, job ID and image digest with each run.
- Generate derived tables and figures through versioned scripts.

## VPN and remote-operation note

The current TRUBA OpenVPN tunnel has a reproducible keepalive/reconnect issue. Use the
DNS-filtered profile and connection-tolerant Slurm/SSH workflow described in
[`docs/TRUBA_VPN_OPERASYON_NOTU.md`](docs/TRUBA_VPN_OPERASYON_NOTU.md). No VPN profile,
password or private key belongs in this repository.
