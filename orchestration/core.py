from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def slug(value: Any) -> str:
    result = SLUG_RE.sub("-", str(value)).strip("-")
    return result or "value"


def git_commit(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_config(path: Path, repo: Path | None = None) -> dict[str, Any]:
    config = json.loads(path.read_text())
    if config.get("schema_version") != 1:
        raise ValueError("experiment config schema_version must be 1")
    if not config.get("experiment_id") or not isinstance(config.get("stages"), dict):
        raise ValueError("experiment_id and stages are required")
    resources = config.get("resources")
    if not isinstance(resources, dict):
        raise ValueError("resources is required")
    missing_resources = {"partition", "cpus", "memory", "time"} - resources.keys()
    if missing_resources:
        raise ValueError(f"missing resources: {sorted(missing_resources)}")
    if not isinstance(resources["cpus"], int) or resources["cpus"] < 1:
        raise ValueError("resources.cpus must be a positive integer")
    if not {"pilot", "full"}.issubset(config["stages"]):
        raise ValueError("stages must define pilot and full")
    if config.get("code_commit") in (None, "AUTO"):
        if repo is None:
            raise ValueError("repo is required to resolve code_commit=AUTO")
        config["code_commit"] = git_commit(repo)
    if not re.fullmatch(r"[0-9a-f]{40}", config["code_commit"]):
        raise ValueError("code_commit must resolve to a full Git SHA")
    # Expanding both mandatory stages validates jobs/matrices before a deployment exists.
    expand_stage(config, "pilot")
    expand_stage(config, "full")
    return config


def expand_stage(config: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    if stage not in config["stages"]:
        raise ValueError(f"stage not defined: {stage}")
    definition = config["stages"][stage]
    if "jobs" in definition:
        jobs = definition["jobs"]
        if not isinstance(jobs, list) or not jobs:
            raise ValueError(f"stage {stage} jobs must be a non-empty list")
        return jobs

    matrix = definition.get("matrix", {})
    if not matrix or not all(isinstance(values, list) and values for values in matrix.values()):
        raise ValueError(f"stage {stage} requires jobs or a non-empty matrix")
    keys = list(matrix)
    engines = definition.get("engines", ["pg", "qdrant"])
    base_args = config.get("base_args", {}) | definition.get("base_args", {})
    engine_args = config.get("engine_args", {}) | definition.get("engine_args", {})
    jobs = []
    for values in itertools.product(*(matrix[key] for key in keys)):
        factors = dict(zip(keys, values))
        job_key = "_".join(f"{slug(key)}-{slug(value)}" for key, value in factors.items())
        shared = base_args | factors
        runs = [
            {"engine": engine, "args": shared | engine_args.get(engine, {})}
            for engine in engines
        ]
        jobs.append({"job_key": job_key, "factors": factors, "runs": runs})
    return jobs


def cli_args(values: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, value in values.items():
        if value is None or value is False:
            continue
        flag = "--" + key.replace("_", "-")
        if value is True:
            args.append(flag)
        elif isinstance(value, list):
            args.extend([flag, ",".join(map(str, value))])
        else:
            args.extend([flag, str(value)])
    return args


def expanded_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value)))


def task_registry_path(registry_root: Path, submission_id: str, task_index: int) -> Path:
    return registry_root / "submissions" / submission_id / "tasks" / f"task_{task_index:04d}.json"
