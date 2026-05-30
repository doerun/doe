#!/usr/bin/env python3
"""Build browser recovery parity artifacts from paired smoke output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CASE_KINDS = ("crash", "hang", "device_loss", "validation_error", "recovery")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_recovery_parity JSON to this path.")
    parser.add_argument("--parity-set-id", default="browser-recovery-parity-smoke")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def repo_relative(path: Path) -> str:
    root = Path(__file__).resolve().parents[3]
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def mode_results(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for row in report.get("modeResults", []):
        if isinstance(row, dict) and row.get("mode") in {"dawn", "doe"}:
            results[str(row["mode"])] = row
    return results


def selector_version(doe_result: dict[str, Any] | None) -> str:
    runtime_selection = doe_result.get("runtimeSelection") if isinstance(doe_result, dict) else None
    if isinstance(runtime_selection, dict) and runtime_selection.get("selectorVersion"):
        return str(runtime_selection["selectorVersion"])
    return "unknown"


def recovery_status(mode_result: dict[str, Any] | None, case_kind: str) -> tuple[str, str]:
    if not isinstance(mode_result, dict):
        return "diagnostic", "missing_mode_result"
    smoke = mode_result.get("smoke", {})
    recovery = smoke.get("recovery", {}) if isinstance(smoke, dict) else {}
    if case_kind in {"crash", "hang"}:
        return "diagnostic", "not_exercised_by_smoke"
    if case_kind == "device_loss":
        row = recovery.get("deviceLost", {}) if isinstance(recovery, dict) else {}
        if isinstance(row, dict) and row.get("pass") is True:
            return "pass", ""
        if isinstance(row, dict) and row.get("promiseAvailable") is False:
            return "unsupported", "device_lost_surface_unavailable"
        return "diagnostic", "device_loss_probe_missing"
    if case_kind == "validation_error":
        row = recovery.get("validationError", {}) if isinstance(recovery, dict) else {}
        if isinstance(row, dict) and row.get("pass") is True:
            return "pass", ""
        if isinstance(row, dict) and row.get("error"):
            return "fail", "validation_error_probe_failed"
        return "diagnostic", "validation_error_probe_missing"
    if case_kind == "recovery":
        row = recovery.get("postValidationCompute", {}) if isinstance(recovery, dict) else {}
        if isinstance(row, dict) and row.get("pass") is True:
            return "pass", ""
        if isinstance(row, dict) and row.get("error"):
            return "fail", "post_validation_compute_failed"
        return "diagnostic", "recovery_probe_missing"
    return "diagnostic", "unknown_case_kind"


def parity_status(dawn_status: str, doe_status: str) -> str:
    if dawn_status == doe_status:
        return "match" if dawn_status in {"pass", "unsupported"} else "diagnostic"
    return "mismatch"


def build_parity(report: dict[str, Any], report_path: Path, parity_set_id: str) -> dict[str, Any]:
    results = mode_results(report)
    dawn_result = results.get("dawn")
    doe_result = results.get("doe")
    report_ref = repo_relative(report_path)
    cases = []
    for case_kind in CASE_KINDS:
        dawn_status, dawn_reason = recovery_status(dawn_result, case_kind)
        doe_status, doe_reason = recovery_status(doe_result, case_kind)
        status = parity_status(dawn_status, doe_status)
        case: dict[str, Any] = {
            "caseId": f"case:{case_kind.replace('_', '-')}",
            "caseKind": case_kind,
            "dawnStatus": dawn_status,
            "doeStatus": doe_status,
            "parityStatus": status,
            "evidencePath": f"{report_ref}#modeResults.{case_kind}",
        }
        reasons = [reason for reason in (dawn_reason, doe_reason) if reason]
        if status != "match" or reasons:
            case["reasonCode"] = "+".join(dict.fromkeys(reasons or [status]))
        cases.append(case)

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_recovery_parity",
        "paritySetId": parity_set_id,
        "runtimeSelector": {
            "selectorVersion": selector_version(doe_result),
            "doeMode": "forced_doe",
            "hiddenFallbackAllowed": False,
        },
        "dawnArtifactPath": f"{report_ref}#modeResults[dawn]",
        "doeArtifactPath": f"{report_ref}#modeResults[doe]",
        "cases": cases,
        "fallbackPolicy": {
            "hiddenFallbackAllowed": False,
            "reasonCodeRequired": True,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_parity(load_json(report_path), report_path, args.parity_set_id)
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
