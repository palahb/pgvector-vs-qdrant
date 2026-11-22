from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

import features  # noqa: E402
import workload  # noqa: E402


class PadIdsTests(unittest.TestCase):
    def test_pads_short_results_with_minus_one(self):
        self.assertEqual(features.pad_ids([3, 4], 4).tolist(), [3, 4, -1, -1])

    def test_truncates_to_k(self):
        self.assertEqual(features.pad_ids([1, 2, 3], 2).tolist(), [1, 2])


class PgVectorTypeTests(unittest.TestCase):
    def test_default_is_the_old_schema(self):
        t = features.pg_vector_type("vector", 1024)
        self.assertEqual(t["column"], "vector(1024)")
        self.assertEqual(t["opclass"], "vector_cosine_ops")
        self.assertEqual(t["param_cast"], "")
        self.assertEqual(t["copy_type"], "vector")

    def test_halfvec(self):
        t = features.pg_vector_type("halfvec", 1024)
        self.assertEqual(t["column"], "halfvec(1024)")
        self.assertEqual(t["opclass"], "halfvec_cosine_ops")
        self.assertEqual(t["param_cast"], "::halfvec(1024)")
        self.assertEqual(t["copy_type"], "halfvec")

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(ValueError):
            features.pg_vector_type("bit", 8)

    def test_query_sql_uses_cast_only_for_halfvec(self):
        self.assertEqual(features.pg_query_sql("vector", 8, 10),
                         "SELECT id FROM items ORDER BY embedding <=> %s LIMIT 10")
        self.assertEqual(features.pg_query_sql("halfvec", 8, 10),
                         "SELECT id FROM items ORDER BY embedding <=> %s::halfvec(8) LIMIT 10")


class PgDdlTests(unittest.TestCase):
    def test_default_ddl_is_unchanged(self):
        self.assertEqual(features.pg_create_table_sql("vector", 1024, False),
                         "CREATE TABLE items (id bigint PRIMARY KEY, embedding vector(1024))")
        self.assertEqual(features.pg_create_index_sql("vector", 16, 64),
                         "CREATE INDEX items_hnsw ON items USING hnsw (embedding vector_cosine_ops) "
                         "WITH (m = 16, ef_construction = 64)")

    def test_unlogged_halfvec_ddl(self):
        self.assertEqual(features.pg_create_table_sql("halfvec", 8, True),
                         "CREATE UNLOGGED TABLE items (id bigint PRIMARY KEY, embedding halfvec(8))")
        self.assertIn("halfvec_cosine_ops", features.pg_create_index_sql("halfvec", 16, 64))

    def test_plan_prepare_casts_the_parameter_for_halfvec(self):
        self.assertEqual(features.pg_plan_prepare_sql("vector", 8, 10),
                         "PREPARE bq(vector) AS SELECT id FROM items ORDER BY embedding <=> $1 LIMIT 10")
        self.assertEqual(features.pg_plan_prepare_sql("halfvec", 8, 10),
                         "PREPARE bq(vector) AS SELECT id FROM items ORDER BY embedding <=> $1::halfvec(8) LIMIT 10")


class QdrantQuantObjectTests(unittest.TestCase):
    def test_none_gives_no_objects(self):
        import engines
        self.assertIsNone(engines.qdrant_quantization_config(None))
        self.assertIsNone(engines.qdrant_search_quantization(None))

    def test_int8_objects_carry_the_recorded_settings(self):
        import engines
        desc = features.qdrant_quantization("int8", always_ram=True, rescore=False, oversampling=1.5)
        cfg = engines.qdrant_quantization_config(desc)
        self.assertTrue(cfg.scalar.always_ram)
        self.assertEqual(str(cfg.scalar.type.value), "int8")
        sq = engines.qdrant_search_quantization(desc)
        self.assertFalse(sq.rescore)
        self.assertEqual(sq.oversampling, 1.5)


class QdrantQuantizationTests(unittest.TestCase):
    def test_none_means_no_quantization(self):
        self.assertIsNone(features.qdrant_quantization("none"))

    def test_int8_records_every_setting(self):
        q = features.qdrant_quantization("int8", always_ram=True, rescore=True, oversampling=2.0)
        self.assertEqual(q, {"type": "int8", "quantile": None, "always_ram": True,
                             "rescore": True, "oversampling": 2.0})

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            features.qdrant_quantization("pq")


class PerfRecordTests(unittest.TestCase):
    def test_command_samples_user_space_of_the_given_pids(self):
        cmd = features.perf_record_cmd([11, 12], "/tmp/x.data", freq=499)
        self.assertEqual(cmd[:2], ["perf", "record"])
        self.assertIn("11,12", cmd)
        self.assertIn("/tmp/x.data", cmd)
        self.assertIn("499", cmd)
        self.assertIn("cycles:u", cmd)  # perf_event_paranoid=2 allows user space only


class PoissonScheduleTests(unittest.TestCase):
    def test_arrivals_are_sorted_and_inside_the_window(self):
        t = features.poisson_arrivals(rate=200, duration_s=5, seed=1)
        self.assertTrue(np.all(np.diff(t) >= 0))
        self.assertTrue(t[-1] < 5e9)

    def test_mean_rate_is_close_to_target(self):
        t = features.poisson_arrivals(rate=500, duration_s=20, seed=2)
        self.assertAlmostEqual(len(t) / 20, 500, delta=500 * 0.05)

    def test_same_seed_same_schedule(self):
        a = features.poisson_arrivals(100, 3, 7)
        b = features.poisson_arrivals(100, 3, 7)
        self.assertTrue(np.array_equal(a, b))

    def test_exponential_gaps(self):
        t = features.poisson_arrivals(rate=1000, duration_s=30, seed=3)
        gaps = np.diff(t) / 1e9
        self.assertAlmostEqual(gaps.std() / gaps.mean(), 1.0, delta=0.05)  # CV of an exponential


class OpenLoopSummaryTests(unittest.TestCase):
    def test_latency_is_measured_from_the_planned_time(self):
        planned = np.array([0, 10_000_000, 20_000_000], dtype=np.int64)
        started = np.array([0, 15_000_000, 30_000_000], dtype=np.int64)   # sender fell behind
        finished = started + 2_000_000
        s = features.open_loop_summary(planned, started, finished, np.array([10, 10, 10]), k=10,
                                       offered_rate=100, window_s=0.03)
        self.assertAlmostEqual(s["mean_ms"], (2 + 7 + 12) / 3, places=6)       # from planned
        self.assertAlmostEqual(s["service_mean_ms"], 2.0, places=6)            # from sent
        self.assertAlmostEqual(s["max_send_lag_ms"], 10.0, places=6)
        self.assertEqual(s["recall_at_k"], 1.0)
        self.assertEqual(s["completed"], 3)

    def test_achieved_rate_uses_the_window(self):
        n = 50
        planned = np.arange(n, dtype=np.int64) * 10_000_000
        s = features.open_loop_summary(planned, planned, planned + 1_000_000, np.full(n, 10), 10,
                                       offered_rate=100, window_s=0.5)
        self.assertAlmostEqual(s["achieved_qps"], 100.0, places=6)
        self.assertEqual(s["offered_qps"], 100)


class PgbouncerTests(unittest.TestCase):
    def test_ini_pins_transaction_pooling_and_prepared_statements(self):
        ini = features.pgbouncer_ini(listen_port=56432, pg_port=55432, pool_size=16,
                                     max_client_conn=200, auth_file="/w/users.txt", log_dir="/w")
        self.assertIn("pool_mode = transaction", ini)
        self.assertIn("default_pool_size = 16", ini)
        self.assertIn("max_client_conn = 200", ini)
        self.assertIn("max_prepared_statements", ini)
        self.assertIn("listen_port = 56432", ini)
        self.assertIn("port=55432", ini)

    def test_dsn_points_at_the_pooler(self):
        self.assertEqual(features.pooled_dsn("host=127.0.0.1 port=55432 dbname=postgres user=postgres", 56432),
                         "host=127.0.0.1 port=56432 dbname=postgres user=postgres")


class StoreIdsSweepTests(unittest.TestCase):
    class Server:
        name = "fake"

        def query_spec(self, ef, proto, k):
            return {"ef": ef, "proto": proto, "k": k}

        def stats_begin(self, proto):
            pass

        def stats_end(self, proto):
            return {}

        def cpu_seconds(self):
            return 0.0

    def run_sweep(self, store_ids):
        from unittest.mock import patch
        queries = np.arange(3, dtype=np.float32).reshape(3, 1)
        gt = np.array([[0, 1], [10, 11], [20, 21]])
        answers = {0: [0, 1], 1: [10], 2: [99, 98]}
        with patch.object(workload, "make_query_fn", lambda spec: (lambda v: answers[int(v[0])])):
            return workload.latency_sweep(self.Server(), ["pg"], [8], 1, queries, queries[:1], gt, 2,
                                          store_ids=store_ids)

    def test_ids_are_stored_when_asked(self):
        _, raw = self.run_sweep(True)
        self.assertEqual(raw["ids_pg_ef8_rep0"].tolist(), [[0, 1], [10, -1], [99, 98]])

    def test_default_stores_nothing_new(self):
        _, raw = self.run_sweep(False)
        self.assertFalse([k for k in raw if k.startswith("ids_")])


class OpenLoopWorkerTests(unittest.TestCase):
    def test_worker_sends_at_planned_times_and_reports_lag(self):
        import queue
        import threading
        from unittest.mock import patch
        from common import now_ns
        gt = np.array([[0], [1], [2]])
        queries = np.arange(3, dtype=np.float32).reshape(3, 1)
        calls = []

        def fake_query(v):
            calls.append(now_ns())
            if int(v[0]) == 1:
                import time
                time.sleep(0.05)  # a slow query delays the next planned one
            return [int(v[0])]

        go = threading.Event()
        go.set()
        zero = SimpleNamespace(value=now_ns() + 20_000_000)
        ready, results = queue.Queue(), queue.Queue()
        jobs = [(0, 0), (10_000_000, 1), (20_000_000, 2)]
        with patch.object(workload, "make_query_fn", lambda spec: fake_query):
            workload._open_loop_worker({}, queries, gt, jobs, zero, go, ready, results)
        self.assertEqual(ready.get()[0], "ok")
        planned, started, finished, hits = results.get()
        self.assertEqual((planned - zero.value).tolist(), [0, 10_000_000, 20_000_000])
        self.assertTrue(np.all(started >= planned))
        self.assertGreater(started[2] - planned[2], 30_000_000)  # third was late behind the slow one
        self.assertEqual(hits.tolist(), [1, 1, 1])


class ConfigIdentityTests(unittest.TestCase):
    def test_new_options_at_defaults_leave_the_config_id_unchanged(self):
        import run
        from common import stable_id
        argv = ["run.py", "--engine", "pg", "--n", "1000", "--out", "/tmp/x"]
        old_keys = {"engine", "n", "dim", "synthetic", "seed", "warm_seed", "k", "m", "efc", "ef", "reps",
                    "warm", "nq", "protocols", "clients", "conc_ef", "conc_recall", "conc_duration",
                    "conc_warmup", "conc_all_limits", "mem_limits", "server_cores", "client_cores",
                    "pg_shared_buffers", "pg_effective_cache", "pg_maintenance_mem", "pg_planner",
                    "pg_unlogged", "qdrant_upload_parallel", "qdrant_upload_batch",
                    "qdrant_defer_indexing", "qdrant_max_indexing_threads", "plan_only",
                    "memory_passes", "memory_ef", "memory_clients", "memory_conc_duration",
                    "order_seed", "qdrant_on_disk", "qdrant_indexing_threshold_kb", "qdrant_segments",
                    "qdrant_search_threads", "qdrant_require_indexed", "qdrant_control_grace_s",
                    "perf", "tag"}
        from unittest.mock import patch
        with patch.object(sys, "argv", argv):
            a = run.parse()
        kept = {k for k in vars(a) if k not in {"out", "work", "keep", "experiment_id"}
                and not (k in run.ADDED_DEFAULTS and vars(a)[k] == run.ADDED_DEFAULTS[k])}
        self.assertEqual(kept, old_keys)

    def test_a_non_default_new_option_changes_the_identity(self):
        import run
        from unittest.mock import patch
        with patch.object(sys, "argv", ["run.py", "--engine", "pg", "--out", "/tmp/x", "--pg-vector-type", "halfvec"]):
            a = run.parse()
        self.assertNotEqual(a.pg_vector_type, run.ADDED_DEFAULTS["pg_vector_type"])


if __name__ == "__main__":
    unittest.main()
