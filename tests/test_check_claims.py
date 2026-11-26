import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.check_claims import Lookup, run_claims  # noqa: E402


def make_repo(tmp: Path):
    d = tmp / "results" / "derived"
    d.mkdir(parents=True)
    (d / "e6_full_9050d65_analysis.json").write_text(json.dumps({"matched_recall_aggregates": [
        {"engine": "pg", "n": 1000, "segments": "one_graph", "search_threads": "n/a", "recall_target": 0.95,
         "metrics": {"mean_ms": {"mean": 6.8}, "server_cpu_ms_per_query": {"mean": 7.0}}},
        {"engine": "qdrant", "n": 1000, "segments": "4", "search_threads": "auto", "recall_target": 0.95,
         "metrics": {"mean_ms": {"mean": 2.0}, "server_cpu_ms_per_query": {"mean": 5.0}}}]}))
    return tmp


class LookupTests(unittest.TestCase):
    def test_ratio_of_two_engines_at_one_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            lk = Lookup(make_repo(Path(tmp)), Path(tmp) / "artifacts")
            self.assertAlmostEqual(lk.e6ratio(1000, "4", "auto", 0.95, "mean_ms"), 3.4)
            self.assertAlmostEqual(lk.e6ratio(1000, "4", "auto", 0.95, "server_cpu_ms_per_query"), 1.4)

    def test_unknown_setting_raises_instead_of_returning_a_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            lk = Lookup(make_repo(Path(tmp)), Path(tmp) / "artifacts")
            with self.assertRaises(KeyError):
                lk.e6ratio(1000, "8", "auto", 0.95, "mean_ms")


class RunClaimsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(Path(self.tmp.name))
        self.lk = Lookup(self.repo, Path(self.tmp.name) / "artifacts")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_true_claim_present_in_the_text_passes(self):
        claims = [{"id": "c1", "where": "abstract", "tex": "3.4$\\times$ lower",
                   "check": "round(e6ratio(1000,'4','auto',0.95,'mean_ms'),1)==3.4"}]
        res = run_claims(claims, "latency is 3.4$\\times$ lower", self.lk)
        self.assertEqual([r["status"] for r in res], ["ok"])

    def test_a_claim_whose_text_is_not_in_the_paper_fails(self):
        claims = [{"id": "c1", "where": "abstract", "tex": "3.4$\\times$ lower", "check": "True"}]
        res = run_claims(claims, "different text", self.lk)
        self.assertEqual(res[0]["status"], "fail")
        self.assertIn("not in paper", res[0]["problem"])

    def test_a_claim_that_the_data_contradicts_fails(self):
        claims = [{"id": "c1", "where": "abstract", "tex": "2.9", "check": "round(e6ratio(1000,'4','auto',0.95,'mean_ms'),1)==2.9"}]
        res = run_claims(claims, "ratio 2.9", self.lk)
        self.assertEqual(res[0]["status"], "fail")

    def test_an_unreadable_source_is_a_failure_not_a_pass(self):
        claims = [{"id": "c1", "where": "abstract", "tex": "x", "check": "e6ratio(5,'4','auto',0.95,'mean_ms')>0"}]
        res = run_claims(claims, "x", self.lk)
        self.assertEqual(res[0]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
