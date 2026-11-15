from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "analysis"))

from adapt_legacy_results import adapt_result  # noqa: E402


class AdaptLegacyResultsTests(unittest.TestCase):
    def test_adapter_preserves_every_legacy_value(self) -> None:
        legacy = {
            "engine": "pg",
            "args": {"n": 10, "ef": [16, 32]},
            "runs": [{"latency": [1, 2]}],
            "custom_unknown_field": {"kept": True},
        }
        before = copy.deepcopy(legacy)
        adapted = adapt_result(legacy, "e1/run/result.json", "a" * 64)
        self.assertEqual(legacy, before)
        for key, value in before.items():
            self.assertEqual(adapted[key], value)
        self.assertEqual(adapted["schema_version"], 2)
        self.assertEqual(adapted["provenance_status"], "legacy_incomplete")
        self.assertIn("code_commit", adapted["legacy_source"]["missing_provenance"])

    def test_adapter_identity_is_deterministic_and_source_sensitive(self) -> None:
        legacy = {"args": {"n": 10}}
        first = adapt_result(legacy, "one/result.json", "a" * 64)
        again = adapt_result(legacy, "one/result.json", "a" * 64)
        other = adapt_result(legacy, "two/result.json", "b" * 64)
        self.assertEqual(first["experiment_id"], again["experiment_id"])
        self.assertNotEqual(first["experiment_id"], other["experiment_id"])
        self.assertEqual(first["config_id"], other["config_id"])


if __name__ == "__main__":
    unittest.main()
