"""Tests for the TSIR real-kernel manifest fixture generator."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import generate_tsir_real_manifest_fixtures as gen  # noqa: E402


class TestRealManifestFixtureGenerator(unittest.TestCase):
    def test_generated_entries_are_schema_valid_and_non_sentinel(self) -> None:
        fixtures = gen.generate_entries()
        self.assertEqual(
            len(fixtures), len(gen.KERNEL_EXACTNESS) * len(gen.SUPPORTED_BACKENDS)
        )
        for name, entry in fixtures.items():
            with self.subTest(name=name):
                self.assertTrue(
                    name.startswith(("embed.", "lm_head_gemv.")),
                    f"unexpected fixture name: {name}",
                )
                for field in (
                    "tsirSemanticDigest",
                    "tsirRealizationDigest",
                    "emitterDigest",
                    "targetDescriptorCorrectnessHash",
                ):
                    digest = entry[field]
                    self.assertNotEqual(
                        digest,
                        gen.SENTINEL_DIGEST,
                        f"{field} is the zero sentinel in {name}",
                    )
                    self.assertEqual(
                        len(digest), 64, f"{field} is not 64-char hex in {name}"
                    )
                self.assertTrue(
                    entry["kernelRef"].startswith(gen.REAL_KERNEL_REF_PREFIX),
                    f"kernelRef does not carry real prefix in {name}",
                )
                self.assertEqual(entry["compilerVersion"], gen.REAL_COMPILER_VERSION)

    def test_per_backend_pins_match_bootstrap(self) -> None:
        for backend in gen.SUPPORTED_BACKENDS:
            emitter, target = gen.load_bootstrap_backend_pins(backend)
            self.assertNotEqual(emitter, gen.SENTINEL_DIGEST)
            self.assertNotEqual(target, gen.SENTINEL_DIGEST)
            for kernel in gen.KERNEL_EXACTNESS:
                entry = gen.real_kernel_entry(kernel, backend)
                self.assertEqual(
                    entry["emitterDigest"],
                    emitter,
                    f"{kernel}.{backend} emitterDigest diverged from bootstrap pin",
                )
                self.assertEqual(
                    entry["targetDescriptorCorrectnessHash"],
                    target,
                    f"{kernel}.{backend} targetDescriptorCorrectnessHash diverged "
                    "from bootstrap pin",
                )

    def test_sentinel_emitter_digest_refused(self) -> None:
        with mock.patch.object(
            gen,
            "load_bootstrap_backend_pins",
            return_value=(gen.SENTINEL_DIGEST, "a" * 64),
        ):
            with self.assertRaisesRegex(ValueError, "emitterDigest"):
                gen.real_kernel_entry("embed", "webgpu-generic")

    def test_sentinel_target_descriptor_refused(self) -> None:
        with mock.patch.object(
            gen,
            "load_bootstrap_backend_pins",
            return_value=("a" * 64, gen.SENTINEL_DIGEST),
        ):
            with self.assertRaisesRegex(
                ValueError, "targetDescriptorCorrectnessHash"
            ):
                gen.real_kernel_entry("embed", "webgpu-generic")

    def test_sentinel_semantic_digest_refused_via_empty_json(self) -> None:
        # sha256 of the canonical form of {} is a known non-zero constant, so
        # a truly zero digest cannot arise from valid JSON. We simulate the
        # failure path by patching _canonical_sha256 to return the sentinel
        # for the semantic file and leaving the realization alone.
        real_sha = gen._canonical_sha256
        calls = {"n": 0}

        def fake_sha(path: Path) -> str:
            calls["n"] += 1
            return gen.SENTINEL_DIGEST if calls["n"] == 1 else real_sha(path)

        with mock.patch.object(gen, "_canonical_sha256", side_effect=fake_sha):
            with self.assertRaisesRegex(ValueError, "tsirSemanticDigest"):
                gen.real_kernel_entry("embed", "webgpu-generic")

    def test_unknown_kernel_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "KERNEL_EXACTNESS registry"):
            gen.real_kernel_entry("attention_head256_f16kv", "wse3")

    def test_generator_output_matches_disk(self) -> None:
        fixtures = gen.generate_entries()
        for name, entry in fixtures.items():
            path = gen.DEFAULT_OUTPUT_DIR / name
            self.assertTrue(path.exists(), f"missing committed fixture: {path}")
            disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                disk,
                entry,
                f"committed fixture drifts from generator output: {path}",
            )


if __name__ == "__main__":
    unittest.main()
