#!/usr/bin/env python3
"""Build browser claim promotion receipts from browser claim reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


VALID_MODES = {"dawn", "doe", "auto"}
REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-report", action="append", required=True, help="Browser claim report JSON path.")
    parser.add_argument("--claim-policy", default="config/browser-claim-policy.json")
    parser.add_argument("--receipt-id", default="")
    parser.add_argument("--out", required=True, help="Output browser claim promotion receipt JSON.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def runtime_selection_mode(selection: dict[str, Any]) -> str:
    mode = selection.get("selectionMode")
    if mode in VALID_MODES:
        return str(mode)
    selected = selection.get("selectedRuntime")
    if selected in VALID_MODES:
        return str(selected)
    forced = selection.get("forcedMode")
    if forced in VALID_MODES:
        return str(forced)
    return ""


def is_forced_doe(selection: dict[str, Any]) -> bool:
    return (
        selection.get("selectionMode") == "doe"
        and selection.get("selectedRuntime") == "doe"
        and selection.get("forcedMode") == "doe"
    )


def selection_has_hidden_fallback(selection: dict[str, Any]) -> bool:
    return (
        selection.get("fallbackApplied") is True
        or selection.get("hiddenFallbackAllowed") is True
        or bool(selection.get("fallbackReasonCode"))
    )


def collect_doe_runtime_selections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    selections: list[dict[str, Any]] = []
    for value in payload.get("runtimeSelections", []):
        if isinstance(value, dict) and runtime_selection_mode(value) == "doe":
            selections.append(value)
    for value in payload.get("modeResults", []):
        if not isinstance(value, dict) or value.get("mode") != "doe":
            continue
        runtime_selection = value.get("runtimeSelection")
        if isinstance(runtime_selection, dict):
            selections.append(runtime_selection)
    for value in payload.get("modeRunDetails", []):
        if not isinstance(value, dict) or value.get("mode") != "doe":
            continue
        runtime_selection = value.get("runtimeSelection")
        if isinstance(runtime_selection, dict):
            selections.append(runtime_selection)
    return selections


def report_claim_policy_passed(payload: dict[str, Any]) -> bool:
    return (
        payload.get("reportKind") == "browser-claim-report"
        and payload.get("comparisonStatus") == "comparable"
        and payload.get("claimStatus") == "claimable"
        and not payload.get("failures")
    )


def window_paths(report_payload: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in report_payload.get("windows", []):
        if not isinstance(row, dict):
            continue
        for key in ("smokeReport", "layeredReport"):
            value = row.get(key)
            if isinstance(value, str) and value:
                paths.append(Path(value))
    return paths


def inspect_window_evidence(paths: list[Path], report_index: int) -> tuple[bool, bool, list[dict[str, str]]]:
    forced_doe = True
    hidden_fallback_used = False
    failures: list[dict[str, str]] = []
    selection_count = 0
    for evidence_path in paths:
        if not evidence_path.exists():
            failures.append(
                failure(
                    "missing_window_artifact",
                    f"claimReports[{report_index}].windows",
                    f"window artifact not found: {evidence_path}",
                )
            )
            forced_doe = False
            continue
        payload = load_json(evidence_path)
        selections = collect_doe_runtime_selections(payload)
        if not selections:
            failures.append(
                failure(
                    "missing_doe_runtime_selection",
                    str(evidence_path),
                    "window artifact must carry Doe runtime selection evidence",
                )
            )
            forced_doe = False
            continue
        selection_count += len(selections)
        for selection in selections:
            if not is_forced_doe(selection):
                forced_doe = False
                failures.append(
                    failure(
                        "window_not_forced_doe",
                        str(evidence_path),
                        "Doe window selection must be forced-Doe",
                    )
                )
            if selection_has_hidden_fallback(selection):
                hidden_fallback_used = True
                failures.append(
                    failure(
                        "window_hidden_fallback_used",
                        str(evidence_path),
                        "Doe window selection cannot apply hidden fallback",
                    )
                )
    if not paths:
        forced_doe = False
        failures.append(
            failure(
                "missing_window_evidence",
                f"claimReports[{report_index}].windows",
                "claim report must link browser window artifacts",
            )
        )
    elif selection_count == 0:
        forced_doe = False
    return forced_doe, hidden_fallback_used, failures


def build_artifact_row(path: Path, payload: dict[str, Any], index: int) -> tuple[dict[str, Any], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    if not report_claim_policy_passed(payload):
        failures.append(
            failure(
                "claim_report_not_claimable",
                f"claimReports[{index}]",
                "browser claim report must be comparable, claimable, and failure-free",
            )
        )
    forced_doe, hidden_fallback_used, evidence_failures = inspect_window_evidence(window_paths(payload), index)
    failures.extend(evidence_failures)
    return (
        {
            "path": str(path),
            "sha256": sha256_file(path),
            "mode": "doe",
            "forcedDoe": forced_doe,
            "hiddenFallbackUsed": hidden_fallback_used,
            "claimPolicyPassed": report_claim_policy_passed(payload),
        },
        failures,
    )


def build_receipt(
    report_paths: list[Path],
    *,
    claim_policy_path: Path,
    receipt_id: str = "",
) -> dict[str, Any]:
    resolved_claim_policy_path = claim_policy_path.resolve()
    artifacts: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, report_path in enumerate(report_paths):
        payload = load_json(report_path)
        policy_path = payload.get("policyPath")
        if isinstance(policy_path, str) and Path(policy_path).resolve() != resolved_claim_policy_path:
            failures.append(
                failure(
                    "claim_policy_path_mismatch",
                    f"claimReports[{index}].policyPath",
                    f"expected {resolved_claim_policy_path}, got {policy_path}",
                )
            )
        row, row_failures = build_artifact_row(report_path, payload, index)
        artifacts.append(row)
        failures.extend(row_failures)

    hidden_fallback_passed = bool(artifacts) and all(
        artifact["forcedDoe"] and not artifact["hiddenFallbackUsed"] for artifact in artifacts
    )
    promotion_status = (
        "promotable"
        if artifacts and hidden_fallback_passed and all(row["claimPolicyPassed"] for row in artifacts) and not failures
        else "diagnostic"
    )
    if not receipt_id:
        receipt_id = f"browser-claim-promotion:{stable_hash([str(path) for path in report_paths])[:16]}"
    return {
        "schemaVersion": 1,
        "artifactKind": "browser_claim_promotion_receipt",
        "receiptId": receipt_id,
        "claimPolicyPath": repo_relative(resolved_claim_policy_path),
        "promotionStatus": promotion_status,
        "artifacts": artifacts,
        "hiddenFallbackCheck": {
            "required": True,
            "passed": hidden_fallback_passed,
        },
        "failureCodes": failures,
    }


def main() -> int:
    args = parse_args()
    receipt = build_receipt(
        [Path(path) for path in args.claim_report],
        claim_policy_path=Path(args.claim_policy),
        receipt_id=args.receipt_id,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 1 if receipt["promotionStatus"] != "promotable" else 0


if __name__ == "__main__":
    sys.exit(main())
