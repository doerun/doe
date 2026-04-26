from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.cluster_b_fixture_drift_guard import (  # noqa: E402
    compare,
    fingerprint_current,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FingerprintCurrentTest(unittest.TestCase):
    def test_records_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "a.json").write_bytes(b'{"a": 1}')
            (root / "b.json").write_bytes(b'{"b": 2}')
            obs = fingerprint_current(("a.json", "b.json"), repo_root=root)
            self.assertEqual(obs["paths"]["a.json"], _sha256_bytes(b'{"a": 1}'))
            self.assertEqual(obs["paths"]["b.json"], _sha256_bytes(b'{"b": 2}'))
            self.assertEqual(obs["missing"], [])

    def test_records_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "a.json").write_bytes(b"x")
            obs = fingerprint_current(("a.json", "b.json"), repo_root=root)
            self.assertIn("a.json", obs["paths"])
            self.assertNotIn("b.json", obs["paths"])
            self.assertEqual(obs["missing"], ["b.json"])


class CompareTest(unittest.TestCase):
    def _build(
        self,
        paths: dict[str, str],
        missing: list[str] | None = None,
    ) -> dict:
        return {
            "schemaVersion": 1,
            "artifactKind": "doe_cluster_b_fixture_fingerprints",
            "computedAt": "2026-04-26T12:00:00+00:00",
            "paths": paths,
            "missing": missing or [],
        }

    def test_match_is_bound(self) -> None:
        baseline = self._build({"x.json": "a" * 64, "y.json": "b" * 64})
        observed = self._build({"x.json": "a" * 64, "y.json": "b" * 64})
        report = compare(baseline, observed)
        self.assertTrue(report["bound"])
        self.assertEqual(report["verdict"], "bound")
        self.assertEqual(report["drifted"], [])

    def test_drift_detected(self) -> None:
        baseline = self._build({"x.json": "a" * 64})
        observed = self._build({"x.json": "0" * 64})
        report = compare(baseline, observed)
        self.assertFalse(report["bound"])
        self.assertEqual(len(report["drifted"]), 1)
        self.assertEqual(report["drifted"][0]["path"], "x.json")
        self.assertEqual(report["drifted"][0]["baselineSha256"], "a" * 64)
        self.assertEqual(report["drifted"][0]["observedSha256"], "0" * 64)

    def test_new_path_flagged(self) -> None:
        baseline = self._build({"x.json": "a" * 64})
        observed = self._build({"x.json": "a" * 64, "y.json": "b" * 64})
        report = compare(baseline, observed)
        self.assertFalse(report["bound"])
        self.assertEqual(report["newPaths"], ["y.json"])

    def test_removed_path_flagged(self) -> None:
        baseline = self._build({"x.json": "a" * 64, "y.json": "b" * 64})
        observed = self._build({"x.json": "a" * 64})
        report = compare(baseline, observed)
        self.assertFalse(report["bound"])
        self.assertEqual(report["removedPaths"], ["y.json"])

    def test_missing_observed_path_flagged(self) -> None:
        baseline = self._build({"x.json": "a" * 64})
        observed = self._build({}, missing=["x.json"])
        report = compare(baseline, observed)
        self.assertFalse(report["bound"])
        self.assertIn("x.json", report["missing"])

    def test_report_is_json_serializable(self) -> None:
        baseline = self._build({"x.json": "a" * 64})
        observed = self._build({"x.json": "0" * 64})
        report = compare(baseline, observed)
        json.dumps(report)


if __name__ == "__main__":
    unittest.main()
