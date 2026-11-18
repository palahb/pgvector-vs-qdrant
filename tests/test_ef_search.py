from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from engines import PG_EF_SEARCH_MAX, set_ef_search  # noqa: E402


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    """Mimics pgvector: an out-of-range value is only warned about and the old value stays."""

    def __init__(self, current: str = "40"):
        self.current = current
        self.statements: list[str] = []

    def execute(self, sql: str, *_args):
        self.statements.append(sql)
        if sql.startswith("SET hnsw.ef_search"):
            value = int(sql.split("=")[1])
            if 1 <= value <= PG_EF_SEARCH_MAX:
                self.current = str(value)
            return Result(None)
        if sql.startswith("SHOW hnsw.ef_search"):
            return Result((self.current,))
        return Result(None)


class SetEfSearchTests(unittest.TestCase):
    def test_a_valid_value_is_set_and_confirmed(self) -> None:
        conn = FakeConn()
        set_ef_search(conn, 512)
        self.assertEqual(conn.current, "512")
        self.assertIn("SHOW hnsw.ef_search", conn.statements)

    def test_the_limit_itself_is_valid(self) -> None:
        set_ef_search(FakeConn(), PG_EF_SEARCH_MAX)

    def test_a_value_above_the_limit_raises_instead_of_keeping_the_default(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            set_ef_search(FakeConn(), 1024)
        self.assertIn("1024", str(caught.exception))

    def test_a_value_below_one_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            set_ef_search(FakeConn(), 0)


if __name__ == "__main__":
    unittest.main()
