#!/bin/bash
# Deterministic single-core distance-kernel lower-bound probe for E7/P6.6-P6.7.
# Submit with: sbatch --export=ALL,EXPECTED_COMMIT=$(git rev-parse HEAD) bench/slurm/e7_kernel_probe.sbatch
#SBATCH --job-name=e7_kernel
#SBATCH --partition=hamsi
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=56
#SBATCH --mem=16G
#SBATCH --time=00:15:00
#SBATCH --exclusive
#SBATCH --output=bench/logs/e7_kernel_%j.out
#SBATCH --error=bench/logs/e7_kernel_%j.err

set -euo pipefail

source "$SLURM_SUBMIT_DIR/bench/env.sh"
: "${BENCH_ROOT:?BENCH_ROOT must point to the TRUBA benchmark root}"
: "${EXPECTED_COMMIT:?EXPECTED_COMMIT must be exported at submission}"

repo=$(git rev-parse --show-toplevel)
actual=$(git -C "$repo" rev-parse HEAD)
test "$actual" = "$EXPECTED_COMMIT" || {
    echo "commit mismatch: expected $EXPECTED_COMMIT, found $actual" >&2
    exit 2
}
test -z "$(git -C "$repo" status --porcelain --untracked-files=no)" || {
    echo "tracked worktree is dirty" >&2
    exit 2
}

short=${EXPECTED_COMMIT:0:12}
out="$BENCH_ROOT/results/e7_kernel/${short}_${SLURM_JOB_ID}"
test ! -e "$out" || {
    echo "refusing to overwrite $out" >&2
    exit 2
}
mkdir -p "$out"

for rep in 1 2 3; do
    "$VENV/bin/python" bench/run_distance_kernel.py \
        --vectors 16384 --dim 1024 --passes 12 --core 0 \
        --expected-commit "$EXPECTED_COMMIT" \
        --output "$out/rep${rep}.json"
done

"$VENV/bin/python" - "$out" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = sorted(root.glob("rep*.json"))
reports = [json.loads(path.read_text()) for path in files]
if len(reports) != 3 or not all(item.get("checksum_consistent") for item in reports):
    raise SystemExit("kernel probe validation failed")
manifest = {
    "schema_version": 1,
    "result_count": len(files),
    "code_commit": reports[0]["code_commit"],
    "slurm_job_id": reports[0]["slurm_job_id"],
    "files": [
        {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in files
    ],
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
PY
