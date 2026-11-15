#!/usr/bin/env python3
"""Audit benchmark result trees without modifying raw evidence.

The validator distinguishes hard integrity/schema errors from provenance gaps in older
baseline runs. It writes a deterministic JSON report that can be tracked in Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_FIELDS = {
    "args",
    "build",
    "client_cores",
    "dataset",
    "dim",
    "engine",
    "host",
    "image_sha256",
    "mode",
    "n",
    "n_queries",
    "runs",
    "server_cores",
    "server_info",
    "status",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Issue:
    severity: str
    message: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, path: str) -> None:
        self.count += 1
        if len(self.examples) < 8:
            self.examples.append(path)


class Audit:
    def __init__(self, root: Path) -> None:
        self.input_root = root.as_posix()
        self.root = root.resolve()
        self.issues: dict[str, Issue] = {}
        self.files: list[dict[str, Any]] = []
        self.experiments: Counter[str] = Counter()
        self.engines: Counter[str] = Counter()
        self.statuses: Counter[str] = Counter()

    def issue(self, code: str, severity: str, message: str, path: Path) -> None:
        relative = self.relative(path)
        item = self.issues.setdefault(code, Issue(severity=severity, message=message))
        item.add(relative)

    def relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def audit_file(self, path: Path) -> None:
        relative = self.relative(path)
        parts = Path(relative).parts
        experiment = parts[0] if parts else "unknown"
        self.experiments[experiment] += 1

        try:
            result = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.issue("invalid_json", "error", f"Result JSON cannot be read: {exc}", path)
            return

        if not isinstance(result, dict):
            self.issue("non_object_result", "error", "Top-level result must be an object", path)
            return

        missing = sorted(REQUIRED_FIELDS - result.keys())
        if missing:
            self.issue(
                "missing_required_fields",
                "error",
                "One or more required top-level fields are absent",
                path,
            )

        status = result.get("status")
        engine = result.get("engine")
        self.statuses[str(status)] += 1
        self.engines[str(engine)] += 1

        if status != "ok":
            self.issue("non_ok_status", "error", "Result status is not 'ok'", path)
        if engine not in {"pg", "qdrant"}:
            self.issue("unknown_engine", "error", "Engine must be 'pg' or 'qdrant'", path)

        for key in ("n", "dim", "n_queries"):
            value = result.get(key)
            if not isinstance(value, int) or value <= 0:
                self.issue("invalid_positive_integer", "error", f"{key} must be positive", path)

        image_sha = result.get("image_sha256")
        if not isinstance(image_sha, str) or not SHA256_RE.fullmatch(image_sha):
            self.issue("invalid_image_sha256", "error", "Container image digest is absent or invalid", path)

        host = result.get("host")
        if not isinstance(host, dict):
            self.issue("invalid_host", "error", "Host metadata must be an object", path)
            host = {}
        slurm = host.get("slurm")
        if not isinstance(slurm, dict) or not slurm.get("SLURM_JOB_ID"):
            self.issue("missing_slurm_job_id", "error", "SLURM_JOB_ID is required", path)
        if not host.get("hostname") or not host.get("time_utc"):
            self.issue("incomplete_host_identity", "error", "Host name and UTC time are required", path)

        server_info = result.get("server_info")
        if not isinstance(server_info, dict) or not server_info.get("version"):
            self.issue("missing_engine_version", "error", "Engine version is required", path)
        if engine == "pg" and isinstance(server_info, dict) and not server_info.get("pgvector"):
            self.issue("missing_pgvector_version", "error", "pgvector version is required", path)

        args = result.get("args")
        if not isinstance(args, dict):
            self.issue("invalid_args", "error", "args must be an object", path)
            args = {}
        for key in ("engine", "n", "dim"):
            if key in result and args.get(key) != result.get(key):
                self.issue("args_result_mismatch", "error", f"args.{key} disagrees with result.{key}", path)

        server_cores = result.get("server_cores")
        client_cores = result.get("client_cores")
        if not isinstance(server_cores, list) or not server_cores:
            self.issue("invalid_server_cores", "error", "Server core list is empty or invalid", path)
            server_cores = []
        if not isinstance(client_cores, list) or not client_cores:
            self.issue("invalid_client_cores", "error", "Client core list is empty or invalid", path)
            client_cores = []
        if set(server_cores) & set(client_cores):
            self.issue("overlapping_cores", "error", "Server and client core sets overlap", path)

        build = result.get("build")
        if not isinstance(build, dict) or not build:
            self.issue("missing_build", "error", "Build measurements are absent", path)
        elif not isinstance(build.get("total_s"), (int, float)) or build.get("total_s", 0) <= 0:
            self.issue("invalid_build_time", "error", "build.total_s must be positive", path)

        runs = result.get("runs")
        if not isinstance(runs, list):
            self.issue("invalid_runs", "error", "runs must be a list", path)

        raw_path = path.with_name("raw.npz")
        if not raw_path.is_file():
            self.issue("missing_raw_npz", "error", "Sibling raw.npz is missing", path)
            raw_keys: list[str] = []
            raw_size = None
        else:
            raw_size = raw_path.stat().st_size
            try:
                with np.load(raw_path, allow_pickle=False) as raw:
                    raw_keys = sorted(raw.files)
            except Exception as exc:  # corrupted zip/npy headers or unsupported object arrays
                self.issue("invalid_raw_npz", "error", f"raw.npz cannot be opened: {exc}", path)
                raw_keys = []

        # The frozen 2026 baseline predates these fields. They are warnings, not fabricated.
        for field_name, code, message in (
            ("schema_version", "missing_schema_version", "Result schema version is absent"),
            ("code_commit", "missing_code_commit", "Code commit SHA is absent"),
            ("config_id", "missing_config_id", "Stable experiment configuration ID is absent"),
            ("seed", "missing_seed", "Explicit random seed is absent"),
        ):
            if field_name not in result:
                self.issue(code, "warning", message, path)

        self.files.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "experiment": experiment,
                "engine": engine,
                "status": status,
                "slurm_job_id": slurm.get("SLURM_JOB_ID") if isinstance(slurm, dict) else None,
                "raw_npz_size_bytes": raw_size,
                "raw_array_count": len(raw_keys),
            }
        )

    def report(self) -> dict[str, Any]:
        errors = sum(issue.count for issue in self.issues.values() if issue.severity == "error")
        warnings = sum(issue.count for issue in self.issues.values() if issue.severity == "warning")
        if errors:
            verdict = "invalid"
        elif warnings:
            verdict = "usable_with_provenance_gaps"
        else:
            verdict = "validated"
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "root": self.input_root,
            "verdict": verdict,
            "summary": {
                "result_files": len(self.files),
                "errors": errors,
                "warnings": warnings,
                "experiments": dict(sorted(self.experiments.items())),
                "engines": dict(sorted(self.engines.items())),
                "statuses": dict(sorted(self.statuses.items())),
            },
            "issues": {
                code: {
                    "severity": issue.severity,
                    "message": issue.message,
                    "count": issue.count,
                    "examples": issue.examples,
                }
                for code, issue in sorted(self.issues.items())
            },
            "files": sorted(self.files, key=lambda item: item["path"]),
        }


def validate(root: Path) -> dict[str, Any]:
    audit = Audit(root)
    for path in sorted(root.glob("**/result.json")):
        audit.audit_file(path)
    if not audit.files and "invalid_json" not in audit.issues:
        audit.issue("no_results", "error", "No result.json files found", root)
    return audit.report()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Root containing experiment result directories")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    parser.add_argument("--strict-warnings", action="store_true", help="Return non-zero for warnings too")
    args = parser.parse_args()

    report = validate(args.root)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered)
        temporary.replace(args.output)
    else:
        print(rendered, end="")

    print(
        f"verdict={report['verdict']} files={report['summary']['result_files']} "
        f"errors={report['summary']['errors']} warnings={report['summary']['warnings']}",
    )
    if report["summary"]["errors"]:
        return 1
    if args.strict_warnings and report["summary"]["warnings"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
