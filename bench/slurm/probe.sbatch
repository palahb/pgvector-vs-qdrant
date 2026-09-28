#!/bin/bash
# Checks what a hamsi node (ARF requires all 56 cores per node on hamsi) gives us and runs the whole harness on tiny synthetic data,
# including the memory-limited path. Submit from the bench/ folder: sbatch slurm/probe.sbatch
#SBATCH -J rb_probe
#SBATCH -p hamsi
#SBATCH --exclude=hamsi20,hamsi65
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 56
#SBATCH --mem=170G
#SBATCH -t 01:00:00
#SBATCH -o logs/%x_%j.out
set -uo pipefail
source "$SLURM_SUBMIT_DIR/env.sh"
section() { echo; echo "=== $* ==="; }

section node
hostname; uname -r; free -g | head -2
lscpu | grep -E "Model name|^CPU\(s\)|Thread|Core\(s\)|Socket|NUMA"
for n in /sys/devices/system/node/node*/cpulist; do echo "$n: $(cat "$n")"; done
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "governor: n/a"

section "scratch disk (must be a local SSD, not tmpfs, for out-of-core runs)"
echo "TMPDIR=${TMPDIR:-unset}"
df -hT /tmp ${TMPDIR:+"$TMPDIR"} /dev/shm
lsblk -d -o NAME,ROTA,SIZE,TYPE,MODEL

section "slurm and cgroups"
scontrol show job "$SLURM_JOB_ID" | grep -E "NumCPUs|TRES|MinMemory|Partition"
echo "our cpuset: $(taskset -cp $$)"
echo "other jobs on this node:"; squeue -h -w "$(hostname)" -o "%i %u %C %j"
cat /proc/loadavg
scontrol show partition hamsi | grep -E "MaxNodes|MaxTime|DefMemPer|MaxMemPer|TRES|OverSubscribe"
stat -fc "cgroup fs: %T" /sys/fs/cgroup
cat /proc/self/cgroup
scontrol show config | grep -E "SLURM_VERSION|TaskPlugin|ProctrackType|SelectTypeParameters|JobAcctGatherType"
grep -v '^#' /etc/slurm/cgroup.conf 2>/dev/null | grep -v '^$'

section "profiling tools"
echo "perf_event_paranoid=$(cat /proc/sys/kernel/perf_event_paranoid)"
perf stat -e task-clock,context-switches,cycles:u,instructions:u,cache-misses:u -- sleep 0.2 2>&1 | tail -9
for t in perf bpftrace fincore numactl taskset apptainer; do printf "%-9s %s\n" "$t" "$(command -v $t || echo MISSING)"; done

section "does srun --mem cap a step? (expect an OOM kill below, exit code 137 or similar)"
srun --overlap -N1 -n1 -c"$SLURM_CPUS_ON_NODE" --mem=1G --cpu-bind=none \
    "$VENV/bin/python" -c "
import os
cg = open('/proc/self/cgroup').read().strip().split(':')[-1]
for f in ('memory.max', 'memory.limit_in_bytes'):
    p = '/sys/fs/cgroup' + cg + '/' + f
    if os.path.exists(p): print(f, open(p).read().strip())
b = bytearray(3 * 1024**3)
print('NOT LIMITED: allocated 3 GB inside a 1 GB step')"
echo "srun exit code: $?"

section "harness smoke test (synthetic, 50K x 256)"
OUT=$BENCH_RESULTS/probe_$SLURM_JOB_ID
COMMON="--synthetic --n 50000 --dim 256 --ef 32,64 --reps 1 --warm 200 --clients 1,8,32
        --conc-duration 5 --conc-warmup 2 --conc-all-limits --mem-limits none,2G --perf --out $OUT"
bench --engine pg $COMMON --pg-shared-buffers 512MB --pg-effective-cache 1GB --pg-maintenance-mem 1GB
echo "pg exit: $?"
bench --engine qdrant $COMMON --qdrant-on-disk
echo "qdrant exit: $?"
"$VENV/bin/python" "$BENCH_CODE/summarize.py" "$OUT"
