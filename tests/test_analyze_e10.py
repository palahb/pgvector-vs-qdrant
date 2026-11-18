import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e10 import analyze, parse_tag  # noqa: E402


def passes(cold_ms: float, steady_ms: float, count: int = 3) -> list[dict]:
    rows = []
    for index in range(count):
        ms = cold_ms if index == 0 else steady_ms
        rows.append({"pass": index, "phase": "cold" if index == 0 else "steady", "mean_ms": ms, "p99_ms": ms * 2,
                     "throughput_qps": 1000 / ms, "recall_at_k": 0.95, "major_faults": 100 if index == 0 else 0,
                     "read_bytes": 4096, "wall_s": ms * 1.677})
    return rows


def result(rep: str, system: str, limit: str, cold: float, steady: float, status: str = "ok",
           n_passes: int = 3, engine: str = "pg") -> dict:
    return {
        "experiment_id": f"e10-{rep}-{system}-{limit}", "engine": engine, "status": status,
        "args": {"tag": f"{rep}_{system}_{limit}"}, "build": {"fully_indexed": True},
        "runs": [{"mem_limit": limit, "memory_passes": passes(cold, steady, n_passes),
                  "concurrency": [{"clients": 8, "throughput_qps": 123.0}],
                  "server_cgroup_memory_bytes": 2_000_000_000}],
    }


class AnalyzeE10Tests(unittest.TestCase):
    def write(self, root: Path, results: list[dict]) -> None:
        for index, item in enumerate(results):
            path = root / f"t{index}" / "result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(item))

    def test_tag_parses_repetition_system_and_limit(self) -> None:
        self.assertEqual(parse_tag("rep2_pg_sb1G_8G"), ("rep2", "pg_sb1G", "8G"))
        self.assertEqual(parse_tag("rep1_qdrant_mmap_none"), ("rep1", "qdrant_mmap", "none"))
        self.assertIsNone(parse_tag("rep1"))

    def test_cold_and_steady_are_aggregated_separately_across_reps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, [result(f"rep{i}", "pg_sbq", "8G", 1000.0 + i, 50.0 + i) for i in (1, 2, 3)])
            report = analyze(root)
        self.assertEqual(report["verdict"], "valid")
        cold = next(a for a in report["aggregates"] if a["phase"] == "cold" and a["metric"] == "mean_ms")
        steady = next(a for a in report["aggregates"] if a["phase"] == "steady_last" and a["metric"] == "mean_ms")
        self.assertAlmostEqual(cold["stats"]["mean"], 1002.0)
        self.assertAlmostEqual(steady["stats"]["mean"], 52.0)
        self.assertEqual(cold["stats"]["n"], 3)

    def test_cut_off_results_are_excluded_not_averaged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = [result(f"rep{i}", "pg_sb1G", "4G", 9.0, 5.0) for i in (1, 2, 3)]
            cut = result("rep4", "pg_sb1G", "4G", 99999.0, 99999.0, status="running", n_passes=0)
            self.write(root, good + [cut])
            report = analyze(root)
        steady = next(a for a in report["aggregates"] if a["phase"] == "steady_last" and a["metric"] == "mean_ms")
        self.assertAlmostEqual(steady["stats"]["mean"], 5.0)
        self.assertEqual(steady["stats"]["n"], 3)
        self.assertEqual([e["rep"] for e in report["excluded"]], ["rep4"])

    def test_a_cell_with_fewer_than_three_reps_makes_the_report_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, [result("rep1", "qdrant_mmap", "none", 5.0, 1.0, engine="qdrant")])
            report = analyze(root)
        self.assertEqual(report["verdict"], "incomplete")
        self.assertTrue(any(i["problem"] == "fewer_than_three_repetitions" for i in report["issues"]))

    def test_cells_of_the_planned_matrix_without_results_are_reported_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, [result(f"rep{i}", "pg_sbq", "8G", 5.0, 2.0) for i in (1, 2, 3)])
            report = analyze(root, expected_cells=[("pg_sbq", "8G"), ("pg_sbq", "4G")])
        self.assertEqual(report["missing_cells"], [{"system": "pg_sbq", "limit": "4G"}])

    def test_unindexed_qdrant_build_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = result("rep1", "qdrant_mmap", "none", 5.0, 1.0, engine="qdrant")
            item["build"]["fully_indexed"] = False
            self.write(root, [item])
            report = analyze(root)
        self.assertTrue(any(i["problem"] == "not_fully_indexed" for i in report["issues"]))


if __name__ == "__main__":
    unittest.main()
