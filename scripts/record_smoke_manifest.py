#!/usr/bin/env python3
"""Write data-manifests/smoke_<job>.json from a copied smoke result tree and its audit.

usage: record_smoke_manifest.py JOB FULL_COMMIT NODE_INFO_FROM_SACCT_STATE,EXIT,ELAPSED,NODE
The result tree is expected at ../artifacts/truba-smoke/<job> with audit.json inside."""
import hashlib
import json
import os
import sys

job, commit, sacct = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
base = f"../artifacts/truba-smoke/{job}"
audit = json.load(open(f"{base}/audit.json"))
files, ids, dirty, status, schema = {}, [], set(), set(), set()
for d in sorted(os.listdir(base)):
    p = f"{base}/{d}"
    if not os.path.isdir(p):
        continue
    for f in ("result.json", "raw.npz"):
        files[f"{d}/{f}"] = hashlib.sha256(open(f"{p}/{f}", "rb").read()).hexdigest()
    r = json.load(open(f"{p}/result.json"))
    assert r["code_commit"] == commit, (d, r["code_commit"])
    ids.append(r["experiment_id"]); dirty.add(r["code_dirty"]); status.add(r["provenance_status"]); schema.add(r["schema_version"])
assert dirty == {False}
short = commit[:12]
manifest = {
    "schema_version": 1, "experiment_id": f"smoke_{job}",
    "purpose": f"Commit-specific smoke gate for {commit[:7]}",
    "slurm": {"job_id": job, "state": sacct[0], "exit_code": sacct[1], "elapsed": sacct[2], "node": sacct[3]},
    "code_commit": commit, "remote_path": f"/arf/scratch/endemir/rag_bench/results/smoke/{short}_{job}",
    "workspace_path": base,
    "audit": {"verdict": audit["verdict"], "result_files": audit["summary"]["result_files"],
              "errors": audit["summary"]["errors"], "warnings": audit["summary"]["warnings"],
              "tracked_report": f"results/validated/smoke_{job}_audit.json"},
    "provenance_assertions": {"schema_version": sorted(schema)[0], "provenance_status": sorted(status)[0],
                              "code_dirty": False, "unique_experiment_ids": len(set(ids)) == len(ids)},
    "files": files,
}
json.dump(manifest, open(f"data-manifests/smoke_{job}.json", "w"), indent=2)
print(manifest["slurm"], manifest["audit"])
