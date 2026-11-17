import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e8 import analyze, interpolate, per_ef_curve  # noqa: E402


def curve():
    return [
        {"ef": 32.0, "recall_at_k": 0.80, "mean_ms": 1.0},
        {"ef": 64.0, "recall_at_k": 0.90, "mean_ms": 2.0},
        {"ef": 128.0, "recall_at_k": 0.96, "mean_ms": 4.0},
    ]


def result(tag: str, shift: float = 0.0) -> dict:
    rows = []
    for ef, recall, ms in ((32, 0.80, 1.0), (64, 0.90, 2.0), (128, 0.96, 4.0)):
        for rep in range(3):
            rows.append({"proto": "pg", "ef": ef, "rep": rep, "recall_at_k": recall + shift, "mean_ms": ms})
    return {
        "experiment_id": f"e8-{tag}", "engine": "pg", "n": 1000,
        "args": {"m": 16, "efc": 64, "tag": tag},
        "build": {"total_s": 10.0},
        "runs": [{"mem_limit": "none", "latency": rows, "concurrency": []}],
    }


class AnalyzeE8Tests(unittest.TestCase):
    def test_interpolates_between_bracketing_points(self) -> None:
        point = interpolate(curve(), 0.93)
        self.assertAlmostEqual(point["mean_ms"], 3.0)
        expected_ef = math.exp(math.log(64) + 0.5 * (math.log(128) - math.log(64)))
        self.assertAlmostEqual(point["ef"], expected_ef)
        self.assertFalse(point["extrapolated_below_grid"])

    def test_target_not_reached_returns_none(self) -> None:
        self.assertIsNone(interpolate(curve(), 0.99))

    def test_target_below_first_point_is_flagged(self) -> None:
        point = interpolate(curve(), 0.5)
        self.assertTrue(point["extrapolated_below_grid"])
        self.assertEqual(point["ef"], 32.0)

    def test_repetitions_are_averaged_per_ef(self) -> None:
        rows = [
            {"proto": "pg", "ef": 64, "recall_at_k": 0.9, "mean_ms": 1.0},
            {"proto": "pg", "ef": 64, "recall_at_k": 0.9, "mean_ms": 3.0},
            {"proto": "other", "ef": 64, "recall_at_k": 0.1, "mean_ms": 9.0},
        ]
        self.assertEqual(per_ef_curve(rows, "pg")[0]["mean_ms"], 2.0)

    def test_variance_is_reported_across_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, shift in enumerate((-0.01, 0.0, 0.01)):
                path = root / f"rep{index + 1}" / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps(result(f"rep{index + 1}", shift)))
            report = analyze(root, [0.95])
        self.assertEqual(report["verdict"], "valid")
        recall = next(a for a in report["aggregates"] if a["metric"] == "recall@ef128")
        self.assertEqual(recall["stats"]["n"], 3)
        self.assertGreater(recall["stats"]["sd"], 0)

    def test_target_below_grid_is_observed_and_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(3):
                path = root / f"rep{index + 1}" / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps(result(f"rep{index + 1}")))
            report = analyze(root, [0.5])
        self.assertEqual(report["verdict"], "valid")
        self.assertEqual(len(report["observations"]), 3)
        self.assertFalse(any(a["metric"].endswith("@0.5") for a in report["aggregates"]))

    def test_fewer_than_three_builds_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rep1" / "result.json"
            path.parent.mkdir()
            path.write_text(json.dumps(result("rep1")))
            report = analyze(Path(directory), [0.95])
        self.assertEqual(report["verdict"], "invalid")
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in report["issues"]))


if __name__ == "__main__":
    unittest.main()
