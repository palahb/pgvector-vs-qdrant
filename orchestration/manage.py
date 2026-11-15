#!/usr/bin/env python3
"""Render, gate, submit, inspect and safely retry TRUBA experiment deployments."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.core import (  # noqa: E402
    atomic_json,
    canonical_sha256,
    expand_stage,
    expanded_path,
    load_config,
    task_registry_path,
)


REPO = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_sbatch(deployment: dict[str, Any], deployment_path: Path) -> str:
    resources = deployment["config"]["resources"]
    count = deployment["task_count"]
    exclude = resources.get("exclude", [])
    lines = [
        "#!/bin/bash",
        f"#SBATCH -J {deployment['experiment_id'][:40]}",
        f"#SBATCH -p {resources['partition']}",
        "#SBATCH -N 1",
        "#SBATCH -n 1",
        f"#SBATCH -c {resources['cpus']}",
        f"#SBATCH --mem={resources['memory']}",
        f"#SBATCH -t {resources['time']}",
        f"#SBATCH --array=0-{count - 1}" + (
            f"%{resources['array_concurrency']}" if resources.get("array_concurrency") else ""
        ),
        "#SBATCH -o bench/logs/orchestration_%A_%a.out",
    ]
    if exclude:
        lines.append(f"#SBATCH --exclude={','.join(exclude)}")
    lines += [
        "set -euo pipefail",
        'REPO_ROOT=$(git rev-parse --show-toplevel)',
        'export BENCH_CODE="$REPO_ROOT/bench"',
        'source "$REPO_ROOT/bench/env.sh"',
        'mkdir -p "$REPO_ROOT/logs"',
        'PYTHON_EXEC=${VENV:+$VENV/bin/python}',
        'PYTHON_EXEC=${PYTHON_EXEC:-python3}',
        '"$PYTHON_EXEC" "$REPO_ROOT/orchestration/run_task.py" \\',
        f"  --deployment {deployment_path} --task-index \"$SLURM_ARRAY_TASK_ID\"",
        "",
    ]
    return "\n".join(lines)


def command_render(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty deployment directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config, REPO)
    if subprocess.run(
        ["git", "-C", str(REPO), "diff", "--quiet"], check=False
    ).returncode or subprocess.run(
        ["git", "-C", str(REPO), "diff", "--cached", "--quiet"], check=False
    ).returncode:
        raise SystemExit("refusing to render from a dirty tracked worktree")
    tasks = expand_stage(config, args.stage)
    config_hash = canonical_sha256(config)
    submission_id = args.submission_id or (
        f"{config['experiment_id']}-{args.stage}-{config['code_commit'][:8]}-{config_hash[:8]}"
    )
    deployment = {
        "schema_version": 1,
        "created_at": now(),
        "submission_id": submission_id,
        "experiment_id": config["experiment_id"],
        "stage": args.stage,
        "config_hash": config_hash,
        "code_commit": config["code_commit"],
        "task_count": len(tasks),
        "repo": str(REPO),
        "config": config,
        "tasks": tasks,
    }
    deployment_path = output / "deployment.json"
    atomic_json(deployment_path, deployment)
    script = output / "submit.sbatch"
    script.write_text(render_sbatch(deployment, deployment_path))
    script.chmod(0o755)
    print(f"rendered={submission_id} tasks={len(tasks)} output={output}")
    return 0


def smoke_gate_path(registry_root: Path, commit: str) -> Path:
    return registry_root / "gates" / f"smoke_{commit}.json"


def command_record_smoke(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("slurm", {}).get("state") != "COMPLETED":
        raise SystemExit("smoke manifest is not COMPLETED")
    if manifest.get("audit", {}).get("verdict") != "validated":
        raise SystemExit("smoke manifest audit is not validated")
    commit = manifest.get("code_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise SystemExit("smoke manifest lacks a full code commit")
    gate = {
        "schema_version": 1,
        "gate": "smoke",
        "verdict": "passed",
        "code_commit": commit,
        "slurm_job_id": manifest["slurm"]["job_id"],
        "node": manifest["slurm"]["node"],
        "manifest": str(args.manifest.resolve()),
        "recorded_at": now(),
    }
    path = smoke_gate_path(args.registry_root, commit)
    atomic_json(path, gate)
    print(f"smoke_gate={path}")
    return 0


def find_pilot_gate(registry_root: Path, deployment: dict[str, Any]) -> Path | None:
    submissions = registry_root / "submissions"
    if not submissions.exists():
        return None
    for path in submissions.glob("*/summary.json"):
        try:
            summary = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (
            summary.get("experiment_id") == deployment["experiment_id"]
            and summary.get("stage") == "pilot"
            and summary.get("code_commit") == deployment["code_commit"]
            and summary.get("verdict") == "complete"
        ):
            return path
    return None


def check_gates(deployment: dict[str, Any]) -> list[str]:
    config = deployment["config"]
    registry_root = expanded_path(config["registry_root"])
    evidence = []
    if config.get("requires_smoke", True):
        gate_path = smoke_gate_path(registry_root, deployment["code_commit"])
        if not gate_path.is_file():
            raise SystemExit(f"missing smoke gate for commit {deployment['code_commit']}: {gate_path}")
        gate = json.loads(gate_path.read_text())
        if gate.get("verdict") != "passed":
            raise SystemExit(f"smoke gate did not pass: {gate_path}")
        evidence.append(str(gate_path))
    if deployment["stage"] == "full":
        pilot = find_pilot_gate(registry_root, deployment)
        if pilot is None:
            raise SystemExit("full stage requires a completed pilot summary for the same commit")
        evidence.append(str(pilot))
    return evidence


def command_submit(args: argparse.Namespace) -> int:
    deployment = json.loads(args.deployment.read_text())
    evidence = check_gates(deployment)
    script = args.deployment.with_name("submit.sbatch")
    command = ["sbatch", "--parsable", str(script)]
    if args.dry_run:
        print(json.dumps({"command": command, "gate_evidence": evidence}, indent=2))
        return 0
    job_id = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    registry_root = expanded_path(deployment["config"]["registry_root"])
    submission = {
        "schema_version": 1,
        "submission_id": deployment["submission_id"],
        "experiment_id": deployment["experiment_id"],
        "stage": deployment["stage"],
        "code_commit": deployment["code_commit"],
        "slurm_job_id": job_id,
        "deployment": str(args.deployment.resolve()),
        "gate_evidence": evidence,
        "submitted_at": now(),
    }
    atomic_json(registry_root / "submissions" / deployment["submission_id"] / "submission.json", submission)
    print(f"submitted={deployment['submission_id']} slurm_job_id={job_id}")
    return 0


def task_records(deployment: dict[str, Any]) -> list[dict[str, Any]]:
    root = expanded_path(deployment["config"]["registry_root"])
    records = []
    for index in range(deployment["task_count"]):
        path = task_registry_path(root, deployment["submission_id"], index)
        if path.is_file():
            record = json.loads(path.read_text())
        else:
            record = {"task_index": index, "status": "missing", "attempts": []}
        records.append(record)
    return records


def summarize(deployment: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    complete = counts.get("completed", 0) == deployment["task_count"]
    nodes: dict[str, list[float]] = {}
    node_failures: dict[str, int] = {}
    for record in records:
        node = record.get("node")
        if not node:
            continue
        if record.get("duration_s") is not None:
            nodes.setdefault(node, []).append(record["duration_s"])
        if record["status"] == "failed":
            node_failures[node] = node_failures.get(node, 0) + 1
    durations = [value for values in nodes.values() for value in values]
    median = statistics.median(durations) if durations else None
    slow_nodes = sorted(
        node for node, values in nodes.items()
        if median and statistics.median(values) > 1.75 * median and len(values) >= 2
    )
    inconsistencies = []
    for record in records:
        if record.get("status") == "completed" and record.get("validator", {}).get("verdict") != "validated":
            inconsistencies.append({"task_index": record["task_index"], "problem": "completed_without_validated_result"})
        if record.get("status") == "failed" and record.get("return_code") == 0:
            inconsistencies.append({"task_index": record["task_index"], "problem": "failed_with_zero_return_code"})
        log = record.get("log")
        if record.get("status") in {"completed", "failed"} and log and not Path(log).is_file():
            inconsistencies.append({"task_index": record["task_index"], "problem": "terminal_task_log_missing", "log": log})
    return {
        "schema_version": 1,
        "submission_id": deployment["submission_id"],
        "experiment_id": deployment["experiment_id"],
        "stage": deployment["stage"],
        "code_commit": deployment["code_commit"],
        "verdict": "complete" if complete else ("failed" if counts.get("failed") else "incomplete"),
        "task_count": deployment["task_count"],
        "counts": counts,
        "consistency": {"ok": not inconsistencies, "issues": inconsistencies},
        "node_diagnostics": {
            "median_task_duration_s": median,
            "failed_tasks_by_node": node_failures,
            "slow_nodes": slow_nodes,
        },
        "updated_at": now(),
    }


def command_status(args: argparse.Namespace) -> int:
    deployment = json.loads(args.deployment.read_text())
    records = task_records(deployment)
    summary = summarize(deployment, records)
    if args.write_summary:
        root = expanded_path(deployment["config"]["registry_root"])
        atomic_json(root / "submissions" / deployment["submission_id"] / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["verdict"] == "complete" else 1


def command_retry(args: argparse.Namespace) -> int:
    deployment = json.loads(args.deployment.read_text())
    records = task_records(deployment)
    max_retries = int(deployment["config"].get("max_retries", 2))
    retry = []
    refused = []
    for record in records:
        attempts = record.get("attempts", [])
        if record["status"] == "failed":
            # attempts includes the first execution; max_retries counts additional attempts.
            if record.get("retryable") and len(attempts) <= max_retries:
                retry.append(record["task_index"])
            else:
                refused.append(record["task_index"])
    if refused:
        print(f"non_retryable_or_exhausted={','.join(map(str, refused))}")
    if not retry:
        print("no retryable tasks")
        return 0
    array = ",".join(map(str, retry))
    command = ["sbatch", "--parsable", f"--array={array}", str(args.deployment.with_name("submit.sbatch"))]
    if args.dry_run:
        print(json.dumps({"command": command, "tasks": retry}, indent=2))
        return 0
    job_id = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    print(f"retry_submitted={job_id} tasks={array}")
    return 0


def command_quota(args: argparse.Namespace) -> int:
    usage = shutil.disk_usage(args.path)
    stat = os.statvfs(args.path)
    inode_free_percent = stat.f_favail / stat.f_files * 100 if stat.f_files else 100.0
    report = {
        "path": str(args.path.resolve()),
        "free_gb": round(usage.free / 2**30, 2),
        "used_percent": round(usage.used / usage.total * 100, 2),
        "inode_free_percent": round(inode_free_percent, 2),
    }
    problems = []
    if report["free_gb"] < args.min_free_gb:
        problems.append("free_gb")
    if report["inode_free_percent"] < args.min_inode_free_percent:
        problems.append("inode_free_percent")
    report["verdict"] = "ok" if not problems else "alarm"
    report["problems"] = problems
    print(json.dumps(report, indent=2))
    return 0 if not problems else 1


def command_daily_report(args: argparse.Namespace) -> int:
    summaries = []
    for path in (args.registry_root / "submissions").glob("*/summary.json"):
        try:
            summaries.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            pass
    lines = ["# TRUBA experiment status", "", f"Generated: {now()}", "", "| Submission | Stage | Commit | Verdict | Tasks |", "|---|---|---|---|---|"]
    for item in sorted(summaries, key=lambda value: value.get("submission_id", "")):
        counts = ", ".join(f"{key}={value}" for key, value in sorted(item.get("counts", {}).items()))
        lines.append(
            f"| {item['submission_id']} | {item['stage']} | {item['code_commit'][:8]} | "
            f"{item['verdict']} | {counts} |"
        )
    text = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render")
    render.add_argument("config", type=Path)
    render.add_argument("stage", choices=["pilot", "full"])
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--submission-id")
    render.set_defaults(func=command_render)

    gate = commands.add_parser("record-smoke")
    gate.add_argument("manifest", type=Path)
    gate.add_argument("--registry-root", type=Path, required=True)
    gate.set_defaults(func=command_record_smoke)

    submit = commands.add_parser("submit")
    submit.add_argument("deployment", type=Path)
    submit.add_argument("--dry-run", action="store_true")
    submit.set_defaults(func=command_submit)

    status = commands.add_parser("status")
    status.add_argument("deployment", type=Path)
    status.add_argument("--write-summary", action="store_true")
    status.set_defaults(func=command_status)

    retry = commands.add_parser("retry")
    retry.add_argument("deployment", type=Path)
    retry.add_argument("--dry-run", action="store_true")
    retry.set_defaults(func=command_retry)

    quota = commands.add_parser("quota")
    quota.add_argument("path", type=Path)
    quota.add_argument("--min-free-gb", type=float, default=50.0)
    quota.add_argument("--min-inode-free-percent", type=float, default=10.0)
    quota.set_defaults(func=command_quota)

    daily = commands.add_parser("daily-report")
    daily.add_argument("--registry-root", type=Path, required=True)
    daily.add_argument("--output", type=Path)
    daily.set_defaults(func=command_daily_report)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.func(arguments))
