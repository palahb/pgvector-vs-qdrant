#!/bin/bash
# One-command audit of code, the frozen E1-E5 baseline and all current paper artifacts.
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON_BIN:-python3}
results=${BASELINE_RESULTS:-$repo/../artifacts/remote-archives/2026-11-14_baseline/extracted/results}
work=$(mktemp -d "${TMPDIR:-/tmp}/pgvector-baseline-verify.XXXXXX")

echo "repo=$repo"
echo "python=$python_bin"
echo "results=$results"
echo "verification_output=$work"

cd "$repo"

"$python_bin" -m unittest discover -s tests -v
"$python_bin" -m compileall -q bench analysis tests
for file in bench/*.sh bench/slurm/*.sbatch scripts/*.sh; do
    bash -n "$file"
done
python3 -m json.tool schemas/result-v2.schema.json >/dev/null

"$python_bin" analysis/validate_results.py "$results" \
    --output "$work/baseline_audit.json"
"$python_bin" analysis/adapt_legacy_results.py "$results" \
    --output "$work/adapted_results_v2.jsonl"
"$python_bin" analysis/build_paper_source_index.py "$results" \
    --output "$work/paper_source_index.json"
"$python_bin" analysis/reconcile_m6.py "$results" \
    --output "$work/m6_throughput_reconciliation.json"
"$python_bin" analysis/verify_figure_reproduction.py "$results" paper/figures \
    --output "$work/figure_reproduction.json"

echo "VERIFY_BASELINE_OK output=$work"
