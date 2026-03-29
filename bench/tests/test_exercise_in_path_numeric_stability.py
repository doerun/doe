#!/usr/bin/env python3
"""Tests for the in-path numeric-stability exercise runner."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

from bench.lib.config_validation import load_validated_config  # noqa: E402
from bench.runners.exercise_in_path_numeric_stability import (  # noqa: E402
    build_commands_from_request,
)
from bench.runners.exercise_runtime_numeric_stability import (  # noqa: E402
    prompt_request_from_signature,
)
from bench.runners.promote_numeric_fragility_signatures import FRAGILITY_SIGNATURE_SCHEMA_PATH  # noqa: E402


class ExerciseInPathNumericStabilityTests(unittest.TestCase):
    def test_build_commands_from_real_signature_keeps_numeric_stability_annotation(self) -> None:
        signature = load_validated_config(
            REPO_ROOT
            / "config"
            / "fragility-signatures"
            / "promoted"
            / "prompt-lm-head-flip-red-go-stop-answer-2f8677733c.json",
            FRAGILITY_SIGNATURE_SCHEMA_PATH,
        )
        request, _ = prompt_request_from_signature(
            signature,
            "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
        )
        commands = build_commands_from_request(request)
        self.assertEqual(len(commands), 4)
        kernel_dispatch = commands[-1]
        self.assertEqual(kernel_dispatch["kind"], "kernel_dispatch")
        self.assertEqual(
            kernel_dispatch["kernel"],
            "bench/inference-pipeline/kernels/matmul_logits_forward_f16accum.wgsl",
        )
        self.assertEqual(kernel_dispatch["semanticOpId"], "matmul.logits")
        self.assertIn("numericStability", kernel_dispatch)
        self.assertEqual(
            kernel_dispatch["numericStability"]["routingPolicyId"],
            "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
        )
        self.assertEqual(
            [candidate["tokenId"] for candidate in kernel_dispatch["numericStability"]["candidates"]],
            [817, 4721],
        )


if __name__ == "__main__":
    unittest.main()
