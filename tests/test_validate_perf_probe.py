from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from analysis.validate_perf_probe import validate  # noqa: E402


class PerfProbeValidationTests(unittest.TestCase):
    def test_both_engines_with_cycles_and_instructions_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for engine in ("pg", "qdrant"):
                path = root / engine / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps({
                    "engine": engine,
                    "runs": [{"concurrency": [{
                        "perf": {"cycles:u": 1000.0, "instructions:u": 2000.0},
                        "perf_derived": {"instructions_per_cycle": 2.0},
                    }]}],
                }))
            report = validate(root)
        self.assertEqual(report["verdict"], "validated")
        self.assertEqual(report["engines"]["pg"]["derived_metrics_present"], 1)

    def test_unsupported_required_counter_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "pg/result.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "engine": "pg", "runs": [{"concurrency": [{
                    "perf": {"cycles:u": "<not supported>", "instructions:u": 10.0}
                }]}],
            }))
            report = validate(root)
        self.assertEqual(report["verdict"], "invalid_or_incomplete")


if __name__ == "__main__":
    unittest.main()
