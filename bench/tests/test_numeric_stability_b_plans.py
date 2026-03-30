#!/usr/bin/env python3
"""Validation tests for B-track numeric-stability planning surfaces."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

from bench.lib.config_validation import load_validated_config  # noqa: E402


class NumericStabilityBPlanTests(unittest.TestCase):
    def test_auto_detection_plan_validates_and_stays_runtime_first(self) -> None:
        plan = load_validated_config(
            REPO_ROOT / "config" / "numeric-stability-auto-detection-plan.json",
            REPO_ROOT / "config" / "numeric-stability-auto-detection-plan.schema.json",
        )
        self.assertEqual(plan["proposalState"], "planning-only")
        self.assertFalse(plan["currentLiveBoundary"]["requiresAnnotation"])
        self.assertEqual(
            plan["currentLiveBoundary"]["operatorFamilies"],
            ["matmul.logits", "rmsnorm.output", "attention.output"],
        )
        self.assertIn("abstain", plan["currentLiveBoundary"]["routeDecisions"])

        profile_ids = {profile["profileId"] for profile in plan["detectionProfiles"]}
        self.assertIn("matmul-logits-shadow-v1", profile_ids)
        self.assertIn("rmsnorm-output-auto-detect-v1", profile_ids)
        self.assertIn("attention-output-auto-detect-v1", profile_ids)

    def test_operator_expansion_plan_ranks_expected_families(self) -> None:
        plan = load_validated_config(
            REPO_ROOT / "config" / "numeric-stability-operator-expansion-plan.json",
            REPO_ROOT / "config" / "numeric-stability-operator-expansion-plan.schema.json",
        )
        self.assertEqual(plan["proposalState"], "planning-only")
        ranked = [(entry["rank"], entry["semanticOpId"]) for entry in plan["operatorFamilies"]]
        self.assertEqual(ranked[0], (1, "softmax.denominator"))
        self.assertEqual(ranked[1], (2, "layernorm.output"))


if __name__ == "__main__":
    unittest.main()
