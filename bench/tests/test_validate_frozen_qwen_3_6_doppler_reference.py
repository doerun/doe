"""Pin the frozen Qwen 3.6 27B Doppler reference fixture against its
manifest schema (parallel to the Gemma 4 31B fixture validation).

The validator at ``bench/tools/validate_frozen_doppler_reference.py`` is
model-agnostic — it walks any fixture conforming to
``config/doe-frozen-doppler-reference.schema.json``. This test binds it
to the Qwen fixture path and asserts:

  - ``frozen-reference.manifest.json`` is schema-valid
  - every cited activation .npy + transcript artifact resolves to a
    file with the cited sha256 and byteLength
  - the manifest's ``fixtureDigest`` recomputes from cited paths +
    sha256s (no path/hash drift)
  - ``modelId`` is one of the recognized Qwen 3.6 27B identifiers

Skips when the Qwen fixture is absent (the expected pre-Doppler-capture
state on this branch). The skip message names the exact Doppler tooling
that produces the fixture so reviewers can tell exactly what's missing.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.validate_frozen_doppler_reference import (  # noqa: E402
    compute_fixture_digest,
    validate_fixture,
)

QWEN_FIXTURE_ROOT = REPO_ROOT / "bench" / "fixtures" / "r3-2-27b-doppler-frozen"
QWEN_MANIFEST = QWEN_FIXTURE_ROOT / "frozen-reference.manifest.json"
QWEN_MODEL_IDS = {
    "qwen-3-6-27b-q4k-ehaf16",
    "qwen-3-6-27b-it-text-q4k-ehaf16",
}
DOPPLER_CAPTURE_INVOCATION = (
    "doppler/docs/cerebras-tsir-fixture-capture.md (Qwen 3.6 27B section); "
    "tl;dr: doppler/tools/run-program-bundle-reference.js "
    "--manifest models/local/qwen-3-6-27b-q4k-ehaf16/manifest.json "
    '--prompt "The color of the sky is" '
    "--tsir-fixture-dir <doe-repo>/bench/fixtures/r3-2-27b-doppler-frozen "
    "--tsir-fixture-layer-filter 3"
)


class FrozenQwenReferenceFixtureTest(unittest.TestCase):
    """Bind-when-present, skip-when-absent. Same pattern as the q4k
    SUMMA receipt parity baseline-witness tests."""

    @classmethod
    def setUpClass(cls) -> None:
        if not QWEN_MANIFEST.is_file():
            raise unittest.SkipTest(
                f"Qwen frozen-reference fixture missing: "
                f"{QWEN_MANIFEST.relative_to(REPO_ROOT)}. "
                f"Capture the Qwen Doppler reference run first; the "
                f"canonical invocation is `{DOPPLER_CAPTURE_INVOCATION}` "
                f"on Doppler's `feat/qwen-3-6-bringup` branch (parallel "
                f"to bench/fixtures/r3-1-31b-doppler-frozen/ for Gemma)."
            )

    def setUp(self) -> None:
        self.manifest = json.loads(QWEN_MANIFEST.read_text(encoding="utf-8"))
        self.report = validate_fixture(QWEN_FIXTURE_ROOT)

    def test_schema_valid(self) -> None:
        self.assertTrue(
            self.report.get("schemaValid"),
            f"schema validation failed: {self.report.get('violations')}",
        )

    def test_artifacts_bind(self) -> None:
        self.assertTrue(
            self.report.get("bound"),
            f"artifact binding failed: violations="
            f"{self.report.get('violations')}",
        )

    def test_verdict_is_bound(self) -> None:
        self.assertEqual(
            self.report.get("verdict"),
            "bound",
            f"verdict={self.report.get('verdict')!r}; expected 'bound'",
        )

    def test_fixture_digest_recomputes(self) -> None:
        cited = self.manifest.get("fixtureDigest")
        recomputed = compute_fixture_digest(self.manifest)
        self.assertEqual(
            cited,
            recomputed,
            "fixtureDigest in the manifest does not recompute from the "
            "cited paths/sha256s — the manifest has drifted from the "
            "fixture it claims to bind.",
        )

    def test_model_id_matches_qwen_3_6_27b(self) -> None:
        model_id = self.manifest.get("modelId")
        self.assertIn(
            model_id,
            QWEN_MODEL_IDS,
            f"modelId={model_id!r} is not in the recognized Qwen 3.6 27B "
            f"set {sorted(QWEN_MODEL_IDS)}; either the fixture was "
            f"captured against the wrong model or this test's "
            f"QWEN_MODEL_IDS set needs an entry.",
        )

    def test_first_full_attention_layer_probes_present(self) -> None:
        # The four-probe boundary set (frozen-Doppler-reference expectation) must be
        # present at L=3, the first full-attention layer in Qwen 3.6's
        # linear x3 -> full hybrid pattern, for downstream parity.
        activations = self.manifest.get("activations") or {}
        layer_3 = activations.get("3") or activations.get(3) or {}
        expected_probes = {
            "post_rmsnorm",
            "post_qkv",
            "post_attn",
            "post_ffn",
        }
        present = set(layer_3.keys()) if isinstance(layer_3, dict) else set()
        missing = expected_probes - present
        self.assertFalse(
            missing,
            f"L=3 probe(s) missing from manifest: {sorted(missing)}; "
            f"present={sorted(present)}",
        )


if __name__ == "__main__":
    unittest.main()
