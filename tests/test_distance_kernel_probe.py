import unittest

from bench.run_distance_kernel import parse_json_lines


class DistanceKernelProbeTests(unittest.TestCase):
    def test_json_line_parser_preserves_kernel_measurements(self):
        rows = parse_json_lines(
            '{"kernel":"scalar","ns_per_distance":10.5}\n'
            '{"kernel":"avx2_fma","ns_per_distance":3.25}\n'
        )
        self.assertEqual([row["kernel"] for row in rows], ["scalar", "avx2_fma"])
        self.assertEqual(rows[1]["ns_per_distance"], 3.25)


if __name__ == "__main__":
    unittest.main()
