import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.perf_profile import CATEGORIES, categorize, parse_report, summarize_profile  # noqa: E402

PG_REPORT = """\
# To display the perf.data header info, please use --header/--header-only options.
#
# Total Lost Samples: 0
#
# Samples: 3K of event 'cycles:u'
# Event count (approx.): 2000000000
#
# Overhead  Shared Object  Symbol
# ........  .............  ......
    11.43%  vector.so         [.] HnswLoadUnvisitedFromDisk     -      -
     7.19%  postgres          [.] LWLockRelease                 -      -
     6.94%  postgres          [.] hash_search_with_hash_value   -      -
     2.80%  vector.so         [.] HalfvecInnerProductF16c       -      -
     2.23%  postgres          [.] 0x0000000000366687            -      -
     1.75%  postgres          [.] pairingheap_remove_first      -      -
     1.19%  postgres          [.] pq_startmsgread               -      -
"""


class ParseTests(unittest.TestCase):
    def test_rows_and_header(self):
        rows, meta = parse_report(PG_REPORT)
        self.assertEqual(meta["samples"], 3000)
        self.assertEqual(meta["event"], "cycles:u")
        self.assertEqual(rows[0], {"percent": 11.43, "dso": "vector.so", "symbol": "HnswLoadUnvisitedFromDisk"})
        self.assertEqual(len(rows), 7)

    def test_unresolved_symbols_are_kept_as_hex(self):
        rows, _ = parse_report(PG_REPORT)
        self.assertTrue(any(r["symbol"].startswith("0x") for r in rows))


class CategoryTests(unittest.TestCase):
    def test_every_category_name_is_listed(self):
        self.assertEqual(set(CATEGORIES), {"distance", "graph_and_element_access", "queues_and_visited",
                                           "buffer_manager", "request_path", "other", "unresolved"})

    def test_pgvector_rules(self):
        c = lambda dso, sym: categorize("pg", dso, sym)
        self.assertEqual(c("vector.so", "HalfvecInnerProductF16c"), "distance")
        self.assertEqual(c("vector.so", "vector_cosine_distance"), "distance")
        self.assertEqual(c("vector.so", "HnswLoadUnvisitedFromDisk"), "graph_and_element_access")
        self.assertEqual(c("vector.so", "tidhash_insert_hash_internal"), "queues_and_visited")
        self.assertEqual(c("postgres", "pairingheap_remove_first"), "queues_and_visited")
        self.assertEqual(c("postgres", "LWLockRelease"), "buffer_manager")
        self.assertEqual(c("postgres", "hash_search_with_hash_value"), "buffer_manager")
        self.assertEqual(c("postgres", "StartReadBuffer"), "buffer_manager")
        self.assertEqual(c("postgres", "pq_startmsgread"), "request_path")
        self.assertEqual(c("postgres", "0x0000000000366687"), "unresolved")
        self.assertEqual(c("libc.so.6", "memcpy"), "other")

    def test_qdrant_rules(self):
        c = lambda sym: categorize("qdrant", "qdrant", sym)
        self.assertEqual(c("_RNvNtNtCsc1J3DAcLXj2_7segment6spaces10simple_avx18dot_similarity_avx"), "distance")
        self.assertEqual(c("_RNvMs_NtNtNtNtCsc1J3DAcLXj2_7segment14vector_storage15chunked_vectors9read_only8re"),
                         "graph_and_element_access")
        self.assertEqual(c("_RNvXs_NtNtCsc1J3DAcLXj2_7segment14vector_storage10raw_scorerINtB4_13RawScorerImplI"),
                         "graph_and_element_access")
        self.assertEqual(c("_RNvMNtCsb5ARVqQ5dtT_6common5top_kNtB2_4TopK11cold_insert"), "queues_and_visited")
        self.assertEqual(c("_RNvMs_NtCsb5ARVqQ5dtT_6common27fixed_length_priority_queueINtB4_24Fixed"), "queues_and_visited")
        self.assertEqual(c("_RNCNCINvNtNtCs3VWlMT7VWCO_5tonic9transport6server16serve_connection"), "request_path")
        self.assertEqual(c("_RNvMs_NtCs8BMjLeSCH0f_11parking_lot7condvarNtB4_7Condvar19wait_until_internal"), "request_path")
        self.assertEqual(c("0x0000000000173613"), "unresolved")
        self.assertEqual(c("some_other_function"), "other")


class SummaryTests(unittest.TestCase):
    def test_shares_sum_to_the_listed_percent_and_are_normalized(self):
        rows, meta = parse_report(PG_REPORT)
        s = summarize_profile("pg", rows, meta)
        total = sum(r["percent"] for r in rows)
        self.assertAlmostEqual(sum(s["shares"].values()), 1.0, places=9)
        self.assertAlmostEqual(s["listed_percent"], total, places=6)
        self.assertAlmostEqual(s["shares"]["distance"], 2.80 / total, places=9)
        self.assertEqual(s["samples"], 3000)
        self.assertTrue(all(name in s["shares"] for name in CATEGORIES))


if __name__ == "__main__":
    unittest.main()
