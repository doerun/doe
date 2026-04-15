import unittest
import tempfile
import struct
from pathlib import Path

from bench.runners.run_reduction_order_counterexample import summarize_lane
from bench.runners.run_reduction_order_counterexample import ulp_distance


class ReductionOrderCounterexampleTests(unittest.TestCase):
    def test_ulp_distance_is_zero_for_equal_words(self):
        self.assertEqual(ulp_distance(0x3f800000, 0x3f800000), 0)

    def test_summarize_lane_detects_counterexample(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            forward_path = tmp_path / "forward.bin"
            reverse_path = tmp_path / "reverse.bin"
            forward_path.write_bytes(struct.pack("<f", 5.0))
            reverse_path.write_bytes(struct.pack("<f", 8.0))
            summary = summarize_lane(
                "doe",
                {
                    "forward": {
                        "policyId": "forward",
                        "lanes": {
                            "doe": {
                                "operators": {
                                    "dot.output": {
                                        "stableAcrossRuns": True,
                                        "dominantDigest": "a",
                                        "artifacts": [{"capturePath": str(forward_path)}],
                                    }
                                }
                            }
                        },
                    },
                    "reverse": {
                        "policyId": "reverse",
                        "lanes": {
                            "doe": {
                                "operators": {
                                    "dot.output": {
                                        "stableAcrossRuns": True,
                                        "dominantDigest": "b",
                                        "artifacts": [{"capturePath": str(reverse_path)}],
                                    }
                                }
                            }
                        },
                    },
                },
                {
                    "captures": [{"semanticOpId": "dot.output"}],
                    "exactReferenceValue": 6.0,
                },
            )
            self.assertTrue(summary["counterexampleObserved"])
            self.assertEqual(summary["uniqueOutputValueCount"], 2)


if __name__ == "__main__":
    unittest.main()
