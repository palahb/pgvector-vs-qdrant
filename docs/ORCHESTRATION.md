# TRUBA experiment orchestration

The orchestration layer turns a reviewed JSON configuration into an immutable Slurm
array deployment. It keeps PostgreSQL/pgvector and Qdrant runs for one matrix point on
the same node and executes them sequentially, preserving the paired comparison.
`resources.array_concurrency` optionally caps simultaneously running array elements so
large pilots do not create an uncontrolled storage or scheduler burst.

## Safety gates

1. Render only from a clean tracked checkout and pin the full Git commit in
   `deployment.json`.
2. A successful synthetic smoke manifest for that exact commit must be recorded before
   any pilot can be submitted.
3. A full deployment additionally requires a completed pilot summary for the same
   experiment and commit.
4. Each task uses a new result directory. Existing raw output is never overwritten.
5. Failed benchmark or validation tasks are not retried automatically. Only transient
   preflight/infrastructure failures are eligible, with a bounded retry count.

## Operator workflow

Run these commands on ARF from the repository root after sourcing `bench/env.sh`:

```bash
$VENV/bin/python orchestration/manage.py render configs/examples/e1_revalidation.json pilot \
  --output runtime/deployments/e1-pilot
$VENV/bin/python orchestration/manage.py record-smoke data-manifests/smoke_JOB.json \
  --registry-root "$BENCH_ROOT/orchestration"
$VENV/bin/python orchestration/manage.py submit runtime/deployments/e1-pilot/deployment.json --dry-run
$VENV/bin/python orchestration/manage.py submit runtime/deployments/e1-pilot/deployment.json
$VENV/bin/python orchestration/manage.py status runtime/deployments/e1-pilot/deployment.json --write-summary
```

Inspect a retry before removing `--dry-run`:

```bash
$VENV/bin/python orchestration/manage.py retry runtime/deployments/e1-pilot/deployment.json --dry-run
```

Quota and daily reporting are read-only:

```bash
$VENV/bin/python orchestration/manage.py quota "$BENCH_RESULTS" --min-free-gb 100
$VENV/bin/python orchestration/manage.py daily-report --registry-root "$BENCH_ROOT/orchestration" \
  --output runtime/daily-status.md
```

Completed task records contain the output path, command vectors, node, duration, attempt
history and strict validator verdict. A matching item is atomically created below
`$BENCH_ROOT/orchestration/analysis_queue/`; downstream analysis must consume only these
validated queue items.
