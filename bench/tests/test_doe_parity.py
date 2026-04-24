"""Unit tests for the Doe parity harness CLI (bench/tools/doe_parity.py)."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import doe_parity  # noqa: E402


def _write_input_doc(
    tmp_path: Path,
    kernel: str,
    inputs: dict[str, dict[str, object]],
    parameters: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / f"{kernel}.oracle-inputs.json"
    payload = {
        "kernel": kernel,
        "inputs": inputs,
        "parameters": parameters or {},
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestParityScaffolding(unittest.TestCase):
    def test_valid_exactness_set_matches_rdrr_taxonomy(self) -> None:
        self.assertEqual(
            doe_parity.VALID_EXACTNESS,
            frozenset(
                {"bit_exact_solo", "algorithm_exact", "tolerance_bounded"}
            ),
        )

    def test_rejection_reasons_match_tsir_taxonomy(self) -> None:
        self.assertEqual(
            doe_parity.REJECTION_REASONS,
            frozenset(
                {
                    "tsir_subgroup_unlowerable",
                    "tsir_pe_budget_exhausted",
                    "tsir_collective_not_representable",
                    "tsir_dependence_unanalyzable",
                    "tsir_source_not_affine",
                    "tsir_target_unfit",
                }
            ),
        )

    def test_rejection_taxonomy_is_consistent_across_schemas(self) -> None:
        """Lockstep check across the four JSON schemas that carry the TSIR
        rejection taxonomy plus the Python CLI's `REJECTION_REASONS`.

        Catches drift where someone adds or renames a reason in one place
        and forgets another — the taxonomy must move in lockstep or not at
        all, since it's a single wire contract shared across semantic,
        realization, manifest-lowering, and parity-receipt artifacts. The
        Zig canonical enum `runtime/zig/src/tsir/schema.zig::RejectionReason`
        is verified separately by `tests/wgsl/tsir_scaffold_test.zig` test
        'rejection taxonomy is exhaustive and enumerable'.
        """

        def find_tsir_enum(obj: object) -> frozenset[str] | None:
            """Return the first enum list containing tsir_* entries."""
            if isinstance(obj, dict):
                enum = obj.get("enum")
                if (
                    isinstance(enum, list)
                    and any(
                        isinstance(v, str) and v.startswith("tsir_")
                        for v in enum
                    )
                ):
                    return frozenset(v for v in enum if isinstance(v, str))
                for v in obj.values():
                    found = find_tsir_enum(v)
                    if found is not None:
                        return found
            elif isinstance(obj, list):
                for v in obj:
                    found = find_tsir_enum(v)
                    if found is not None:
                        return found
            return None

        config_dir = REPO_ROOT / "config"
        schema_files = (
            "doe-parity-receipt.schema.json",
            "doe-tsir-semantic.schema.json",
            "doe-tsir-realization.schema.json",
            "doe-tsir-manifest-lowering.schema.json",
        )
        schema_sets: dict[str, frozenset[str]] = {}
        for name in schema_files:
            with (config_dir / name).open(encoding="utf-8") as handle:
                doc = json.load(handle)
            enum = find_tsir_enum(doc)
            self.assertIsNotNone(enum, f"no tsir_* enum found in {name}")
            schema_sets[name] = enum  # type: ignore[assignment]

        canonical = doe_parity.REJECTION_REASONS
        for name, enum in schema_sets.items():
            self.assertEqual(
                enum,
                canonical,
                f"{name} rejection taxonomy drifted from doe_parity.REJECTION_REASONS",
            )

    def test_reference_interpreter_is_not_implemented(self) -> None:
        outcome = doe_parity.run_reference_interpreter("rmsnorm", "abc")
        self.assertEqual(outcome.backend, "reference")
        self.assertEqual(outcome.status, "not_implemented")

    def test_reference_interpreter_runs_fused_gemv_bootstrap_inputs(self) -> None:
        semantic = (
            REPO_ROOT
            / "runtime"
            / "zig"
            / "tests"
            / "tsir"
            / "bootstrap"
            / "fused_gemv.tsir-semantic.json"
        )
        realization = (
            REPO_ROOT
            / "runtime"
            / "zig"
            / "tests"
            / "tsir"
            / "bootstrap"
            / "fused_gemv.tsir-realization.webgpu-generic.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            inputs_path = _write_input_doc(
                Path(tmp),
                "fused_gemv",
                {
                    "W": {
                        "elem": "f32",
                        "shape": [2, 2],
                        "values": [1.0, 2.0, 4.0, 8.0],
                    },
                    "x": {
                        "elem": "f32",
                        "shape": [2],
                        "values": [1.0, 2.0],
                    },
                },
            )
            outcome = doe_parity.run_reference_interpreter(
                "fused_gemv",
                "abc",
                inputs_path=inputs_path,
                semantic_path=semantic,
                realization_path=realization,
            )
        expected = _sha256_hex(struct.pack("<ff", 5.0, 20.0))
        self.assertEqual(outcome.backend, "reference")
        self.assertEqual(outcome.status, "pass")
        self.assertEqual(outcome.backend_hash, expected)
        self.assertEqual(outcome.detail, "zig bootstrap TSIR oracle executed")

    def test_reference_interpreter_runs_gather_bootstrap_inputs(self) -> None:
        semantic = (
            REPO_ROOT
            / "runtime"
            / "zig"
            / "tests"
            / "tsir"
            / "bootstrap"
            / "gather.tsir-semantic.json"
        )
        realization = (
            REPO_ROOT
            / "runtime"
            / "zig"
            / "tests"
            / "tsir"
            / "bootstrap"
            / "gather.tsir-realization.webgpu-generic.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            inputs_path = _write_input_doc(
                Path(tmp),
                "gather",
                {
                    "indices": {
                        "elem": "u32",
                        "shape": [2],
                        "values": [1, 0],
                    },
                    "table": {
                        "elem": "f32",
                        "shape": [2, 2],
                        "values": [1.5, 2.5, 3.5, 4.5],
                    },
                },
            )
            outcome = doe_parity.run_reference_interpreter(
                "gather",
                "abc",
                inputs_path=inputs_path,
                semantic_path=semantic,
                realization_path=realization,
            )
        expected = _sha256_hex(struct.pack("<ffff", 3.5, 4.5, 1.5, 2.5))
        self.assertEqual(outcome.status, "pass")
        self.assertEqual(outcome.backend_hash, expected)

    def test_reference_interpreter_runs_rms_norm_with_uniform_epsilon(
        self,
    ) -> None:
        semantic = (
            REPO_ROOT
            / "runtime"
            / "zig"
            / "tests"
            / "tsir"
            / "bootstrap"
            / "rms_norm.tsir-semantic.json"
        )
        realization = (
            REPO_ROOT
            / "runtime"
            / "zig"
            / "tests"
            / "tsir"
            / "bootstrap"
            / "rms_norm.tsir-realization.webgpu-generic.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            inputs_path = _write_input_doc(
                Path(tmp),
                "rms_norm",
                {
                    "input": {
                        "elem": "f32",
                        "shape": [2],
                        "values": [2.0, 2.0],
                    },
                    "weight": {
                        "elem": "f32",
                        "shape": [2],
                        "values": [3.0, 4.0],
                    },
                    "u": {
                        "elem": "u32",
                        "shape": [2],
                        "bytesHex": "0000000000000000",
                    },
                },
            )
            outcome = doe_parity.run_reference_interpreter(
                "rms_norm",
                "abc",
                inputs_path=inputs_path,
                semantic_path=semantic,
                realization_path=realization,
            )
        expected = _sha256_hex(struct.pack("<ff", 3.0, 4.0))
        self.assertEqual(outcome.status, "pass")
        self.assertEqual(outcome.backend_hash, expected)

    def test_reference_interpreter_declines_manifest_fixture_inputs(self) -> None:
        fixture = (
            REPO_ROOT
            / "bench"
            / "fixtures"
            / "tsir-manifest-entries"
            / "fused_gemv.webgpu-generic.json"
        )
        outcome = doe_parity.run_reference_interpreter(
            "fused_gemv",
            "abc",
            inputs_path=fixture,
        )
        self.assertEqual(outcome.status, "not_implemented")
        self.assertIn("unsupported or missing kernel/inputs", outcome.detail or "")

    def test_reference_interpreter_declines_gather_oob_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs_path = _write_input_doc(
                Path(tmp),
                "gather",
                {
                    "indices": {
                        "elem": "u32",
                        "shape": [1],
                        "values": [2],
                    },
                    "table": {
                        "elem": "f32",
                        "shape": [2, 1],
                        "values": [1.0, 2.0],
                    },
                },
            )
            outcome = doe_parity.run_reference_interpreter(
                "gather",
                "abc",
                inputs_path=inputs_path,
            )
        self.assertEqual(outcome.status, "not_implemented")
        self.assertIn("cannot execute this input", outcome.detail or "")

    def test_reference_interpreter_reports_rejected_tsir(self) -> None:
        outcome = doe_parity.run_reference_interpreter(
            "rmsnorm",
            "abc",
            ["tsir_collective_not_representable", "tsir_target_unfit"],
        )
        self.assertEqual(outcome.backend, "reference")
        self.assertEqual(outcome.status, "rejected")
        self.assertIn("tsir_collective_not_representable", outcome.detail or "")

    def test_backend_lanes_are_not_implemented(self) -> None:
        for backend in ("webgpu", "csl-simfabric"):
            with self.subTest(backend=backend):
                outcome = doe_parity.run_backend(backend)
                self.assertEqual(outcome.status, "not_implemented")

    def test_compare_defers_when_reference_missing(self) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference", status="not_implemented"
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="not_implemented"
        )
        result = doe_parity.compare(reference, backend, "bit_exact_solo")
        self.assertEqual(result.status, "deferred")

    def test_compare_defers_when_backend_missing_after_reference_executes(
        self,
    ) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference", status="pass", backend_hash="abc"
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="not_implemented"
        )
        result = doe_parity.compare(reference, backend, "bit_exact_solo")
        self.assertEqual(result.status, "deferred")
        self.assertIn("reference=pass", result.detail or "")

    def test_compare_marks_backend_rejected_when_reference_rejects(self) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference",
            status="rejected",
            detail="TSIR rejected before execution: tsir_target_unfit",
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="not_implemented"
        )
        result = doe_parity.compare(reference, backend, "bit_exact_solo")
        self.assertEqual(result.status, "rejected")
        self.assertIn("reference=rejected", result.detail or "")

    def test_compare_rejects_unknown_exactness_class(self) -> None:
        reference = doe_parity.ComparisonOutcome(backend="reference", status="ok")
        backend = doe_parity.ComparisonOutcome(backend="webgpu", status="ok")
        with self.assertRaises(ValueError):
            doe_parity.compare(reference, backend, "looks_good_to_me")

    def test_tolerance_bounded_refuses_without_metric_wiring(self) -> None:
        reference = doe_parity.ComparisonOutcome(
            backend="reference", status="ok", backend_hash="abc"
        )
        backend = doe_parity.ComparisonOutcome(
            backend="webgpu", status="ok", backend_hash="abc"
        )
        result = doe_parity.compare(reference, backend, "tolerance_bounded")
        self.assertEqual(result.status, "fail")
        self.assertIn("tolerance_bounded", result.detail or "")

    def test_bit_exact_pass_and_fail(self) -> None:
        ref = doe_parity.ComparisonOutcome(
            backend="reference", status="ok", backend_hash="deadbeef"
        )
        ok = doe_parity.ComparisonOutcome(
            backend="webgpu", status="ok", backend_hash="deadbeef"
        )
        self.assertEqual(
            doe_parity.compare(ref, ok, "bit_exact_solo").status, "pass"
        )
        bad = doe_parity.ComparisonOutcome(
            backend="webgpu", status="ok", backend_hash="cafef00d"
        )
        self.assertEqual(
            doe_parity.compare(ref, bad, "bit_exact_solo").status, "fail"
        )

    def test_schema_is_well_formed(self) -> None:
        schema_path = REPO_ROOT / "config" / "doe-parity-receipt.schema.json"
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["$id"], "doe-parity-receipt.schema.json")
        self.assertEqual(parsed["properties"]["schemaVersion"]["const"], 2)
        self.assertIn("bit_exact_solo", parsed["properties"]["exactnessClass"]["enum"])

    def test_generated_receipt_validates_against_schema(self) -> None:
        receipt = doe_parity.ParityReceipt(
            schema_version=2,
            artifact_kind="doe_parity_receipt",
            kernel="rmsnorm",
            exactness_class="bit_exact_solo",
            reference_hash=None,
            inputs_digest="0" * 64,
            comparisons=[
                doe_parity.ComparisonOutcome(
                    backend="reference",
                    status="pass",
                    backend_hash="1" * 64,
                    detail="oracle executed",
                ),
                doe_parity.ComparisonOutcome(
                    backend="webgpu",
                    status="deferred",
                    detail="backend pending",
                ),
            ],
            rejection_reasons=[],
        )
        doe_parity.validate_receipt_doc(receipt.to_json())

    def test_receipt_schema_rejects_invalid_comparison_status(self) -> None:
        receipt = doe_parity.ParityReceipt(
            schema_version=2,
            artifact_kind="doe_parity_receipt",
            kernel="rmsnorm",
            exactness_class="bit_exact_solo",
            reference_hash=None,
            inputs_digest="0" * 64,
            comparisons=[
                doe_parity.ComparisonOutcome(
                    backend="reference",
                    status="not_implemented",
                ),
            ],
            rejection_reasons=[],
        )
        doc = receipt.to_json()
        doc["comparisons"][0]["status"] = "looks_green"
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            doe_parity.validate_receipt_doc(doc)

    def test_lowering_identity_from_manifest_fixture(self) -> None:
        fixture = (
            REPO_ROOT
            / "bench"
            / "fixtures"
            / "tsir-manifest-entries"
            / "fused_gemv.webgpu-generic.json"
        )
        entry = json.loads(fixture.read_text(encoding="utf-8"))
        identity = doe_parity.lowering_identity_from_manifest_entry(
            fixture,
            "algorithm_exact",
        )
        self.assertIsNotNone(identity)
        self.assertEqual(
            identity.to_json(),
            {
                "emitterDigest": entry["emitterDigest"],
                "targetDescriptorCorrectnessHash": (
                    entry["targetDescriptorCorrectnessHash"]
                ),
                "tsirRealizationDigest": entry["tsirRealizationDigest"],
                "tsirSemanticDigest": entry["tsirSemanticDigest"],
            },
        )

    def test_manifest_fixture_identity_receipt_stays_non_claimable(self) -> None:
        fixture = (
            REPO_ROOT
            / "bench"
            / "fixtures"
            / "tsir-manifest-entries"
            / "fused_gemv.webgpu-generic.json"
        )
        identity = doe_parity.lowering_identity_from_manifest_entry(
            fixture,
            "algorithm_exact",
        )
        receipt = doe_parity.ParityReceipt(
            schema_version=2,
            artifact_kind="doe_parity_receipt",
            kernel="fused_gemv",
            exactness_class="algorithm_exact",
            reference_hash=None,
            inputs_digest="0" * 64,
            comparisons=[
                doe_parity.ComparisonOutcome(
                    backend="reference",
                    status="not_implemented",
                ),
                doe_parity.ComparisonOutcome(
                    backend="webgpu",
                    status="deferred",
                    detail="backend pending",
                ),
            ],
            rejection_reasons=[],
            lowering_identity=identity,
        )
        doc = receipt.to_json()
        self.assertIn("loweringIdentity", doc)
        doe_parity.validate_receipt_doc(doc)
        self.assertNotIn("pass", {row["status"] for row in doc["comparisons"]})

    def test_manifest_lowering_exactness_mismatch_rejects(self) -> None:
        fixture = (
            REPO_ROOT
            / "bench"
            / "fixtures"
            / "tsir-manifest-entries"
            / "fused_gemv.webgpu-generic.json"
        )
        with self.assertRaisesRegex(ValueError, "exactness class"):
            doe_parity.lowering_identity_from_manifest_entry(
                fixture,
                "bit_exact_solo",
            )

    def test_extract_rejection_reasons_deduplicates_and_validates(self) -> None:
        reasons = doe_parity.extract_rejection_reasons(
            {
                "rejections": [
                    {"reason": "tsir_target_unfit"},
                    {"reason": "tsir_target_unfit"},
                ]
            },
            {
                "rejections": [
                    {"reason": "tsir_collective_not_representable"},
                ]
            },
        )
        self.assertEqual(
            reasons,
            ["tsir_target_unfit", "tsir_collective_not_representable"],
        )

    def test_extract_rejection_reasons_rejects_unknown_reason(self) -> None:
        with self.assertRaises(ValueError):
            doe_parity.extract_rejection_reasons(
                {"rejections": [{"reason": "looks_fine"}]},
                {"rejections": []},
            )


if __name__ == "__main__":
    unittest.main()
