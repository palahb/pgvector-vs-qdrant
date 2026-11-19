import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e18 import analyze, distribution, per_query_recall  # noqa: E402


def write_result(root: Path, name: str, engine: str, dim: int, rep: str, hits_by_ef: dict[int, list[int]],
                 status: str = "ok", with_raw: bool = True) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    proto = "pg" if engine == "pg" else "grpc_raw"
    (folder / "result.json").write_text(json.dumps({
        "experiment_id": f"e18-{name}", "engine": engine, "dim": dim, "status": status,
        "args": {"tag": f"{rep}_d{dim}"}}))
    if with_raw:
        arrays = {f"none_hits_{proto}_ef{ef}_rep0": np.array(h, dtype=np.int16) for ef, h in hits_by_ef.items()}
        np.savez_compressed(folder / "raw.npz", **arrays)


class DistributionTests(unittest.TestCase):
    def test_distribution_reports_tail_and_shares(self) -> None:
        recall = per_query_recall(np.array([10, 10, 10, 10, 9, 8, 7, 5, 3, 0]))
        d = distribution(recall)
        self.assertAlmostEqual(d["mean"], 0.72)
        self.assertEqual(d["min"], 0.0)
        self.assertAlmostEqual(d["share_perfect"], 0.4)
        self.assertAlmostEqual(d["share_below_0_8"], 0.4)   # 0.7, 0.5, 0.3, 0.0
        self.assertAlmostEqual(d["share_at_most_0_5"], 0.3)


class AnalyzeE18Tests(unittest.TestCase):
    def build(self, root: Path, dim: int, rep: str, scale: int = 0) -> None:
        good = [10] * 18 + [9, 9 - scale]
        poor = [8] * 20
        write_result(root, f"pg_{dim}_{rep}", "pg", dim, rep, {64: poor, 128: good})

    def test_the_distribution_comes_from_the_smallest_ef_reaching_the_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rep in ("rep1", "rep2", "rep3"):
                self.build(root, 768, rep)
            report = analyze(root, target=0.95)
        self.assertEqual(report["verdict"], "valid")
        ef = next(a for a in report["aggregates"] if a["metric"] == "ef_at_target")
        self.assertEqual(ef["stats"]["mean"], 128.0)
        perfect = next(a for a in report["aggregates"] if a["metric"] == "share_perfect")
        self.assertAlmostEqual(perfect["stats"]["mean"], 0.9)

    def test_recall_at_fixed_ef_is_aggregated_across_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, rep in enumerate(("rep1", "rep2", "rep3")):
                self.build(root, 768, rep, scale=index * 3)
            report = analyze(root)
        r128 = next(a for a in report["aggregates"] if a["metric"] == "recall@ef128")
        self.assertEqual(r128["stats"]["n"], 3)
        self.assertGreater(r128["stats"]["sd"], 0)

    def test_a_result_without_raw_arrays_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_result(root, "x", "pg", 128, "rep1", {}, with_raw=False)
            report = analyze(root)
        self.assertEqual(report["verdict"], "invalid")
        self.assertEqual(report["issues"][0]["problem"], "missing_raw_or_not_ok")

    def test_fewer_than_three_builds_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build(root, 128, "rep1")
            report = analyze(root)
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in report["issues"]))

    def test_target_not_reached_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rep in ("rep1", "rep2", "rep3"):
                write_result(root, f"p{rep}", "pg", 128, rep, {64: [5] * 20})
            report = analyze(root)
        self.assertTrue(any(i["problem"] == "target_not_reached" for i in report["issues"]))


if __name__ == "__main__":
    unittest.main()
