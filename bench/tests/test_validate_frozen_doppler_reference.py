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

from bench.tools.validate_frozen_doppler_reference import (  # noqa: E402
    compute_fixture_digest,
    validate_fixture,
)
from bench.tools._lane_dtype_profile import (  # noqa: E402
    LaneDtypeProfileError,
    assert_lane_match,
    canonical_dtype_profile,
    lane_key,
    lane_suffix,
    receipt_path_lane_suffix,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_npy(path: Path, dtype: str = "float32", shape: tuple = (4,)) -> bytes:
    """Write a minimal v1.0 .npy file. Returns the raw bytes."""
    header_dict = (
        f"{{'descr': '<{dtype[0] if dtype == 'float32' else 'f'}4', "
        if dtype == "float32"
        else "{'descr': '<f4', "
    )
    # Use the canonical numpy v1.0 format directly.
    header_str = (
        "{"
        f"'descr': '<f4', 'fortran_order': False, 'shape': ({shape[0]},), "
        "}"
    )
    pad_len = 64 - ((10 + len(header_str)) % 64)
    header_str = header_str + " " * (pad_len - 1) + "\n"
    header_bytes = header_str.encode("latin-1")
    payload = (
        b"\x93NUMPY"
        + b"\x01\x00"
        + struct.pack("<H", len(header_bytes))
        + header_bytes
    )
    payload += b"\x00\x00\x00\x00" * shape[0]
    path.write_bytes(payload)
    return payload


def _build_minimal_fixture(root: Path) -> dict:
    """Materialize a minimal fixture and return the manifest dict (already
    written to disk with the correct fixtureDigest)."""
    transcript_payload = b'{"reference":"ok"}'
    transcript_path = root / "transcript.json"
    transcript_path.write_bytes(transcript_payload)

    activations_dir = root / "activations" / "1"
    activations_dir.mkdir(parents=True, exist_ok=True)
    rms_payload = _write_npy(activations_dir / "post_rmsnorm.npy")
    qkv_payload = _write_npy(activations_dir / "post_qkv.npy")

    manifest = {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_manifest",
        "modelId": "gemma-4-31b-it-text-q4k-ehf16-af32",
        "transcript": {
            "path": "transcript.json",
            "sha256": _sha256_bytes(transcript_payload),
            "byteLength": len(transcript_payload),
        },
        "activations": {
            "1": {
                "post_rmsnorm": {
                    "path": "activations/1/post_rmsnorm.npy",
                    "sha256": _sha256_bytes(rms_payload),
                    "byteLength": len(rms_payload),
                },
                "post_qkv": {
                    "path": "activations/1/post_qkv.npy",
                    "sha256": _sha256_bytes(qkv_payload),
                    "byteLength": len(qkv_payload),
                },
            }
        },
        "fixtureDigest": "0" * 64,
    }
    digest = compute_fixture_digest(manifest)
    manifest["fixtureDigest"] = digest
    (root / "frozen-reference.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


class FixtureDigestTest(unittest.TestCase):
    def test_digest_is_stable_across_serialization_orders(self) -> None:
        manifest_a = {
            "transcript": {"path": "t.json", "sha256": "a" * 64},
            "activations": {
                "1": {
                    "post_rmsnorm": {"path": "a.npy", "sha256": "b" * 64},
                    "post_qkv": {"path": "b.npy", "sha256": "c" * 64},
                }
            },
        }
        manifest_b = {
            "transcript": {"path": "t.json", "sha256": "a" * 64},
            "activations": {
                "1": {
                    "post_qkv": {"path": "b.npy", "sha256": "c" * 64},
                    "post_rmsnorm": {"path": "a.npy", "sha256": "b" * 64},
                }
            },
        }
        self.assertEqual(
            compute_fixture_digest(manifest_a),
            compute_fixture_digest(manifest_b),
        )

    def test_digest_changes_when_artifact_hash_changes(self) -> None:
        base = {
            "transcript": {"path": "t.json", "sha256": "a" * 64},
            "activations": {
                "1": {"post_rmsnorm": {"path": "a.npy", "sha256": "b" * 64}}
            },
        }
        drift = {
            "transcript": {"path": "t.json", "sha256": "a" * 64},
            "activations": {
                "1": {"post_rmsnorm": {"path": "a.npy", "sha256": "0" * 64}}
            },
        }
        self.assertNotEqual(
            compute_fixture_digest(base), compute_fixture_digest(drift)
        )


class ValidateFixtureTest(unittest.TestCase):
    def test_minimal_fixture_validates(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            manifest = _build_minimal_fixture(root)
            report = validate_fixture(root)
            self.assertTrue(report["bound"], msg=report)
            self.assertTrue(report["schemaValid"])
            self.assertEqual(report["artifactViolations"], [])
            self.assertEqual(report["digestViolations"], [])
            self.assertEqual(
                report["fixtureDigestCited"], manifest["fixtureDigest"]
            )

    def test_artifact_hash_drift_caught(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture(root)
            (root / "transcript.json").write_bytes(b"different bytes")
            report = validate_fixture(root)
            self.assertFalse(report["bound"], msg=report)
            self.assertTrue(
                any(
                    "transcript: sha256 drift" in v
                    for v in report["artifactViolations"]
                )
            )

    def test_missing_artifact_caught(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture(root)
            (root / "transcript.json").unlink()
            report = validate_fixture(root)
            self.assertFalse(report["bound"], msg=report)
            self.assertTrue(
                any(
                    "transcript: cited path=" in v
                    for v in report["artifactViolations"]
                )
            )

    def test_fixture_digest_drift_caught(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            manifest = _build_minimal_fixture(root)
            manifest["fixtureDigest"] = "0" * 64
            (root / "frozen-reference.manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = validate_fixture(root)
            self.assertFalse(report["bound"], msg=report)
            self.assertTrue(
                any(
                    "fixtureDigest drift" in v
                    for v in report["digestViolations"]
                )
            )

    def test_schema_violation_caught(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture(root)
            manifest = json.loads(
                (root / "frozen-reference.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            del manifest["modelId"]
            (root / "frozen-reference.manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = validate_fixture(root)
            self.assertFalse(report["bound"], msg=report)
            self.assertFalse(report["schemaValid"])
            self.assertTrue(report["schemaErrors"])

    def test_unknown_probe_point_rejected_by_schema(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture(root)
            manifest = json.loads(
                (root / "frozen-reference.manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            manifest["activations"]["1"]["unsupported_probe"] = {
                "path": "x.npy",
                "sha256": "f" * 64,
            }
            (root / "frozen-reference.manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report = validate_fixture(root)
            self.assertFalse(report["bound"], msg=report)
            self.assertFalse(report["schemaValid"])

    def test_missing_manifest_raises(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            with self.assertRaises(SystemExit):
                validate_fixture(root)


class LaneDtypeProfileHelperTest(unittest.TestCase):
    """Cover the canonical-profile / lane-key / suffix helpers."""

    AF32_QI = {
        "weights": "q4k",
        "embeddings": "f16",
        "compute": "f32",
        "layout": "row",
        "variantTag": "q4k-ehf16-af32",
    }
    AF16_QI = {
        "weights": "q4k",
        "embeddings": "f16",
        "compute": "f16",
        "layout": "row",
        "variantTag": "q4k-ehf16-af16",
    }
    QWEN_QI = {
        "weights": "q4k",
        "embeddings": "f16",
        "lmHead": "q4k",
        "compute": "f32",
        "layout": "row",
        "variantTag": "q4k-ef16-af32",
    }

    def test_canonical_profile_defaults_lmhead_to_weights(self) -> None:
        profile = canonical_dtype_profile(self.AF32_QI)
        self.assertEqual(profile["lmHead"], "q4k")
        self.assertEqual(profile["compute"], "f32")
        self.assertEqual(profile["variantTag"], "q4k-ehf16-af32")

    def test_canonical_profile_preserves_explicit_lmhead(self) -> None:
        profile = canonical_dtype_profile(self.QWEN_QI)
        self.assertEqual(profile["lmHead"], "q4k")

    def test_canonical_profile_rejects_missing_required(self) -> None:
        bad = dict(self.AF32_QI)
        del bad["variantTag"]
        with self.assertRaises(LaneDtypeProfileError):
            canonical_dtype_profile(bad)

    def test_canonical_profile_rejects_none(self) -> None:
        with self.assertRaises(LaneDtypeProfileError):
            canonical_dtype_profile(None)

    def test_lane_key_returns_variant_tag(self) -> None:
        self.assertEqual(lane_key(self.AF16_QI), "q4k-ehf16-af16")

    def test_lane_suffix_derives_from_compute(self) -> None:
        self.assertEqual(lane_suffix(self.AF32_QI), "af32")
        self.assertEqual(lane_suffix(self.AF16_QI), "af16")

    def test_receipt_path_suffix_empty_for_af32(self) -> None:
        # Pre-existing af32 receipt paths are NOT renamed; helper returns ''
        # so new writers preserve legacy paths for the af32 lane.
        self.assertEqual(receipt_path_lane_suffix(self.AF32_QI), "")

    def test_receipt_path_suffix_set_for_af16(self) -> None:
        self.assertEqual(receipt_path_lane_suffix(self.AF16_QI), "af16")

    def test_assert_lane_match_passes_when_aligned(self) -> None:
        profile = canonical_dtype_profile(self.AF16_QI)
        assert_lane_match("q4k-ehf16-af16", profile)  # no raise

    def test_assert_lane_match_raises_on_mismatch(self) -> None:
        profile = canonical_dtype_profile(self.AF32_QI)
        with self.assertRaises(LaneDtypeProfileError):
            assert_lane_match("q4k-ehf16-af16", profile)

    def test_assert_lane_match_permissive_when_absent(self) -> None:
        # Default permissive behavior: legacy fixtures lacking dtypeProfile
        # are accepted so they continue to bind.
        assert_lane_match("q4k-ehf16-af32", None)  # no raise

    def test_assert_lane_match_strict_when_required(self) -> None:
        with self.assertRaises(LaneDtypeProfileError):
            assert_lane_match(
                "q4k-ehf16-af16", None, permissive_when_absent=False
            )


def _build_minimal_fixture_with_profile(
    root: Path, dtype_profile: dict | None
) -> dict:
    """Build the minimal fixture and inject an optional dtypeProfile."""
    manifest = _build_minimal_fixture(root)
    if dtype_profile is not None:
        manifest["dtypeProfile"] = dtype_profile
        (root / "frozen-reference.manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


class ValidateFixtureLaneKeyTest(unittest.TestCase):
    """Cover --lane-key / --require-dtype-profile behavior end-to-end."""

    AF16_PROFILE = {
        "weights": "q4k",
        "embeddings": "f16",
        "compute": "f16",
        "variantTag": "q4k-ehf16-af16",
    }
    AF32_PROFILE = {
        "weights": "q4k",
        "embeddings": "f16",
        "compute": "f32",
        "variantTag": "q4k-ehf16-af32",
    }

    def test_legacy_fixture_binds_without_lane_key(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture_with_profile(root, None)
            report = validate_fixture(root)
            self.assertTrue(report["bound"], msg=report)
            self.assertIsNone(report["dtypeProfile"])
            self.assertEqual(report["laneViolations"], [])

    def test_legacy_fixture_permissive_with_lane_key(self) -> None:
        # Lane key set, no require flag, no dtypeProfile in fixture →
        # permissive bind for backward compat with pre-contract fixtures.
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture_with_profile(root, None)
            report = validate_fixture(
                root, lane_key="q4k-ehf16-af32"
            )
            self.assertTrue(report["bound"], msg=report)
            self.assertEqual(report["laneKeyExpected"], "q4k-ehf16-af32")

    def test_legacy_fixture_rejected_when_dtype_profile_required(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture_with_profile(root, None)
            report = validate_fixture(
                root,
                lane_key="q4k-ehf16-af16",
                require_dtype_profile=True,
            )
            self.assertFalse(report["bound"], msg=report)
            self.assertTrue(report["laneViolations"])

    def test_dtype_profile_match_binds(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture_with_profile(root, self.AF16_PROFILE)
            report = validate_fixture(
                root,
                lane_key="q4k-ehf16-af16",
                require_dtype_profile=True,
            )
            self.assertTrue(report["bound"], msg=report)
            self.assertEqual(report["dtypeProfile"], self.AF16_PROFILE)
            self.assertEqual(report["laneViolations"], [])

    def test_dtype_profile_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            _build_minimal_fixture_with_profile(root, self.AF32_PROFILE)
            report = validate_fixture(
                root,
                lane_key="q4k-ehf16-af16",
                require_dtype_profile=True,
            )
            self.assertFalse(report["bound"], msg=report)
            self.assertTrue(
                any("lane key mismatch" in v for v in report["laneViolations"]),
                msg=report["laneViolations"],
            )

    def test_dtype_profile_schema_required_fields(self) -> None:
        # Schema enforces required fields on dtypeProfile when present —
        # missing variantTag is a schema violation, not just a lane mismatch.
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            bad_profile = {
                "weights": "q4k",
                "embeddings": "f16",
                "compute": "f16",
            }
            _build_minimal_fixture_with_profile(root, bad_profile)
            report = validate_fixture(root)
            self.assertFalse(report["bound"], msg=report)
            self.assertFalse(report["schemaValid"])


if __name__ == "__main__":
    unittest.main()
