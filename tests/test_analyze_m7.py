import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_m7 import analyze, correct_throughput  # noqa: E402


class CorrectionTests(unittest.TestCase):
    def test_throughput_scales_with_the_inverse_of_cpu_per_query(self):
        # measured 1000 qps at a point costing 8.0 ms; at the exact target the query costs 7.2 ms
        self.assertAlmostEqual(correct_throughput(1000.0, cpu_at_point=8.0, cpu_at_target=7.2), 1000 * 8.0 / 7.2)

    def test_no_correction_when_the_point_is_the_target(self):
        self.assertAlmostEqual(correct_throughput(900.0, 5.0, 5.0), 900.0)

    def test_missing_cpu_gives_none(self):
        self.assertIsNone(correct_throughput(900.0, None, 5.0))
        self.assertIsNone(correct_throughput(900.0, 5.0, 0))


def write(root, engine, rep, scale=1.0):
    proto = "pg" if engine == "pg" else "grpc_raw"
    rows = []
    for ef, recall, cpu in ((32, 0.80, 2.0), (64, 0.90, 4.0), (128, 0.97, 8.0)):
        for r in range(3):
            rows.append({"proto": proto, "ef": ef, "rep": r, "recall_at_k": recall, "server_cpu_ms_per_query": cpu * scale})
    # saturated throughput = 8 cores / cpu per query (matched point ef 128, fixed point ef 64)
    conc = [{"proto": proto, "ef": 128, "clients": c, "throughput_qps": 8000 / (8.0 * scale), "recall_at_k": 0.97} for c in (8, 32)]
    conc += [{"proto": proto, "ef": 64, "clients": c, "throughput_qps": 8000 / (4.0 * scale), "recall_at_k": 0.90, "server_cores_busy": 7.1} for c in (8, 32)]
    d = root / f"{engine}_{rep}_base"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({
        "experiment_id": f"m7-{engine}-{rep}", "engine": engine, "n": 1000, "status": "ok",
        "args": {"tag": f"{rep}_base", "m": 16, "efc": 64},
        "runs": [{"mem_limit": "none", "latency": rows, "concurrency": conc, "conc_matched_ef": 128}]}))


class AnalyzeM7Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rep in ("rep1", "rep2", "rep3"):
            write(self.root, "pg", rep)
            write(self.root, "qdrant", rep, scale=0.6)

    def tearDown(self):
        self.tmp.cleanup()

    def test_throughput_at_exactly_the_target_recall(self):
        r = analyze(self.root, 0.95)
        row = next(x for x in r["builds"] if x["engine"] == "pg" and x["clients"] == 32)
        # recall 0.95 lies 5/7 of the way from ef 64 (0.90) to ef 128 (0.97): cpu 4 + 5/7*4
        cpu_t = 4.0 + (5 / 7) * 4.0
        self.assertAlmostEqual(row["cpu_ms_at_target"], cpu_t, places=5)
        self.assertAlmostEqual(row["qps_at_target"], 1000.0 * 8.0 / cpu_t, places=3)
        self.assertGreater(row["qps_at_target"], row["qps_at_point"])   # a lower recall is cheaper, so faster

    def test_correction_is_reported_in_percent(self):
        r = analyze(self.root, 0.95)
        row = next(x for x in r["builds"] if x["engine"] == "pg" and x["clients"] == 8)
        self.assertAlmostEqual(row["correction_percent"], 100 * (row["qps_at_target"] / row["qps_at_point"] - 1), places=6)

    def test_the_model_is_checked_against_a_second_measured_point(self):
        r = analyze(self.root, 0.95)
        row = next(x for x in r["builds"] if x["engine"] == "pg" and x["clients"] == 8)
        # prediction of the ef=64 throughput from the matched point must equal the measurement in this synthetic set
        self.assertAlmostEqual(row["validation_error_percent"], 0.0, places=6)

    def test_cores_busy_of_the_validation_window_is_kept_to_judge_saturation(self):
        r = analyze(self.root, 0.95)
        row = next(x for x in r["builds"] if x["engine"] == "pg" and x["clients"] == 8)
        self.assertEqual(row["validation_cores_busy"], 7.1)

    def test_aggregates_cover_both_engines_and_three_builds(self):
        r = analyze(self.root, 0.95)
        keys = {(a["engine"], a["clients"]): a["stats"]["n"] for a in r["aggregates"] if a["metric"] == "correction_percent"}
        self.assertEqual(keys[("pg", 32)], 3)
        self.assertEqual(keys[("qdrant", 8)], 3)

    def test_a_build_that_never_reaches_the_target_is_an_issue_not_a_number(self):
        low = Path(self.tmp.name) / "low"
        write(low, "pg", "rep1")
        path = low / "pg_rep1_base" / "result.json"
        data = json.loads(path.read_text())
        for row in data["runs"][0]["latency"]:
            row["recall_at_k"] = min(row["recall_at_k"], 0.92)
        path.write_text(json.dumps(data))
        r = analyze(low, 0.95)
        self.assertTrue(any(i["problem"] == "target_not_reached" for i in r["issues"]))
        self.assertEqual(r["builds"], [])


if __name__ == "__main__":
    unittest.main()
