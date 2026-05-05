from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from bench.tools.build_doppler_to_csl_splice_receipt import build_receipt


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


class BuildDopplerToCslSpliceReceiptTest(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, Path]:
        manifest = root / "manifest.json"
        _write(manifest, b'{"model":"x"}\n')
        reference = root / "reference.json"
        reference_payload = {
            "manifestSha256": _sha(manifest.read_bytes()),
            "executionGraphSha256": "1" * 64,
            "weightSetSha256": "2" * 64,
            "inputSetSha256": "3" * 64,
            "programBundleId": None,
            "decodeTranscript": {
                "generatedTokenIds": {"preview": [3730]},
                "promptTokenCount": 4,
            },
        }
        reference.write_text(json.dumps(reference_payload), encoding="utf-8")
        fixture = root / "fixture"
        input_sha = _write(fixture / "layer_59/pre_layer_input.npy", b"input")
        expected = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)
        np.save(fixture / "layer_59/post_ffn.npy", expected)
        expected_sha = _sha((fixture / "layer_59/post_ffn.npy").read_bytes())
        fixture_manifest = {
            "schemaVersion": 1,
            "artifactKind": "doe_frozen_doppler_reference_manifest",
            "modelId": "gemma-4-31b-it-text-q4k-ehf16-af16",
            "fixtureDigest": "f" * 64,
            "transcript": {"path": "reference.json", "sha256": "0" * 64},
            "activations": {
                "59": {
                    "pre_layer_input": {
                        "path": "layer_59/pre_layer_input.npy",
                        "sha256": input_sha,
                    },
                    "post_ffn": {
                        "path": "layer_59/post_ffn.npy",
                        "sha256": expected_sha,
                    },
                }
            },
        }
        (fixture / "frozen-reference.manifest.json").write_text(
            json.dumps(fixture_manifest), encoding="utf-8"
        )
        return {"manifest": manifest, "reference": reference, "fixture": fixture}

    def test_single_block_blocks_without_csl_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            args = type("Args", (), {
                "kind": "single_block_hidden",
                "layer_index": 59,
                "model_id": "gemma-4-31b-it-text-q4k-ehf16-af16",
                "manifest": paths["manifest"],
                "reference_export": paths["reference"],
                "frozen_fixture_root": paths["fixture"],
                "input_probe": "pre_layer_input",
                "expected_probe": "post_ffn",
                "csl_output_tensor": None,
                "csl_output_token_id": None,
                "csl_command": None,
                "atol": 0.02,
                "rtol": 0.02,
            })()
            receipt = build_receipt(args)
        self.assertEqual(receipt["verdict"], "blocked")
        self.assertEqual(receipt["blocker"], "csl_splice_output_absent")
        self.assertEqual(
            receipt["comparison"]["status"], "blocked_missing_csl_output"
        )
        self.assertEqual(
            receipt["dopplerReference"]["inputTensor"]["sha256"],
            _sha(b"input"),
        )

    def test_single_block_matches_identical_tensor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            csl = root / "csl.npy"
            np.save(csl, np.asarray([1.001, 1.999, 3.002], dtype=np.float16))
            args = type("Args", (), {
                "kind": "single_block_hidden",
                "layer_index": 59,
                "model_id": "gemma-4-31b-it-text-q4k-ehf16-af16",
                "manifest": paths["manifest"],
                "reference_export": paths["reference"],
                "frozen_fixture_root": paths["fixture"],
                "input_probe": "pre_layer_input",
                "expected_probe": "post_ffn",
                "csl_output_tensor": csl,
                "csl_output_token_id": None,
                "csl_command": "test",
                "atol": 0.02,
                "rtol": 0.02,
            })()
            receipt = build_receipt(args)
        self.assertEqual(receipt["verdict"], "bound")
        self.assertIsNone(receipt["blocker"])
        self.assertTrue(receipt["comparison"]["match"])
        self.assertEqual(receipt["comparison"]["mode"], "hidden_tensor_tolerance")

    def test_tail_token_compares_token_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._fixture(Path(tmp))
            args = type("Args", (), {
                "kind": "last_layer_tail_token",
                "layer_index": 59,
                "model_id": "gemma-4-31b-it-text-q4k-ehf16-af16",
                "manifest": paths["manifest"],
                "reference_export": paths["reference"],
                "frozen_fixture_root": paths["fixture"],
                "input_probe": "pre_layer_input",
                "expected_probe": "post_ffn",
                "csl_output_tensor": None,
                "csl_output_token_id": 3730,
                "csl_command": "test",
                "atol": 0.02,
                "rtol": 0.02,
            })()
            receipt = build_receipt(args)
        self.assertEqual(receipt["verdict"], "bound")
        self.assertTrue(receipt["comparison"]["match"])


if __name__ == "__main__":
    unittest.main()
