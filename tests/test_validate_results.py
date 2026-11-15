from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "analysis"))

from validate_results import validate  # noqa: E402


def valid_result() -> dict:
    return {
        "schema_version": 1,
        "experiment_id": "unit-pg-1",
        "code_commit": "a" * 40,
        "config_id": "unit",
        "seed": 42,
        "args": {"engine": "pg", "n": 10, "dim": 4},
        "build": {"total_s": 1.0},
        "client_cores": [1],
        "dataset": "synthetic",
        "dim": 4,
        "engine": "pg",
        "host": {
            "hostname": "node",
            "time_utc": "2026-01-01T00:00:00Z",
            "slurm": {"SLURM_JOB_ID": "1"},
        },
        "image_sha256": "b" * 64,
        "mode": "arf",
        "n": 10,
        "n_queries": 2,
        "runs": [],
        "server_cores": [0],
        "server_info": {"version": "PostgreSQL 17", "pgvector": "0.8.6"},
        "status": "ok",
    }


class ValidateResultsTests(unittest.TestCase):
    def write_fixture(self, root: Path, result: dict, raw: bool = True) -> None:
        run = root / "e0" / "run"
        run.mkdir(parents=True)
        (run / "result.json").write_text(json.dumps(result))
        if raw:
            np.savez(run / "raw.npz", latency=np.array([1, 2], dtype=np.int64))

    def test_valid_fixture_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_fixture(root, valid_result())
            report = validate(root)
        self.assertEqual(report["verdict"], "validated")
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["warnings"], 0)

    def test_missing_raw_and_provenance_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = valid_result()
            for key in ("schema_version", "code_commit", "config_id", "seed"):
                result.pop(key)
            self.write_fixture(root, result, raw=False)
            report = validate(root)
        self.assertEqual(report["verdict"], "invalid")
        self.assertEqual(report["issues"]["missing_raw_npz"]["count"], 1)
        self.assertEqual(report["issues"]["missing_code_commit"]["severity"], "warning")

    def test_schema_v2_duplicate_experiment_id_conflict_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = valid_result()
            first["schema_version"] = 2
            first["experiment_id"] = "same-id"
            self.write_fixture(root, first)
            second = dict(first)
            second["n_queries"] = 3
            run = root / "e0" / "other"
            run.mkdir(parents=True)
            (run / "result.json").write_text(json.dumps(second))
            np.savez(run / "raw.npz", latency=np.array([1], dtype=np.int64))
            report = validate(root)
        self.assertEqual(report["verdict"], "invalid")
        self.assertEqual(report["issues"]["conflicting_experiment_id"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
