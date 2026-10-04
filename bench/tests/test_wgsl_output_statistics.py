from __future__ import annotations

import unittest
import math

from bench.browser.wgsl_output_statistics import interval, paired_rows, summarize


class PairedWGSLStatistics(unittest.TestCase):
    settings = {"bootstrapSeed": 37, "bootstrapResamples": 10000, "confidence": 0.95}

    def test_identical_arms_have_zero_difference_and_unit_ratio(self) -> None:
        pairs = [[{"comparison": "aa", "metrics": {"applicationMs": {
            "differenceMs": 0, "logCostRatio": 0}}}] for _ in range(6)]
        summary = summarize(pairs, self.settings, 1.1)["aa"]["applicationMs"]
        self.assertEqual(summary["differenceIntervalMs"], [0, 0])
        self.assertEqual(summary["costRatioInterval"], [1, 1])
        self.assertEqual(summary["decision"], "within-practical-margin")

    def test_process_uncertainty_preserves_opposing_effects(self) -> None:
        bounds = interval([-1, 1, -1, 1, -1, 1], self.settings)
        self.assertLess(bounds[0], 0)
        self.assertGreater(bounds[1], 0)
        self.assertEqual(bounds, interval([-1, 1, -1, 1, -1, 1], self.settings))

    def test_repeated_label_bias_remains_a_control_failure(self) -> None:
        pairs = [[{"comparison": "aa", "metrics": {"applicationMs": {
            "differenceMs": 2, "logCostRatio": math.log(2)}}}] for _ in range(6)]
        summary = summarize(pairs, self.settings, 1.1)["aa"]["applicationMs"]
        self.assertEqual(summary["decision"], "meaningful-cost-increase")
        self.assertEqual(summary["differenceIntervalMs"], [2, 2])

    def test_matching_work_is_required_before_any_statistics(self) -> None:
        rows = [{"cohort": 0, "variant": name, "wgslHash": "same", "compileMs": 0,
                 "oracle": {"passed": True}, "parity": None, "workerRoundTripMs": 0,
                 "dispatches": 64 if name != "transformed" else 0,
                 "draws": 1, "workgroupsPerDispatch": 512,
                 "copiedParticleBytes": 1024, "ownedBufferBytes": 4096,
                 "pipelinePreparationMs": 1, "gpuComputeMs": 1,
                 "completeOperationMs": 2, "applicationMs": 4}
                for name in ["original", "disabled", "transformed"]]
        with self.assertRaisesRegex(ValueError, "Work shape differs"):
            paired_rows(rows, [["original", "disabled", "transformed"]])

    def test_mismatched_or_unpaired_samples_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing or extra"):
            paired_rows([], [["original", "disabled", "transformed"]])
        rows = [{"cohort": 0, "variant": variant} for variant in ["disabled", "original", "transformed"]]
        with self.assertRaisesRegex(ValueError, "Trial order"):
            paired_rows(rows, [["original", "disabled", "transformed"]])

    def test_identical_shader_control_is_required(self) -> None:
        rows = [{"cohort": 0, "variant": name, "wgslHash": name}
                for name in ["original", "disabled", "transformed"]]
        with self.assertRaisesRegex(ValueError, "A/A shader text differs"):
            paired_rows(rows, [["original", "disabled", "transformed"]])


if __name__ == "__main__":
    unittest.main()
