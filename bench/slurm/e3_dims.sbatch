#!/bin/bash
# E3: dimensionality at 100K, 128..1024 in steps of 128 (Matryoshka truncation, re-normalized).
# Qdrant runs twice per dimension: default optimizer settings, and indexing_threshold=1 KB,
# which forces HNSW on every segment. If the old 384-dim "anomaly" was small segments staying
# unindexed (brute force), it shows up only in the default runs, together with recall near 1.0.
#SBATCH -J rb_e3
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 56
#SBATCH --mem=170G
#SBATCH -t 12:00:00
#SBATCH -o logs/%x_%j.out
set -uo pipefail
source "$SLURM_SUBMIT_DIR/env.sh"
preflight
N=${N:-100000}
for D in 128 256 384 512 640 768 896 1024; do
    OUT=$BENCH_RESULTS/e3_dims/n${N}_d$D
    COMMON="--n $N --dim $D --ef 16,32,64,128 --clients 1,8,32 --protocols grpc_raw,grpc --out $OUT"
    bench --engine pg $COMMON || echo "pg d=$D FAILED"
    bench --engine qdrant $COMMON --tag default || echo "qdrant default d=$D FAILED"
    bench --engine qdrant $COMMON --tag forced --qdrant-indexing-threshold-kb 1 || echo "qdrant forced d=$D FAILED"
done
"$VENV/bin/python" "$BENCH_CODE/summarize.py" "$BENCH_RESULTS/e3_dims"
