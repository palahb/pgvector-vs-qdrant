#!/bin/bash
# E1: scale. Rebuilds the original 100K/500K/1M comparison with the fixed harness:
# gRPC + REST + lean gRPC for Qdrant, real TREC-DL queries, index build measured to completion,
# closed-loop concurrency with server-side timing. Submit one job per scale:
#   sbatch slurm/e1_scale.sbatch 100000 ; sbatch slurm/e1_scale.sbatch 500000 ; sbatch slurm/e1_scale.sbatch 1000000
#SBATCH -J rb_e1
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
N=${1:?usage: sbatch slurm/e1_scale.sbatch <n>}
OUT=$BENCH_RESULTS/e1_scale/n$N
# ENGINES="pg" reruns one engine only, e.g. sbatch --export=ALL,ENGINES=pg ...
for e in ${ENGINES:-pg qdrant}; do
    bench --engine "$e" --n "$N" --perf --out "$OUT" || echo "$e FAILED"
done
"$VENV/bin/python" "$BENCH_CODE/summarize.py" "$OUT"
