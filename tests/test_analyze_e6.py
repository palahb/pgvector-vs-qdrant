from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from analysis.analyze_e6 import analyze, interval  # noqa: E402


def result(tag: str, actual_segments: int = 2) -> dict:
    return {
        "experiment_id": f"e6-{tag}", "engine": "qdrant", "n": 100,
        "args": {"tag": tag, "qdrant_segments": 2, "qdrant_search_threads": 1, "qdrant_require_indexed": True},
        "build": {"actual_segments": actual_segments, "fully_indexed": True},
        "runs": [{"mem_limit": "none", "conc_matched_ef": 64, "latency": [
            {"proto": "grpc_raw", "ef": 32, "rep": 0, "recall_at_k": 0.91, "mean_ms": 1.0, "p99_ms": 2.0, "server_cpu_ms_per_query": 0.5, "client_cpu_ms_per_query": 0.2},
            {"proto": "grpc_raw", "ef": 64, "rep": 0, "recall_at_k": 0.96, "mean_ms": 1.5, "p99_ms": 2.5, "server_cpu_ms_per_query": 0.8, "client_cpu_ms_per_query": 0.2},
        ], "concurrency": [
            {"proto": "grpc_raw", "ef": 64, "clients": 4, "recall_at_k": 0.96,
             "throughput_qps": 1000.0, "mean_ms": 4.0, "p99_ms": 5.0,
             "server_cpu_ms_per_query": 0.9, "client_cpu_ms_per_query": 0.3,
             "server_cores_busy": 0.9, "client_cores_busy": 0.3}
        ]}],
    }


class E6AnalysisTests(unittest.TestCase):
    def test_interval_uses_t_interval_for_three_builds(self) -> None:
        stats = interval([1.0, 2.0, 3.0])
        self.assertEqual(stats["mean"], 2.0)
        self.assertLess(stats["ci95_low"], 0)

    def test_three_valid_builds_form_complete_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(3):
                path = root / f"rep{index + 1}" / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps(result(f"rep{index + 1}")))
            report = analyze(root, [0.90, 0.95])
        self.assertEqual(report["verdict"], "valid")
        self.assertEqual(report["control_cells"][0]["build_count"], 3)
        self.assertEqual(len(report["matched_recall_aggregates"]), 2)
        self.assertEqual(len(report["matched_concurrency_aggregates"]), 1)

    def test_segment_target_difference_is_recorded_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(3):
                path = root / f"rep{index + 1}" / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps(result(f"rep{index + 1}", actual_segments=3 if index == 0 else 2)))
            report = analyze(root, [0.90])
        self.assertEqual(report["verdict"], "valid")
        self.assertTrue(any(
            item["observation"] == "actual_segment_count_differs_from_optimizer_target"
            for item in report["observations"]
        ))


if __name__ == "__main__":
    unittest.main()
