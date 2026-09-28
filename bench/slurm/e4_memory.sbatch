#!/bin/bash
# E4: memory pressure at 1M, the causal test for the buffer pool explanation.
#   task 0-3: pgvector with shared_buffers 128MB / 1GB / 4GB / 32GB and no memory cap.
#             Shows how much of pgvector's latency comes from shared buffers vs the OS page cache
#             (shared_blks_read per query and read time are recorded from pg_stat_statements).
#   task 4:   pgvector, shared_buffers 1GB, server capped at 16G/8G/4G/2G (cold cache each time)
#   task 5:   Qdrant with mmap storage (on_disk), same caps
# Each cap restarts the server as its own Slurm step with srun --mem, after evicting its files
# from the page cache, so the kernel really has to go to disk.
# The node-local disk on hamsi is a spinning drive (E5 disk probe: ~5 ms per random 8 KiB read,
# ~200 IOPS), so a capped query can take seconds. Capped runs therefore measure 300 queries,
# one rep, 100 warm-up queries, and concurrency at ef=64 only.
#SBATCH -J rb_e4
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 56
#SBATCH --mem=170G
#SBATCH -t 24:00:00
#SBATCH --array=0-5
#SBATCH -o logs/%x_%A_%a.out
set -uo pipefail
source "$SLURM_SUBMIT_DIR/env.sh"
preflight
N=${N:-1000000}
OUT=$BENCH_RESULTS/e4_memory/n$N
LIMITS=none,16G,8G,4G,2G
PRESSURE="--ef 64,128 --reps 1 --warm 100 --nq 300 --clients 1,8,32 --conc-all-limits --conc-recall 0 --conc-duration 30"
case $SLURM_ARRAY_TASK_ID in
    0|1|2|3)
        SB=(128MB 1GB 4GB 32GB)
        bench --engine pg --n "$N" --pg-shared-buffers "${SB[$SLURM_ARRAY_TASK_ID]}" \
              --tag "sb${SB[$SLURM_ARRAY_TASK_ID]}" --clients 1,8,32 --out "$OUT" ;;
    4)  bench --engine pg --n "$N" --pg-shared-buffers 1GB --mem-limits "$LIMITS" $PRESSURE \
              --tag capped --out "$OUT" ;;
    5)  bench --engine qdrant --n "$N" --qdrant-on-disk --protocols grpc_raw --mem-limits "$LIMITS" \
              $PRESSURE --tag capped_ondisk --out "$OUT" ;;
esac
