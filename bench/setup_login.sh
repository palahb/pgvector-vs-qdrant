#!/bin/bash
# One-time setup on the ARF login node (it has internet, compute nodes do not).
# Usage: cd <repo>/bench && bash setup_login.sh
set -euo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p "$BENCH_ROOT"/{images,data,cache,results,hf_cache} "$BENCH_CODE/logs" "$APPTAINER_CACHEDIR"

echo "== container images"
[ -f "$QDRANT_SIF" ] || apptainer pull "$QDRANT_SIF" "docker://qdrant/qdrant:$QDRANT_VERSION"
[ -f "$PG_SIF" ] || apptainer pull "$PG_SIF" "docker://pgvector/pgvector:$PGVECTOR_TAG"
apptainer exec "$QDRANT_SIF" /qdrant/qdrant --version
apptainer exec --cleanenv "$PG_SIF" postgres --version

echo "== python 3.11 venv (uv fetches a standalone CPython, no root or modules needed)"
if ! command -v uv >/dev/null; then
    python3 -m pip install --user --quiet uv || curl -LsSf https://astral.sh/uv/install.sh | sh
fi
[ -x "$VENV/bin/python" ] || uv venv --python 3.11 "$VENV"
uv pip install --python "$VENV/bin/python" -r "$BENCH_CODE/requirements.txt"
"$VENV/bin/python" -c "import numpy, psycopg, qdrant_client, psutil, datasets; print('python deps ok, numpy', numpy.__version__)"

echo
echo "Setup done. Next:"
echo "  1) sbatch slurm/probe.sbatch      (checks the node and runs a tiny end-to-end test)"
echo "  2) nohup $VENV/bin/python $BENCH_CODE/prepare_data.py > logs/prepare_data.log 2>&1 &"
