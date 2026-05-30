#!/usr/bin/env python3
"""Build browser canvas/WebGPU fusion probes from Playwright smoke output."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_canvas_webgpu_fusion_probe JSON to this path.")
    parser.add_argument("--mode", default="doe", choices=("dawn", "doe"), help="Mode result to extract.")
    parser.add_argument("--probe-id", default="canvas-webgpu-fusion-smoke")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def fallback_reason(surface_id: str, reason_code: str, message: str = "") -> dict[str, str]:
    row = {
        "surfaceId": surface_id,
        "reasonCode": reason_code,
    }
    if message:
        row["message"] = message
    return row


def build_probe(report: dict[str, Any], report_path: Path, mode: str, probe_id: str) -> dict[str, Any]:
    mode_result = find_mode_result(report, mode)
    smoke = mode_result.get("smoke", {})
    if not isinstance(smoke, dict):
        smoke = {}
    canvas_api = mode_result.get("webgpuCanvasApi", {})
    if not isinstance(canvas_api, dict):
        canvas_api = {}
    render = smoke.get("renderTriangle", {})
    if not isinstance(render, dict):
        render = {}

    surfaces = [
        {
            "surfaceId": "surface:canvas2d",
            "kind": "canvas_2d",
            "responsibilityMapEntry": "canvas_2d",
        },
        {
            "surfaceId": "surface:webgpu",
            "kind": "webgpu",
            "responsibilityMapEntry": "webgpu",
        },
        {
            "surfaceId": "surface:filter",
            "kind": "image_filter",
            "responsibilityMapEntry": "image_filters",
        },
        {
            "surfaceId": "surface:present",
            "kind": "presentation",
            "responsibilityMapEntry": "swapchain_surface_presentation",
        },
    ]
    nodes = [
        {"nodeId": "node:canvas_draw", "surfaceId": "surface:canvas2d", "op": "canvas_draw"},
        {"nodeId": "node:webgpu_render", "surfaceId": "surface:webgpu", "op": "webgpu_render"},
        {"nodeId": "node:filter", "surfaceId": "surface:filter", "op": "image_filter"},
        {"nodeId": "node:present", "surfaceId": "surface:present", "op": "present"},
    ]
    edges = [
        {"fromNodeId": "node:canvas_draw", "toNodeId": "node:webgpu_render", "edgeKind": "feeds"},
        {"fromNodeId": "node:webgpu_render", "toNodeId": "node:filter", "edgeKind": "feeds"},
        {"fromNodeId": "node:filter", "toNodeId": "node:present", "edgeKind": "presents"},
    ]
    graph_payload = {
        "nodes": nodes,
        "edges": edges,
        "source": {
            "report": repo_relative(report_path),
            "mode": mode,
        },
    }
    fallback_reasons = []
    if canvas_api.get("offscreenCanvasAvailable") is not True:
        fallback_reasons.append(fallback_reason("surface:canvas2d", "offscreen_canvas_unavailable"))
    if canvas_api.get("webgpuContextAvailable") is not True:
        fallback_reasons.append(fallback_reason("surface:present", "webgpu_canvas_context_unavailable"))
    if render.get("pass") is not True:
        fallback_reasons.append(
            fallback_reason(
                "surface:webgpu",
                "webgpu_render_failed",
                str(render.get("error") or ""),
            )
        )

    present_output = {
        "renderTriangle": render.get("centerRgba"),
        "canvasApi": canvas_api,
        "fallbackReasons": fallback_reasons,
    }
    upload_us = mode_result.get("benches", {}).get("writeBuffer64kbUsPerOp") if isinstance(mode_result.get("benches"), dict) else None
    dispatch_us = mode_result.get("benches", {}).get("computeDispatchUsPerOp") if isinstance(mode_result.get("benches"), dict) else None
    return {
        "schemaVersion": 1,
        "artifactKind": "browser_canvas_webgpu_fusion_probe",
        "probeId": probe_id,
        "runtimeIdentity": {
            "runtimeIdentityPath": repo_relative(report_path),
            "selectedRuntime": selected_runtime(mode_result),
            "fallbackApplied": fallback_applied(mode_result),
        },
        "surfaces": surfaces,
        "graph": {
            "graphSha256": stable_hash(graph_payload),
            "nodes": nodes,
            "edges": edges,
        },
        "outputHashes": [
            {
                "surfaceId": "surface:present",
                "outputSha256": stable_hash(present_output),
            }
        ],
        "timingScopes": [
            {"surfaceId": "surface:canvas2d", "phase": "canvas_2d", "durationNs": 0},
            {"surfaceId": "surface:webgpu", "phase": "webgpu", "durationNs": int((dispatch_us or 0) * 1000)},
            {"surfaceId": "surface:filter", "phase": "filter", "durationNs": 0},
            {"surfaceId": "surface:present", "phase": "present", "durationNs": int((upload_us or 0) * 1000)},
        ],
        "fallbackReasons": fallback_reasons,
        "privacy": {
            "originScoped": True,
            "rawPageDataIncluded": False,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_probe(load_json(report_path), report_path, args.mode, args.probe_id)
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
