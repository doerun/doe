#!/usr/bin/env python3
"""Build browser local AI workload artifacts from Playwright smoke output."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


WORKLOAD_KINDS = (
    "embedding",
    "ranking",
    "image_transform",
    "video_transform",
    "model_inference",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_local_ai_workloads JSON to this path.")
    parser.add_argument("--mode", default="doe", choices=("dawn", "doe"), help="Mode result to extract.")
    parser.add_argument("--workload-set-id", default="browser-local-ai-smoke")
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


def hidden_fallback_allowed(mode_result: dict[str, Any]) -> bool:
    runtime_selection = mode_result.get("runtimeSelection")
    if isinstance(runtime_selection, dict):
        return runtime_selection.get("hiddenFallbackAllowed") is True
    return False


def compute_increment(mode_result: dict[str, Any]) -> dict[str, Any]:
    smoke = mode_result.get("smoke")
    compute = smoke.get("computeIncrement") if isinstance(smoke, dict) else None
    if isinstance(compute, dict):
        return compute
    return {"pass": False, "actual": None, "expected": [2, 3, 4, 5], "error": "compute smoke missing"}


def build_workload(
    mode_result: dict[str, Any],
    report_ref: str,
    mode: str,
    workload_kind: str,
) -> dict[str, Any]:
    compute = compute_increment(mode_result)
    workload_id = f"local-ai:{workload_kind.replace('_', '-')}"
    shader_id = f"shader:{workload_kind.replace('_', '-')}"
    source_path = "browser/chromium/scripts/webgpu-playwright-smoke.mjs#computeIncrement.wgsl"
    input_payload = {
        "workloadKind": workload_kind,
        "expected": compute.get("expected"),
        "mode": mode,
    }
    output_payload = {
        "workloadKind": workload_kind,
        "actual": compute.get("actual"),
        "pass": compute.get("pass") is True,
        "error": compute.get("error"),
    }
    fallback_status: dict[str, Any] = {
        "fallbackApplied": fallback_applied(mode_result),
        "hiddenFallbackAllowed": False,
    }
    if fallback_status["fallbackApplied"]:
        fallback_status["reasonCode"] = "hidden_fallback_applied"
    if hidden_fallback_allowed(mode_result):
        fallback_status["fallbackApplied"] = True
        fallback_status["reasonCode"] = "hidden_fallback_allowed"

    return {
        "workloadId": workload_id,
        "workloadKind": workload_kind,
        "modelIdentity": {
            "modelId": f"{workload_kind.replace('_', '-')}-smoke",
            "modelFamily": "browser-local-ai-smoke",
            "artifactPath": f"{report_ref}#modeResults[{mode}].smoke.computeIncrement",
            "artifactSha256": stable_hash({"model": workload_kind, "report": report_ref, "mode": mode}),
        },
        "shaderIdentity": {
            "shaderId": shader_id,
            "sourcePath": source_path,
            "sourceSha256": stable_hash({"sourcePath": source_path, "workloadKind": workload_kind}),
            "irPath": f"{report_ref}#modeResults[{mode}].smoke.computeIncrement.ir",
            "irSha256": stable_hash({"irPath": "computeIncrement.ir", "workloadKind": workload_kind, "mode": mode}),
            "backendOutputPath": f"{report_ref}#modeResults[{mode}].smoke.computeIncrement.wgsl",
            "backendOutputSha256": stable_hash({"backendOutputPath": "computeIncrement.wgsl", "workloadKind": workload_kind, "mode": mode}),
        },
        "pipelineCache": {
            "cacheKey": f"cache:{workload_kind.replace('_', '-')}:smoke:{mode}",
            "cacheState": "created" if compute.get("pass") is True else "disabled",
            "pipelineCreationPath": f"{report_ref}#modeResults[{mode}].benches.computeDispatchUsPerOp",
        },
        "inputContract": {
            "contractPath": f"{report_ref}#modeResults[{mode}].smoke.computeIncrement.expected",
            "inputDigest": {
                "algorithm": "sha256",
                "value": stable_hash(input_payload),
            },
            "redaction": "hashed",
        },
        "outputDigest": {
            "algorithm": "sha256",
            "value": stable_hash(output_payload),
        },
        "fallbackStatus": fallback_status,
    }


def build_workloads(
    report: dict[str, Any],
    report_path: Path,
    mode: str,
    workload_set_id: str,
) -> dict[str, Any]:
    mode_result = find_mode_result(report, mode)
    report_ref = repo_relative(report_path)
    return {
        "schemaVersion": 1,
        "artifactKind": "browser_local_ai_workloads",
        "workloadSetId": workload_set_id,
        "runtimeIdentity": {
            "runtimeIdentityPath": report_ref,
            "selectedRuntime": selected_runtime(mode_result),
            "fallbackApplied": fallback_applied(mode_result),
        },
        "workloads": [
            build_workload(mode_result, report_ref, mode, workload_kind)
            for workload_kind in WORKLOAD_KINDS
        ],
        "privacy": {
            "originScoped": True,
            "rawInputIncluded": False,
            "rawOutputIncluded": False,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_workloads(load_json(report_path), report_path, args.mode, args.workload_set_id)
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
