#!/usr/bin/env python3
"""Validate browser runtime identity evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_KIND = "browser_runtime_identity"
EXPECTED_SURFACE = "doe-gpu/browser"
WRAPPER_SOURCE = "browser_wrapper_probe"
SELECTOR_SOURCE = "runtime_selection_artifact"
WRAPPER_RUNTIME = "browser_navigator_gpu"
SELECTOR_RUNTIMES = {"dawn", "doe"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", required=True, help="browser_runtime_identity JSON path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def check_identity(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []

    if payload.get("schemaVersion") != 1:
        failures.append(
            failure(
                "invalid_schema_version",
                "schemaVersion",
                "schemaVersion must be 1",
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
    if payload.get("surface") != EXPECTED_SURFACE:
        failures.append(
            failure(
                "invalid_surface",
                "surface",
                f"surface must be {EXPECTED_SURFACE}",
            )
        )
    if not isinstance(payload.get("provider"), dict):
        failures.append(
            failure("invalid_provider", "provider", "provider must be an object")
        )
    if not isinstance(payload.get("webgpuAvailable"), bool):
        failures.append(
            failure(
                "invalid_webgpu_available",
                "webgpuAvailable",
                "webgpuAvailable must be boolean",
            )
        )

    evidence_source = payload.get("evidenceSource")
    if evidence_source == WRAPPER_SOURCE:
        return failures + check_wrapper_probe(payload)
    if evidence_source == SELECTOR_SOURCE:
        return failures + check_runtime_selection_artifact(payload)

    failures.append(
        failure(
            "invalid_evidence_source",
            "evidenceSource",
            "evidenceSource must be browser_wrapper_probe or runtime_selection_artifact",
        )
    )
    return failures


def check_wrapper_probe(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("selectedRuntime") != WRAPPER_RUNTIME:
        failures.append(
            failure(
                "wrapper_selected_runtime",
                "selectedRuntime",
                "browser wrapper probes must report browser_navigator_gpu",
            )
        )
    if payload.get("executionOwner") != "browser":
        failures.append(
            failure(
                "wrapper_execution_owner",
                "executionOwner",
                "browser wrapper probes must be owned by browser",
            )
        )
    if payload.get("doeRuntimeActive") is not False:
        failures.append(
            failure(
                "wrapper_claims_doe_active",
                "doeRuntimeActive",
                "browser wrapper probes cannot claim Doe runtime execution",
            )
        )
    if payload.get("runtimeSelection") is not None:
        failures.append(
            failure(
                "wrapper_runtime_selection_present",
                "runtimeSelection",
                "browser wrapper probes must not embed Chromium runtime selection evidence",
            )
        )
    return failures


def check_runtime_selection_artifact(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("executionOwner") != "chromium_runtime_selector":
        failures.append(
            failure(
                "selector_execution_owner",
                "executionOwner",
                "runtime selection artifacts must be owned by chromium_runtime_selector",
            )
        )

    runtime_selection = payload.get("runtimeSelection")
    if not isinstance(runtime_selection, dict):
        failures.append(
            failure(
                "missing_runtime_selection",
                "runtimeSelection",
                "runtime selection artifacts must embed the selector result",
            )
        )
        return failures

    selected_runtime = payload.get("selectedRuntime")
    selector_runtime = runtime_selection.get("selectedRuntime")
    if selected_runtime not in SELECTOR_RUNTIMES:
        failures.append(
            failure(
                "invalid_selected_runtime",
                "selectedRuntime",
                "runtime selection artifacts must resolve to dawn or doe",
            )
        )
    if selector_runtime != selected_runtime:
        failures.append(
            failure(
                "selected_runtime_mismatch",
                "runtimeSelection.selectedRuntime",
                "runtimeSelection.selectedRuntime must match selectedRuntime",
            )
        )

    hidden_fallback_allowed = runtime_selection.get("hiddenFallbackAllowed")
    fallback_applied = runtime_selection.get("fallbackApplied")
    fallback_reason = _text(runtime_selection.get("fallbackReasonCode"))

    if hidden_fallback_allowed is not False:
        failures.append(
            failure(
                "hidden_fallback_not_disabled",
                "runtimeSelection.hiddenFallbackAllowed",
                "hidden fallback must be explicitly false",
            )
        )
    if not isinstance(fallback_applied, bool):
        failures.append(
            failure(
                "invalid_fallback_applied",
                "runtimeSelection.fallbackApplied",
                "fallbackApplied must be boolean",
            )
        )
    elif fallback_applied:
        if selected_runtime != "dawn":
            failures.append(
                failure(
                    "fallback_selected_runtime_mismatch",
                    "selectedRuntime",
                    "applied fallback must resolve to dawn",
                )
            )
        if not fallback_reason:
            failures.append(
                failure(
                    "missing_fallback_reason",
                    "runtimeSelection.fallbackReasonCode",
                    "applied fallback requires a reason code",
                )
            )
    elif fallback_reason:
        failures.append(
            failure(
                "unexpected_fallback_reason",
                "runtimeSelection.fallbackReasonCode",
                "non-fallback selection must not carry a reason code",
            )
        )

    if not _text(runtime_selection.get("selectorVersion")):
        failures.append(
            failure(
                "missing_selector_version",
                "runtimeSelection.selectorVersion",
                "runtime selection artifacts must carry selectorVersion",
            )
        )

    expected_active = (
        selected_runtime == "doe"
        and fallback_applied is False
        and hidden_fallback_allowed is False
    )
    if payload.get("doeRuntimeActive") is not expected_active:
        failures.append(
            failure(
                "doe_runtime_active_mismatch",
                "doeRuntimeActive",
                "doeRuntimeActive must match selected runtime and fallback state",
            )
        )

    return failures


def main() -> int:
    args = parse_args()
    identity_path = Path(args.identity)
    failures = check_identity(load_json(identity_path))
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_runtime_identity_check",
        "identityPath": str(identity_path),
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser runtime identity")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser runtime identity")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
