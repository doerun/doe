from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.build_frozen_doppler_reference_manifest import (  # noqa: E402
    collect_activations,
    compute_fixture_digest as builder_compute_fixture_digest,
)
from bench.tools.validate_frozen_doppler_reference import (  # noqa: E402
    compute_fixture_digest as validator_compute_fixture_digest,
    validate_fixture,
)

_BUILDER_PATH = (
    REPO_ROOT / "bench/tools/build_frozen_doppler_reference_manifest.py"
)


def _write_npy_f32(path: Path, shape: tuple[int, ...], fill: float) -> bytes:
    """Write a tiny .npy v1.0 float32 file and return the raw bytes."""
    descr = "<f4"
    shape_str = "(" + ", ".join(str(d) for d in shape) + (",)" if len(shape) == 1 else ")")
    header_str = (
        "{'descr': '" + descr + "', 'fortran_order': False, 'shape': "
        + shape_str + ", }"
    )
    pad = 64 - ((10 + len(header_str) + 1) % 64)
    header_str = header_str + (" " * pad) + "\n"
    header_bytes = header_str.encode("latin-1")
    elems = 1
    for d in shape:
        elems *= d
    body = struct.pack("<" + "f" * elems, *([fill] * elems))
    payload = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header_bytes)) + header_bytes + body
    path.write_bytes(payload)
    return payload


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class CollectActivationsTest(unittest.TestCase):
    def test_walks_layer_dirs_and_collects_subset_of_probes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "layer_0").mkdir()
            _write_npy_f32(root / "layer_0/post_rmsnorm.npy", (4,), 1.0)
            _write_npy_f32(root / "layer_0/post_attn.npy", (4,), 2.0)
            (root / "layer_3").mkdir()
            _write_npy_f32(root / "layer_3/post_ffn.npy", (8,), 3.0)
            (root / "ignored").mkdir()
            (root / "ignored/post_rmsnorm.npy").write_bytes(b"x")

            acts = collect_activations(root)

            self.assertEqual(set(acts), {"0", "3"})
            self.assertEqual(
                set(acts["0"]), {"post_rmsnorm", "post_attn"}
            )
            self.assertEqual(set(acts["3"]), {"post_ffn"})
            for layer in acts.values():
                for spec in layer.values():
                    self.assertEqual(spec["elemDtype"], "float32")
                    self.assertEqual(len(spec["sha256"]), 64)
                    self.assertGreater(spec["byteLength"], 0)


class FixtureDigestParityTest(unittest.TestCase):
    """Builder must defer to the validator's canonical digest projection."""

    def test_builder_digest_matches_validator_digest(self) -> None:
        transcript = {
            "path": "transcript.json",
            "sha256": "a" * 64,
            "byteLength": 17,
        }
        activations = {
            "0": {
                "post_rmsnorm": {
                    "path": "layer_0/post_rmsnorm.npy",
                    "sha256": "b" * 64,
                    "byteLength": 80,
                    "elemDtype": "float32",
                    "elemShape": [19, 5376],
                },
                "post_ffn": {
                    "path": "layer_0/post_ffn.npy",
                    "sha256": "c" * 64,
                    "byteLength": 80,
                    "elemDtype": "float32",
                    "elemShape": [19, 5376],
                },
            }
        }
        builder_digest = builder_compute_fixture_digest(
            transcript=transcript,
            activations=activations,
            first_token_logits=None,
        )
        validator_digest = validator_compute_fixture_digest(
            {"transcript": transcript, "activations": activations}
        )
        self.assertEqual(builder_digest, validator_digest)


class CliRoundTripTest(unittest.TestCase):
    """End-to-end: builder writes a manifest, validator binds it."""

    def test_partial_probe_fixture_binds_through_validator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript_payload = b'{"reference":"ok"}'
            transcript_path = root / "reference-report.json"
            transcript_path.write_bytes(transcript_payload)
            (root / "layer_0").mkdir()
            _write_npy_f32(root / "layer_0/post_rmsnorm.npy", (4,), 0.5)
            _write_npy_f32(root / "layer_0/post_attn.npy", (4,), -0.5)

            result = subprocess.run(
                [
                    sys.executable,
                    str(_BUILDER_PATH),
                    "--fixture-dir",
                    str(root),
                    "--transcript",
                    str(transcript_path),
                    "--model-id",
                    "synthetic-test-model",
                    "--prompt",
                    "hello",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("fixtureDigest", result.stdout)

            manifest_path = root / "frozen-reference.manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["modelId"], "synthetic-test-model")
            self.assertEqual(set(manifest["activations"]["0"]), {"post_rmsnorm", "post_attn"})

            report = validate_fixture(root)
            self.assertTrue(report["bound"], msg=report)
            self.assertEqual(report["verdict"], "bound")
            self.assertEqual(
                report["fixtureDigestCited"], report["fixtureDigestRecomputed"]
            )

    def test_canonical_dtype_alias_does_not_violate_validator(self) -> None:
        """Builder writes elemDtype='float32'; validator reads raw '<f4' from
        the .npy header. The two must agree via the dtype-name table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript_payload = b"{}"
            (root / "transcript.json").write_bytes(transcript_payload)
            (root / "layer_0").mkdir()
            _write_npy_f32(root / "layer_0/post_rmsnorm.npy", (2,), 0.0)
            subprocess.run(
                [
                    sys.executable,
                    str(_BUILDER_PATH),
                    "--fixture-dir",
                    str(root),
                    "--transcript",
                    str(root / "transcript.json"),
                    "--model-id",
                    "synthetic-test-model",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            report = validate_fixture(root)
            self.assertEqual(report["artifactViolations"], [])
            self.assertTrue(report["bound"])


if __name__ == "__main__":
    unittest.main()
