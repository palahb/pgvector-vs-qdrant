# Sourced by every script. Code, images, data and results live under $BENCH_ROOT on Lustre;
# database files go to node-local scratch during a job (see run.py --work).
# ARF only accepts jobs submitted from /arf/scratch, so the whole project lives there
export BENCH_ROOT=${BENCH_ROOT:-/arf/scratch/$USER/rag_bench}
export BENCH_CODE=${BENCH_CODE:-${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}}
export BENCH_DATA=$BENCH_ROOT/data
export BENCH_CACHE=$BENCH_ROOT/cache
export BENCH_RESULTS=$BENCH_ROOT/results
export BENCH_MODE=apptainer

export QDRANT_VERSION=v1.19.1
export PGVECTOR_TAG=0.8.6-pg17
export QDRANT_SIF=$BENCH_ROOT/images/qdrant-$QDRANT_VERSION.sif
export PG_SIF=$BENCH_ROOT/images/pgvector-$PGVECTOR_TAG.sif
export VENV=$BENCH_ROOT/venv

export APPTAINER_CACHEDIR=${APPTAINER_CACHEDIR:-/tmp/$USER-apptainer-cache}
export HF_HOME=$BENCH_ROOT/hf_cache
export PYTHONUNBUFFERED=1
export PATH=$HOME/.local/bin:$PATH

bench() { "$VENV/bin/python" "$BENCH_CODE/run.py" "$@"; }

# Refuse to run on a node that cannot hold the databases. hamsi65 had a full /dev/shm on
# 2026-09-27, which made PostgreSQL's initdb and Python multiprocessing fail within seconds,
# so the scheduler kept handing it our jobs. Failing loudly here keeps that visible.
preflight() {
    local shm_gb tmp_gb
    shm_gb=$(df -BG --output=avail /dev/shm | tail -1 | tr -dc 0-9)
    tmp_gb=$(df -BG --output=avail "${TMPDIR:-/tmp}" | tail -1 | tr -dc 0-9)
    echo "preflight $(hostname): /dev/shm ${shm_gb}G free, ${TMPDIR:-/tmp} ${tmp_gb}G free"
    if [ "$shm_gb" -lt 40 ] || [ "$tmp_gb" -lt 100 ]; then
        echo "PREFLIGHT FAILED on $(hostname): add it to --exclude and resubmit" >&2
        exit 3
    fi
}
