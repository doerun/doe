#!/usr/bin/env python3
"""Build a browser GPU flight-recorder artifact from report and component data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
RESPONSIBILITY_MAP_PATH = REPO_ROOT / "config" / "browser-responsibility-map.json"
CAPTURE_POLICY_PATH = REPO_ROOT / "config" / "browser-capture-policy.json"
FLIGHT_RECORDER_SURFACE_ID = "gpu_flight_recorder"

REQUIRED_COMPONENT_FIELDS = {
    "shaders",
    "bindGroups",
    "buffers",
    "textures",
    "commandGraph",
    "frames",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Browser smoke or layered diagnostic report.")
    parser.add_argument(
        "--components",
        required=True,
        help="JSON component manifest carrying shaders, resources, graph, and frame hashes.",
    )
    parser.add_argument("--mode", default="doe", choices=["dawn", "doe"], help="Runtime mode to extract.")
    parser.add_argument("--scenario-id", default="webgpu-smoke", help="Page scenario identifier.")
    parser.add_argument("--workload-id", default="", help="Optional workload identifier.")
    parser.add_argument("--origin", default="browser-chromium-local", help="Origin label or URL.")
    parser.add_argument(
        "--capture-policy",
        default=str(CAPTURE_POLICY_PATH),
        help="Browser capture policy JSON path.",
    )
    parser.add_argument("--out", required=True, help="Output browser_gpu_flight_recorder JSON path.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def hash_hex(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_responsibility_map_version() -> str:
    payload = load_json(RESPONSIBILITY_MAP_PATH)
    return str(payload["mapVersion"])


def load_capture_surface_policy(policy_path: Path, surface_id: str = FLIGHT_RECORDER_SURFACE_ID) -> dict[str, Any]:
    payload = load_json(policy_path)
    for row in payload.get("surfaces", []):
        if isinstance(row, dict) and row.get("surfaceId") == surface_id:
            return row
    raise ValueError(f"capture policy missing surface {surface_id!r}: {policy_path}")


def require_component_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_COMPONENT_FIELDS - set(payload))
    if missing:
        raise ValueError(f"component manifest missing fields: {', '.join(missing)}")
    for field in REQUIRED_COMPONENT_FIELDS:
        if field != "commandGraph" and not isinstance(payload[field], list):
            raise ValueError(f"component manifest {field} must be an array")
    if not isinstance(payload["commandGraph"], dict):
        raise ValueError("component manifest commandGraph must be an object")
    return payload


def mode_results(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw = report.get("modeResults")
    if isinstance(raw, list):
        return [entry for entry in raw if isinstance(entry, dict)]
    raw = report.get("modeRunDetails")
    if isinstance(raw, list):
        return [entry for entry in raw if isinstance(entry, dict)]
    return []


def select_mode_result(report: dict[str, Any], mode: str) -> dict[str, Any]:
    for entry in mode_results(report):
        if entry.get("mode") == mode:
            return entry
    raise ValueError(f"report does not contain mode result {mode!r}")


def selected_runtime_hashes(report: dict[str, Any], result: dict[str, Any]) -> tuple[str | None, str | None]:
    doe_hash = result.get("runtimeSelection", {}).get("artifactIdentity", {}).get("doeLibSha256")
    artifact_identity = result.get("runtimeSelection", {}).get("artifactIdentity", {})
    dawn_hash = artifact_identity.get("dawnRuntimeSha256")
    for selection in report.get("runtimeSelections", []):
        if not isinstance(selection, dict):
            continue
        if selection.get("selectedRuntime") == "dawn":
            dawn_hash = selection.get("artifactIdentity", {}).get("dawnRuntimeSha256") or dawn_hash
            break
    return doe_hash, dawn_hash


def build_runtime_identity(report: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    runtime_selection = result.get("runtimeSelection", {})
    artifact_identity = runtime_selection.get("artifactIdentity", {})
    doe_hash, dawn_hash = selected_runtime_hashes(report, result)
    return {
        "selectedRuntime": runtime_selection.get("selectedRuntime", result.get("mode")),
        "selectorVersion": runtime_selection.get("selectorVersion", ""),
        "browserExecutableSha256": artifact_identity.get("browserExecutableSha256"),
        "doeRuntimeSha256": doe_hash,
        "dawnDelegateSha256": dawn_hash,
        "fallbackApplied": bool(runtime_selection.get("fallbackApplied", False)),
        "fallbackReasonCode": runtime_selection.get("fallbackReasonCode", ""),
    }


def build_adapter_identity(result: dict[str, Any]) -> dict[str, Any]:
    adapter_info = result.get("adapterInfo") or result.get("runtimeProbe", {}).get("adapterInfo") or {}
    limits = result.get("limits") or {}
    return {
        "name": str(adapter_info.get("description") or adapter_info.get("device") or "unknown-adapter"),
        "vendorId": str(adapter_info.get("vendor") or adapter_info.get("vendorId") or "unknown-vendor"),
        "deviceId": str(adapter_info.get("deviceId") or "unknown-device"),
        "backend": str(adapter_info.get("backend") or "unknown-backend"),
        "limitsSha256": hash_hex(limits),
    }


def timings_from_result(result: dict[str, Any], components: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(components.get("timings"), list) and components["timings"]:
        return components["timings"]

    timings: list[dict[str, Any]] = []
    benches = result.get("benches", {})
    iterations = benches.get("iterations", {})
    upload_us = benches.get("writeBuffer64kbUsPerOp")
    upload_iters = iterations.get("upload")
    if isinstance(upload_us, (int, float)) and isinstance(upload_iters, int):
        timings.append({
            "phase": "upload",
            "durationNs": max(0, round(upload_us * upload_iters * 1000)),
        })

    dispatch_us = benches.get("computeDispatchUsPerOp")
    dispatch_iters = iterations.get("dispatch")
    if isinstance(dispatch_us, (int, float)) and isinstance(dispatch_iters, int):
        timings.append({
            "phase": "submit_wait",
            "durationNs": max(0, round(dispatch_us * dispatch_iters * 1000)),
        })

    if timings:
        return timings
    return [{"phase": "page_setup", "durationNs": max(0, int(result.get("elapsedMs", 0)) * 1_000_000)}]


def failure_codes_from_result(result: dict[str, Any]) -> list[dict[str, str]]:
    codes: list[dict[str, str]] = []
    for index, error in enumerate(result.get("errors", [])):
        if error:
            codes.append({
                "code": "browser_result_error",
                "severity": "error",
                "source": "capture",
                "message": str(error),
            })
    for index, error in enumerate(result.get("benches", {}).get("errors", [])):
        if error:
            codes.append({
                "code": "browser_bench_error",
                "severity": "error",
                "source": "command_execution",
                "message": str(error),
            })
    smoke = result.get("smoke", {})
    if isinstance(smoke, dict):
        for name, entry in smoke.items():
            if isinstance(entry, dict) and entry.get("error"):
                codes.append({
                    "code": f"{name}_error",
                    "severity": "error",
                    "source": "command_execution",
                    "message": str(entry["error"]),
                })
    if codes:
        return codes
    return [{
        "code": "ok",
        "severity": "info",
        "source": "capture",
        "message": "browser report carried no failure",
    }]


def policy_failure(code: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "error",
        "source": "browser_policy",
        "message": message,
    }


def privacy_from_components(
    components: dict[str, Any],
    capture_surface_policy: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    raw_privacy = components.get("privacy")
    privacy = raw_privacy if isinstance(raw_privacy, dict) else {}
    failures: list[dict[str, str]] = []

    if privacy.get("originScoped") is not True:
        failures.append(policy_failure("capture_not_origin_scoped", "flight-recorder capture must be origin-scoped"))

    raw_data_included = privacy.get("rawPageDataIncluded") is True
    raw_page_policy = capture_surface_policy.get("rawPageDataPolicy")
    if raw_data_included and raw_page_policy in {"hash", "redact", "forbid"}:
        failures.append(
            policy_failure(
                "raw_page_data_forbidden",
                "flight-recorder policy does not allow raw page data in artifacts",
            )
        )

    page_data_policy = privacy.get("pageDataPolicy")
    if raw_page_policy == "hash":
        normalized_page_policy = "hash_only"
    elif raw_page_policy == "redact":
        normalized_page_policy = "redacted"
    else:
        normalized_page_policy = "hash_only"
    if page_data_policy == "explicit_debug_capture" and raw_page_policy != "forbid":
        failures.append(
            policy_failure(
                "debug_capture_not_allowed",
                "flight-recorder policy requires hashed or redacted page data",
            )
        )

    safe_privacy = {
        "originScoped": True,
        "pageDataPolicy": normalized_page_policy,
        "rawPageDataIncluded": False,
    }
    redaction_notes = privacy.get("redactionNotes")
    if isinstance(redaction_notes, str) and redaction_notes:
        safe_privacy["redactionNotes"] = redaction_notes
    elif failures:
        safe_privacy["redactionNotes"] = "unsafe privacy input normalized by capture policy"
    return safe_privacy, failures


def build_flight_recorder(
    report: dict[str, Any],
    components: dict[str, Any],
    mode: str,
    scenario_id: str,
    workload_id: str,
    origin: str,
    capture_surface_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = select_mode_result(report, mode)
    capture_policy = capture_surface_policy or load_capture_surface_policy(CAPTURE_POLICY_PATH)
    privacy, policy_failures = privacy_from_components(components, capture_policy)
    result_failures = failure_codes_from_result(result)
    if policy_failures:
        result_failures = [failure for failure in result_failures if failure.get("code") != "ok"]
        result_failures.extend(policy_failures)
    page = {
        "origin": origin,
        "urlSha256": hash_hex({"origin": origin, "scenarioId": scenario_id}),
        "scenarioId": scenario_id,
    }
    if workload_id:
        page["workloadId"] = workload_id

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_gpu_flight_recorder",
        "captureId": f"{scenario_id}-{mode}",
        "generatedAt": str(report.get("generatedAt", "")),
        "page": page,
        "runtimeIdentity": build_runtime_identity(report, result),
        "adapterIdentity": build_adapter_identity(result),
        "responsibilityMap": {
            "path": "config/browser-responsibility-map.json",
            "mapVersion": load_responsibility_map_version(),
        },
        "shaders": components["shaders"],
        "bindGroups": components["bindGroups"],
        "buffers": components["buffers"],
        "textures": components["textures"],
        "commandGraph": components["commandGraph"],
        "timings": timings_from_result(result, components),
        "frames": components["frames"],
        "failureCodes": result_failures,
        "privacy": privacy,
    }


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    components = require_component_manifest(load_json(Path(args.components)))
    artifact = build_flight_recorder(
        report=report,
        components=components,
        mode=args.mode,
        scenario_id=args.scenario_id,
        workload_id=args.workload_id,
        origin=args.origin,
        capture_surface_policy=load_capture_surface_policy(Path(args.capture_policy)),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
