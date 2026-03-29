import struct
import tempfile
import unittest
from pathlib import Path

from bench.runners.run_reduction_order_logit_flip import scalar_argmax
from bench.runners.run_reduction_order_logit_flip import summarize_lane_variants


class ReductionOrderLogitFlipTests(unittest.TestCase):
    def test_scalar_argmax_prefers_first_max(self):
        self.assertEqual(scalar_argmax([8.0, 8.0]), 0)
        self.assertEqual(scalar_argmax([6.0, 6.7]), 1)

    def test_summarize_lane_variants_detects_token_flip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            forward_logits = tmp_path / "forward.logits.bin"
            pairwise_logits = tmp_path / "pairwise.logits.bin"
            forward_logits.write_bytes(struct.pack("<ff", 6.0, 6.7))
            pairwise_logits.write_bytes(struct.pack("<ff", 6.0, 4.0))
            summary = summarize_lane_variants(
                "doe",
                {
                    "forward": {
                        "policyId": "forward",
                        "lanes": {
                            "doe": {
                                "operators": {
                                    "matmul.logits": {
                                        "stableAcrossRuns": True,
                                        "dominantDigest": "a",
                                        "artifacts": [{"capturePath": str(forward_logits)}],
                                    },
                                    "sample.token": {
                                        "stableAcrossRuns": True,
                                        "dominantDigest": "b",
                                        "dominantDecodedValue": 1,
                                    },
                                }
                            }
                        },
                    },
                    "pairwise": {
                        "policyId": "pairwise",
                        "lanes": {
                            "doe": {
                                "operators": {
                                    "matmul.logits": {
                                        "stableAcrossRuns": True,
                                        "dominantDigest": "c",
                                        "artifacts": [{"capturePath": str(pairwise_logits)}],
                                    },
                                    "sample.token": {
                                        "stableAcrossRuns": True,
                                        "dominantDigest": "d",
                                        "dominantDecodedValue": 0,
                                    },
                                }
                            }
                        },
                    },
                },
                logits_op_id="matmul.logits",
                selected_token_op_id="sample.token",
                exact_reference_logits=[6.0, 8.85],
                exact_reference_top_token=1,
            )
            self.assertTrue(summary["tokenFlipObserved"])
            self.assertTrue(summary["sampleFlipObserved"])


if __name__ == "__main__":
    unittest.main()
