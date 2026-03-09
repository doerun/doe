#!/usr/bin/env python3
"""Run deterministic module incubation prototype requests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_INCUBATION_ROOT = REPO_ROOT / "nursery/fawn-browser/module-incubation"
SCHEMA_DIR = MODULE_INCUBATION_ROOT / "schemas"
POLICY_PATH = MODULE_INCUBATION_ROOT / "policy.json"
SCHEMA_PATHS = {
    "fawn_2d_sdf_renderer": SCHEMA_DIR / "fawn-2d-sdf-renderer.schema.json",
    "fawn_path_engine": SCHEMA_DIR / "fawn-path-engine.schema.json",
    "fawn_effects_pipeline": SCHEMA_DIR / "fawn-effects-pipeline.schema.json",
    "fawn_compute_services": SCHEMA_DIR / "fawn-compute-services.schema.json",
    "fawn_resource_scheduler": SCHEMA_DIR / "fawn-resource-scheduler.schema.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, help="Module request JSON path.")
    parser.add_argument("--policy", default=str(POLICY_PATH), help="Policy JSON path.")
    parser.add_argument("--out", default="", help="Optional output path for result JSON.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_payload(module_id: str, payload: dict[str, Any]) -> None:
    schema = load_json(SCHEMA_PATHS[module_id])
    artifact_kind = payload.get("artifactKind")
    if artifact_kind not in {"request", "result"}:
        raise ValueError(f"invalid artifactKind for {module_id}: {artifact_kind}")
    specific = schema["$defs"][artifact_kind]
    merged_schema = {
        "type": "object",
        "required": sorted(set(schema["required"]) | set(specific.get("required", []))),
        "properties": {
            **schema.get("properties", {}),
            **specific.get("properties", {}),
        },
        "additionalProperties": False,
        "$defs": schema.get("$defs", {}),
    }
    Draft202012Validator(merged_schema).validate(payload)


def fallback_histogram(*codes: str) -> dict[str, int]:
    histogram: dict[str, int] = {}
    for code in codes:
        if not code:
            continue
        histogram[code] = histogram.get(code, 0) + 1
    return histogram


def build_trace_link(module_id: str, request_hash: str, policy_hash: str, result_payload: dict[str, Any]) -> dict[str, str]:
    result_hash = stable_hash(result_payload)
    return {
        "moduleIdentity": module_id,
        "requestHash": request_hash,
        "policyHash": policy_hash,
        "resultHash": result_hash,
    }


def run_sdf_renderer(request: dict[str, Any], policy: dict[str, Any], request_hash: str, policy_hash: str) -> dict[str, Any]:
    module_policy = policy["modules"]["fawn_2d_sdf_renderer"]
    text_runs = request["textRuns"]
    path_ops = request["pathOps"]
    glyph_count = sum(len(run["glyphIds"]) for run in text_runs)
    atlas_miss_count = max(0, glyph_count - module_policy["atlasGlyphCapacity"])
    fallback_codes: list[str] = []
    if request["paintState"]["blendMode"] not in module_policy["allowedBlendModes"]:
        fallback_codes.append("unsupported_blend_mode")
    if request["paintState"]["clipState"]["mode"] not in module_policy["allowedClipModes"]:
        fallback_codes.append("unsupported_clip_mode")
    if request["target"]["sampleCount"] not in module_policy["allowedSampleCounts"]:
        fallback_codes.append("required_capability_missing")
    if len(path_ops) > module_policy["maxPathOps"]:
        fallback_codes.append("path_complexity_exceeded")
    if request["target"]["width"] * request["target"]["height"] > module_policy["maxTargetPixels"]:
        fallback_codes.append("resource_budget_exceeded")
    atlas_hit_count = max(0, glyph_count - atlas_miss_count)
    render_stats = {
        "drawCallCount": len(text_runs) + max(1, len(path_ops) // 2),
        "atlasHitCount": atlas_hit_count,
        "atlasMissCount": atlas_miss_count,
        "passCount": 1 if not fallback_codes else 0,
    }
    result = {
        "schemaVersion": 1,
        "moduleId": "fawn_2d_sdf_renderer",
        "artifactKind": "result",
        "renderArtifact": {"artifactId": f"sdf://{request_hash[:16]}"},
        "renderStats": render_stats,
        "timingStats": {
            "setupNs": 10000 + glyph_count * 50 + len(path_ops) * 30,
            "encodeNs": 5000 + render_stats["drawCallCount"] * 120,
            "submitWaitNs": 2000 + request["target"]["sampleCount"] * 500,
        },
        "qualityStats": {
            "fallbackCount": len(fallback_codes),
            "fallbackReasonHistogram": fallback_histogram(*fallback_codes),
        },
    }
    result["traceLink"] = build_trace_link("fawn_2d_sdf_renderer", request_hash, policy_hash, result)
    return result


def run_path_engine(request: dict[str, Any], policy: dict[str, Any], request_hash: str, policy_hash: str) -> dict[str, Any]:
    module_policy = policy["modules"]["fawn_path_engine"]
    segment_count = len(request["pathStream"])
    fallback_codes: list[str] = []
    if request["strokeState"]["joinMode"] not in module_policy["allowedJoinModes"]:
        fallback_codes.append("join_mode_unsupported")
    if request["strokeState"]["dashPattern"] and not module_policy["allowDashPatterns"]:
        fallback_codes.append("dash_pattern_unsupported")
    if segment_count > module_policy["maxSegments"]:
        fallback_codes.append("geometry_pathological")
    if request["target"]["width"] * request["target"]["height"] > module_policy["maxTargetPixels"]:
        fallback_codes.append("resource_budget_exceeded")
    result = {
        "schemaVersion": 1,
        "moduleId": "fawn_path_engine",
        "artifactKind": "result",
        "geometryStats": {
            "segmentCount": segment_count,
            "tessellatedPrimitiveCount": segment_count * 2,
        },
        "rasterStats": {
            "passCount": 1 if not fallback_codes else 0,
            "drawCallCount": max(1, segment_count // 2),
        },
        "fallbackStats": {
            "fallbackCount": len(fallback_codes),
            "fallbackReasonHistogram": fallback_histogram(*fallback_codes),
        },
    }
    result["traceLink"] = build_trace_link("fawn_path_engine", request_hash, policy_hash, result)
    return result


def run_effects_pipeline(request: dict[str, Any], policy: dict[str, Any], request_hash: str, policy_hash: str) -> dict[str, Any]:
    module_policy = policy["modules"]["fawn_effects_pipeline"]
    nodes = request["effectGraph"]
    total_input_bytes = sum(entry["bytes"] for entry in request["inputs"])
    fallback_codes: list[str] = []
    if len(nodes) > module_policy["maxNodeCount"]:
        fallback_codes.append("effect_op_unsupported")
    if request["executionPolicy"]["colorSpace"] not in module_policy["allowedColorSpaces"]:
        fallback_codes.append("color_space_mode_unsupported")
    if any(node["op"] not in module_policy["allowedOps"] for node in nodes):
        fallback_codes.append("effect_op_unsupported")
    temporary_bytes = total_input_bytes * max(1, len(nodes))
    if temporary_bytes > module_policy["maxIntermediateBytes"]:
        fallback_codes.append("intermediate_budget_exceeded")
    result = {
        "schemaVersion": 1,
        "moduleId": "fawn_effects_pipeline",
        "artifactKind": "result",
        "outputArtifact": {"artifactId": f"effects://{request_hash[:16]}"},
        "executionStats": {
            "nodeCount": len(nodes),
            "passCount": len(nodes),
            "temporaryBytes": temporary_bytes,
        },
        "timingStats": {
            "setupNs": 8000 + len(nodes) * 400,
            "encodeNs": 7000 + len(nodes) * 700,
            "submitWaitNs": 3000 + len(nodes) * 500,
        },
        "fallbackStats": {
            "fallbackCount": len(fallback_codes),
            "fallbackReasonHistogram": fallback_histogram(*fallback_codes),
        },
    }
    result["traceLink"] = build_trace_link("fawn_effects_pipeline", request_hash, policy_hash, result)
    return result


def run_compute_services(request: dict[str, Any], policy: dict[str, Any], request_hash: str, policy_hash: str) -> dict[str, Any]:
    module_policy = policy["modules"]["fawn_compute_services"]
    supported_kernels = module_policy["services"].get(request["serviceId"], [])
    total_input_bytes = sum(entry["bytes"] for entry in request["inputs"])
    dispatch_count = request["dispatch"]["x"] * request["dispatch"]["y"] * request["dispatch"]["z"]
    status = "ok"
    failure_code = "none"
    if request["serviceId"] not in module_policy["services"]:
        status = "error"
        failure_code = "service_id_unknown"
    elif request["kernelId"] not in supported_kernels:
        status = "error"
        failure_code = "kernel_id_unknown"
    elif total_input_bytes > module_policy["maxInputBytes"]:
        status = "fallback"
        failure_code = "input_contract_invalid"
    elif dispatch_count > module_policy["maxDispatchesPerRequest"]:
        status = "fallback"
        failure_code = "dispatch_contract_invalid"
    result = {
        "schemaVersion": 1,
        "moduleId": "fawn_compute_services",
        "artifactKind": "result",
        "serviceResult": {"status": status},
        "executionStats": {
            "dispatchCount": dispatch_count,
            "bytesMoved": total_input_bytes,
        },
        "timingStats": {
            "setupNs": 6000 + len(request["inputs"]) * 300,
            "encodeNs": 5000 + dispatch_count * 2,
            "submitNs": 3000 + dispatch_count,
            "dispatchNs": 4000 + dispatch_count * 3,
        },
        "failureDetails": {"code": failure_code},
    }
    result["traceLink"] = build_trace_link("fawn_compute_services", request_hash, policy_hash, result)
    return result


def run_resource_scheduler(request: dict[str, Any], policy: dict[str, Any], request_hash: str, policy_hash: str) -> dict[str, Any]:
    module_policy = policy["modules"]["fawn_resource_scheduler"]
    requests = request["resourceRequest"]
    total_bytes = sum(entry["bytes"] for entry in requests)
    fallback_codes: list[str] = []
    if request["schedulerPolicy"]["cadenceMode"] not in module_policy["allowedCadenceModes"]:
        fallback_codes.append("cadence_policy_invalid")
    if request["workloadContext"]["moduleId"] not in module_policy["allowedModules"]:
        fallback_codes.append("profile_policy_missing")
    if len(requests) > module_policy["maxResourcesPerRequest"]:
        fallback_codes.append("determinism_guard_triggered")
    if request["schedulerPolicy"]["poolLimitBytes"] > module_policy["maxPoolBytes"]:
        fallback_codes.append("pool_limit_exceeded")
    allocation_result = []
    pool_limit = min(request["schedulerPolicy"]["poolLimitBytes"], module_policy["maxPoolBytes"])
    used = 0
    hit_count = 0
    miss_count = 0
    for index, entry in enumerate(requests):
        disposition = "reused" if index % 2 == 0 else "allocated"
        if disposition == "reused":
            hit_count += 1
        else:
            miss_count += 1
        bytes_granted = min(entry["bytes"], max(0, pool_limit - used))
        used += bytes_granted
        if bytes_granted < entry["bytes"]:
            disposition = "fallback"
            fallback_codes.append("pool_limit_exceeded")
        allocation_result.append(
            {
                "resourceId": f"res_{index}",
                "disposition": disposition,
                "bytesGranted": bytes_granted,
            }
        )
    result = {
        "schemaVersion": 1,
        "moduleId": "fawn_resource_scheduler",
        "artifactKind": "result",
        "allocationResult": allocation_result,
        "poolStats": {
            "hitCount": hit_count,
            "missCount": miss_count,
            "evictionCount": max(0, len(requests) - module_policy["maxResourcesPerRequest"]),
            "highWaterBytes": min(total_bytes, pool_limit),
        },
        "submitStats": {
            "submitCount": max(1, len(requests) // 2),
            "cadenceModeUsed": request["schedulerPolicy"]["cadenceMode"],
        },
        "fallbackStats": {
            "fallbackCount": len(fallback_codes),
            "fallbackReasonHistogram": fallback_histogram(*fallback_codes),
        },
    }
    result["traceLink"] = build_trace_link("fawn_resource_scheduler", request_hash, policy_hash, result)
    return result


RUNNERS = {
    "fawn_2d_sdf_renderer": run_sdf_renderer,
    "fawn_path_engine": run_path_engine,
    "fawn_effects_pipeline": run_effects_pipeline,
    "fawn_compute_services": run_compute_services,
    "fawn_resource_scheduler": run_resource_scheduler,
}


def main() -> int:
    args = parse_args()
    request_payload = load_json(Path(args.request).resolve())
    module_id = request_payload.get("moduleId")
    if module_id not in RUNNERS:
        raise ValueError(f"unsupported moduleId: {module_id}")

    policy_payload = load_json(Path(args.policy).resolve())
    validate_payload(module_id, request_payload)
    request_hash = stable_hash(request_payload)
    policy_hash = stable_hash(policy_payload)
    result_payload = RUNNERS[module_id](request_payload, policy_payload, request_hash, policy_hash)
    validate_payload(module_id, result_payload)

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result_payload, indent=2) + "\n", encoding="utf-8")

    if args.emit_json or not args.out:
        print(json.dumps(result_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
