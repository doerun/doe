"""Evidence controls reject CPU fallback, altered metrics and reused cold caches."""

from __future__ import annotations

import copy
from collections.abc import Callable
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "reports/benchmarks/amd-vulkan/20261005-onnx-vulkan-campaign"
SPEC = importlib.util.spec_from_file_location(
    "onnx_campaign_verify",
    REPO / "bench/external-projects/onnx-vulkan-campaign/verify.py",
)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class TestCampaignEvidence(unittest.TestCase):
    def test_completed_negative_decision_verifies(self) -> None:
        result = VERIFY.verify(REPORT, REPO)
        self.assertEqual(result["application"], "qualified-bounded-host")
        self.assertEqual(result["advantage"], "rejected")

    def mutated_report(
        self, root: Path, relative: str, mutate: Callable[[dict], None]
    ) -> Path:
        """Rebind artifact hashes to test semantic admission beyond byte integrity."""
        target = root / "report"
        shutil.copytree(REPORT, target)
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        name = relative if relative in manifest["files"] else relative + ".gz"
        record = manifest["files"][name]
        data = (target / name).read_bytes()
        value = json.loads(
            gzip.decompress(data) if record["compression"] == "gzip" else data
        )
        mutate(value)
        content = (json.dumps(value, indent=2) + "\n").encode()
        data = (
            gzip.compress(content, mtime=0)
            if record["compression"] == "gzip"
            else content
        )
        (target / name).write_bytes(data)
        record["sha256"] = hashlib.sha256(data).hexdigest()
        record["contentSha256"] = hashlib.sha256(content).hexdigest()
        if relative == "raw/measurement-qualified/measurement.json":
            for linked, field in [
                ("cache-audit.json", "qualifiedMeasurementSha256"),
                ("measurement-summary.json", "rawMeasurementSha256"),
            ]:
                linked_value = json.loads((target / linked).read_text())
                linked_value[field] = hashlib.sha256(content).hexdigest()
                linked_content = (json.dumps(linked_value, indent=2) + "\n").encode()
                (target / linked).write_bytes(linked_content)
                manifest["files"][linked]["sha256"] = hashlib.sha256(
                    linked_content
                ).hexdigest()
                manifest["files"][linked]["contentSha256"] = hashlib.sha256(
                    linked_content
                ).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        return target

    def test_false_speed_promotion_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:

            def promote(value: dict) -> None:
                value["primaryRatio"] = 10.0
                value["passed"] = True
                value["disposition"] = "material-advantage-qualified"

            target = self.mutated_report(
                Path(directory), "raw/measurement-qualified/measurement.json", promote
            )
            with self.assertRaisesRegex(ValueError, "Derived statistic changed"):
                VERIFY.verify(target, REPO)

    def test_application_cpu_fallback_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:

            def fallback(value: dict) -> None:
                value["operatorProviders"][0] = "CPUExecutionProvider"

            target = self.mutated_report(
                Path(directory), "raw/doe-matched.json", fallback
            )
            with self.assertRaisesRegex(ValueError, "Application CPU fallback"):
                VERIFY.verify(target, REPO)

    def test_unscoped_native_cache_home_rejected(self) -> None:
        measurement = json.loads(
            gzip.decompress(
                (REPORT / "raw/measurement-qualified/measurement.json.gz").read_bytes()
            )
        )
        measurement["rows"][0]["cacheHome"] = "/home/x"
        policy = json.loads((REPORT / "policy.json").read_text())
        with self.assertRaisesRegex(ValueError, "Native cache HOME escaped"):
            VERIFY.measurement_values(measurement, policy)

    def test_cold_cache_reuse_rejected(self) -> None:
        manifest = json.loads((REPORT / "manifest.json").read_text())
        name = "raw/measurement-qualified/measurement.json"
        if name not in manifest["files"]:
            name += ".gz"
        data = (REPORT / name).read_bytes()
        measurement = json.loads(
            gzip.decompress(data) if name.endswith(".gz") else data
        )
        mutated = copy.deepcopy(measurement)
        cold = [row for row in mutated["rows"] if row["stage"] == "cold"]
        cold[1]["cache"] = cold[0]["cache"]
        cold[1]["cacheHome"] = cold[0]["cacheHome"]
        policy = json.loads((REPORT / "policy.json").read_text())
        with self.assertRaisesRegex(ValueError, "Cold processes reused a cache"):
            VERIFY.measurement_values(mutated, policy)


if __name__ == "__main__":
    unittest.main()
