from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from engines import pg_activity_delta, pg_activity_snapshot  # noqa: E402


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, rows, failing=()):
        self.rows, self.failing, self.statements = rows, failing, []

    def execute(self, sql, *_args):
        self.statements.append(sql)
        for name in self.failing:
            if name in sql:
                raise RuntimeError(f"{name} unavailable")
        for name, row in self.rows.items():
            if name in sql:
                return Result(row)
        return Result(None)


class PgActivityTests(unittest.TestCase):
    def test_snapshot_collects_wal_and_checkpoint_counters(self) -> None:
        conn = FakeConn({
            "pg_stat_wal": (10, 2, 4096),
            "pg_stat_checkpointer": (1, 0, 12.5, 3.0, 100),
            "pg_stat_io": (8192,),
        })
        snap = pg_activity_snapshot(conn)
        self.assertEqual(snap["wal_bytes"], 4096)
        self.assertEqual(snap["wal_fpi"], 2)
        self.assertEqual(snap["checkpoints_timed"], 1)
        self.assertEqual(snap["checkpoint_write_ms"], 12.5)
        self.assertEqual(snap["io_write_bytes"], 8192)

    def test_unavailable_views_are_omitted_not_zero(self) -> None:
        conn = FakeConn({"pg_stat_wal": (10, 2, 4096)},
                        failing=("pg_stat_checkpointer", "pg_stat_bgwriter", "pg_stat_io"))
        snap = pg_activity_snapshot(conn)
        self.assertEqual(snap["wal_bytes"], 4096)
        self.assertNotIn("checkpoints_timed", snap)
        self.assertNotIn("io_write_bytes", snap)

    def test_delta_subtracts_only_counters_present_in_both(self) -> None:
        before = {"wal_bytes": 100, "checkpoints_timed": 1, "wal_fpi": 5}
        after = {"wal_bytes": 700, "checkpoints_timed": 1, "io_write_bytes": 9}
        delta = pg_activity_delta(before, after)
        self.assertEqual(delta, {"wal_bytes": 600, "checkpoints_timed": 0})


if __name__ == "__main__":
    unittest.main()
