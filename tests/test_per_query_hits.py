from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

import workload  # noqa: E402


class FakeServer:
    name = "fake"

    def query_spec(self, ef, proto, k):
        return {"ef": ef, "proto": proto, "k": k}

    def stats_begin(self, proto):
        pass

    def stats_end(self, proto):
        return {}

    def cpu_seconds(self):
        return 0.0


class PerQueryHitsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queries = np.arange(6, dtype=np.float32).reshape(6, 1)
        # ground truth: each query's neighbors are {10*i, 10*i+1}
        self.gt = np.array([[10 * i, 10 * i + 1] for i in range(6)])
        # the fake index returns both neighbors for even queries, one for queries 1 and 3, none for 5
        self.answers = {0: [0, 1], 1: [10], 2: [20, 21], 3: [31], 4: [40, 41], 5: [99]}

    def run_sweep(self, reps: int = 2):
        def factory(spec):
            return lambda vec: self.answers[int(vec[0])]
        with patch.object(workload, "make_query_fn", side_effect=factory):
            return workload.latency_sweep(FakeServer(), ["p"], [16, 32], reps, self.queries, [], self.gt, 2)

    def test_hits_are_stored_per_query_for_every_ef_and_repetition(self) -> None:
        _rows, raw = self.run_sweep(reps=2)
        for ef in (16, 32):
            for rep in (0, 1):
                self.assertIn(f"hits_p_ef{ef}_rep{rep}", raw)

    def test_values_are_the_number_of_ground_truth_neighbors_returned(self) -> None:
        _rows, raw = self.run_sweep(reps=1)
        self.assertEqual(raw["hits_p_ef16_rep0"].tolist(), [2, 1, 2, 1, 2, 0])

    def test_the_reported_recall_equals_the_mean_of_the_per_query_array(self) -> None:
        rows, raw = self.run_sweep(reps=1)
        row = next(r for r in rows if r["ef"] == 16)
        self.assertAlmostEqual(row["recall_at_k"], raw["hits_p_ef16_rep0"].sum() / (2 * 6), places=5)

    def test_latency_arrays_are_still_stored(self) -> None:
        _rows, raw = self.run_sweep(reps=1)
        self.assertEqual(len(raw["lat_p_ef16_rep0"]), 6)


if __name__ == "__main__":
    unittest.main()
