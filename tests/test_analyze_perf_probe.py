import json
import tempfile
import unittest
from pathlib import Path

from analysis.analyze_perf_probe import summarize


class PerfProbeAnalysisTests(unittest.TestCase):
    def test_normalizes_and_reconciles_both_engines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for engine, cpu in (("pg", 2.0), ("qdrant", 1.0)):
                path = root / engine / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps({
                    "engine": engine,
                    "runs": [{"mem_limit": "none", "concurrency": [{
                        "ef": 32, "clients": 4, "server_mean_ms": cpu * 0.8,
                        "server_cpu_ms_per_query": cpu,
                        "perf_derived": {"query_count": 100, "events_per_query": {
                            "task-clock": cpu * 1.02,
                            "cycles:u": 2000 * cpu,
                            "instructions:u": 3000 * cpu,
                            "cache-references:u": 100,
                            "cache-misses:u": 5,
                            "branches:u": 200,
                            "branch-misses:u": 4,
                        }},
                    }]}],
                }))
            report = summarize(root)
            self.assertEqual(report["verdict"], "valid")
            self.assertEqual(len(report["rows"]), 2)
            self.assertEqual(report["rows"][0]["instructions_per_cycle"], 1.5)
            self.assertEqual(report["rows"][0]["cache_miss_ratio"], 0.05)

    def test_missing_required_events_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for engine in ("pg", "qdrant"):
                path = root / engine / "result.json"
                path.parent.mkdir()
                path.write_text(json.dumps({
                    "engine": engine,
                    "runs": [{"mem_limit": "none", "concurrency": [{
                        "ef": 32, "clients": 4, "server_cpu_ms_per_query": 1,
                        "perf_derived": {"query_count": 10, "events_per_query": {"task-clock": 1}},
                    }]}],
                }))
            report = summarize(root)
            self.assertEqual(report["verdict"], "invalid_or_incomplete")
            self.assertTrue(any(issue.get("problem") == "missing_required_events" for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
