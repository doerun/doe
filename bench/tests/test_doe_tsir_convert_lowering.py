"""Unit tests for the AOT convert-time TSIR lowering orchestrator."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import doe_tsir_convert_lowering as aot  # noqa: E402


def _write_manifest(tmp: Path, kernel_refs: list[str]) -> Path:
    path = tmp / "manifest.json"
    kernels = {ref: {"entry": "main"} for ref in kernel_refs}
    doc = {
        "modelId": "test-fixture",
        "inference": {
            "execution": {"kernels": kernels},
        },
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


class TestKernelRefClassification(unittest.TestCase):
    def test_bootstrap_prefix(self) -> None:
        self.assertEqual(
            aot.classify_kernel_ref("doe.tsir.bootstrap.fused_gemv"),
            "bootstrap",
        )

    def test_real_prefix(self) -> None:
        self.assertEqual(
            aot.classify_kernel_ref("doe.tsir.real.embed"), "real"
        )

    def test_external_kernel(self) -> None:
        self.assertEqual(aot.classify_kernel_ref("attn_decode"), "external")

    def test_bootstrap_short_name_extraction(self) -> None:
        self.assertEqual(
            aot.bootstrap_kernel_short_name("doe.tsir.bootstrap.rms_norm"),
            "rms_norm",
        )


class TestTargetMatrixParsing(unittest.TestCase):
    def test_default_matrix(self) -> None:
        self.assertEqual(
            aot.parse_target_matrix("webgpu-generic,wse3"),
            ("webgpu-generic", "wse3"),
        )

    def test_single_target(self) -> None:
        self.assertEqual(aot.parse_target_matrix("wse3"), ("wse3",))

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            aot.parse_target_matrix("")

    def test_strips_whitespace(self) -> None:
        self.assertEqual(
            aot.parse_target_matrix(" webgpu-generic , wse3 "),
            ("webgpu-generic", "wse3"),
        )


class TestManifestKernelLoading(unittest.TestCase):
    def test_returns_sorted_kernel_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_manifest(
                Path(tmp),
                [
                    "doe.tsir.bootstrap.rms_norm",
                    "doe.tsir.bootstrap.fused_gemv",
                    "attn_decode",
                ],
            )
            refs = aot.load_manifest_kernels(path)
        self.assertEqual(
            refs,
            [
                "attn_decode",
                "doe.tsir.bootstrap.fused_gemv",
                "doe.tsir.bootstrap.rms_norm",
            ],
        )

    def test_rejects_missing_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(
                json.dumps({"modelId": "x", "inference": {}}), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                aot.load_manifest_kernels(path)

    def test_rejects_missing_kernels_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(
                json.dumps(
                    {"modelId": "x", "inference": {"execution": {}}}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                aot.load_manifest_kernels(path)


class TestRejectionPaths(unittest.TestCase):
    def test_real_kernel_rejects_with_typed_reason(self) -> None:
        outcome = aot.reject_real_kernel_pair(
            "doe.tsir.real.embed", "wse3"
        )
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.rejection_reason, "tsir_source_not_affine")
        self.assertIn("Move 4", outcome.detail or "")

    def test_external_kernel_rejects_with_typed_reason(self) -> None:
        outcome = aot.reject_external_kernel_pair("attn_decode", "wse3")
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.rejection_reason, "tsir_source_not_affine")

    def test_rejection_is_serializable(self) -> None:
        outcome = aot.reject_real_kernel_pair(
            "doe.tsir.real.embed", "wse3"
        )
        doc = outcome.to_json()
        self.assertEqual(doc["status"], "rejected")
        self.assertEqual(doc["kernelRef"], "doe.tsir.real.embed")
        self.assertEqual(doc["backend"], "wse3")
        self.assertEqual(doc["rejectionReason"], "tsir_source_not_affine")


class TestOrchestrationShape(unittest.TestCase):
    def test_mixed_manifest_produces_outcomes_per_pair(self) -> None:
        kernel_refs = [
            "doe.tsir.real.embed",
            "attn_decode",
        ]
        target_matrix = ("webgpu-generic", "wse3")
        outcomes = aot.orchestrate_lowering(
            kernel_refs,
            target_matrix,
            receipts_dir=Path("/tmp/doe-convert-test-receipts"),
            python=sys.executable,
        )
        # 2 kernels × 2 targets = 4 outcomes
        self.assertEqual(len(outcomes), 4)
        # All should be rejected under the current TSIR coverage (real +
        # external kernels; no bootstrap in this fixture).
        self.assertTrue(all(o.status == "rejected" for o in outcomes))
        pairs = {(o.kernel_ref, o.backend) for o in outcomes}
        self.assertEqual(
            pairs,
            {
                ("doe.tsir.real.embed", "webgpu-generic"),
                ("doe.tsir.real.embed", "wse3"),
                ("attn_decode", "webgpu-generic"),
                ("attn_decode", "wse3"),
            },
        )

    def test_build_lowerings_doc_skips_rejections(self) -> None:
        outcomes = [
            aot.reject_real_kernel_pair("doe.tsir.real.embed", "wse3"),
            aot.reject_external_kernel_pair("attn_decode", "wse3"),
        ]
        doc = aot.build_lowerings_doc(outcomes)
        self.assertEqual(doc["contractVersion"], 1)
        self.assertEqual(doc["entries"], [])


class TestBootstrapFixtureAvailability(unittest.TestCase):
    """Ensures the bootstrap fixture surface is complete.

    If any bootstrap fixture goes missing or diverges from the tool's
    expectations, the orchestrator would silently reject the kernel
    with tsir_target_unfit. Keep the test close to the tool so the
    invariant fails fast.
    """

    def test_bootstrap_fixture_files_exist(self) -> None:
        for kernel in ("fused_gemv", "rms_norm", "gather"):
            self.assertTrue(
                aot.bootstrap_inputs_path(kernel).is_file(),
                f"bootstrap inputs missing for {kernel}",
            )
            semantic, realization_wg = aot.bootstrap_tsir_paths(
                kernel, "webgpu-generic"
            )
            _, realization_wse3 = aot.bootstrap_tsir_paths(kernel, "wse3")
            self.assertTrue(semantic.is_file(), f"semantic TSIR missing for {kernel}")
            self.assertTrue(
                realization_wg.is_file(),
                f"webgpu-generic realization missing for {kernel}",
            )
            self.assertTrue(
                realization_wse3.is_file(),
                f"wse3 realization missing for {kernel}",
            )
            entry_wg = aot.bootstrap_fixture_entry_path(kernel, "webgpu-generic")
            entry_wse3 = aot.bootstrap_fixture_entry_path(kernel, "wse3")
            self.assertTrue(
                entry_wg.is_file(),
                f"webgpu-generic manifest-entry fixture missing for {kernel}",
            )
            self.assertTrue(
                entry_wse3.is_file(),
                f"wse3 manifest-entry fixture missing for {kernel}",
            )


if __name__ == "__main__":
    unittest.main()
