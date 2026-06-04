#!/usr/bin/env python3
"""Validate the browser runtime selector policy contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_SELECTION_MODES = {"dawn", "doe", "auto"}
REQUIRED_PRECEDENCE = [
    "emergency_kill_switch",
    "explicit_override",
    "enterprise_policy",
    "auto_profile_policy",
    "default_dawn",
]
REQUIRED_FALLBACK_REASONS = {
    "global_disable_active",
    "runtime_artifact_missing",
    "runtime_artifact_load_failed",
    "symbol_surface_incomplete",
    "profile_denylisted",
    "capability_requirement_failed",
    "runtime_health_degraded",
    "explicit_operator_override",
    "unknown_selection_error",
}
REQUIRED_OBSERVABILITY_FIELDS = {
    "selectionMode",
    "selectedRuntime",
    "forcedMode",
    "fallbackApplied",
    "fallbackReasonCode",
    "hiddenFallbackAllowed",
    "profile.vendor",
    "profile.api",
    "profile.deviceFamily",
    "profile.driver",
    "adapterDenylist.matched",
    "adapterDenylist.reasonCode",
    "adapterDenylist.profileId",
    "adapterDenylist.vendor",
    "adapterDenylist.api",
    "adapterDenylist.deviceFamily",
    "adapterDenylist.driverPattern",
    "selectorVersion",
    "artifactIdentity.browserExecutablePath",
    "artifactIdentity.browserExecutableSha256",
    "artifactIdentity.dawnRuntimePath",
    "artifactIdentity.dawnRuntimeSha256",
    "artifactIdentity.doeLibPath",
    "artifactIdentity.doeLibSha256",
    "launchArgsHash",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True, help="browser runtime selector policy JSON path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def check_policy(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    selection_modes = set(payload.get("selectionModes", []))
    if selection_modes != REQUIRED_SELECTION_MODES:
        failures.append(
            failure(
                "invalid_selection_modes",
                "selectionModes",
                "selection modes must be exactly dawn, doe, auto",
            )
        )

    control_precedence = payload.get("controlPrecedence", [])
    if control_precedence != REQUIRED_PRECEDENCE:
        failures.append(
            failure(
                "invalid_control_precedence",
                "controlPrecedence",
                "control precedence must start with emergency kill switch and end with default Dawn",
            )
        )

    fallback_reasons = set(payload.get("fallbackReasons", []))
    missing_reasons = REQUIRED_FALLBACK_REASONS - fallback_reasons
    for reason in sorted(missing_reasons):
        failures.append(failure("missing_fallback_reason", "fallbackReasons", f"missing fallback reason {reason}"))

    forced_doe_failure = payload.get("forcedDoeFailure", {})
    if (
        not isinstance(forced_doe_failure, dict)
        or forced_doe_failure.get("failClosed") is not True
        or forced_doe_failure.get("fallbackToDawn") is not False
    ):
        failures.append(
            failure(
                "forced_doe_not_fail_closed",
                "forcedDoeFailure",
                "forced Doe must fail closed without falling back to Dawn",
            )
        )

    observability_fields = set(payload.get("observabilityFields", []))
    for field in sorted(REQUIRED_OBSERVABILITY_FIELDS - observability_fields):
        failures.append(
            failure("missing_observability_field", "observabilityFields", f"missing observability field {field}")
        )

    emergency_kill_switch = payload.get("emergencyKillSwitch", {})
    if (
        not isinstance(emergency_kill_switch, dict)
        or emergency_kill_switch.get("selectsRuntime") != "dawn"
        or emergency_kill_switch.get("reasonCode") != "global_disable_active"
    ):
        failures.append(
            failure(
                "invalid_kill_switch",
                "emergencyKillSwitch",
                "kill switch must select Dawn with global_disable_active",
            )
        )

    denylist = payload.get("denylist", {})
    if not isinstance(denylist, dict) or denylist.get("reasonCode") != "profile_denylisted":
        failures.append(
            failure("invalid_denylist_reason", "denylist.reasonCode", "denylist reason must be profile_denylisted")
        )

    return failures


def main() -> int:
    args = parse_args()
    failures = check_policy(load_json(Path(args.policy)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_runtime_selector_policy_check",
        "policyPath": args.policy,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser runtime selector policy")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser runtime selector policy")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
