from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bench"))

from workload import memory_passes, pass_order, proc_counters  # noqa: E402


def fake_proc(root: Path, pid: int, minflt: int, majflt: int, read_bytes: int, rss_kb: int = 100) -> None:
    directory = root / str(pid)
    directory.mkdir(parents=True)
    # comm may contain spaces and parentheses, which is why the parser splits after the last ")"
    fields = ["S", "1", "1", "1", "0", "-1", "4194560", str(minflt), "0", str(majflt), "0"] + ["0"] * 30
    (directory / "stat").write_text(f"{pid} (post gres (x)) " + " ".join(fields) + "\n")
    (directory / "io").write_text(f"rchar: 1\nwchar: 2\nread_bytes: {read_bytes}\nwrite_bytes: 7\n")
    (directory / "status").write_text(f"Name:\tx\nVmRSS:\t{rss_kb} kB\nRssFile:\t{rss_kb // 2} kB\n")


class ProcCounterTests(unittest.TestCase):
    def test_sums_faults_and_read_bytes_over_processes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_proc(root, 10, minflt=100, majflt=3, read_bytes=4096, rss_kb=200)
            fake_proc(root, 11, minflt=50, majflt=2, read_bytes=8192, rss_kb=300)
            counters = proc_counters([10, 11, 12], proc_root=root)  # 12 does not exist
        self.assertEqual(counters["minor_faults"], 150)
        self.assertEqual(counters["major_faults"], 5)
        self.assertEqual(counters["read_bytes"], 12288)
        self.assertEqual(counters["rss_kb"], 500)

    def test_no_processes_gives_zero_counters(self) -> None:
        self.assertEqual(proc_counters([], proc_root=Path("/nonexistent"))["major_faults"], 0)


class PassOrderTests(unittest.TestCase):
    def test_every_pass_is_a_permutation_and_is_reproducible(self) -> None:
        first = pass_order(50, seed=7, index=0)
        self.assertEqual(sorted(first.tolist()), list(range(50)))
        self.assertTrue(np.array_equal(first, pass_order(50, seed=7, index=0)))
        self.assertFalse(np.array_equal(first, pass_order(50, seed=7, index=1)))
        self.assertFalse(np.array_equal(first, pass_order(50, seed=8, index=0)))


class MemoryPassesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queries = np.arange(20, dtype=np.float32).reshape(20, 1)
        self.gt = np.array([[i] for i in range(20)])
        self.calls: list[int] = []

    def query(self, vector):
        index = int(vector[0])
        self.calls.append(index)
        return [index] if index % 4 else [-1]  # every fourth query misses

    def run_passes(self, passes: int = 3):
        counters = iter(range(0, 1000, 10))
        return memory_passes(
            self.query, self.queries, self.gt, k=1, passes=passes, order_seed=5,
            counters_fn=lambda: {"major_faults": next(counters), "minor_faults": 0, "read_bytes": 0, "rss_kb": 1},
            stats_begin=lambda: None, stats_end=lambda: {},
        )

    def test_first_pass_is_cold_and_the_rest_steady(self) -> None:
        rows, _raw = self.run_passes(3)
        self.assertEqual([r["phase"] for r in rows], ["cold", "steady", "steady"])
        self.assertEqual([r["pass"] for r in rows], [0, 1, 2])

    def test_each_pass_uses_every_query_once_in_a_new_order(self) -> None:
        self.run_passes(2)
        first, second = self.calls[:20], self.calls[20:]
        self.assertEqual(sorted(first), list(range(20)))
        self.assertEqual(sorted(second), list(range(20)))
        self.assertNotEqual(first, second)

    def test_recall_is_scored_against_the_matching_ground_truth(self) -> None:
        rows, _ = self.run_passes(1)
        self.assertAlmostEqual(rows[0]["recall_at_k"], 15 / 20)

    def test_counters_are_reported_as_per_pass_deltas(self) -> None:
        rows, _ = self.run_passes(2)
        self.assertEqual([r["major_faults"] for r in rows], [10, 10])

    def test_raw_latencies_are_kept_per_pass(self) -> None:
        _rows, raw = self.run_passes(2)
        self.assertEqual(set(raw), {"mem_pass0_lat", "mem_pass0_order", "mem_pass1_lat", "mem_pass1_order"})
        self.assertEqual(len(raw["mem_pass0_lat"]), 20)


if __name__ == "__main__":
    unittest.main()
