#!/usr/bin/env python3
"""Execute one immutable orchestration task and atomically record its lifecycle."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.core import atomic_json, cli_args, expanded_path, task_registry_path  # noqa: E402


REPO = Path(__file__).resolve().parents[1]


class TransientPreflightError(RuntimeError):
    """Infrastructure condition that may safely be retried on another node/later."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def storage_check(path: Path, minimum_gb: float, minimum_inode_percent: float) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(path)
    stat = os.statvfs(path)
    free_gb = usage.free / 2**30
    inode_percent = stat.f_favail / stat.f_files * 100 if stat.f_files else 100.0
    result = {
        "path": str(path),
        "free_gb": round(free_gb, 2),
        "inode_free_percent": round(inode_percent, 2),
    }
    if free_gb < minimum_gb or inode_percent < minimum_inode_percent:
        raise TransientPreflightError(f"storage preflight failed: {result}")
    return result


def load_record(path: Path, task_index: int) -> dict[str, Any]:
    if path.is_file():
        return json.loads(path.read_text())
    return {"task_index": task_index, "status": "new", "attempts": []}


def execute(deployment_path: Path, task_index: int) -> int:
    deployment = json.loads(deployment_path.read_text())
    if not 0 <= task_index < deployment["task_count"]:
        raise SystemExit(f"task index out of range: {task_index}")
    task = deployment["tasks"][task_index]
    config = deployment["config"]
    registry_root = expanded_path(config["registry_root"])
    registry_path = task_registry_path(registry_root, deployment["submission_id"], task_index)
    record = load_record(registry_path, task_index)
    attempt_number = len(record["attempts"]) + 1
    job_id = os.environ.get("SLURM_JOB_ID", "local")
    node = socket.gethostname()
    started = time.monotonic()
    attempt = {
        "attempt": attempt_number,
        "started_at": now(),
        "slurm_job_id": job_id,
        "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "node": node,
    }
    array_id = os.environ.get("SLURM_ARRAY_TASK_ID", str(task_index))
    array_job_id = os.environ.get("SLURM_ARRAY_JOB_ID", job_id)
    log_path = REPO / "bench/logs" / f"orchestration_{array_job_id}_{array_id}.out"
    record.update({
        "submission_id": deployment["submission_id"],
        "experiment_id": deployment["experiment_id"],
        "task_index": task_index,
        "job_key": task["job_key"],
        "status": "running",
        "node": node,
        "retryable": False,
        "log": str(log_path),
    })
    record["attempts"].append(attempt)
    atomic_json(registry_path, record)

    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        if commit != deployment["code_commit"]:
            raise RuntimeError(f"commit mismatch: checkout={commit} deployment={deployment['code_commit']}")
        dirty = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if dirty:
            raise RuntimeError("tracked worktree changed after deployment render")
        if node in config.get("resources", {}).get("exclude", []):
            raise TransientPreflightError(f"scheduler placed task on excluded node: {node}")

        results_root = expanded_path(os.environ.get("BENCH_RESULTS", "$BENCH_ROOT/results"))
        storage = config.get("storage", {})
        preflight = storage_check(
            results_root,
            float(storage.get("min_free_gb", 50)),
            float(storage.get("min_inode_free_percent", 10)),
        )
        output = (
            results_root / deployment["experiment_id"] / deployment["stage"] /
            deployment["submission_id"] / f"task_{task_index:04d}_{job_id}"
        )
        if output.exists():
            raise RuntimeError(f"immutable output path already exists: {output}")
        output.mkdir(parents=True)

        python_exec = Path(os.environ.get("VENV", "")) / "bin/python" if os.environ.get("VENV") else Path(sys.executable)
        if not python_exec.is_file():
            python_exec = Path(sys.executable)
        commands = []
        for run_index, run in enumerate(task["runs"]):
            experiment_id = (
                f"{deployment['submission_id']}-t{task_index:04d}-a{attempt_number}-"
                f"r{run_index:02d}-{run['engine']}"
            )
            command = [
                str(python_exec), str(REPO / "bench/run.py"), "--engine", run["engine"],
                *cli_args(run.get("args", {})), "--out", str(output), "--experiment-id", experiment_id,
            ]
            subprocess.run(command, check=True)
            commands.append(command)

        audit_path = output / "audit.json"
        validation = subprocess.run(
            [str(python_exec), str(REPO / "analysis/validate_results.py"), str(output),
             "--strict-warnings", "--output", str(audit_path)],
            check=False,
        )
        audit = json.loads(audit_path.read_text()) if audit_path.is_file() else {"verdict": "missing"}
        if validation.returncode != 0 or audit.get("verdict") != "validated":
            raise ValueError(f"strict result validation failed: return_code={validation.returncode}")

        duration = round(time.monotonic() - started, 3)
        attempt.update({"finished_at": now(), "status": "completed", "duration_s": duration})
        record.update({
            "status": "completed", "retryable": False, "return_code": 0,
            "duration_s": duration, "output": str(output), "preflight": preflight,
            "commands": commands,
            "validator": {"verdict": audit["verdict"], "report": str(audit_path)},
        })
        atomic_json(registry_path, record)
        queue_item = {
            "schema_version": 1, "status": "ready", "created_at": now(),
            "submission_id": deployment["submission_id"], "task_index": task_index,
            "output": str(output), "audit": str(audit_path),
        }
        atomic_json(registry_root / "analysis_queue" / deployment["submission_id"] / f"task_{task_index:04d}.json", queue_item)
        return 0
    except Exception as exc:
        duration = round(time.monotonic() - started, 3)
        retryable = isinstance(exc, (TransientPreflightError, OSError))
        attempt.update({"finished_at": now(), "status": "failed", "duration_s": duration, "error": str(exc)})
        record.update({
            "status": "failed", "retryable": retryable,
            "return_code": getattr(exc, "returncode", 1) or 1,
            "duration_s": duration, "error": str(exc),
        })
        atomic_json(registry_path, record)
        print(f"TASK_FAILED retryable={retryable}: {exc}", file=sys.stderr)
        return int(record["return_code"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--task-index", type=int, required=True)
    args = parser.parse_args()
    return execute(args.deployment.resolve(), args.task_index)


if __name__ == "__main__":
    raise SystemExit(main())
