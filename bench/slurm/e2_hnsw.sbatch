#!/bin/bash
# E2: HNSW parameter space at 500K (the "black box, default parameters" criticism).
# pgvector needs ef_construction >= 2*M, so (64, 64) is left out. One array task per config.
#   sbatch slurm/e2_hnsw.sbatch
#SBATCH -J rb_e2
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 56
#SBATCH --mem=170G
#SBATCH -t 12:00:00
#SBATCH --array=0-7
#SBATCH -o logs/%x_%A_%a.out
set -uo pipefail
source "$SLURM_SUBMIT_DIR/env.sh"
preflight
CONFIGS=("16 64" "16 128" "16 256" "32 64" "32 128" "32 256" "64 128" "64 256")
read -r M EFC <<< "${CONFIGS[$SLURM_ARRAY_TASK_ID]}"
N=${N:-500000}
OUT=$BENCH_RESULTS/e2_hnsw/n${N}_m${M}_efc${EFC}
for e in pg qdrant; do
    bench --engine "$e" --n "$N" --m "$M" --efc "$EFC" --ef 16,32,64,128,256,512 \
          --clients 1,8,32 --protocols grpc_raw,grpc --out "$OUT" || echo "$e FAILED"
done
"$VENV/bin/python" "$BENCH_CODE/summarize.py" "$OUT"
