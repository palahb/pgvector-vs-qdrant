import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.e23_gate import (coverage, decide, doc_of_segment, load_qrels, passages_to_documents,  # noqa: E402
                               segment_v2_docs)


class DocIdTests(unittest.TestCase):
    def test_segment_id_maps_to_the_v2_document_id(self):
        self.assertEqual(doc_of_segment("msmarco_v2.1_doc_00_10#2_30"), "msmarco_doc_00_10")
        self.assertEqual(doc_of_segment("msmarco_v2.1_doc_59_1234567#0_9"), "msmarco_doc_59_1234567")

    def test_v2_document_id_is_unchanged(self):
        self.assertEqual(doc_of_segment("msmarco_doc_00_10"), "msmarco_doc_00_10")


class SegmentMappingTests(unittest.TestCase):
    V2 = ["msmarco_doc_00_0\thttp://a/\t0", "msmarco_doc_00_4806\thttp://b/\t4806", "msmarco_doc_00_9\thttp://c/\t9"]
    SEGMENTS = ["msmarco_v2.1_doc_00_0#0_0\thttp://a/", "msmarco_v2.1_doc_00_0#1_9\thttp://a/",
                "msmarco_v2.1_doc_00_4810#0_0\thttp://b/", "msmarco_v2.1_doc_00_77#0_0\thttp://zzz/"]

    def test_segments_map_to_the_v2_document_with_the_same_url(self):
        mapped = segment_v2_docs(self.SEGMENTS, self.V2)
        self.assertEqual(mapped, ["msmarco_doc_00_0", "msmarco_doc_00_0", "msmarco_doc_00_4806", None])

    def test_a_url_shared_by_two_v2_documents_is_not_mapped(self):
        v2 = self.V2 + ["msmarco_doc_00_5\thttp://a/\t5"]
        self.assertEqual(segment_v2_docs(self.SEGMENTS, v2)[:2], [None, None])


class PassageQrelsTests(unittest.TestCase):
    def test_passage_judgments_become_document_judgments_with_the_best_grade(self):
        qrels = {"1": {"p1": 2, "p2": 3, "p3": 1}, "2": {"p9": 3}}
        out = passages_to_documents(qrels, {"p1": "doc_a", "p2": "doc_a", "p3": "doc_b"})
        self.assertEqual(out["1"], {"doc_a": 3, "doc_b": 1})

    def test_a_passage_with_an_unknown_document_stays_a_document_of_its_own(self):
        out = passages_to_documents({"2": {"p9": 3}}, {})
        self.assertEqual(out["2"], {"p9": 3})   # kept, so it counts in the total, but never matches the prefix


class QrelsTests(unittest.TestCase):
    def test_reads_trec_lines_and_keeps_the_highest_grade_per_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.txt"
            path.write_text("1 0 msmarco_doc_00_1 3\n1 0 msmarco_doc_00_2 0\n2 0 msmarco_doc_00_1 1\n1 0 msmarco_doc_00_1 2\n")
            q = load_qrels(path)
        self.assertEqual(q["1"], {"msmarco_doc_00_1": 3, "msmarco_doc_00_2": 0})
        self.assertEqual(q["2"], {"msmarco_doc_00_1": 1})


class CoverageTests(unittest.TestCase):
    QRELS = {"1": {"d1": 3, "d2": 2, "d3": 1, "d4": 0}, "2": {"d5": 2, "d6": 3}, "3": {"d1": 1}}

    def test_counts_relevant_documents_at_grade_two_or_more(self):
        c = coverage(self.QRELS, prefix_docs={"d1", "d3", "d5"}, query_ids={"1", "2", "3"})
        self.assertEqual(c["q_judged"], 2)  # query 3 has only a grade-1 document
        self.assertEqual(c["r_total"], 4)   # d1, d2, d5, d6
        self.assertEqual(c["r_in"], 2)      # d1, d5
        self.assertAlmostEqual(c["coverage"], 0.5)
        self.assertEqual(c["q_cov"], 2)     # queries 1 and 2 have a relevant document in the prefix

    def test_queries_outside_the_query_set_are_not_counted(self):
        c = coverage(self.QRELS, {"d1"}, query_ids={"1"})
        self.assertEqual((c["q_judged"], c["r_total"]), (1, 2))

    def test_queries_without_a_relevant_document_are_not_judged_relevant(self):
        c = coverage({"9": {"d1": 0, "d2": 1}}, {"d1"}, {"9"})
        self.assertEqual((c["q_judged"], c["r_total"], c["q_cov"]), (0, 0, 0))


class DecisionTests(unittest.TestCase):
    def test_absolute_when_coverage_and_queries_suffice(self):
        self.assertEqual(decide({"coverage": 0.6, "q_cov": 80})["mode"], "absolute")

    def test_boundary_values_pass(self):
        self.assertEqual(decide({"coverage": 0.5, "q_cov": 50})["mode"], "absolute")

    def test_sensitivity_when_only_the_query_count_suffices(self):
        self.assertEqual(decide({"coverage": 0.04, "q_cov": 50})["mode"], "sensitivity")

    def test_not_measured_below_fifty_queries(self):
        self.assertEqual(decide({"coverage": 0.9, "q_cov": 49})["mode"], "not_measured")


if __name__ == "__main__":
    unittest.main()
