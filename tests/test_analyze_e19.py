import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.analyze_e19 import KERNEL_NS, analyze, distance_upper_bound  # noqa: E402
from analysis.perf_profile import CATEGORIES  # noqa: E402


def shares(**given):
    out = {name: 0.0 for name in CATEGORIES}
    out.update(given)
    total = sum(out.values())
    return {k: v / total for k, v in out.items()}


def write_result(root, engine, arm, rep, cpu, cycles, instructions, blocks=None, matched=256):
    proto = "pg" if engine == "pg" else "grpc_raw"
    latency = []
    for ef, recall in ((128, 0.90), (256, 0.96), (384, 0.98)):
        for r in range(3):
            row = {"proto": proto, "ef": ef, "rep": r, "recall_at_k": recall, "mean_ms": ef / 64,
                   "server_cpu_ms_per_query": cpu * ef / 256 + (100 if r == 0 else 0)}  # rep 0 is perturbed
            if blocks is not None:
                row["blks_hit_per_query"] = blocks * ef / 256
            latency.append(row)
    conc = [{"proto": proto, "ef": matched, "clients": 1, "perf_derived": {"events_per_query": {
        "cycles:u": cycles, "instructions:u": instructions, "cache-misses:u": 1000.0,
        "cache-references:u": 4000.0, "task-clock": 3.0}}}]
    d = root / f"{engine}_{rep}_{arm}"
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({
        "experiment_id": f"e19-{engine}-{rep}-{arm}", "engine": engine, "n": 1000, "dim": 1024, "status": "ok",
        "args": {"tag": f"{rep}_{arm}", "m": 16, "efc": 64},
        "runs": [{"mem_limit": "none", "latency": latency, "concurrency": conc, "conc_matched_ef": matched}]}))
    return d.name, proto


def profiles(entries):
    return {"profiles": [{"file": f"{d}/perfrec_{proto}_ef{ef}.data", "engine": engine, "shares": sh}
                         for d, proto, ef, engine, sh in entries]}


class UpperBoundTests(unittest.TestCase):
    def test_distance_count_is_time_over_the_fastest_kernel(self):
        self.assertAlmostEqual(distance_upper_bound(1.0, "avx512f_fma"), 1e6 / KERNEL_NS["avx512f_fma"])


class AnalyzeE19Tests(unittest.TestCase):
    def build(self, tmp, with_profiles=True):
        root = Path(tmp)
        entries = []
        for rep in ("rep1", "rep2", "rep3"):
            d, proto = write_result(root, "pg", "pg", rep, cpu=6.0, cycles=20e6, instructions=15e6, blocks=900.0)
            entries.append((d, proto, 256, "pg", shares(distance=0.10, graph_and_element_access=0.40,
                                                        buffer_manager=0.30, other=0.20)))
            d, proto = write_result(root, "qdrant", "auto", rep, cpu=4.0, cycles=14e6, instructions=8e6)
            entries.append((d, proto, 256, "qdrant", shares(distance=0.25, graph_and_element_access=0.45,
                                                            request_path=0.30)))
        if with_profiles:
            (root / "perf_profiles.json").write_text(json.dumps(profiles(entries)))
        return root

    def get(self, report, engine, arm, metric):
        for item in report["aggregates"]:
            if (item["engine"], item["arm"], item["metric"]) == (engine, arm, metric):
                return item["stats"]
        self.fail(f"missing {engine} {arm} {metric}")

    def test_timing_ignores_the_profiled_rep(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp))
        self.assertAlmostEqual(self.get(report, "pg", "pg", "server_cpu_ms_per_query")["mean"], 6.0)
        self.assertEqual(self.get(report, "pg", "pg", "ef")["mean"], 256)

    def test_category_cycles_are_share_times_cycles_per_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp))
        self.assertAlmostEqual(self.get(report, "pg", "pg", "cycles_distance")["mean"], 2e6)
        self.assertAlmostEqual(self.get(report, "pg", "pg", "cycles_buffer_manager")["mean"], 6e6)
        self.assertAlmostEqual(self.get(report, "qdrant", "auto", "cycles_request_path")["mean"], 4.2e6)
        self.assertAlmostEqual(self.get(report, "pg", "pg", "ipc")["mean"], 0.75)

    def test_distance_upper_bounds_and_block_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp))
        t = 6.0 * 0.10
        self.assertAlmostEqual(self.get(report, "pg", "pg", "distance_ms")["mean"], t)
        self.assertAlmostEqual(self.get(report, "pg", "pg", "distances_upper_avx2")["mean"],
                               t * 1e6 / KERNEL_NS["avx2_fma"])
        self.assertAlmostEqual(self.get(report, "pg", "pg", "blocks_per_query")["mean"], 900.0)

    def test_missing_profiles_are_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp, with_profiles=False))
        self.assertTrue(any(i["problem"] == "no_profile" for i in report["issues"]))
        self.assertEqual(report["verdict"], "invalid")

    def test_engine_comparison_gives_ratio_of_means_and_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = analyze(self.build(tmp))
        row = next(c for c in report["comparisons"] if c["metric"] == "server_cpu_ms_per_query"
                   and c["arm"] == "auto")
        self.assertAlmostEqual(row["ratio_of_means"], 1.5)
        self.assertAlmostEqual(row["pairwise_min"], 1.5)

    def test_fewer_than_three_builds_is_an_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d, proto = write_result(root, "pg", "pg", "rep1", 6.0, 20e6, 15e6)
            (root / "perf_profiles.json").write_text(json.dumps(profiles([(d, proto, 256, "pg", shares(other=1))])))
            report = analyze(root)
        self.assertTrue(any(i["problem"] == "fewer_than_three_builds" for i in report["issues"]))


class ConfigTests(unittest.TestCase):
    def test_every_run_parses_and_arms_are_unique(self):
        from unittest.mock import patch
        from orchestration.core import cli_args
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
        import run
        config = json.loads((Path(__file__).resolve().parents[1]
                             / "configs/examples/e19_causal_decomposition.json").read_text())
        for stage, jobs_expected in (("pilot", 2), ("full", 6)):
            jobs = config["stages"][stage]["jobs"]
            self.assertEqual(len(jobs), jobs_expected)
            for job in jobs:
                tags = []
                for item in job["runs"]:
                    with patch.object(sys, "argv", ["run.py", "--engine", item["engine"], "--out", "/tmp/x",
                                                    *cli_args(item["args"])]):
                        a = run.parse()
                    self.assertTrue(a.perf and a.perf_record)
                    self.assertEqual(a.clients, [1])
                    tags.append(a.tag)
                self.assertEqual(len(set(tags)), len(tags))


if __name__ == "__main__":
    unittest.main()
