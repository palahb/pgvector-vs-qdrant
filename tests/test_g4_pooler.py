from __future__ import annotations

import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

import engines  # noqa: E402
import features  # noqa: E402
import workload  # noqa: E402


class TxnSettingsTests(unittest.TestCase):
    def test_ef_and_planner_settings_are_local_to_the_transaction(self):
        self.assertEqual(features.pg_txn_settings(512, True),
                         ["SET LOCAL hnsw.ef_search = 512", "SET LOCAL enable_seqscan = off"])

    def test_planner_setting_is_left_out_when_the_planner_is_free(self):
        self.assertEqual(features.pg_txn_settings(64, False), ["SET LOCAL hnsw.ef_search = 64"])

    def test_out_of_range_ef_is_rejected_not_silently_ignored(self):
        for bad in (0, 1001, -3):
            with self.assertRaises(ValueError):
                features.pg_txn_settings(bad, True)


class ConnModeTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(features.parse_conn_modes("direct,direct_txn,pooled"), ["direct", "direct_txn", "pooled"])
        self.assertEqual(features.parse_conn_modes("direct"), ["direct"])

    def test_unknown_and_duplicate_modes_are_rejected(self):
        for bad in ("direct,odd", "pooled,pooled", ""):
            with self.assertRaises(ValueError):
                features.parse_conn_modes(bad)

    def test_flags_of_each_mode(self):
        self.assertEqual(features.conn_mode_flags("direct"), {"use_pooler": False, "per_query_txn": False})
        self.assertEqual(features.conn_mode_flags("direct_txn"), {"use_pooler": False, "per_query_txn": True})
        self.assertEqual(features.conn_mode_flags("pooled"), {"use_pooler": True, "per_query_txn": True})


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self):
        self.log = []
        self.local_ef = "40"

    @contextmanager
    def transaction(self):
        self.log.append("BEGIN")
        yield
        self.log.append("COMMIT")

    def execute(self, sql, params=None, **kwargs):
        self.log.append(sql)
        if sql.startswith("SET LOCAL hnsw.ef_search"):
            self.local_ef = sql.split("=")[1].strip()
        if sql.startswith("SHOW hnsw.ef_search"):
            return FakeResult([(self.local_ef,)])
        return FakeResult([(7,), (8,)] if sql.startswith("SELECT id") else [])


class TxnQueryTests(unittest.TestCase):
    def test_settings_run_inside_the_transaction_before_the_query(self):
        conn = FakeConn()
        ids = features.txn_query(conn, ["SET LOCAL a = 1", "SET LOCAL b = 2"], "SELECT id FROM items", "vec")
        self.assertEqual(ids, [7, 8])
        self.assertEqual(conn.log, ["BEGIN", "SET LOCAL a = 1", "SET LOCAL b = 2", "SELECT id FROM items", "COMMIT"])


class QuerySpecTests(unittest.TestCase):
    def make(self, **kw):
        args = SimpleNamespace(pg_planner="force-index", pg_vector_type="vector", pg_pooler_pool_size=8,
                               pg_pooler_max_client_conn=200, **kw)
        return engines.Pg("/tmp/work", [0, 1, 2, 3], args)

    def test_default_mode_is_direct_and_changes_nothing(self):
        srv = self.make()
        spec = srv.query_spec(64, "pg", 10)
        self.assertFalse(spec["per_query_txn"])
        self.assertEqual(spec["dsn"], srv.dsn)

    def test_pooled_mode_points_at_the_pooler_and_uses_transactions(self):
        srv = self.make()
        srv.conn_mode = "pooled"
        spec = srv.query_spec(64, "pg", 10)
        self.assertTrue(spec["per_query_txn"])
        self.assertIn(f"port={srv.pooler_port}", spec["dsn"])

    def test_direct_txn_stays_on_the_server_port(self):
        srv = self.make()
        srv.conn_mode = "direct_txn"
        spec = srv.query_spec(64, "pg", 10)
        self.assertTrue(spec["per_query_txn"])
        self.assertEqual(spec["dsn"], srv.dsn)


class PoolerPidsTests(unittest.TestCase):
    def test_descendants_of_the_wrapper_are_included(self):
        srv = QuerySpecTests.make(self)
        proc = subprocess.Popen(["sh", "-c", "sleep 30 & wait"], start_new_session=True)
        try:
            import time
            time.sleep(0.3)
            srv.pooler = proc
            pids = srv.pooler_pids()
            self.assertIn(proc.pid, pids)
            self.assertGreaterEqual(len(pids), 2)
        finally:
            import os
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def test_no_pooler_means_no_pids(self):
        self.assertEqual(QuerySpecTests.make(self).pooler_pids(), [])


class PgbouncerIniTests(unittest.TestCase):
    def ini(self):
        return features.pgbouncer_ini(listen_port=56432, pg_port=55432, pool_size=8, max_client_conn=200,
                                      auth_file="/w/users.txt", log_dir="/w")

    def test_server_connections_are_prewarmed_and_the_unix_socket_is_off(self):
        ini = self.ini()
        self.assertIn("min_pool_size = 8", ini)
        self.assertIn("unix_socket_dir =", ini)
        self.assertIn("ignore_startup_parameters = extra_float_digits", ini)


class PoolerCmdTests(unittest.TestCase):
    def test_image_runs_the_binary_by_its_full_path_with_the_work_dir_bound(self):
        cmd = features.pooler_cmd("/img/pgbouncer.sif", None, "/w/pgbouncer.ini", "/w")
        self.assertEqual(cmd, ["apptainer", "exec", "--cleanenv", "--bind", "/w", "/img/pgbouncer.sif",
                               "/opt/pgbouncer/pgbouncer", "/w/pgbouncer.ini"])

    def test_native_binary_when_there_is_no_image(self):
        self.assertEqual(features.pooler_cmd(None, "/usr/bin/pgbouncer", "/w/p.ini", "/w"),
                         ["/usr/bin/pgbouncer", "/w/p.ini"])


class PoolerUsageTests(unittest.TestCase):
    def test_share_of_cpu_per_query_and_cores_busy(self):
        u = features.pooler_usage(cpu0=1.0, cpu1=3.0, wall_s=10.0, completed=1000)
        self.assertAlmostEqual(u["pooler_cores_busy"], 0.2)
        self.assertAlmostEqual(u["pooler_cpu_ms_per_query"], 2.0)

    def test_no_completed_queries_does_not_divide_by_zero(self):
        self.assertEqual(features.pooler_usage(0, 1, 5, 0)["pooler_cpu_ms_per_query"], None)


class RawKeyTests(unittest.TestCase):
    def test_default_key_is_unchanged(self):
        self.assertEqual(workload.conc_raw_key("pg", 64, 8, "lat"), "conc_pg_ef64_c8_lat")

    def test_mode_is_inserted_before_the_suffix(self):
        self.assertEqual(workload.conc_raw_key("pg", 64, 8, "lat", "pooled"), "conc_pg_ef64_c8_pooled_lat")


class MakeQueryFnTests(unittest.TestCase):
    def test_per_query_txn_does_not_use_a_session_level_set(self):
        conn = FakeConn()
        spec = {"engine": "pg", "dsn": "x", "ef": 128, "k": 10, "proto": "pg", "force_index": True,
                "vector_type": "vector", "dim": 4, "per_query_txn": True}
        with patch("psycopg.connect", return_value=conn), patch("pgvector.psycopg.register_vector"):
            q = engines.make_query_fn(spec)
            self.assertEqual(q(np.zeros(4, dtype=np.float32)), [7, 8])
        statements = [s for s in conn.log if s not in ("BEGIN", "COMMIT")]
        self.assertFalse(any(s.startswith("SET hnsw") or s.startswith("SET enable") for s in statements))
        self.assertIn("SET LOCAL hnsw.ef_search = 128", statements)


if __name__ == "__main__":
    unittest.main()
