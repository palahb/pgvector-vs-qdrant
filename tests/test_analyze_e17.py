import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e17 import analyze  # noqa: E402


def grid_row(ef: int, uses_index: bool, index_cost: float = 10.0, scan_cost: float = 20.0) -> dict:
    default_cost = index_cost if uses_index else scan_cost
    return {"ef": ef,
            "default": {"nodes": "Limit/Index Scan" if uses_index else "Limit/Gather", "cost": default_cost,
                        "uses_index": uses_index},
            "forced_index": {"nodes": "Limit/Index Scan", "cost": index_cost, "uses_index": True},
            "forced_scan": {"nodes": "Limit/Gather", "cost": scan_cost, "uses_index": False},
            "index_to_scan_cost_ratio": index_cost / scan_cost}


def result(n: int, dim: int, rows: list[dict], status: str = "ok") -> dict:
    return {"experiment_id": f"e17-{n}-{dim}", "status": status, "n": n, "dim": dim,
            "runs": [{"mem_limit": "none", "plan_grid": {
                "table_pages": {"heap": 100, "heap_tuples": 1000.0, "toast": 5000, "index": 3000},
                "planner_settings": {}, "grid": rows}}] if rows else []}


class AnalyzeE17Tests(unittest.TestCase):
    def write(self, root: Path, results: list[dict]) -> None:
        for index, item in enumerate(results):
            path = root / f"t{index}" / "result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(item))

    def test_exposure_is_the_share_of_cells_where_the_default_avoids_the_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, [
                result(1000, 1024, [grid_row(64, True), grid_row(256, False), grid_row(384, True)]),
                result(5000, 1024, [grid_row(64, True), grid_row(256, True)]),
            ])
            report = analyze(root)
        self.assertEqual(report["verdict"], "valid")
        self.assertEqual(report["summary"]["cells"], 5)
        self.assertEqual(report["summary"]["exposed_cells"], 1)
        self.assertAlmostEqual(report["summary"]["exposure"], 0.2)
        self.assertEqual(report["summary"]["builds_with_exposure"], 1)

    def test_builds_list_the_exposed_ef_values_and_page_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, [result(1000, 128, [grid_row(64, True), grid_row(256, False)])])
            report = analyze(root)
        build = report["builds"][0]
        self.assertEqual((build["n"], build["dim"], build["exposed_ef"]), (1000, 128, [256]))
        self.assertEqual((build["heap_pages"], build["toast_pages"], build["index_pages"]), (100, 5000, 3000))

    def test_a_result_without_a_plan_grid_makes_the_report_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, [result(1000, 1024, [grid_row(64, True)]), result(2000, 1024, [], status="failed")])
            report = analyze(root)
        self.assertEqual(report["verdict"], "incomplete")
        self.assertEqual(report["issues"][0]["problem"], "no_plan_grid")
        self.assertEqual(report["summary"]["cells"], 1)


if __name__ == "__main__":
    unittest.main()
