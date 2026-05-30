#!/usr/bin/env python3
"""Build browser WebGPU effect experiment artifacts from Playwright smoke output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SURFACES = [
    {
        "surfaceId": "surface:canvas-overlay",
        "sourceKind": "canvas_overlay",
        "webgpuBacked": True,
        "doeBoundary": "visual_effect_only",
        "layoutOwner": "browser",
        "accessibilityOwner": "browser",
        "securityOwner": "browser",
        "sourcePath": "browser/chromium/scripts/webgpu-playwright-smoke.mjs#renderTriangle",
    },
    {
        "surfaceId": "surface:presentation-filter",
        "sourceKind": "presentation_filter",
        "webgpuBacked": True,
        "doeBoundary": "visual_effect_only",
        "layoutOwner": "browser",
        "accessibilityOwner": "browser",
        "securityOwner": "browser",
        "sourcePath": "browser/chromium/scripts/webgpu-playwright-smoke.mjs#renderTriangle",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_webgpu_effect_experiment JSON to this path.")
    parser.add_argument("--mode", default="doe", choices=("dawn", "doe"), help="Mode result to extract.")
    parser.add_argument("--experiment-id", default="webgpu-effect-smoke")
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


def fallback_behavior_status(mode_result: dict[str, Any]) -> tuple[str, str]:
    if hidden_fallback_allowed(mode_result):
        return "fail", "hidden_fallback_allowed"
    if fallback_applied(mode_result):
        return "fail", "hidden_fallback_applied"
    return "pass", "hidden_fallback_disabled"


def render_status(mode_result: dict[str, Any]) -> tuple[str, str]:
    smoke = mode_result.get("smoke")
    render = smoke.get("renderTriangle") if isinstance(smoke, dict) else None
    if not isinstance(render, dict):
        return "diagnostic", "render_probe_missing"
    if render.get("pass") is True:
        return "pass", ""
    if render.get("error"):
        return "fail", "render_probe_failed"
    return "diagnostic", "render_probe_inconclusive"


def build_experiment(
    report: dict[str, Any],
    report_path: Path,
    mode: str,
    experiment_id: str,
) -> dict[str, Any]:
    mode_result = find_mode_result(report, mode)
    report_ref = repo_relative(report_path)
    render_probe_status, render_probe_reason = render_status(mode_result)
    fallback_status, fallback_reason = fallback_behavior_status(mode_result)
    probes: list[dict[str, Any]] = [
        {
            "probeId": "probe:output-hash",
            "probeKind": "output_hash",
            "surfaceIds": ["surface:canvas-overlay", "surface:presentation-filter"],
            "status": render_probe_status,
            "evidencePath": f"{report_ref}#modeResults[{mode}].smoke.renderTriangle.centerRgba",
        },
        {
            "probeId": "probe:semantics-boundary",
            "probeKind": "semantics_boundary",
            "surfaceIds": ["surface:canvas-overlay", "surface:presentation-filter"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#modeResults[{mode}].webgpuCanvasApi",
            "reasonCode": "browser_ownership_declared_not_proven_by_smoke",
        },
        {
            "probeId": "probe:fallback-behavior",
            "probeKind": "fallback_behavior",
            "surfaceIds": ["surface:canvas-overlay", "surface:presentation-filter"],
            "status": fallback_status,
            "evidencePath": f"{report_ref}#modeResults[{mode}].runtimeSelection",
            "reasonCode": fallback_reason,
        },
        {
            "probeId": "probe:frame-timing",
            "probeKind": "frame_timing",
            "surfaceIds": ["surface:canvas-overlay", "surface:presentation-filter"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#modeResults[{mode}].benches",
            "reasonCode": "frame_timing_not_measured_by_smoke",
        },
        {
            "probeId": "probe:security-policy",
            "probeKind": "security_policy",
            "surfaceIds": ["surface:canvas-overlay", "surface:presentation-filter"],
            "status": "diagnostic",
            "evidencePath": f"{report_ref}#privacy",
            "reasonCode": "origin_scoped_no_raw_dom",
        },
    ]
    if render_probe_reason:
        probes[0]["reasonCode"] = render_probe_reason

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_webgpu_effect_experiment",
        "experimentId": experiment_id,
        "runtimeIdentity": {
            "runtimeIdentityPath": report_ref,
            "selectedRuntime": selected_runtime(mode_result),
            "fallbackApplied": fallback_applied(mode_result),
        },
        "surfaces": SURFACES,
        "pipelines": [
            {
                "pipelineId": "pipeline:smoke-visual-effect",
                "surfaceIds": ["surface:canvas-overlay", "surface:presentation-filter"],
                "shaderLanguage": "wgsl",
                "shaderSourcePath": "browser/chromium/scripts/webgpu-playwright-smoke.mjs#renderTriangle.wgsl",
                "backendTarget": "wgsl",
                "backendOutputPath": f"{report_ref}#modeResults[{mode}].smoke.renderTriangle",
            }
        ],
        "probes": probes,
        "fallbackPolicy": {
            "hiddenFallbackAllowed": False,
            "reasonCodeRequired": True,
        },
        "privacy": {
            "originScoped": True,
            "rawDomIncluded": False,
            "rawPageDataIncluded": False,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_experiment(load_json(report_path), report_path, args.mode, args.experiment_id)
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
