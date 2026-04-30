from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._inference_evidence_gate import (  # noqa: E402
    InferenceEvidenceGateError,
    REASON_DISPATCH_EVIDENCE_ABSENT,
    REASON_DISPATCH_EVIDENCE_LM_HEAD_MISSING,
    REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND,
    REASON_DISPATCH_EVIDENCE_SAMPLE_UNBOUND,
    REASON_KERNEL_REGISTRY_MISSING_LM_HEAD,
    REASON_LM_HEAD_DANGLING,
    REASON_NO_TOKEN_OUTPUT_PHASE,
    REASON_SAMPLE_PREDECESSOR_NOT_LM_HEAD,
    REASON_SAMPLE_WITHOUT_LOGITS_PRODUCER,
    REASON_TARGET_INVENTORY_MISMATCH,
    enforce_inference_evidence_gate,
    evaluate_inference_evidence_gate,
)


def _good_host_plan() -> dict:
    return {
        "hostPlan": {
            "kernels": [
                {"name": "embed", "pattern": "embed"},
                {"name": "lm_head_gemv", "pattern": "fused_gemv_dequant"},
                {"name": "sample", "pattern": "sample"},
            ],
            "phases": {
                "decode": [
                    {"kernelName": "embed"},
                    {"kernelName": "lm_head_gemv"},
                    {"kernelName": "sample"},
                ],
            },
        },
    }


def _good_per_kernel() -> dict:
    return {
        "kernels": [
            {"kernel": "embed", "verdict": "bound"},
            {
                "kernel": "lm_head_gemv",
                "verdict": "bound",
                "dispatchMode": "monolithic_full_fabric",
                "lmHeadEvidenceScope": "manifest_shape_direct_dispatch",
            },
            {"kernel": "sample", "verdict": "bound"},
        ],
    }


def _codes(result) -> set[str]:
    return {r.code for r in result.reasons}


class InferenceEvidenceGateTest(unittest.TestCase):
    def test_good_plan_passes(self) -> None:
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(),
            per_kernel_summary=_good_per_kernel(),
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())

    def test_sample_without_upstream_lm_head(self) -> None:
        plan = _good_host_plan()
        plan["hostPlan"]["phases"]["decode"] = [
            {"kernelName": "embed"},
            {"kernelName": "sample"},
        ]
        result = evaluate_inference_evidence_gate(
            host_plan=plan, per_kernel_summary=_good_per_kernel(),
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_SAMPLE_WITHOUT_LOGITS_PRODUCER, _codes(result))

    def test_sample_predecessor_not_lm_head(self) -> None:
        plan = _good_host_plan()
        plan["hostPlan"]["kernels"].append(
            {"name": "rmsnorm", "pattern": "rmsnorm"}
        )
        plan["hostPlan"]["phases"]["decode"] = [
            {"kernelName": "lm_head_gemv"},
            {"kernelName": "rmsnorm"},
            {"kernelName": "sample"},
        ]
        evidence = _good_per_kernel()
        evidence["kernels"].append({"kernel": "rmsnorm", "verdict": "bound"})
        result = evaluate_inference_evidence_gate(
            host_plan=plan, per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_SAMPLE_PREDECESSOR_NOT_LM_HEAD, _codes(result))

    def test_lm_head_dangling_in_phase_with_no_sample(self) -> None:
        plan = _good_host_plan()
        plan["hostPlan"]["phases"]["prefill"] = [
            {"kernelName": "embed"},
            {"kernelName": "lm_head_gemv"},
        ]
        result = evaluate_inference_evidence_gate(
            host_plan=plan, per_kernel_summary=_good_per_kernel(),
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_LM_HEAD_DANGLING, _codes(result))

    def test_kernel_registry_missing_lm_head(self) -> None:
        plan = {
            "hostPlan": {
                "kernels": [
                    {"name": "embed", "pattern": "embed"},
                    {"name": "sample", "pattern": "sample"},
                ],
                "phases": {
                    "decode": [
                        {"kernelName": "embed"},
                        {"kernelName": "sample"},
                    ],
                },
            },
        }
        result = evaluate_inference_evidence_gate(
            host_plan=plan,
            per_kernel_summary={
                "kernels": [
                    {"kernel": "embed", "verdict": "bound"},
                    {"kernel": "sample", "verdict": "bound"},
                ],
            },
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_KERNEL_REGISTRY_MISSING_LM_HEAD, _codes(result))

    def test_no_token_output_phase_when_sample_not_terminal(self) -> None:
        plan = _good_host_plan()
        plan["hostPlan"]["kernels"].append(
            {"name": "residual", "pattern": "residual"}
        )
        plan["hostPlan"]["phases"]["decode"] = [
            {"kernelName": "embed"},
            {"kernelName": "lm_head_gemv"},
            {"kernelName": "sample"},
            {"kernelName": "residual"},
        ]
        evidence = _good_per_kernel()
        evidence["kernels"].append({"kernel": "residual", "verdict": "bound"})
        result = evaluate_inference_evidence_gate(
            host_plan=plan, per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_NO_TOKEN_OUTPUT_PHASE, _codes(result))

    def test_dispatch_evidence_absent_rejects(self) -> None:
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(),
            per_kernel_summary=None,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_ABSENT, _codes(result))

    def test_dispatch_evidence_optional_when_disabled(self) -> None:
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(),
            per_kernel_summary=None,
            require_dispatch_evidence=False,
        )
        self.assertTrue(result.eligible)

    def test_sample_blocked_verdict(self) -> None:
        evidence = _good_per_kernel()
        for entry in evidence["kernels"]:
            if entry["kernel"] == "sample":
                entry["verdict"] = "blocked"
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_SAMPLE_UNBOUND, _codes(result))

    def test_sample_missing_from_dispatch(self) -> None:
        evidence = _good_per_kernel()
        evidence["kernels"] = [
            entry for entry in evidence["kernels"]
            if entry["kernel"] != "sample"
        ]
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_SAMPLE_UNBOUND, _codes(result))

    def test_lm_head_missing_from_dispatch(self) -> None:
        evidence = _good_per_kernel()
        evidence["kernels"] = [
            entry for entry in evidence["kernels"]
            if entry["kernel"] != "lm_head_gemv"
        ]
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_LM_HEAD_MISSING, _codes(result))

    def test_lm_head_blocked_verdict(self) -> None:
        evidence = _good_per_kernel()
        for entry in evidence["kernels"]:
            if entry["kernel"] == "lm_head_gemv":
                entry["verdict"] = "blocked"
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND, _codes(result))

    def test_lm_head_bound_without_dispatch_mode_rejects(self) -> None:
        evidence = _good_per_kernel()
        for entry in evidence["kernels"]:
            if entry["kernel"] == "lm_head_gemv":
                entry.pop("dispatchMode")
                entry.pop("lmHeadEvidenceScope")
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND, _codes(result))

    def test_lm_head_width_tiled_requires_complete_contract(self) -> None:
        evidence = _good_per_kernel()
        for entry in evidence["kernels"]:
            if entry["kernel"] == "lm_head_gemv":
                entry["dispatchMode"] = "dense_gemv_width_tiled"
                entry["lmHeadEvidenceScope"] = (
                    "full_vocab_host_reduced_width_row_tiles"
                )
                entry["tileDispatches"] = {
                    "tileCount": 2,
                    "blockedCount": 1,
                    "boundCount": 1,
                }
                entry["tileCoverage"] = {"covered": False}
                entry["hostReduction"] = {"kind": "sum_hidden_width_tiles"}
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND, _codes(result))

    def test_lm_head_width_tiled_promotes_with_complete_contract(self) -> None:
        evidence = _good_per_kernel()
        for entry in evidence["kernels"]:
            if entry["kernel"] == "lm_head_gemv":
                entry["dispatchMode"] = "dense_gemv_width_tiled"
                entry["lmHeadEvidenceScope"] = (
                    "full_vocab_host_reduced_width_row_tiles"
                )
                entry["tileDispatches"] = {
                    "tileCount": 2,
                    "blockedCount": 0,
                    "boundCount": 2,
                }
                entry["tileCoverage"] = {
                    "covered": True,
                    "tileShapeSafety": {"safe": True},
                }
                entry["hostReduction"] = {"kind": "sum_hidden_width_tiles"}
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())

    def test_lm_head_width_tiled_rejects_unsafe_shape(self) -> None:
        evidence = _good_per_kernel()
        for entry in evidence["kernels"]:
            if entry["kernel"] == "lm_head_gemv":
                entry["dispatchMode"] = "dense_gemv_width_tiled"
                entry["lmHeadEvidenceScope"] = (
                    "full_vocab_host_reduced_width_row_tiles"
                )
                entry["tileDispatches"] = {
                    "tileCount": 2,
                    "blockedCount": 0,
                    "boundCount": 2,
                }
                entry["tileCoverage"] = {
                    "covered": True,
                    "tileShapeSafety": {"safe": False},
                    "unsafeTileShapeAllowed": True,
                }
                entry["hostReduction"] = {"kind": "sum_hidden_width_tiles"}
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(), per_kernel_summary=evidence,
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND, _codes(result))

    def test_target_inventory_mismatch(self) -> None:
        result = evaluate_inference_evidence_gate(
            host_plan=_good_host_plan(),
            per_kernel_summary=_good_per_kernel(),
            source_graph_kernels=[
                "embed", "lm_head_gemv", "sample", "rmsnorm",
            ],
        )
        self.assertFalse(result.eligible)
        self.assertIn(REASON_TARGET_INVENTORY_MISMATCH, _codes(result))

    def test_enforce_raises_typed_error(self) -> None:
        with self.assertRaises(InferenceEvidenceGateError) as ctx:
            enforce_inference_evidence_gate(
                host_plan=_good_host_plan(),
                per_kernel_summary=None,
            )
        self.assertEqual(
            {r.code for r in ctx.exception.result.reasons},
            {REASON_DISPATCH_EVIDENCE_ABSENT},
        )

    def test_enforce_returns_result_when_eligible(self) -> None:
        result = enforce_inference_evidence_gate(
            host_plan=_good_host_plan(),
            per_kernel_summary=_good_per_kernel(),
        )
        self.assertTrue(result.eligible)


if __name__ == "__main__":
    unittest.main()
