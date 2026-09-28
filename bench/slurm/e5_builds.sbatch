#!/bin/bash
# E5: build-time repeats on ONE node, plus a disk check for E4.
# Builds of the same configuration differed by up to ~30% across nodes, so build times in
# the paper come from this job: 3 builds per engine and scale, interleaved (rep, scale,
# engine) so drift over the job's lifetime does not favor either system.
#   sbatch slurm/e5_builds.sbatch
#SBATCH -J rb_e5
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 56
#SBATCH --mem=170G
#SBATCH -t 04:00:00
#SBATCH -o logs/%x_%j.out
set -uo pipefail
source "$SLURM_SUBMIT_DIR/env.sh"
preflight
OUT=$BENCH_RESULTS/e5_builds
mkdir -p "$OUT"

echo "== disk probe (node-local scratch, O_DIRECT)"
"$VENV/bin/python" "$BENCH_CODE/disk_probe.py" "${TMPDIR:-/tmp}" 32 | tee "$OUT/disk_probe_$(hostname).json"

for rep in 1 2 3; do
    for n in 100000 500000 1000000; do
        for e in pg qdrant; do
            bench --engine "$e" --n "$n" --ef 64 --reps 1 --warm 100 --clients "" \
                  --protocols grpc_raw --tag "r$rep" --out "$OUT/n$n" || echo "$e n=$n rep=$rep FAILED"
        done
    done
done
