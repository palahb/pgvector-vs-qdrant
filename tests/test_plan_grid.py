from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from engines import explain_summary, plan_grid_rows  # noqa: E402


def plan(node: str, cost: float, child: str | None = None) -> list[dict]:
    root = {"Node Type": node, "Total Cost": cost}
    if child:
        root["Plans"] = [{"Node Type": child}]
    return [{"Plan": root}]


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    """Answers EXPLAIN with a plan chosen by the planner switches that are currently set."""

    def __init__(self, index_cost: float, scan_cost: float):
        self.settings: dict[str, str] = {}
        self.index_cost, self.scan_cost = index_cost, scan_cost
        self.statements: list[str] = []

    def execute(self, sql: str, *_args):
        self.statements.append(sql)
        if sql.startswith("SET "):
            name, value = sql[4:].split("=", 1)
            self.settings[name.strip()] = value.strip()
            return Result(None)
        if sql.startswith("RESET "):
            self.settings.pop(sql[6:].strip(), None)
            return Result(None)
        if sql.startswith("EXPLAIN"):
            index_allowed = self.settings.get("enable_indexscan", "on") == "on"
            scan_allowed = self.settings.get("enable_seqscan", "on") == "on"
            if index_allowed and (not scan_allowed or self.index_cost <= self.scan_cost):
                return Result((plan("Limit", self.index_cost, "Index Scan"),))
            return Result((plan("Limit", self.scan_cost, "Gather"),))
        return Result(None)


class ExplainSummaryTests(unittest.TestCase):
    def test_collects_node_types_cost_and_index_use(self) -> None:
        summary = explain_summary(plan("Limit", 12.5, "Index Scan")[0]["Plan"])
        self.assertEqual(summary, {"nodes": "Limit/Index Scan", "cost": 12.5, "uses_index": True})

    def test_a_scan_plan_does_not_use_the_index(self) -> None:
        summary = explain_summary(plan("Limit", 99.0, "Gather")[0]["Plan"])
        self.assertFalse(summary["uses_index"])


class PlanGridTests(unittest.TestCase):
    def test_default_choice_follows_the_cheaper_plan(self) -> None:
        conn = FakeConn(index_cost=20.0, scan_cost=10.0)  # scan is cheaper: the fallback
        rows = plan_grid_rows(conn, [64], "[0.1]")
        row = rows[0]
        self.assertEqual(row["ef"], 64)
        self.assertFalse(row["default"]["uses_index"])
        self.assertTrue(row["forced_index"]["uses_index"])
        self.assertEqual(row["forced_index"]["cost"], 20.0)
        self.assertEqual(row["forced_scan"]["cost"], 10.0)
        self.assertAlmostEqual(row["index_to_scan_cost_ratio"], 2.0)

    def test_default_uses_the_index_when_it_is_cheaper(self) -> None:
        rows = plan_grid_rows(FakeConn(index_cost=5.0, scan_cost=10.0), [64], "[0.1]")
        self.assertTrue(rows[0]["default"]["uses_index"])
        self.assertAlmostEqual(rows[0]["index_to_scan_cost_ratio"], 0.5)

    def test_every_ef_is_set_and_the_planner_switches_are_restored(self) -> None:
        conn = FakeConn(index_cost=5.0, scan_cost=10.0)
        plan_grid_rows(conn, [16, 32], "[0.1]")
        self.assertIn("SET hnsw.ef_search = 16", conn.statements)
        self.assertIn("SET hnsw.ef_search = 32", conn.statements)
        self.assertNotIn("enable_seqscan", conn.settings)
        self.assertNotIn("enable_indexscan", conn.settings)

    def test_no_query_is_executed_only_explained(self) -> None:
        conn = FakeConn(index_cost=5.0, scan_cost=10.0)
        plan_grid_rows(conn, [16], "[0.1]")
        executed = [s for s in conn.statements if not s.startswith(("SET", "RESET", "EXPLAIN", "PREPARE"))]
        self.assertEqual(executed, [])


if __name__ == "__main__":
    unittest.main()
