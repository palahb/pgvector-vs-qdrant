from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from orchestration.core import canonical_sha256, cli_args, expand_stage, load_config  # noqa: E402


class OrchestrationCoreTests(unittest.TestCase):
    def test_matrix_expansion_keeps_engines_on_same_job(self) -> None:
        config = {
            "stages": {
                "pilot": {
                    "matrix": {"n": [100, 200], "dim": [64]},
                    "engines": ["pg", "qdrant"],
                }
            },
            "base_args": {"reps": 3},
            "engine_args": {"qdrant": {"protocols": ["grpc_raw"]}},
        }
        jobs = expand_stage(config, "pilot")
        self.assertEqual(len(jobs), 2)
        self.assertEqual([run["engine"] for run in jobs[0]["runs"]], ["pg", "qdrant"])
        self.assertEqual(jobs[0]["runs"][0]["args"]["reps"], 3)
        self.assertEqual(jobs[0]["runs"][1]["args"]["protocols"], ["grpc_raw"])

    def test_cli_args_do_not_use_shell_evaluation(self) -> None:
        self.assertEqual(
            cli_args({"perf": True, "keep": False, "ef": [16, 32], "tag": "safe value"}),
            ["--perf", "--ef", "16,32", "--tag", "safe value"],
        )

    def test_canonical_hash_is_order_independent(self) -> None:
        self.assertEqual(canonical_sha256({"a": 1, "b": 2}), canonical_sha256({"b": 2, "a": 1}))

    def test_config_rejects_missing_resources(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({
                "schema_version": 1, "experiment_id": "bad", "code_commit": "0" * 40,
                "stages": {"pilot": {"matrix": {"n": [1]}}, "full": {"matrix": {"n": [1]}}},
            }))
            with self.assertRaisesRegex(ValueError, "resources"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
