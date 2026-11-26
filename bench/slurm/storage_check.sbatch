#!/bin/bash
# Read-only look at the storage of a compute node: which devices exist, which are rotational, and what /tmp and /dev/shm are.
# Submit from bench/: sbatch slurm/storage_check.sbatch
#SBATCH -J rb_storage
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem=4G
#SBATCH -t 00:05:00
#SBATCH -o logs/%x_%j.out
set -uo pipefail
echo "node=$(hostname) job=$SLURM_JOB_ID date=$(date -u +%FT%TZ)"
echo "TMPDIR=${TMPDIR:-unset}"
echo "== lsblk"; lsblk -o NAME,SIZE,TYPE,ROTA,TRAN,MODEL,FSTYPE,MOUNTPOINT 2>&1
echo "== rotational flag per block device"; for d in /sys/block/*; do echo "$(basename "$d") rotational=$(cat "$d/queue/rotational" 2>/dev/null)"; done
echo "== findmnt for the paths the benchmark uses"; for p in /tmp "${TMPDIR:-/tmp}" /dev/shm /arf/scratch; do findmnt -T "$p" -o TARGET,SOURCE,FSTYPE,SIZE,AVAIL 2>&1; done
echo "== df"; df -h /tmp "${TMPDIR:-/tmp}" /dev/shm 2>&1
echo "== nvme"; (command -v nvme >/dev/null && nvme list 2>&1) || echo "nvme tool not available"; ls /dev/nvme* 2>&1 | head
echo "== mounts of interest"; grep -E " (/tmp|/scratch|/local|/dev/shm) " /proc/mounts 2>&1
echo "== /sys/block summary"; ls /sys/block
echo STORAGE_CHECK_DONE
