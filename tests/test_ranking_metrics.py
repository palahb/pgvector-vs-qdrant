import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.ranking_metrics import dcg, mrr_at_k, ndcg_at_k, recall_at_k  # noqa: E402


class DcgTests(unittest.TestCase):
    def test_linear_gain_and_log_discount(self):
        self.assertAlmostEqual(dcg([3, 2, 0], 3), 3 / math.log2(2) + 2 / math.log2(3))

    def test_cuts_at_k(self):
        self.assertAlmostEqual(dcg([1, 1, 1], 2), 1 + 1 / math.log2(3))


class NdcgTests(unittest.TestCase):
    def test_perfect_ranking_is_one(self):
        self.assertAlmostEqual(ndcg_at_k([3, 2, 1], [3, 2, 1, 0], 3), 1.0)

    def test_ideal_comes_from_the_best_available_grades(self):
        # ranking found only a grade-1 item, a grade-3 item exists
        self.assertAlmostEqual(ndcg_at_k([1, 0], [3, 1], 2), 1.0 / (3 + 1 / math.log2(3)))

    def test_no_relevant_items_gives_none(self):
        self.assertIsNone(ndcg_at_k([0, 0], [0, 0], 2))

    def test_ranking_order_matters(self):
        self.assertLess(ndcg_at_k([0, 3], [3], 2), ndcg_at_k([3, 0], [3], 2))


class MrrRecallTests(unittest.TestCase):
    def test_reciprocal_rank_of_first_relevant(self):
        self.assertAlmostEqual(mrr_at_k([0, 0, 2, 3], 10, threshold=2), 1 / 3)

    def test_zero_when_nothing_relevant_in_the_top_k(self):
        self.assertEqual(mrr_at_k([0, 1, 0], 3, threshold=2), 0.0)

    def test_recall_is_over_the_relevant_items_that_could_be_found(self):
        # 3 relevant items exist in the corpus, k=2 can hold at most 2 of them: denominator min(k, 3)
        self.assertAlmostEqual(recall_at_k([2, 0], 3, 2, threshold=2), 0.5)

    def test_recall_none_without_relevant_items(self):
        self.assertIsNone(recall_at_k([0, 0], 0, 2, threshold=2))


if __name__ == "__main__":
    unittest.main()
