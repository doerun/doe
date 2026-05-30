#!/usr/bin/env python3
"""Build browser GPU scheduler probes from Playwright smoke output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


WORK_CLASSES = [
    {"workClassId": "work:webgpu", "surface": "webgpu", "priorityClass": "interactive"},
    {"workClassId": "work:canvas", "surface": "canvas", "priorityClass": "frame"},
    {"workClassId": "work:video", "surface": "video", "priorityClass": "frame"},
    {"workClassId": "work:css_effects", "surface": "css_effects", "priorityClass": "frame"},
    {"workClassId": "work:local_ai", "surface": "local_ai", "priorityClass": "background"},
    {"workClassId": "work:compositor", "surface": "compositor_adjacent", "priorityClass": "frame"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_gpu_scheduler_probe JSON to this path.")
    parser.add_argument("--mode", default="doe", choices=("dawn", "doe"), help="Mode result to extract.")
    parser.add_argument("--scheduler-id", default="browser-gpu-scheduler-smoke")
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


def find_mode_result(report: dict[str, Any], mode: str) -> dict[str, Any]:
    for result in report.get("modeResults", []):
        if isinstance(result, dict) and result.get("mode") == mode:
            return result
    raise ValueError(f"mode result not found in smoke report: {mode}")


def selected_runtime(mode_result: dict[str, Any]) -> str:
    runtime_selection = mode_result.get("runtimeSelection")
    if isinstance(runtime_selection, dict):
        selected = runtime_selection.get("selectedRuntime")
        if selected in {"dawn", "doe", "auto"}:
            return str(selected)
    mode = mode_result.get("mode")
    if mode in {"dawn", "doe", "auto"}:
        return str(mode)
    return "unknown"


def fallback_applied(mode_result: dict[str, Any]) -> bool:
    runtime_selection = mode_result.get("runtimeSelection")
    if isinstance(runtime_selection, dict):
        return runtime_selection.get("fallbackApplied") is True
    return False


def hidden_fallback_allowed(mode_result: dict[str, Any]) -> bool:
    runtime_selection = mode_result.get("runtimeSelection")
    if isinstance(runtime_selection, dict):
        return runtime_selection.get("hiddenFallbackAllowed") is True
    return False


def device_loss_status(mode_result: dict[str, Any]) -> tuple[str, str]:
    smoke = mode_result.get("smoke")
    recovery = smoke.get("recovery") if isinstance(smoke, dict) else None
    row = recovery.get("deviceLost") if isinstance(recovery, dict) else None
    if not isinstance(row, dict):
        return "diagnostic", "device_loss_probe_missing"
    if row.get("pass") is True:
        return "pass", ""
    if row.get("promiseAvailable") is False:
        return "blocked", "device_lost_surface_unavailable"
    if row.get("error"):
        return "fail", "device_loss_probe_failed"
    return "diagnostic", "device_loss_probe_inconclusive"


def fallback_behavior_status(mode_result: dict[str, Any]) -> tuple[str, str]:
    if hidden_fallback_allowed(mode_result):
        return "fail", "hidden_fallback_allowed"
    if fallback_applied(mode_result):
        return "fail", "hidden_fallback_applied"
    return "pass", "hidden_fallback_disabled"


def build_probe(
    report: dict[str, Any],
    report_path: Path,
    mode: str,
    scheduler_id: str,
) -> dict[str, Any]:
    mode_result = find_mode_result(report, mode)
    report_ref = repo_relative(report_path)
    device_status, device_reason = device_loss_status(mode_result)
    fallback_status, fallback_reason = fallback_behavior_status(mode_result)
    probes: list[dict[str, Any]] = [
        {
            "probeId": "probe:priority",
            "probeKind": "priority",
            "workClassIds": ["work:webgpu", "work:canvas", "work:local_ai"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#modeResults[{mode}].benches",
            "reasonCode": "not_measured_by_smoke",
        },
        {
            "probeId": "probe:fairness",
            "probeKind": "fairness",
            "workClassIds": ["work:webgpu", "work:local_ai"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#modeResults[{mode}].benches",
            "reasonCode": "not_measured_by_smoke",
        },
        {
            "probeId": "probe:frame_deadline",
            "probeKind": "frame_deadline",
            "workClassIds": ["work:canvas", "work:css_effects", "work:compositor"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#modeResults[{mode}].smoke.renderTriangle",
            "reasonCode": "frame_deadline_not_measured_by_smoke",
        },
        {
            "probeId": "probe:origin_quota",
            "probeKind": "origin_quota",
            "workClassIds": ["work:webgpu", "work:local_ai"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#modeResults[{mode}].runtimeSelection",
            "reasonCode": "origin_quota_not_measured_by_smoke",
        },
        {
            "probeId": "probe:device_loss",
            "probeKind": "device_loss",
            "workClassIds": ["work:webgpu", "work:canvas", "work:video"],
            "status": device_status,
            "evidencePath": f"{report_ref}#modeResults[{mode}].smoke.recovery.deviceLost",
        },
        {
            "probeId": "probe:fallback_behavior",
            "probeKind": "fallback_behavior",
            "workClassIds": [
                "work:webgpu",
                "work:canvas",
                "work:video",
                "work:css_effects",
                "work:local_ai",
                "work:compositor",
            ],
            "status": fallback_status,
            "evidencePath": f"{report_ref}#modeResults[{mode}].runtimeSelection",
            "reasonCode": fallback_reason,
        },
    ]
    if device_reason:
        probes[4]["reasonCode"] = device_reason

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_gpu_scheduler_probe",
        "schedulerId": scheduler_id,
        "runtimeIdentity": {
            "runtimeIdentityPath": report_ref,
            "selectedRuntime": selected_runtime(mode_result),
            "fallbackApplied": fallback_applied(mode_result),
        },
        "workClasses": WORK_CLASSES,
        "probes": probes,
        "fallbackPolicy": {
            "hiddenFallbackAllowed": False,
            "reasonCodeRequired": True,
        },
        "privacy": {
            "originScoped": True,
            "rawPageDataIncluded": False,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_probe(load_json(report_path), report_path, args.mode, args.scheduler_id)
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
