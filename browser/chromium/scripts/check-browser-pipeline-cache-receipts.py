#!/usr/bin/env python3
"""Validate browser pipeline cache receipt artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from browser_runtime_identity_reference import check_runtime_identity_reference

EXPECTED_KIND = "browser_pipeline_cache_receipts"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", required=True, help="browser_pipeline_cache_receipts JSON path.")
    parser.add_argument(
        "--verify-workloads-root",
        default="",
        help="Resolve sourceWorkloadsPath under this root and verify receipt coverage.",
    )
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


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_repo_path(path_text: str, root: Path) -> Path | None:
    if not safe_repo_path(path_text):
        return None
    resolved = root.joinpath(*PurePosixPath(path_text).parts).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def creation_status_for(cache_state: Any) -> str:
    if cache_state == "hit":
        return "reused"
    if cache_state == "disabled":
        return "skipped"
    return "created"


def add_mismatch(
    failures: list[dict[str, str]],
    receipt_path: str,
    field: str,
    expected: Any,
    actual: Any,
) -> None:
    if actual != expected:
        path = f"{receipt_path}.{field}" if receipt_path else field
        failures.append(
            failure(
                "receipt_workload_mismatch",
                path,
                f"expected {field}={expected!r} from source workload, got {actual!r}",
            )
        )


def verify_source_workloads(
    payload: dict[str, Any],
    receipts: list[Any],
    verify_workloads_root: Path,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    source_path = payload.get("sourceWorkloadsPath")
    if not isinstance(source_path, str) or not source_path:
        return [failure("missing_source_workloads_path", "sourceWorkloadsPath", "source workload artifact path is required")]

    resolved_source_path = resolve_repo_path(source_path, verify_workloads_root)
    if resolved_source_path is None:
        return [
            failure(
                "unsafe_source_workloads_path",
                "sourceWorkloadsPath",
                "sourceWorkloadsPath must be repo-relative",
            )
        ]
    if not resolved_source_path.is_file():
        return [
            failure(
                "source_workloads_missing",
                "sourceWorkloadsPath",
                f"source workload artifact not found: {source_path}",
            )
        ]

    try:
        source_payload = load_json(resolved_source_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [
            failure(
                "invalid_source_workloads",
                "sourceWorkloadsPath",
                f"source workload artifact is not valid JSON object: {exc}",
            )
        ]
    if source_payload.get("artifactKind") != "browser_local_ai_workloads":
        failures.append(
            failure(
                "source_workloads_kind_mismatch",
                "sourceWorkloadsPath",
                "sourceWorkloadsPath must point to browser_local_ai_workloads",
            )
        )

    add_mismatch(
        failures,
        "",
        "sourceWorkloadSetId",
        source_payload.get("workloadSetId"),
        payload.get("sourceWorkloadSetId"),
    )
    if payload.get("runtimeIdentity") != source_payload.get("runtimeIdentity"):
        failures.append(
            failure(
                "runtime_identity_mismatch",
                "runtimeIdentity",
                "pipeline cache receipts runtimeIdentity must match source workloads runtimeIdentity",
            )
        )

    receipts_by_workload: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            continue
        workload_id = receipt.get("workloadId")
        if not isinstance(workload_id, str) or not workload_id:
            continue
        if workload_id in receipts_by_workload:
            failures.append(
                failure(
                    "duplicate_workload_receipt",
                    f"receipts[{index}].workloadId",
                    f"duplicate pipeline cache receipt for workload {workload_id}",
                )
            )
            continue
        receipts_by_workload[workload_id] = (index, receipt)

    source_workloads = source_payload.get("workloads", [])
    expected_workload_ids = {
        workload.get("workloadId")
        for workload in source_workloads
        if isinstance(workload, dict) and isinstance(workload.get("workloadId"), str)
    }
    for workload_id, (index, _receipt) in receipts_by_workload.items():
        if workload_id not in expected_workload_ids:
            failures.append(
                failure(
                    "extra_workload_receipt",
                    f"receipts[{index}].workloadId",
                    f"receipt references workload not present in source workload artifact: {workload_id}",
                )
            )

    for workload in source_workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("workloadId")
        if not isinstance(workload_id, str) or not workload_id:
            continue
        receipt_pair = receipts_by_workload.get(workload_id)
        if receipt_pair is None:
            failures.append(
                failure(
                    "missing_workload_receipt",
                    "receipts",
                    f"missing pipeline cache receipt for source workload {workload_id}",
                )
            )
            continue
        receipt_index, receipt = receipt_pair
        receipt_path = f"receipts[{receipt_index}]"
        shader_identity = workload.get("shaderIdentity", {})
        pipeline_cache = workload.get("pipelineCache", {})
        fallback_status = workload.get("fallbackStatus", {})
        if not isinstance(shader_identity, dict):
            shader_identity = {}
        if not isinstance(pipeline_cache, dict):
            pipeline_cache = {}
        if not isinstance(fallback_status, dict):
            fallback_status = {}

        source_fields = {
            "workloadKind": workload.get("workloadKind"),
            "shaderId": shader_identity.get("shaderId"),
            "sourceSha256": shader_identity.get("sourceSha256"),
            "irSha256": shader_identity.get("irSha256"),
            "backendOutputSha256": shader_identity.get("backendOutputSha256"),
            "cacheKey": pipeline_cache.get("cacheKey"),
            "cacheState": pipeline_cache.get("cacheState"),
            "pipelineCreationPath": pipeline_cache.get("pipelineCreationPath"),
            "fallbackApplied": fallback_status.get("fallbackApplied", False),
            "hiddenFallbackAllowed": False,
        }
        for field, expected in source_fields.items():
            add_mismatch(failures, receipt_path, field, expected, receipt.get(field))
        add_mismatch(
            failures,
            receipt_path,
            "creationStatus",
            creation_status_for(pipeline_cache.get("cacheState")),
            receipt.get("creationStatus"),
        )
        if receipt.get("reasonCode") != fallback_status.get("reasonCode"):
            failures.append(
                failure(
                    "receipt_workload_mismatch",
                    f"{receipt_path}.reasonCode",
                    f"reasonCode must match source workload fallbackStatus for {workload_id}",
                )
            )
    return failures


def check_receipts(
    payload: dict[str, Any],
    verify_workloads_root: Path | None = None,
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
    if payload.get("receiptStatus") != "pass":
        failure_codes = payload.get("failureCodes")
        if isinstance(failure_codes, list) and failure_codes:
            for index, item in enumerate(failure_codes):
                if not isinstance(item, dict):
                    continue
                failures.append(
                    failure(
                        str(item.get("code", "receipt_failure")),
                        str(item.get("path", f"failureCodes[{index}]")),
                        str(item.get("message", "pipeline cache receipt failure")),
                    )
                )
        else:
            failures.append(failure("receipt_status_not_pass", "receiptStatus", "receiptStatus must be pass"))

    receipts = payload.get("receipts", [])
    if not isinstance(receipts, list) or not receipts:
        failures.append(failure("missing_receipts", "receipts", "pipeline cache receipts must be non-empty"))
        return failures

    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            failures.append(failure("invalid_receipt", f"receipts[{index}]", "receipt must be object"))
            continue
        receipt_path = f"receipts[{index}]"
        for field in (
            "receiptId",
            "workloadId",
            "workloadKind",
            "shaderId",
            "sourceSha256",
            "irSha256",
            "backendOutputSha256",
            "cacheKey",
            "pipelineCreationPath",
        ):
            if not receipt.get(field):
                failures.append(failure("missing_cache_receipt_field", f"{receipt_path}.{field}", f"missing cache receipt field {field}"))
        cache_state = receipt.get("cacheState")
        creation_status = receipt.get("creationStatus")
        if cache_state == "hit" and creation_status != "reused":
            failures.append(failure("cache_creation_status_mismatch", f"{receipt_path}.creationStatus", "cache hit must use creationStatus=reused"))
        if cache_state in {"miss", "created"} and creation_status != "created":
            failures.append(failure("cache_creation_status_mismatch", f"{receipt_path}.creationStatus", "cache miss/created must use creationStatus=created"))
        if cache_state == "disabled" and creation_status != "skipped":
            failures.append(failure("cache_creation_status_mismatch", f"{receipt_path}.creationStatus", "disabled cache must use creationStatus=skipped"))
        if receipt.get("hiddenFallbackAllowed") is not False:
            failures.append(failure("hidden_fallback_allowed", f"{receipt_path}.hiddenFallbackAllowed", "hidden fallback must be false"))
        if receipt.get("fallbackApplied") is True and not receipt.get("reasonCode"):
            failures.append(failure("missing_fallback_reason", f"{receipt_path}.reasonCode", "applied fallback requires reasonCode"))
    if verify_workloads_root is not None:
        failures.extend(verify_source_workloads(payload, receipts, verify_workloads_root))
    return failures


def main() -> int:
    args = parse_args()
    verify_workloads_root = Path(args.verify_workloads_root).resolve() if args.verify_workloads_root else None
    runtime_identity_root = (
        Path(args.runtime_identity_root).resolve()
        if args.runtime_identity_root.strip()
        else None
    )
    failures = check_receipts(load_json(Path(args.receipts)), verify_workloads_root, runtime_identity_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_pipeline_cache_receipts_check",
        "receiptsPath": args.receipts,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser pipeline cache receipts")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser pipeline cache receipts")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
