#!/usr/bin/env python3
"""Validate browser local AI workload receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from browser_runtime_identity_reference import check_runtime_identity_reference


REQUIRED_WORKLOAD_KINDS = {
    "embedding",
    "ranking",
    "image_transform",
    "video_transform",
    "model_inference",
}
EXPECTED_KIND = "browser_local_ai_workloads"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", required=True, help="browser_local_ai_workloads JSON path.")
    parser.add_argument(
        "--runtime-identity-root",
        default="",
        help="Optional repository root used to resolve runtimeIdentity.runtimeIdentityPath.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def check_unique_ids(
    rows: Any,
    *,
    field: str,
    path: str,
    code: str,
    label: str,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(rows, list):
        return failures
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        value = row.get(field)
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            failures.append(failure(code, f"{path}[{index}].{field}", f"duplicate {label} {value}"))
        seen.add(value)
    return failures


def _missing_object_field(item: dict[str, Any], path: str, field: str, failures: list[dict[str, str]]) -> None:
    if not item.get(field):
        failures.append(failure("missing_receipt_field", f"{path}.{field}", f"missing receipt field {field}"))


def check_workloads(
    payload: dict[str, Any],
    runtime_identity_root: Path | None = None,
) -> list[dict[str, str]]:
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
    if runtime_identity_root is not None:
        failures.extend(check_runtime_identity_reference(payload, runtime_identity_root))
    workloads = payload.get("workloads", [])
    failures.extend(
        check_unique_ids(
            workloads,
            field="workloadId",
            path="workloads",
            code="duplicate_workload_id",
            label="workloadId",
        )
    )
    workload_kinds = {
        workload.get("workloadKind")
        for workload in workloads
        if isinstance(workload, dict)
    }
    for workload_kind in sorted(REQUIRED_WORKLOAD_KINDS - workload_kinds):
        failures.append(failure("missing_workload_kind", "workloads", f"missing workload kind {workload_kind}"))

    for workload_index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            continue
        workload_path = f"workloads[{workload_index}]"
        model_identity = workload.get("modelIdentity", {})
        if isinstance(model_identity, dict):
            for field in ("modelId", "artifactPath", "artifactSha256"):
                _missing_object_field(model_identity, f"{workload_path}.modelIdentity", field, failures)

        shader_identity = workload.get("shaderIdentity", {})
        if isinstance(shader_identity, dict):
            for field in (
                "shaderId",
                "sourcePath",
                "sourceSha256",
                "irPath",
                "irSha256",
                "backendOutputPath",
                "backendOutputSha256",
            ):
                _missing_object_field(shader_identity, f"{workload_path}.shaderIdentity", field, failures)

        pipeline_cache = workload.get("pipelineCache", {})
        if isinstance(pipeline_cache, dict):
            for field in ("cacheKey", "cacheState", "pipelineCreationPath"):
                _missing_object_field(pipeline_cache, f"{workload_path}.pipelineCache", field, failures)

        input_contract = workload.get("inputContract", {})
        if isinstance(input_contract, dict):
            for field in ("contractPath", "inputDigest", "redaction"):
                _missing_object_field(input_contract, f"{workload_path}.inputContract", field, failures)

        output_digest = workload.get("outputDigest", {})
        if not isinstance(output_digest, dict) or not output_digest.get("value"):
            failures.append(
                failure("missing_output_digest", f"{workload_path}.outputDigest", "workload requires output digest")
            )

        fallback_status = workload.get("fallbackStatus", {})
        if not isinstance(fallback_status, dict):
            failures.append(
                failure("missing_receipt_field", f"{workload_path}.fallbackStatus", "missing receipt field fallbackStatus")
            )
            continue
        if fallback_status.get("hiddenFallbackAllowed") is not False:
            failures.append(
                failure(
                    "hidden_fallback_allowed",
                    f"{workload_path}.fallbackStatus.hiddenFallbackAllowed",
                    "hidden fallback must be false",
                )
            )
        if fallback_status.get("fallbackApplied") is True and not fallback_status.get("reasonCode"):
            failures.append(
                failure(
                    "missing_fallback_reason",
                    f"{workload_path}.fallbackStatus.reasonCode",
                    "applied fallback requires reasonCode",
                )
            )

    privacy = payload.get("privacy", {})
    if (
        not isinstance(privacy, dict)
        or privacy.get("originScoped") is not True
        or privacy.get("rawInputIncluded") is not False
        or privacy.get("rawOutputIncluded") is not False
    ):
        failures.append(
            failure(
                "unsafe_privacy_policy",
                "privacy",
                "local AI workloads must be origin-scoped and exclude raw inputs/outputs",
            )
        )

    return failures


def main() -> int:
    args = parse_args()
    runtime_identity_root = (
        Path(args.runtime_identity_root).resolve()
        if args.runtime_identity_root.strip()
        else None
    )
    failures = check_workloads(load_json(Path(args.workloads)), runtime_identity_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_local_ai_workloads_check",
        "workloadsPath": args.workloads,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser local AI workloads")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser local AI workloads")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
