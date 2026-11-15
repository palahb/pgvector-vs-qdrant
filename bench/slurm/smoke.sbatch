#!/bin/bash
# Fast end-to-end validation of both engines and the result schema.
# Submit from bench/: sbatch slurm/smoke.sbatch
#SBATCH -J rb_smoke
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 56
#SBATCH --mem=170G
#SBATCH -t 00:15:00
#SBATCH -o logs/%x_%j.out
set -euo pipefail

source "$SLURM_SUBMIT_DIR/env.sh"
preflight

commit=$(git -C "$SLURM_SUBMIT_DIR/.." rev-parse --short=12 HEAD)
out="$BENCH_ROOT/results/smoke/${commit}_${SLURM_JOB_ID}"
common=(
    --synthetic
    --seed 42
    --warm-seed 7
    --n 5000
    --dim 64
    --ef 16,32
    --reps 1
    --warm 50
    --clients 1,4
    --conc-ef 32
    --conc-recall 0
    --conc-duration 2
    --conc-warmup 1
    --mem-limits none
    --out "$out"
)

echo "smoke commit=$commit job=$SLURM_JOB_ID node=$(hostname) out=$out"
bench --engine pg "${common[@]}" \
    --pg-shared-buffers 256MB --pg-effective-cache 512MB --pg-maintenance-mem 512MB
bench --engine qdrant "${common[@]}" --protocols grpc_raw

"$VENV/bin/python" "$SLURM_SUBMIT_DIR/../analysis/validate_results.py" \
    "$out" --strict-warnings --output "$out/audit.json"
"$VENV/bin/python" "$BENCH_CODE/summarize.py" "$out"
echo "SMOKE_OK commit=$commit job=$SLURM_JOB_ID"
