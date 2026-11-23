import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e23 import analyze, bootstrap_ci, query_metrics  # noqa: E402

JUDGMENTS = {"schema_version": 1, "queries": {
    "a": {"query_index": 0, "year": "2021", "relevant_docs_in_prefix": {"d": 3},
          "segments": {"10": 3, "11": 3, "12": 1}},
    "b": {"query_index": 1, "year": "2022", "relevant_docs_in_prefix": {"e": 2}, "segments": {"20": 2}},
}}


class QueryMetricsTests(unittest.TestCase):
    def test_found_item_at_rank_one(self):
        m = query_metrics([10, 99], {"10": 3, "11": 3, "12": 1}, k=2)
        ideal = 3 + 3 / math.log2(3)
        self.assertAlmostEqual(m["ndcg"], 3 / ideal)
        self.assertEqual(m["mrr"], 1.0)
        self.assertAlmostEqual(m["recall"], 1 / 2)   # one of min(2, 2 relevant segments)

    def test_nothing_found(self):
        m = query_metrics([1, 2, 3], {"20": 2}, k=3)
        self.assertEqual((m["ndcg"], m["mrr"], m["recall"]), (0.0, 0.0, 0.0))


class BootstrapTests(unittest.TestCase):
    def test_interval_contains_the_mean_and_is_seeded(self):
        values = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        a = bootstrap_ci(values, seed=1)
        self.assertEqual(a, bootstrap_ci(values, seed=1))
        self.assertLessEqual(a[0], 0.3)
        self.assertGreaterEqual(a[1], 0.3)


def write_build(root, engine, rep, ids_by_ef):
    proto = "pg" if engine == "pg" else "grpc_raw"
    d = root / f"{engine}_{rep}"
    d.mkdir(parents=True)
    rows = [{"proto": proto, "ef": ef, "rep": 0, "recall_at_k": r} for ef, (_, r) in ids_by_ef.items()]
    (d / "result.json").write_text(json.dumps({
        "experiment_id": f"e23-{engine}-{rep}", "engine": engine, "n": 1000, "status": "ok", "args": {"tag": rep},
        "runs": [{"mem_limit": "none", "latency": rows}]}))
    np.savez(d / "raw.npz", **{f"none_ids_{proto}_ef{ef}_rep0": np.array(ids) for ef, (ids, _) in ids_by_ef.items()})


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "judgments.json").write_text(json.dumps(JUDGMENTS))
        # exact neighbors (k=2) for 3 queries; queries 0 and 1 are judged
        self.gt = np.array([[10, 11], [20, 30], [40, 41]])
        np.save(self.root / "gt.npy", self.gt)
        good = [[10, 11], [20, 30], [40, 41]]
        weak = [[10, 99], [31, 32], [40, 99]]
        for rep in ("rep1", "rep2", "rep3"):
            write_build(self.root / "res", "pg", rep, {64: (weak, 0.5), 128: (good, 1.0)})
            write_build(self.root / "res", "qdrant", rep, {64: (good, 1.0), 128: (good, 1.0)})

    def tearDown(self):
        self.tmp.cleanup()

    def run_analysis(self):
        return analyze(self.root / "res", self.root / "judgments.json", self.root / "gt.npy", k=2, target=0.95)

    def get(self, report, engine, ef, metric):
        for item in report["by_ef"]:
            if (item["engine"], item["ef"]) == (engine, ef):
                return item[metric]
        self.fail("missing")

    def test_exact_search_is_the_reference(self):
        r = self.run_analysis()
        self.assertEqual(r["queries"], 2)
        self.assertAlmostEqual(r["exact"]["ndcg"], 1.0)      # exact top-2 holds the best items of both queries

    def test_exact_ndcg_is_below_one_when_the_best_items_are_not_the_nearest(self):
        np.save(self.root / "gt.npy", np.array([[12, 99], [30, 31], [40, 41]]))
        r = self.run_analysis()
        self.assertLess(r["exact"]["ndcg"], 1.0)

    def test_ratio_of_ann_to_exact(self):
        r = self.run_analysis()
        self.assertAlmostEqual(self.get(r, "qdrant", 64, "ndcg_ratio"), 1.0)
        self.assertLess(self.get(r, "pg", 64, "ndcg_ratio"), 1.0)
        self.assertAlmostEqual(self.get(r, "pg", 128, "ndcg_ratio"), 1.0)

    def test_ann_recall_is_reported_beside_the_ndcg_ratio(self):
        r = self.run_analysis()
        self.assertAlmostEqual(self.get(r, "pg", 64, "ann_recall_all_queries"), 1 / 3)   # 1/2, 0 and 1/2 of the exact neighbors

    def test_matched_recall_point_is_the_smallest_ef_reaching_the_target(self):
        r = self.run_analysis()
        self.assertEqual(r["matched"]["pg"]["ef"], 128)
        self.assertEqual(r["matched"]["qdrant"]["ef"], 64)

    def test_three_builds_are_counted(self):
        r = self.run_analysis()
        self.assertEqual(r["builds"], {"pg": 3, "qdrant": 3})


class ConfigTests(unittest.TestCase):
    def test_every_run_parses_with_the_bench_cli_and_stores_ids(self):
        from unittest.mock import patch
        from orchestration.core import cli_args
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
        import run
        config = json.loads((Path(__file__).resolve().parents[1] / "configs/examples/e23_ranking_quality.json").read_text())
        for stage, expected in (("pilot", 2), ("full", 6)):
            jobs = config["stages"][stage]["jobs"]
            self.assertEqual(len(jobs), expected)
            for job in jobs:
                for item in job["runs"]:
                    with patch.object(sys, "argv", ["run.py", "--engine", item["engine"], "--out", "/tmp/x",
                                                    *cli_args(item["args"])]):
                        a = run.parse()
                    self.assertTrue(a.store_ids)
                    self.assertEqual(a.clients, [])
                    self.assertLessEqual(max(a.ef), 1000)


if __name__ == "__main__":
    unittest.main()
