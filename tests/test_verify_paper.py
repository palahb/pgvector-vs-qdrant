import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.verify_paper import compare_json, label_coverage, paper_structure  # noqa: E402


class CompareTests(unittest.TestCase):
    def test_equal_documents_have_no_differences(self):
        self.assertEqual(compare_json({"a": [1, 2.0, {"b": "x"}]}, {"a": [1, 2.0, {"b": "x"}]}), [])

    def test_ignored_keys_are_skipped_at_any_depth(self):
        a = {"generated_at": "t1", "root": "/x", "n": {"root": "/a", "v": 1}}
        b = {"generated_at": "t2", "root": "/y", "n": {"root": "/b", "v": 1}}
        self.assertEqual(compare_json(a, b), [])

    def test_floats_are_compared_with_a_relative_tolerance(self):
        self.assertEqual(compare_json({"x": 1.0}, {"x": 1.0 + 1e-12}), [])
        self.assertEqual(len(compare_json({"x": 1.0}, {"x": 1.001})), 1)

    def test_a_difference_reports_its_path(self):
        d = compare_json({"a": [{"b": 1}]}, {"a": [{"b": 2}]})
        self.assertEqual(d, ["a[0].b: 1 != 2"])

    def test_missing_and_extra_keys_and_length_changes_are_differences(self):
        self.assertEqual(len(compare_json({"a": 1}, {"b": 1})), 2)
        self.assertEqual(len(compare_json([1, 2], [1])), 1)

    def test_bool_is_not_a_number(self):
        self.assertEqual(len(compare_json({"x": True}, {"x": 1})), 1)


class StructureTests(unittest.TestCase):
    GOOD = "\\begin{table}\\label{tab:a}\\end{table} see \\ref{tab:a}"

    def test_clean_text(self):
        s = paper_structure(self.GOOD)
        self.assertEqual((s["env_mismatch"], s["undefined_refs"], s["todo_calls"]), ({}, [], 0))

    def test_unbalanced_environment_undefined_ref_and_todo_are_found(self):
        s = paper_structure("\\begin{table} \\ref{nope} \\todo{x}")
        self.assertEqual(s["env_mismatch"], {"table": [1, 0]})
        self.assertEqual(s["undefined_refs"], ["nope"])
        self.assertEqual(s["todo_calls"], 1)

    def test_comments_are_ignored(self):
        s = paper_structure("% \\todo{x} \\ref{gone}\n\\label{a}\n")
        self.assertEqual((s["undefined_refs"], s["todo_calls"]), ([], 0))

    def test_unused_labels_are_reported(self):
        self.assertEqual(paper_structure("\\label{a}")["unused_labels"], ["a"])


class CoverageTests(unittest.TestCase):
    def test_every_table_and_figure_label_needs_a_source_or_an_exemption(self):
        tex = "\\label{tab:a}\\label{fig:b}\\label{tab:c}\\label{sec:x}"
        cov = label_coverage(tex, {"tab:a": {}}, exempt={"tab:c"})
        self.assertEqual(cov["uncovered"], ["fig:b"])
        self.assertEqual(cov["stale_entries"], [])

    def test_entries_for_labels_that_no_longer_exist_are_stale(self):
        cov = label_coverage("\\label{tab:a}", {"tab:a": {}, "tab:gone": {}}, exempt=set())
        self.assertEqual(cov["stale_entries"], ["tab:gone"])


if __name__ == "__main__":
    unittest.main()
