#!/usr/bin/env python3
"""Validate browser crash/hang/device-loss/recovery parity coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


REQUIRED_CASES = {
    "crash",
    "hang",
    "device_loss",
    "validation_error",
    "recovery",
}
EXPECTED_KIND = "browser_recovery_parity"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parity", required=True, help="browser_recovery_parity JSON path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def check_path(path_text: Any, path: str, label: str) -> list[dict[str, str]]:
    if not isinstance(path_text, str) or not path_text:
        return []
    if safe_repo_path(path_text):
        return []
    return [
        failure(
            "unsafe_artifact_path",
            path,
            f"{label} must be repo-relative",
        )
    ]


def check_parity(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("schemaVersion") != EXPECTED_SCHEMA_VERSION:
        failures.append(
            failure(
                "invalid_schema_version",
                "schemaVersion",
                f"schemaVersion must be {EXPECTED_SCHEMA_VERSION}",
            )
        )
    if payload.get("artifactKind") != EXPECTED_KIND:
        failures.append(
            failure(
                "invalid_artifact_kind",
                "artifactKind",
                f"artifactKind must be {EXPECTED_KIND}",
            )
        )
    runtime_selector = payload.get("runtimeSelector", {})
    if not isinstance(runtime_selector, dict) or runtime_selector.get("hiddenFallbackAllowed") is not False:
        failures.append(
            failure("hidden_fallback_allowed", "runtimeSelector.hiddenFallbackAllowed", "hidden fallback must be false")
        )
    failures.extend(check_path(payload.get("dawnArtifactPath"), "dawnArtifactPath", "Dawn recovery artifact path"))
    failures.extend(check_path(payload.get("doeArtifactPath"), "doeArtifactPath", "Doe recovery artifact path"))

    cases = payload.get("cases", [])
    case_kinds = {
        case.get("caseKind")
        for case in cases
        if isinstance(case, dict)
    }
    for case_kind in sorted(REQUIRED_CASES - case_kinds):
        failures.append(failure("missing_case_kind", "cases", f"missing recovery parity case {case_kind}"))

    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        case_path = f"cases[{case_index}]"
        failures.extend(check_path(case.get("evidencePath"), f"{case_path}.evidencePath", "recovery evidence path"))
        parity_status = case.get("parityStatus")
        dawn_status = case.get("dawnStatus")
        doe_status = case.get("doeStatus")
        if parity_status == "match" and dawn_status != doe_status:
            failures.append(
                failure(
                    "parity_status_mismatch",
                    f"{case_path}.parityStatus",
                    "match parity requires identical Dawn and Doe statuses",
                )
            )
        if parity_status in {"mismatch", "diagnostic"} and not case.get("reasonCode"):
            failures.append(
                failure(
                    "missing_reason_code",
                    f"{case_path}.reasonCode",
                    "diagnostic or mismatch parity requires reasonCode",
                )
            )

    fallback_policy = payload.get("fallbackPolicy", {})
    if not isinstance(fallback_policy, dict) or fallback_policy.get("hiddenFallbackAllowed") is not False:
        failures.append(
            failure("hidden_fallback_allowed", "fallbackPolicy.hiddenFallbackAllowed", "hidden fallback must be false")
        )

    return failures


def main() -> int:
    args = parse_args()
    failures = check_parity(load_json(Path(args.parity)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_recovery_parity_check",
        "parityPath": args.parity,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser recovery parity")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser recovery parity")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
