import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.predict_hnsw_cost_threshold import (  # noqa: E402
    compare, correction_applies, observed_drop, predicted_threshold, scan_ratio)

GRID = [16, 24, 32, 48, 64, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512, 640, 768, 1000]


class CostThresholdTests(unittest.TestCase):
    def test_the_scan_fraction_grows_with_ef(self) -> None:
        self.assertLess(scan_ratio(500_000, 128), scan_ratio(500_000, 256))

    def test_the_known_500k_1024d_case_switches_between_ef_256_and_320(self) -> None:
        # recorded in E17: 3,712 table pages, 498,862 index pages; the index cost fell from
        # 13,323 at ef=256 to 3,782 at ef=320
        self.assertFalse(correction_applies(500_000, 256, 3712, 498_862))
        self.assertTrue(correction_applies(500_000, 320, 3712, 498_862))
        self.assertEqual(predicted_threshold(500_000, 3712, 498_862, GRID), 320)

    def test_a_large_table_never_triggers_the_correction(self) -> None:
        # 128-dimensional vectors are stored in the table itself
        self.assertIsNone(predicted_threshold(500_000, 35_776, 50_686, GRID))

    def test_the_correction_needs_a_fraction_below_one_half(self) -> None:
        self.assertFalse(correction_applies(10, 1000, 1, 1_000_000))  # tiny table: fraction caps at 1

    def test_the_observed_drop_is_the_first_decrease_of_the_index_cost(self) -> None:
        cells = [{"ef": 128, "index_cost": 7581.0}, {"ef": 256, "index_cost": 13323.0},
                 {"ef": 320, "index_cost": 3782.0}, {"ef": 384, "index_cost": 3787.0}]
        self.assertEqual(observed_drop(cells), 320)
        self.assertIsNone(observed_drop(cells[:2]))

    def test_compare_flags_agreement_and_lists_exposed_ef(self) -> None:
        cells = [{"dim": 1024, "n": 500_000, "ef": ef, "index_cost": cost, "default_uses_index": ef != 256}
                 for ef, cost in ((128, 7581.0), (256, 13323.0), (320, 3782.0), (384, 3787.0))]
        analysis = {"builds": [{"dim": 1024, "n": 500_000, "heap_pages": 3712, "index_pages": 498_862}],
                    "cells": cells}
        row = compare(analysis)[0]
        self.assertTrue(row["match"])
        self.assertEqual((row["predicted_ef"], row["observed_ef"], row["exposed_ef"]), (320, 320, [256]))


if __name__ == "__main__":
    unittest.main()
