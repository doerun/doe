"""Tests for TSIR manifest lowering entry binding helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-manifest-entries"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import tsir_manifest_lowering  # noqa: E402


class TestTsirManifestLowering(unittest.TestCase):
    def _valid_inputs(self) -> tsir_manifest_lowering.ManifestLoweringInputs:
        return tsir_manifest_lowering.ManifestLoweringInputs(
            kernel_ref="gemma-4-e2b.rmsnorm",
            backend="wse3",
            target_descriptor_correctness_hash="1" * 64,
            frontend_version="frontend-0.1.0",
            tsir_semantic_digest="2" * 64,
            tsir_realization_digest="3" * 64,
            emitter_digest="4" * 64,
            compiler_version="doe-0.3.2",
            exactness_class="algorithm_exact",
            algorithm_exact_invariants=("reduction_order", "tree_shape"),
        )

    def test_builds_runtime_canonical_manifest_entry(self) -> None:
        entry = tsir_manifest_lowering.build_manifest_lowering_entry(
            self._valid_inputs()
        )
        canonical = tsir_manifest_lowering.canonical_entry_bytes(entry).decode(
            "utf-8"
        )

        expected = (
            '{"backend":"wse3",'
            '"compilerVersion":"doe-0.3.2",'
            '"emitterDigest":"'
            + "4" * 64
            + '",'
            '"exactness":{'
            '"algorithmExactInvariants":["reduction_order","tree_shape"],'
            '"class":"algorithm_exact",'
            '"toleranceEpsilon":0,'
            '"toleranceMetric":""},'
            '"frontendVersion":"frontend-0.1.0",'
            '"kernelRef":"gemma-4-e2b.rmsnorm",'
            '"rejectionReasons":[],'
            '"targetDescriptorCorrectnessHash":"'
            + "1" * 64
            + '",'
            '"tsirRealizationDigest":"'
            + "3" * 64
            + '",'
            '"tsirSemanticDigest":"'
            + "2" * 64
            + '"}'
        )
        self.assertEqual(canonical, expected)
        self.assertEqual(
            tsir_manifest_lowering.manifest_lowering_entry_digest(entry),
            hashlib.sha256(expected.encode("utf-8")).hexdigest(),
        )

    def test_builder_rejects_uppercase_digest(self) -> None:
        inputs = self._valid_inputs()
        bad = tsir_manifest_lowering.ManifestLoweringInputs(
            kernel_ref=inputs.kernel_ref,
            backend=inputs.backend,
            target_descriptor_correctness_hash="A" * 64,
            frontend_version=inputs.frontend_version,
            tsir_semantic_digest=inputs.tsir_semantic_digest,
            tsir_realization_digest=inputs.tsir_realization_digest,
            emitter_digest=inputs.emitter_digest,
            compiler_version=inputs.compiler_version,
            exactness_class=inputs.exactness_class,
            algorithm_exact_invariants=inputs.algorithm_exact_invariants,
        )
        with self.assertRaisesRegex(ValueError, "64 lowercase hex"):
            tsir_manifest_lowering.build_manifest_lowering_entry(bad)

    def test_builder_rejects_duplicate_rejection_reasons(self) -> None:
        inputs = self._valid_inputs()
        bad = tsir_manifest_lowering.ManifestLoweringInputs(
            kernel_ref=inputs.kernel_ref,
            backend=inputs.backend,
            target_descriptor_correctness_hash=(
                inputs.target_descriptor_correctness_hash
            ),
            frontend_version=inputs.frontend_version,
            tsir_semantic_digest=inputs.tsir_semantic_digest,
            tsir_realization_digest=inputs.tsir_realization_digest,
            emitter_digest=inputs.emitter_digest,
            compiler_version=inputs.compiler_version,
            exactness_class=inputs.exactness_class,
            algorithm_exact_invariants=inputs.algorithm_exact_invariants,
            rejection_reasons=("tsir_target_unfit", "tsir_target_unfit"),
        )
        with self.assertRaisesRegex(ValueError, "duplicates"):
            tsir_manifest_lowering.build_manifest_lowering_entry(bad)

    def test_schema_rejects_algorithm_exact_without_invariants(self) -> None:
        entry = tsir_manifest_lowering.build_manifest_lowering_entry(
            self._valid_inputs()
        )
        entry["exactness"] = {"class": "algorithm_exact"}
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            tsir_manifest_lowering.validate_entry_doc(entry)

    def test_schema_rejects_unknown_fields(self) -> None:
        entry = tsir_manifest_lowering.build_manifest_lowering_entry(
            self._valid_inputs()
        )
        entry["manifestLoweringEntryDigest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            tsir_manifest_lowering.validate_entry_doc(entry)

    def test_validate_existing_entry_file(self) -> None:
        entry = tsir_manifest_lowering.build_manifest_lowering_entry(
            self._valid_inputs()
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entry.json"
            path.write_text(json.dumps(entry), encoding="utf-8")
            self.assertEqual(tsir_manifest_lowering.load_entry_doc(path), entry)

    def test_cli_builds_entry_and_prints_digest(self) -> None:
        script = REPO_ROOT / "bench" / "tools" / "tsir_manifest_lowering.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--kernel-ref",
                "gemma-4-e2b.rmsnorm",
                "--backend",
                "wse3",
                "--target-descriptor-correctness-hash",
                "1" * 64,
                "--frontend-version",
                "frontend-0.1.0",
                "--tsir-semantic-digest",
                "2" * 64,
                "--tsir-realization-digest",
                "3" * 64,
                "--emitter-digest",
                "4" * 64,
                "--compiler-version",
                "doe-0.3.2",
                "--exactness-class",
                "algorithm_exact",
                "--algorithm-exact-invariant",
                "reduction_order",
                "--algorithm-exact-invariant",
                "tree_shape",
                "--print-digest",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(result.stdout)
        tsir_manifest_lowering.validate_entry_doc(entry)
        self.assertIn("manifestLoweringEntryDigest=", result.stderr)

    def test_bootstrap_fixtures_validate_and_bind_distinct_targets(self) -> None:
        paths = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertEqual(len(paths), 6)

        seen = set()
        semantic_by_kernel: dict[str, str] = {}
        realization_by_pair: dict[tuple[str, str], str] = {}
        for path in paths:
            entry = tsir_manifest_lowering.load_entry_doc(path)
            digest = tsir_manifest_lowering.manifest_lowering_entry_digest(entry)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertNotEqual(entry["emitterDigest"], "0" * 64)

            pair = (entry["kernelRef"], entry["backend"])
            self.assertNotIn(pair, seen)
            seen.add(pair)

            semantic_by_kernel.setdefault(
                entry["kernelRef"],
                entry["tsirSemanticDigest"],
            )
            self.assertEqual(
                semantic_by_kernel[entry["kernelRef"]],
                entry["tsirSemanticDigest"],
            )
            realization_by_pair[pair] = entry["tsirRealizationDigest"]

        for kernel_ref in semantic_by_kernel:
            webgpu = realization_by_pair[(kernel_ref, "webgpu-generic")]
            wse3 = realization_by_pair[(kernel_ref, "wse3")]
            self.assertNotEqual(webgpu, wse3)

    def test_bootstrap_fixtures_share_version_and_descriptor_identity(self) -> None:
        """The full bootstrap fixture set must agree on
        `frontendVersion`, `compilerVersion`, and per-backend
        `targetDescriptorCorrectnessHash`.

        Partial regeneration — someone runs the generator after a
        frontend bump on one fixture but forgets the others, or
        bumps the target descriptor and regenerates only one
        backend's fixture — would leave the set internally
        inconsistent. Downstream consumers (canary, manifest binder,
        parity CLI) all assume the set is a coherent snapshot of a
        single compiler+descriptor state; inconsistency silently
        attributes receipts to a compiler identity that never
        existed. Catch that before it reaches Loop 3 promotion.
        """
        paths = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertEqual(len(paths), 6)

        frontend_versions: set[str] = set()
        compiler_versions: set[str] = set()
        descriptor_hashes: dict[str, str] = {}
        for path in paths:
            entry = tsir_manifest_lowering.load_entry_doc(path)
            frontend_versions.add(entry["frontendVersion"])
            compiler_versions.add(entry["compilerVersion"])
            backend = entry["backend"]
            descriptor_hash = entry["targetDescriptorCorrectnessHash"]
            if backend in descriptor_hashes:
                self.assertEqual(
                    descriptor_hashes[backend],
                    descriptor_hash,
                    msg=(
                        f"{path.name}: targetDescriptorCorrectnessHash "
                        f"drifted for backend {backend!r} — set is not a "
                        "coherent descriptor snapshot"
                    ),
                )
            else:
                descriptor_hashes[backend] = descriptor_hash

        self.assertEqual(
            len(frontend_versions),
            1,
            msg=f"fixture set disagrees on frontendVersion: {frontend_versions}",
        )
        self.assertEqual(
            len(compiler_versions),
            1,
            msg=f"fixture set disagrees on compilerVersion: {compiler_versions}",
        )
        # Both target descriptors must be present and distinct.
        self.assertEqual(set(descriptor_hashes), {"webgpu-generic", "wse3"})
        self.assertNotEqual(
            descriptor_hashes["webgpu-generic"],
            descriptor_hashes["wse3"],
        )


if __name__ == "__main__":
    unittest.main()
