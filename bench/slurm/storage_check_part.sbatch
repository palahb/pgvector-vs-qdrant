#!/bin/bash
# Read-only storage look on any partition. Submit: sbatch -p <partition> [-c N --mem=M] slurm/storage_check_part.sbatch
#SBATCH -J rb_storage_p
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:05:00
#SBATCH -o logs/%x_%j.out
set -uo pipefail
echo "node=$(hostname) part=$SLURM_JOB_PARTITION job=$SLURM_JOB_ID date=$(date -u +%FT%TZ)"
echo "TMPDIR=${TMPDIR:-unset}"
echo "== lsblk"; lsblk -o NAME,SIZE,TYPE,ROTA,TRAN,MODEL,FSTYPE,MOUNTPOINT 2>&1
echo "== rotational"; for d in /sys/block/*; do echo "$(basename "$d") rotational=$(cat "$d/queue/rotational" 2>/dev/null)"; done
echo "== findmnt for benchmark paths"; for p in /tmp "${TMPDIR:-/tmp}" /dev/shm /arf/scratch; do findmnt -T "$p" -o TARGET,SOURCE,FSTYPE,SIZE,AVAIL 2>&1; done
echo "== df"; df -h 2>&1
echo "== nvme"; ls /dev/nvme* 2>&1 | head
echo "== weka/lustre mounts"; grep -i -E "weka|lustre|nvme" /proc/mounts
echo "== all non-pseudo mounts"; grep -v -E "^(proc|sysfs|cgroup|tmpfs|devtmpfs|devpts|mqueue|hugetlbfs|debugfs|tracefs|securityfs|pstore|configfs|fusectl|autofs|binfmt_misc|bpf|selinuxfs|rpc_pipefs|nfsd) " /proc/mounts
echo STORAGE_CHECK_DONE
