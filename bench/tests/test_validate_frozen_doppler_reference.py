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


if __name__ == "__main__":
    unittest.main()
