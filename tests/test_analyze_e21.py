import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e21 import RECALL_TOLERANCE, analyze, recall_disagreements  # noqa: E402


def row(mode, ef, clients, qps, mean, p99, cpu, recall=0.95, pooler=None):
    r = {"proto": "pg", "ef": ef, "clients": clients, "throughput_qps": qps, "mean_ms": mean, "p99_ms": p99,
         "server_cpu_ms_per_query": cpu, "recall_at_k": recall, "server_cores_busy": 7.0}
    if mode != "direct":
        r["conn_mode"] = mode
    if mode == "pooled":
        r.update({"pooler_cores_busy": 0.8, "pooler_cpu_ms_per_query": pooler if pooler is not None else 0.1})
    return r


def write(root, rep, scale=1.0, pooled_recall=0.95):
    rows = []
    for ef in (64, 448):
        for clients in (1, 32):
            rows += [row("direct", ef, clients, 1000 * scale, 3.0, 9.0, 6.0),
                     row("direct_txn", ef, clients, 800 * scale, 3.5, 10.0, 6.5),
                     row("pooled", ef, clients, 600 * scale, 4.0, 12.0, 7.0, recall=pooled_recall)]
    d = root / f"pg_{rep}"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({
        "experiment_id": f"e21-{rep}", "engine": "pg", "n": 1000, "status": "ok", "args": {"tag": rep},
        "runs": [{"mem_limit": "none", "conc_matched_ef": 448, "concurrency": rows,
                  "pooler": {"image": "x.sif", "version": "PgBouncer 1.25.1"}}]}))


class RecallAgreementTests(unittest.TestCase):
    def test_modes_that_agree_pass(self):
        rows = [row("direct", 64, 1, 1, 1, 1, 1, 0.95), row("pooled", 64, 1, 1, 1, 1, 1, 0.951)]
        self.assertEqual(recall_disagreements(rows), [])

    def test_a_pooled_arm_that_ran_at_another_ef_is_flagged(self):
        rows = [row("direct", 64, 1, 1, 1, 1, 1, 0.95), row("pooled", 64, 1, 1, 1, 1, 1, 0.80)]
        bad = recall_disagreements(rows)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["mode"], "pooled")

    def test_tolerance_is_wider_than_window_sampling_noise(self):
        self.assertGreaterEqual(RECALL_TOLERANCE, 0.005)


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for i, rep in enumerate(("rep1", "rep2", "rep3")):
            write(self.root, rep, scale=1.0 + 0.1 * i)

    def tearDown(self):
        self.tmp.cleanup()

    def cmp(self, report, base, mode, ef_role, clients, metric):
        for c in report["comparisons"]:
            if (c["baseline"], c["mode"], c["ef_role"], c["clients"], c["metric"]) == (base, mode, ef_role, clients, metric):
                return c["stats"]
        self.fail("missing comparison")

    def test_paired_ratios_between_modes(self):
        r = analyze(self.root)
        self.assertEqual(r["verdict"], "valid")
        self.assertAlmostEqual(self.cmp(r, "direct", "direct_txn", "matched", 32, "throughput_qps")["mean"], 0.8)
        self.assertAlmostEqual(self.cmp(r, "direct_txn", "pooled", "matched", 32, "throughput_qps")["mean"], 0.75)
        self.assertAlmostEqual(self.cmp(r, "direct", "pooled", "matched", 32, "p99_ms")["mean"], 12 / 9, places=5)

    def test_ef_roles(self):
        r = analyze(self.root)
        roles = {(a["ef_role"], a["ef"]) for a in r["aggregates"]}
        self.assertEqual(roles, {("matched", 448), ("fixed", 64)})

    def test_pooler_cost_is_reported_only_for_the_pooled_arm(self):
        r = analyze(self.root)
        agg = {(a["mode"], a["ef_role"], a["clients"], a["metric"]): a["stats"] for a in r["aggregates"]}
        self.assertAlmostEqual(agg[("pooled", "matched", 32, "pooler_cores_busy")]["mean"], 0.8)
        self.assertNotIn(("direct", "matched", 32, "pooler_cores_busy"), agg)

    def test_a_disagreeing_pooled_recall_makes_the_report_invalid(self):
        bad = Path(self.tmp.name) / "bad"
        write(bad, "rep1", pooled_recall=0.7)
        r = analyze(bad)
        self.assertEqual(r["verdict"], "invalid")
        self.assertTrue(any(i["problem"] == "recall_disagrees_between_modes" for i in r["issues"]))

    def test_fewer_than_three_builds_is_an_issue(self):
        one = Path(self.tmp.name) / "one"
        write(one, "rep1")
        r = analyze(one)
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in r["issues"]))


class ConfigTests(unittest.TestCase):
    def test_every_run_parses_and_asks_for_three_modes(self):
        from unittest.mock import patch
        from orchestration.core import cli_args
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
        import run
        config = json.loads((Path(__file__).resolve().parents[1] / "configs/examples/e21_pgbouncer.json").read_text())
        for stage, expected in (("pilot", 1), ("full", 3)):
            jobs = config["stages"][stage]["jobs"]
            self.assertEqual(len(jobs), expected)
            for job in jobs:
                for item in job["runs"]:
                    self.assertEqual(item["engine"], "pg")
                    with patch.object(sys, "argv", ["run.py", "--engine", "pg", "--out", "/tmp/x", *cli_args(item["args"])]):
                        a = run.parse()
                    self.assertEqual(a.pg_conn_modes, ["direct", "direct_txn", "pooled"])
                    self.assertEqual(a.pg_pooler_pool_size, 8)
                    self.assertTrue({32, 48} <= set(a.clients))
                    self.assertLessEqual(max(a.ef), 1000)


if __name__ == "__main__":
    unittest.main()
