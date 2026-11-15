from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

import common  # noqa: E402
import workload  # noqa: E402


class CommonTests(unittest.TestCase):
    def test_normalize_handles_zero_rows(self) -> None:
        values = np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32)
        normalized = common.normalize(values)
        np.testing.assert_allclose(normalized[0], [0.6, 0.8], rtol=1e-6)
        np.testing.assert_array_equal(normalized[1], [0.0, 0.0])

    def test_synthetic_vectors_are_repeatable_and_normalized(self) -> None:
        base_a, queries_a, tag_a = common.load_vectors(32, 16, synthetic=1, seed=7)
        base_b, queries_b, tag_b = common.load_vectors(32, 16, synthetic=1, seed=7)
        self.assertEqual(tag_a, "synth7")
        self.assertEqual(tag_a, tag_b)
        np.testing.assert_array_equal(base_a, base_b)
        np.testing.assert_array_equal(queries_a, queries_b)
        np.testing.assert_allclose(np.linalg.norm(base_a, axis=1), 1.0, rtol=1e-5)

    def test_ground_truth_is_cached_and_sorted(self) -> None:
        base = np.eye(4, dtype=np.float32)
        queries = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as directory:
            previous = common.CACHE_DIR
            common.CACHE_DIR = directory
            try:
                first = common.ground_truth(base, queries, 2, "unit")
                second = common.ground_truth(base, queries, 2, "unit")
            finally:
                common.CACHE_DIR = previous
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first[0, 0], 0)

    def test_latency_summary_and_cpu_specs(self) -> None:
        summary = common.summarize(np.array([1_000_000, 2_000_000, 3_000_000]))
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["mean_ms"], 2.0)
        self.assertEqual(common.parse_cpus("0-2,5,7-8"), [0, 1, 2, 5, 7, 8])
        self.assertEqual(common.fmt_cpus([8, 2, 5]), "2,5,8")

    def test_recall_hits_deduplicates_returned_ids(self) -> None:
        self.assertEqual(workload.recall_hits([1, 1, 2, 9], np.array([1, 2, 3])), 2)

    def test_stable_id_is_order_independent(self) -> None:
        self.assertEqual(common.stable_id({"a": 1, "b": [2]}), common.stable_id({"b": [2], "a": 1}))
        self.assertNotEqual(common.stable_id({"a": 1}), common.stable_id({"a": 2}))


if __name__ == "__main__":
    unittest.main()
