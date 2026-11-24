import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "bench"))

import features  # noqa: E402
from analysis.analyze_e22 import (STEADY_ACHIEVED, STEADY_LAG_MS, TRIM_S, achieved_in_window, analyze,  # noqa: E402
                                  is_steady)


class WorkerLifecycleTests(unittest.TestCase):
    def run_worker(self, jobs, warm, release_set):
        import queue
        import threading
        from types import SimpleNamespace
        from unittest.mock import patch
        import numpy as np
        import workload
        from common import now_ns
        calls = []

        def fake_query(v):
            calls.append(int(v[0]))
            return [int(v[0])]
        queries = np.arange(5, dtype=np.float32).reshape(5, 1)
        gt = np.arange(5).reshape(5, 1)
        go, release = threading.Event(), threading.Event()
        go.set()
        if release_set:
            release.set()
        zero = SimpleNamespace(value=now_ns() + 20_000_000)
        ready, results = queue.Queue(), queue.Queue()
        with patch.object(workload, "make_query_fn", lambda spec: fake_query):
            thread = threading.Thread(target=workload._open_loop_worker,
                                      args=({}, queries, gt, jobs, zero, go, ready, results, release, warm))
            thread.start()
        return thread, calls, ready, results, release

    def test_warm_up_queries_run_before_the_worker_reports_ready(self):
        thread, calls, ready, results, release = self.run_worker([(0, 4)], warm=6, release_set=True)
        thread.join(5)
        self.assertEqual(ready.get()[0], "ok")
        self.assertEqual(len(calls), 6 + 1)          # six warm-up queries, then the one planned query
        self.assertEqual(calls[-1], 4)

    def test_zero_warm_up_keeps_one_connection_check_only(self):
        thread, calls, ready, results, release = self.run_worker([(0, 3)], warm=0, release_set=True)
        thread.join(5)
        self.assertEqual(len(calls), 1 + 1)

    def test_the_worker_stays_alive_after_its_results_until_it_is_released(self):
        import time
        thread, calls, ready, results, release = self.run_worker([(0, 2)], warm=0, release_set=False)
        deadline = time.time() + 5
        while results.empty() and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(results.empty())            # the parent can read the results
        self.assertTrue(thread.is_alive())           # ...while the connection (and the backend's CPU time) still exists
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())


class OpenLoopEfTests(unittest.TestCase):
    def test_explicit_ef_wins(self):
        self.assertEqual(features.choose_open_loop_ef(256, 448, 64), 256)

    def test_matched_ef_of_the_closed_loop_is_used_when_there_is_one(self):
        self.assertEqual(features.choose_open_loop_ef(0, 448, 64), 448)

    def test_without_a_matched_ef_the_closed_loop_ef_is_used_so_the_capacity_row_exists(self):
        self.assertEqual(features.choose_open_loop_ef(0, None, 64), 64)


class LoadLevelTests(unittest.TestCase):
    def test_rates_are_fractions_of_the_measured_capacity(self):
        self.assertEqual(features.open_loop_rates(1000.0, [0.5, 0.8, 0.95, 1.1]), [500, 800, 950, 1100])

    def test_rates_are_whole_and_at_least_one(self):
        self.assertEqual(features.open_loop_rates(1.4, [0.5]), [1])
        self.assertEqual(features.open_loop_rates(1234.6, [0.95]), [1173])

    def test_no_capacity_is_an_error_not_a_silent_zero(self):
        for bad in (0, -5, None):
            with self.assertRaises(ValueError):
                features.open_loop_rates(bad, [0.5])

    def test_fractions_are_parsed_and_must_be_positive(self):
        self.assertEqual(features.parse_fractions("0.5,0.8,1.1"), [0.5, 0.8, 1.1])
        self.assertEqual(features.parse_fractions(""), [])
        for bad in ("0,0.5", "-1", "a"):
            with self.assertRaises(ValueError):
                features.parse_fractions(bad)

    def test_capacity_is_read_from_the_closed_loop_row_at_the_matched_ef(self):
        rows = [{"proto": "pg", "ef": 64, "clients": 32, "throughput_qps": 900.0},
                {"proto": "pg", "ef": 448, "clients": 32, "throughput_qps": 1000.0},
                {"proto": "pg", "ef": 448, "clients": 8, "throughput_qps": 990.0},
                {"proto": "grpc", "ef": 448, "clients": 32, "throughput_qps": 5.0}]
        self.assertEqual(features.capacity_qps(rows, "pg", 448, 32), 1000.0)

    def test_missing_capacity_row_gives_none(self):
        self.assertIsNone(features.capacity_qps([], "pg", 448, 32))


def level(frac, offered, achieved, p99, p999, lag, recall=0.95, cpu=6.0):
    return {"proto": "pg", "ef": 448, "workers": 64, "seed": 42, "load_fraction": frac, "capacity_qps": 1000.0,
            "offered_qps": offered, "achieved_qps": achieved, "completed": int(achieved * 60), "mean_ms": 8.0,
            "p99_ms": p99, "p999_ms": p999, "max_send_lag_ms": lag, "mean_send_lag_ms": lag / 10,
            "service_mean_ms": 7.0, "recall_at_k": recall, "server_cpu_ms_per_query": cpu}


def write(root, engine, rep, closed_p99=40.0, overload_lag=5000.0):
    proto = "pg" if engine == "pg" else "grpc_raw"
    ol = [level(0.5, 500, 500, 12.0, 20.0, 5.0), level(0.8, 800, 799, 20.0, 35.0, 8.0),
          level(0.95, 950, 948, 60.0, 120.0, 50.0), level(1.1, 1100, 1004, 4000.0, 8000.0, overload_lag)]
    for row in ol:
        row["proto"] = proto
    d = root / f"{engine}_{rep}"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({
        "experiment_id": f"e22-{engine}-{rep}", "engine": engine, "n": 1000, "status": "ok", "args": {"tag": rep},
        "runs": [{"mem_limit": "none", "conc_matched_ef": 448, "open_loop": ol,
                  "concurrency": [{"proto": proto, "ef": 448, "clients": 32, "throughput_qps": 1000.0,
                                   "p99_ms": closed_p99, "mean_ms": 30.0, "recall_at_k": 0.95}]}]}))


class AchievedInWindowTests(unittest.TestCase):
    def test_only_queries_finished_inside_the_window_count(self):
        import numpy as np
        planned = np.array([0, 1e9, 2e9, 3e9])           # ns after the start
        latency = np.array([1e6, 1e6, 2.5e9, 5e9])      # the last two finish at 4.5 s and 8 s
        self.assertAlmostEqual(achieved_in_window(planned, latency, window_s=4.0), 2 / 4.0)

    def test_a_server_that_keeps_up_completes_everything_in_the_window(self):
        import numpy as np
        planned = np.arange(0, 4e9, 1e8)
        self.assertAlmostEqual(achieved_in_window(planned, np.full(len(planned), 1e6), window_s=4.0), len(planned) / 4.0)


class TrimmedStatsTests(unittest.TestCase):
    def test_the_start_up_seconds_are_left_out_of_the_tail(self):
        import numpy as np
        from analysis.analyze_e22 import trimmed_latency
        planned = np.arange(0, 20e9, 1e7)                     # 100 arrivals per second for 20 s
        lat = np.full(len(planned), 5e6)                       # 5 ms everywhere...
        lat[planned < 2e9] = 400e6                             # ...except 400 ms in the first two seconds
        all_ = trimmed_latency(planned, lat, trim_s=0.0, window_s=20.0)
        cut = trimmed_latency(planned, lat, trim_s=3.0, window_s=20.0)
        self.assertGreater(all_["p99_ms"], 100)
        self.assertAlmostEqual(cut["p99_ms"], 5.0)
        self.assertEqual(cut["count"], int(((planned >= 3e9) & (planned < 20e9)).sum()))

    def test_p999_and_mean_are_reported(self):
        import numpy as np
        from analysis.analyze_e22 import trimmed_latency
        planned = np.arange(0, 10e9, 1e7)
        lat = np.full(len(planned), 2e6)
        out = trimmed_latency(planned, lat, trim_s=1.0, window_s=10.0)
        self.assertAlmostEqual(out["mean_ms"], 2.0)
        self.assertAlmostEqual(out["p999_ms"], 2.0)


class SteadyTests(unittest.TestCase):
    def test_a_level_that_keeps_up_is_steady(self):
        self.assertTrue(is_steady(level(0.5, 500, 499, 10, 20, 5)))

    def test_a_level_that_falls_behind_is_not(self):
        self.assertFalse(is_steady(level(1.1, 1100, 1000, 4000, 8000, 3000)))

    def test_a_long_send_lag_alone_makes_it_overload(self):
        self.assertFalse(is_steady(level(0.95, 950, 949, 100, 200, STEADY_LAG_MS + 1)))

    def test_thresholds_are_the_ones_in_the_design(self):
        self.assertEqual((STEADY_ACHIEVED, STEADY_LAG_MS), (0.98, 1000.0))
        self.assertEqual(TRIM_S, 5.0)


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rep in ("rep1", "rep2", "rep3"):
            write(self.root, "pg", rep)
            write(self.root, "qdrant", rep, closed_p99=20.0)

    def tearDown(self):
        self.tmp.cleanup()

    def agg(self, r, engine, frac, metric):
        for a in r["aggregates"]:
            if (a["engine"], a["load_fraction"], a["metric"]) == (engine, frac, metric):
                return a["stats"]
        self.fail("missing")

    def test_levels_are_aggregated_over_builds(self):
        r = analyze(self.root)
        self.assertEqual(r["verdict"], "valid")
        self.assertAlmostEqual(self.agg(r, "pg", 0.5, "p99_ms")["mean"], 12.0)
        self.assertEqual(self.agg(r, "pg", 0.5, "p999_ms")["n"], 3)

    def test_steady_and_overload_levels_are_labelled(self):
        r = analyze(self.root)
        status = {(s["engine"], s["load_fraction"]): s["steady_builds"] for s in r["status"]}
        self.assertEqual(status[("pg", 0.95)], 3)
        self.assertEqual(status[("pg", 1.1)], 0)

    def test_no_p99_is_offered_for_an_overload_level(self):
        r = analyze(self.root)
        self.assertNotIn(("pg", 1.1, "p99_ms"), {(a["engine"], a["load_fraction"], a["metric"]) for a in r["aggregates"] if a["steady"]})

    def test_closed_loop_reference_comes_from_the_same_build(self):
        r = analyze(self.root)
        ref = {c["engine"]: c for c in r["closed_loop_comparison"]}
        self.assertAlmostEqual(ref["pg"]["closed_p99_ms"], 40.0)
        self.assertAlmostEqual(ref["pg"]["open_p99_ms_at_95"], 60.0)
        self.assertAlmostEqual(ref["pg"]["ratio_open_to_closed"], 1.5)

    def test_recall_disagreement_with_the_closed_loop_is_an_issue(self):
        bad = Path(self.tmp.name) / "bad"
        write(bad, "pg", "rep1")
        path = bad / "pg_rep1" / "result.json"
        data = json.loads(path.read_text())
        data["runs"][0]["open_loop"][0]["recall_at_k"] = 0.6
        path.write_text(json.dumps(data))
        r = analyze(bad)
        self.assertTrue(any(i["problem"] == "recall_disagrees_with_closed_loop" for i in r["issues"]))
        self.assertEqual(r["verdict"], "invalid")

    def test_fewer_than_three_builds_is_an_issue(self):
        one = Path(self.tmp.name) / "one"
        write(one, "pg", "rep1")
        r = analyze(one)
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in r["issues"]))


class ConfigTests(unittest.TestCase):
    def test_every_run_parses_and_asks_for_the_four_levels(self):
        from unittest.mock import patch
        from orchestration.core import cli_args
        import run
        config = json.loads((REPO / "configs/examples/e22_open_loop.json").read_text())
        for stage, expected in (("pilot", 2), ("full", 6)):
            jobs = config["stages"][stage]["jobs"]
            self.assertEqual(len(jobs), expected)
            for job in jobs:
                for item in job["runs"]:
                    with patch.object(sys, "argv", ["run.py", "--engine", item["engine"], "--out", "/tmp/x",
                                                    *cli_args(item["args"])]):
                        a = run.parse()
                    self.assertEqual(a.open_loop_fractions, [0.5, 0.8, 0.95, 1.1])
                    self.assertEqual(a.open_loop_capacity_clients, 32)
                    self.assertIn(32, a.clients)
                    self.assertEqual(a.open_loop_rates, [])


if __name__ == "__main__":
    unittest.main()
