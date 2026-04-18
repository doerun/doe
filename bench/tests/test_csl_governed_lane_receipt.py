#!/usr/bin/env python3
"""Verify bench/runners/run_csl_governed_lane.py surfaces HostPlan kernel
patterns into the receipts.operationGraph summary.

The governed-lane report is the single artifact gates assert on when asking
"did this lane produce first-class evidence?". kernelPatternCount is the
lightweight signal that makes heterogeneous HostPlans (like the 270M or
Gemma 4 E2B plan) observable in the receipt summary without forcing
readers to parse the embedded driverResult.operationGraph JSON blob.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners"))

from run_csl_governed_lane import write_markdown  # type: ignore[import-not-found]


def _minimal_report(op_graph_receipt: dict | None) -> dict:
    receipts = {"operationGraph": op_graph_receipt} if op_graph_receipt else {"operationGraph": {"status": "absent"}}
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-04-18T00:00:00Z",
        "fixture": {"id": "unit-test", "inputJsonPath": "/dev/null"},
        "laneStatus": "blocked",
        "compile": {"status": "blocked", "reason": "unit_test", "runnerExitCode": 2},
        "run": {"status": "blocked", "reason": "unit_test", "traceProduced": False},
        "parity": {
            "status": "not-run",
            "reason": "unit_test",
            "expectedHostPlanSha256": "",
            "actualHostPlanSha256": "",
        },
        "artifacts": {
            "actualHostPlanPath": "/dev/null",
            "expectedHostPlanPath": "/dev/null",
            "simulatorPlanPath": "/dev/null",
            "simulatorResultPath": "",
            "driverResultPath": "",
        },
        "comparisonStatus": "diagnostic",
        "claimStatus": "not-evaluated",
        "receipts": receipts,
    }


class GovernedLaneReceiptMarkdownTests(unittest.TestCase):
    def test_markdown_surfaces_kernel_pattern_count(self) -> None:
        """When the op-graph receipt carries kernelPatternCount, the
        markdown shows a 'HostPlan kernel patterns' line so humans can
        see that a heterogeneous HostPlan was bound without opening the JSON."""
        report = _minimal_report(
            {
                "status": "bound",
                "graphId": "gemv-rpc-launch",
                "executionPattern": "rpc_launch",
                "orchestrationMode": "memcpy",
                "operationCount": 3,
                "exportedSymbolCount": 2,
                "kernelPatternCount": 10,
                "sdkVersionFloor": "1.4.0",
            }
        )
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "report.md"
            write_markdown(md_path, report)
            rendered = md_path.read_text(encoding="utf-8")
            self.assertIn("## Operation graph receipt", rendered)
            self.assertIn("HostPlan kernel patterns: `10`", rendered)
            self.assertIn("Operations: `3`", rendered)

    def test_markdown_omits_kernel_pattern_count_when_absent(self) -> None:
        """Receipt without kernelPatternCount must not render a stray
        'HostPlan kernel patterns' line — the field is optional."""
        report = _minimal_report(
            {
                "status": "bound",
                "graphId": "single-rpc-launch",
                "executionPattern": "rpc_launch",
                "orchestrationMode": "memcpy",
                "operationCount": 3,
                "exportedSymbolCount": 2,
                "sdkVersionFloor": "1.4.0",
            }
        )
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "report.md"
            write_markdown(md_path, report)
            rendered = md_path.read_text(encoding="utf-8")
            self.assertIn("## Operation graph receipt", rendered)
            self.assertNotIn("HostPlan kernel patterns", rendered)

    def test_markdown_absent_receipt_has_no_receipt_section(self) -> None:
        """When the graph was not bound, the markdown still includes the
        receipt section (with status=absent) so the missing-evidence signal
        is visible — but no per-field lines are emitted."""
        report = _minimal_report({"status": "absent"})
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "report.md"
            write_markdown(md_path, report)
            rendered = md_path.read_text(encoding="utf-8")
            self.assertIn("## Operation graph receipt", rendered)
            self.assertIn("Status: `absent`", rendered)
            self.assertNotIn("Operations:", rendered)


class GovernedLaneReceiptSchemaTests(unittest.TestCase):
    """Receipt shape validates against the lane-report schema when
    kernelPatternCount is present OR absent."""

    def setUp(self) -> None:
        import jsonschema
        self.jsonschema = jsonschema
        schema_path = REPO_ROOT / "config" / "csl-governed-lane-report.schema.json"
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft202012Validator(self.schema)

    def test_receipt_validates_with_kernel_pattern_count(self) -> None:
        report = _minimal_report(
            {
                "status": "bound",
                "graphId": "gemv",
                "executionPattern": "rpc_launch",
                "orchestrationMode": "memcpy",
                "operationCount": 3,
                "exportedSymbolCount": 2,
                "kernelPatternCount": 10,
                "sdkVersionFloor": "1.4.0",
            }
        )
        self.validator.validate(report)

    def test_receipt_validates_without_kernel_pattern_count(self) -> None:
        """Existing reports produced before this change omit
        kernelPatternCount. Schema must continue to accept them so the lane
        contract stays backward-compatible with any persisted evidence."""
        report = _minimal_report(
            {
                "status": "bound",
                "graphId": "legacy",
                "executionPattern": "rpc_launch",
                "orchestrationMode": "memcpy",
                "operationCount": 1,
                "exportedSymbolCount": 1,
                "sdkVersionFloor": "1.4.0",
            }
        )
        self.validator.validate(report)

    def test_receipt_rejects_negative_count(self) -> None:
        report = _minimal_report(
            {
                "status": "bound",
                "graphId": "bad",
                "executionPattern": "rpc_launch",
                "orchestrationMode": "memcpy",
                "operationCount": 1,
                "exportedSymbolCount": 1,
                "kernelPatternCount": -1,
                "sdkVersionFloor": "1.4.0",
            }
        )
        with self.assertRaises(self.jsonschema.ValidationError):
            self.validator.validate(report)


if __name__ == "__main__":
    unittest.main()
