"""Prove retained device lifecycle evidence rejects semantic tampering after resealing hashes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-device-lifecycle"
SPEC = importlib.util.spec_from_file_location(
    "native_device_lifecycle_verify",
    ROOT / "bench/external-projects/onnx-vulkan-device-lifecycle/verify.py",
)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class NativeDeviceLifecycleEvidenceTests(unittest.TestCase):
    def test_retained_qualification(self) -> None:
        self.assertEqual(
            VERIFY.verify(REPORT)["deviceLifecycle"], "qualified-tested-paths"
        )

    def tamper(self, change: str, expected: str) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "bench/out") as temporary:
            copy = Path(temporary) / "report"
            shutil.copytree(REPORT, copy)
            relative = "controls/native-00.jsonl"
            rows = [
                json.loads(line) for line in (copy / relative).read_text().splitlines()
            ]
            if change == "phase":
                next(
                    r
                    for r in rows
                    if r.get("operation") == "Destroy" and r.get("mode") == 1
                )["phase"] = 1
            elif change == "status":
                next(
                    r for r in rows if r.get("operation") == "ReleaseBeforeLostDelivery"
                )["nullDevice"] = False
            else:
                next(r for r in rows if r["kind"] == "readback")["values"][0] += 1
            data = "".join(json.dumps(row) + "\n" for row in rows).encode()
            (copy / relative).write_bytes(data)
            receipt_path = copy / "controls/receipt.json"
            receipt = json.loads(receipt_path.read_text())
            target = next(
                r for r in receipt["runs"] if r["arm"] == "native" and r["index"] == 0
            )
            target["stdout"]["sha256"] = hashlib.sha256(data).hexdigest()
            receipt_path.write_text(json.dumps(receipt) + "\n")
            manifest_path = copy / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            for name in (relative, "controls/receipt.json"):
                sha = hashlib.sha256((copy / name).read_bytes()).hexdigest()
                manifest["files"][name] = {"sha256": sha, "contentSha256": sha}
            manifest_path.write_text(json.dumps(manifest) + "\n")
            with self.assertRaisesRegex(ValueError, expected):
                VERIFY.verify(copy)

    def test_early_wait_only_loss_callback_cannot_be_resealed_as_pass(self) -> None:
        self.tamper("phase", "Loss verdict drift")

    def test_final_release_cannot_retain_callback_device(self) -> None:
        self.tamper("status", "Loss verdict drift")

    def test_wrong_gpu_readback_cannot_be_resealed_as_pass(self) -> None:
        self.tamper("readback", "Submitted readback changed")


if __name__ == "__main__":
    unittest.main()
