import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e20 import analyze, arm_of, paired_ratio  # noqa: E402


def write(root: Path, engine: str, tag: str, scale: float, size: int, build_s: float, ceiling: float = 1.0,
          vector_type=None):
    """One result: latency grows with ef, recall saturates at `ceiling`; `scale` multiplies latency."""
    proto = "pg" if engine == "pg" else "grpc_raw"
    rows, hits = [], {}
    for ef, base in ((32, 0.80), (64, 0.90), (128, 0.97)):
        recall = min(base, ceiling)
        for rep in range(3):
            rows.append({"proto": proto, "ef": ef, "rep": rep, "recall_at_k": recall,
                         "mean_ms": scale * ef / 32, "p99_ms": scale * ef / 16,
                         "server_cpu_ms_per_query": scale * ef / 64})
        h = np.full(100, round(recall * 10), dtype=np.int16)
        hits[f"none_hits_{proto}_ef{ef}_rep0"] = h
    d = root / f"{engine}_{tag}"
    d.mkdir(parents=True)
    build = {"total_s": build_s}
    build.update({"index_bytes": size, "heap_bytes": 10, "toast_bytes": 5, "table_total_bytes": size + 20}
                 if engine == "pg" else {"storage_bytes": size})
    (d / "result.json").write_text(json.dumps({
        "experiment_id": f"e20-{engine}-{tag}", "engine": engine, "n": 1000, "dim": 1024, "status": "ok",
        "args": {"tag": tag, "m": 16, "efc": 64}, "build": build,
        "runs": [{"mem_limit": "none", "latency": rows,
                  "concurrency": [{"proto": proto, "clients": 8, "throughput_qps": 100.0 / scale,
                                   "recall_at_k": 0.9}]}]}))
    np.savez(d / "raw.npz", **hits)


class ArmTests(unittest.TestCase):
    def test_arm_is_the_tag_after_the_repetition(self):
        self.assertEqual(arm_of("rep2_halfvec"), ("rep2", "halfvec"))
        self.assertEqual(arm_of("rep1_f32"), ("rep1", "f32"))


class PairedRatioTests(unittest.TestCase):
    def test_ratio_of_the_same_repetition(self):
        self.assertEqual(paired_ratio({"rep1": 4.0, "rep2": 9.0}, {"rep1": 2.0, "rep2": 3.0}), [2.0, 3.0])

    def test_unpaired_repetitions_are_dropped(self):
        self.assertEqual(paired_ratio({"rep1": 4.0, "rep3": 9.0}, {"rep1": 2.0, "rep2": 3.0}), [2.0])


class AnalyzeE20Tests(unittest.TestCase):
    def build(self, tmp, halfvec_ceiling=1.0):
        root = Path(tmp)
        for rep in (1, 2, 3):
            write(root / f"r{rep}", "pg", f"rep{rep}_vector", 2.0, 8000, 100.0)
            write(root / f"r{rep}", "pg", f"rep{rep}_halfvec", 1.5, 4000, 80.0, halfvec_ceiling)
            write(root / f"r{rep}", "qdrant", f"rep{rep}_f32", 1.0, 5000, 50.0)
            write(root / f"r{rep}", "qdrant", f"rep{rep}_int8", 0.8, 6000, 60.0)
        return root

    def get(self, report, engine, arm, metric):
        for item in report["aggregates"]:
            if (item["engine"], item["arm"], item["metric"]) == (engine, arm, metric):
                return item["stats"]
        self.fail(f"missing {engine} {arm} {metric}")

    def test_per_arm_aggregates_and_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp), [0.95])
        self.assertEqual(report["verdict"], "valid")
        self.assertEqual(self.get(report, "pg", "halfvec", "index_bytes")["mean"], 4000)
        self.assertEqual(self.get(report, "qdrant", "int8", "storage_bytes")["n"], 3)
        # recall 0.95 lies between ef 64 (0.90) and ef 128 (0.97): weight 5/7
        self.assertAlmostEqual(self.get(report, "pg", "vector", "mean_ms@0.95")["mean"],
                               2.0 * (2 + (5 / 7) * 2), places=4)

    def test_paired_comparison_is_against_the_baseline_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp), [0.95])
        cmp = {(c["engine"], c["arm"], c["metric"]): c["stats"] for c in report["comparisons"]}
        self.assertAlmostEqual(cmp[("pg", "halfvec", "index_bytes")]["mean"], 0.5)
        self.assertAlmostEqual(cmp[("pg", "halfvec", "build_total_s")]["mean"], 0.8)
        self.assertAlmostEqual(cmp[("qdrant", "int8", "storage_bytes")]["mean"], 1.2)
        self.assertAlmostEqual(cmp[("pg", "halfvec", "mean_ms@0.95")]["mean"], 0.75, places=4)

    def test_recall_ceiling_below_target_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp, halfvec_ceiling=0.93), [0.95])
        self.assertEqual(report["verdict"], "valid")
        obs = [o for o in report["observations"] if o["observation"] == "target_not_reached"]
        self.assertEqual(len(obs), 3)
        self.assertTrue(all(o["arm"] == "halfvec" and abs(o["max_recall"] - 0.93) < 1e-9 for o in obs))

    def test_fewer_than_three_builds_is_an_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "pg", "rep1_vector", 2.0, 8000, 100.0)
            report = analyze(root, [0.95])
        self.assertEqual(report["verdict"], "invalid")
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in report["issues"]))

    def test_distribution_at_the_target_comes_from_per_query_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp), [0.95])
        self.assertEqual(self.get(report, "pg", "vector", "ef_at_target")["mean"], 128)
        self.assertAlmostEqual(self.get(report, "pg", "vector", "share_below_0_8")["mean"], 0.0)


class ConfigTests(unittest.TestCase):
    def test_every_run_parses_with_the_bench_cli_and_tags_are_unique(self):
        from unittest.mock import patch
        from orchestration.core import cli_args
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
        import run
        config = json.loads((Path(__file__).resolve().parents[1] / "configs/examples/e20_quantization.json").read_text())
        for stage, expected_jobs in (("pilot", 2), ("full", 6)):
            jobs = config["stages"][stage]["jobs"]
            self.assertEqual(len(jobs), expected_jobs)
            for job in jobs:
                tags = []
                for item in job["runs"]:
                    with patch.object(sys, "argv", ["run.py", "--engine", item["engine"], "--out", "/tmp/x",
                                                    *cli_args(item["args"])]):
                        a = run.parse()
                    tags.append(a.tag)
                    self.assertLessEqual(max(a.ef), 1000)
                self.assertEqual(len(set(tags)), len(tags))
        arms = {(r["engine"], r["args"].get("pg_vector_type") or r["args"].get("qdrant_quantization", "base"))
                for j in config["stages"]["full"]["jobs"] for r in j["runs"]}
        self.assertEqual(arms, {("pg", "base"), ("pg", "halfvec"), ("qdrant", "base"), ("qdrant", "int8")})


if __name__ == "__main__":
    unittest.main()
