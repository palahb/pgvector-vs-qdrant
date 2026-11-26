import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.check_tables import compare_rows, table_rows, fmt_pm  # noqa: E402

TEX = r"""
\begin{table}\label{tab:x}
\begin{tabular}{rr}
\toprule
 a & b \\
\midrule
 16 & 64 & 4.85 $\pm$ 0.11 & 4.76 \\
  & 32\,GB & --- & 5 \\
\bottomrule
\end{tabular}
\end{table}
"""


class RowsTests(unittest.TestCase):
    def test_rows_are_split_into_normalised_cells(self):
        rows = table_rows(TEX, "tab:x")
        self.assertEqual(rows[1], ["16", "64", "4.85 $\\pm$ 0.11", "4.76"])
        self.assertEqual(rows[2], ["", "32 GB", "---", "5"])

    def test_header_rule_lines_are_not_rows(self):
        self.assertEqual(len(table_rows(TEX, "tab:x")), 3)


class CompareTests(unittest.TestCase):
    def test_equal_rows_pass(self):
        self.assertEqual(compare_rows([["16", "4.85"]], [["16", "4.85"]]), [])

    def test_a_changed_number_is_reported_with_both_values(self):
        diff = compare_rows([["16", "4.85"]], [["16", "4.58"]])
        self.assertEqual(len(diff), 1)
        self.assertIn("4.85", diff[0])
        self.assertIn("4.58", diff[0])

    def test_a_missing_row_is_reported(self):
        self.assertEqual(len(compare_rows([["1"], ["2"]], [["1"]])), 1)

    def test_the_paper_may_have_extra_columns_only_when_the_expected_cells_are_a_subsequence(self):
        self.assertEqual(compare_rows([["a", "c"]], [["a", "b", "c"]], subsequence=True), [])
        self.assertEqual(len(compare_rows([["c", "a"]], [["a", "b", "c"]], subsequence=True)), 1)


class FormatTests(unittest.TestCase):
    def test_mean_and_sd(self):
        self.assertEqual(fmt_pm(4.8512, 0.1049, 2), "4.85 $\\pm$ 0.10")
        self.assertEqual(fmt_pm(273.4, 14.6, 0), "273 $\\pm$ 15")


if __name__ == "__main__":
    unittest.main()
