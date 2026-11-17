import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e9 import activity_total, analyze, split_tag  # noqa: E402


def pg_result(rep: str, arm: str, load: float) -> dict:
    return {
        "experiment_id": f"e9-{rep}-{arm}", "engine": "pg", "n": 1000,
        "args": {"tag": f"{rep}_{arm}"},
        "build": {"load_s": load, "index_s": 10.0, "total_s": load + 10.0, "vacuum_checkpoint_s": 1.0,
                  "write_activity": {"copy": {"wal_bytes": 2_000_000, "io_write_bytes": 0, "checkpoints_requested": 0},
                                     "index": {"wal_bytes": 1_000_000, "io_write_bytes": 5_000_000},
                                     "vacuum_checkpoint": {"io_write_bytes": 1_000_000, "checkpoints_requested": 1}}},
    }


def qdrant_result(rep: str, arm: str, upload: float, indexed: bool = True) -> dict:
    return {
        "experiment_id": f"e9-{rep}-{arm}", "engine": "qdrant", "n": 1000,
        "args": {"tag": f"{rep}_{arm}"},
        "build": {"upload_s": upload, "index_wait_s": 2.0, "total_s": upload + 2.0, "fully_indexed": indexed},
    }


class AnalyzeE9Tests(unittest.TestCase):
    def test_tag_splits_repetition_and_arm(self) -> None:
        self.assertEqual(split_tag("rep2_q_par4"), ("rep2", "q_par4"))
        self.assertIsNone(split_tag("rep1"))

    def test_activity_total_sums_available_phases_only(self) -> None:
        build = pg_result("rep1", "pg_logged", 5.0)["build"]
        self.assertEqual(activity_total(build, "io_write_bytes"), 6_000_000.0)
        self.assertIsNone(activity_total(build, "missing_counter"))

    def _write(self, root: Path, results: list[dict]) -> None:
        for index, result in enumerate(results):
            path = root / f"r{index}" / "result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(result))

    def test_arms_aggregate_across_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, [pg_result(f"rep{i}", "pg_logged", 5.0 + i) for i in (1, 2, 3)]
                        + [qdrant_result(f"rep{i}", "q_base", 20.0) for i in (1, 2, 3)])
            report = analyze(root)
        self.assertEqual(report["verdict"], "valid")
        load = next(a for a in report["aggregates"] if a["arm"] == "pg_logged" and a["metric"] == "load_s")
        self.assertEqual(load["stats"]["n"], 3)
        self.assertAlmostEqual(load["stats"]["mean"], 7.0)
        wal = next(a for a in report["aggregates"] if a["arm"] == "pg_logged" and a["metric"] == "wal_mb_copy")
        self.assertAlmostEqual(wal["stats"]["mean"], 2.0)

    def test_unindexed_qdrant_build_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, [qdrant_result(f"rep{i}", "q_base", 20.0, indexed=(i != 2)) for i in (1, 2, 3)])
            report = analyze(root)
        self.assertEqual(report["verdict"], "invalid")
        self.assertTrue(any(i["problem"] == "not_fully_indexed" for i in report["issues"]))

    def test_fewer_than_three_builds_is_an_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, [pg_result("rep1", "pg_logged", 5.0)])
            report = analyze(root)
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in report["issues"]))


if __name__ == "__main__":
    unittest.main()
