#!/usr/bin/env python3
"""Validate browser shader-link artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_SHADER_FIELDS = (
    "shaderId",
    "sourceLanguage",
    "sourcePath",
    "sourceSha256",
    "irPath",
    "irSha256",
    "loweringReceiptPath",
    "loweringReceiptRowId",
    "backendTarget",
    "backendOutputPath",
    "backendOutputSha256",
)
EXPECTED_KIND = "browser_shader_links"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--links", required=True, help="browser_shader_links JSON path.")
    parser.add_argument(
        "--verify-flight-recorder-root",
        default="",
        help="Optional repository root for verifying linked browser flight-recorder shader rows.",
    )
    parser.add_argument(
        "--verify-lowering-root",
        default="",
        help="Optional repository root for verifying linked WGSL lowering receipts.",
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


def resolve_repo_path(path_text: str, root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return root / path


def add_mismatch(
    failures: list[dict[str, str]],
    path: str,
    field: str,
    expected: Any,
    actual: Any,
) -> None:
    if actual != expected:
        failures.append(
            failure(
                "flight_recorder_shader_mismatch",
                f"{path}.{field}",
                f"expected {field}={expected!r} from flight recorder, got {actual!r}",
            )
        )


def check_flight_recorder(
    payload: dict[str, Any],
    shaders: list[Any],
    root: Path,
) -> list[dict[str, str]]:
    source_path = payload.get("sourceFlightRecorderPath")
    if not isinstance(source_path, str) or not source_path:
        return [failure("missing_flight_recorder_path", "sourceFlightRecorderPath", "sourceFlightRecorderPath is required")]
    if Path(source_path).is_absolute() or ".." in Path(source_path).parts:
        return [
            failure(
                "unsafe_flight_recorder_path",
                "sourceFlightRecorderPath",
                "sourceFlightRecorderPath must be repo-relative",
            )
        ]
    resolved = resolve_repo_path(source_path, root)
    if not resolved.is_file():
        return [
            failure(
                "missing_flight_recorder",
                "sourceFlightRecorderPath",
                f"missing browser flight recorder: {source_path}",
            )
        ]
    try:
        flight_recorder = load_json(resolved)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [
            failure(
                "invalid_flight_recorder",
                "sourceFlightRecorderPath",
                f"failed to load flight recorder: {exc}",
            )
        ]

    failures: list[dict[str, str]] = []
    if flight_recorder.get("artifactKind") != "browser_gpu_flight_recorder":
        failures.append(
            failure(
                "invalid_flight_recorder",
                "sourceFlightRecorderPath",
                "sourceFlightRecorderPath must point to browser_gpu_flight_recorder",
            )
        )
    if payload.get("captureId") != flight_recorder.get("captureId"):
        failures.append(
            failure(
                "flight_recorder_capture_mismatch",
                "captureId",
                "shader links captureId must match source flight recorder captureId",
            )
        )
    runtime_identity = flight_recorder.get("runtimeIdentity", {})
    expected_runtime = runtime_identity.get("selectedRuntime") if isinstance(runtime_identity, dict) else None
    if payload.get("selectedRuntime") != expected_runtime:
        failures.append(
            failure(
                "flight_recorder_runtime_mismatch",
                "selectedRuntime",
                "shader links selectedRuntime must match source flight recorder runtimeIdentity",
            )
        )

    links_by_shader: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, shader in enumerate(shaders):
        if not isinstance(shader, dict):
            continue
        shader_id = shader.get("shaderId")
        if not isinstance(shader_id, str) or not shader_id:
            continue
        if shader_id in links_by_shader:
            failures.append(
                failure(
                    "duplicate_shader_link",
                    f"shaders[{index}].shaderId",
                    f"duplicate shader link for {shader_id}",
                )
            )
            continue
        links_by_shader[shader_id] = (index, shader)

    source_shaders = flight_recorder.get("shaders", [])
    expected_shader_ids = {
        shader.get("shaderId")
        for shader in source_shaders
        if isinstance(shader, dict) and isinstance(shader.get("shaderId"), str)
    }
    for shader_id, (index, _shader) in links_by_shader.items():
        if shader_id not in expected_shader_ids:
            failures.append(
                failure(
                    "extra_shader_link",
                    f"shaders[{index}].shaderId",
                    f"shader link references shader not present in source flight recorder: {shader_id}",
                )
            )

    for source_shader in source_shaders:
        if not isinstance(source_shader, dict):
            continue
        shader_id = source_shader.get("shaderId")
        if not isinstance(shader_id, str) or not shader_id:
            continue
        link_pair = links_by_shader.get(shader_id)
        if link_pair is None:
            failures.append(
                failure(
                    "missing_shader_link",
                    "shaders",
                    f"missing shader link for source flight-recorder shader {shader_id}",
                )
            )
            continue
        link_index, link = link_pair
        link_path = f"shaders[{link_index}]"
        for field in REQUIRED_SHADER_FIELDS:
            add_mismatch(failures, link_path, field, source_shader.get(field), link.get(field))
        if link.get("diagnosticStatus") != source_shader.get("diagnosticStatus"):
            add_mismatch(
                failures,
                link_path,
                "diagnosticStatus",
                source_shader.get("diagnosticStatus"),
                link.get("diagnosticStatus"),
            )
    return failures


def check_lowering_receipt(
    shader: dict[str, Any],
    shader_path: str,
    root: Path,
) -> list[dict[str, str]]:
    receipt_path = shader.get("loweringReceiptPath")
    row_id = shader.get("loweringReceiptRowId")
    if not isinstance(receipt_path, str) or not receipt_path:
        return []
    if not isinstance(row_id, str) or not row_id:
        return []
    if Path(receipt_path).is_absolute() or ".." in Path(receipt_path).parts:
        return [
            failure(
                "unsafe_lowering_receipt_path",
                f"{shader_path}.loweringReceiptPath",
                "loweringReceiptPath must be repo-relative",
            )
        ]

    resolved = root / receipt_path
    if not resolved.is_file():
        return [
            failure(
                "missing_lowering_receipt",
                f"{shader_path}.loweringReceiptPath",
                f"missing lowering receipt: {receipt_path}",
            )
        ]
    try:
        receipt = load_json(resolved)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [
            failure(
                "invalid_lowering_receipt",
                f"{shader_path}.loweringReceiptPath",
                f"failed to load lowering receipt: {exc}",
            )
        ]

    if receipt.get("artifactKind") != "wgsl_lowering_link_receipt":
        return [
            failure(
                "invalid_lowering_receipt",
                f"{shader_path}.loweringReceiptPath",
                "lowering receipt must have artifactKind=wgsl_lowering_link_receipt",
            )
        ]

    row = None
    for candidate in receipt.get("rows", []):
        if not isinstance(candidate, dict):
            continue
        if candidate.get("shaderId") == row_id or candidate.get("manifestShaderId") == row_id:
            row = candidate
            break
    if row is None:
        return [
            failure(
                "lowering_receipt_row_missing",
                f"{shader_path}.loweringReceiptRowId",
                f"lowering receipt does not contain row {row_id}",
            )
        ]

    comparisons = (
        ("sourcePath", "sourcePath"),
        ("sourceSha256", "sourceSha256"),
        ("backendTarget", "backendTarget"),
        ("irSha256", "doeIrSha256"),
        ("backendOutputSha256", "doeBackendOutputSha256"),
    )
    failures: list[dict[str, str]] = []
    for shader_field, row_field in comparisons:
        if shader.get(shader_field) != row.get(row_field):
            failures.append(
                failure(
                    "lowering_receipt_hash_mismatch",
                    f"{shader_path}.{shader_field}",
                    f"{shader_field} does not match lowering receipt row {row_id}",
                )
            )
    return failures


def check_shader_links(
    payload: dict[str, Any],
    *,
    verify_flight_recorder_root: Path | None = None,
    verify_lowering_root: Path | None = None,
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
        failures.append(failure("invalid_artifact_kind", "artifactKind", f"artifactKind must be {EXPECTED_KIND}"))
    if payload.get("linkStatus") != "pass":
        failure_codes = payload.get("failureCodes")
        if isinstance(failure_codes, list) and failure_codes:
            for index, item in enumerate(failure_codes):
                if not isinstance(item, dict):
                    continue
                failures.append(
                    failure(
                        str(item.get("code", "shader_link_failure")),
                        str(item.get("path", f"failureCodes[{index}]")),
                        str(item.get("message", "shader link failure")),
                    )
                )
        else:
            failures.append(failure("link_status_not_pass", "linkStatus", "linkStatus must be pass"))

    shaders = payload.get("shaders", [])
    if not isinstance(shaders, list) or not shaders:
        failures.append(failure("missing_shader_links", "shaders", "shader links must be non-empty"))
        return failures

    for index, shader in enumerate(shaders):
        shader_path = f"shaders[{index}]"
        if not isinstance(shader, dict):
            failures.append(failure("invalid_shader_link", shader_path, "shader link must be object"))
            continue
        for field in REQUIRED_SHADER_FIELDS:
            if not shader.get(field):
                failures.append(failure("missing_shader_link_field", f"{shader_path}.{field}", f"missing shader link field {field}"))
        for field in ("sourceSha256", "irSha256", "backendOutputSha256"):
            digest = shader.get(field)
            if isinstance(digest, str) and digest and not SHA256_RE.fullmatch(digest):
                failures.append(failure("invalid_shader_link_hash", f"{shader_path}.{field}", f"{field} must be sha256 hex"))
    if verify_flight_recorder_root is not None:
        failures.extend(check_flight_recorder(payload, shaders, verify_flight_recorder_root))
    for index, shader in enumerate(shaders):
        shader_path = f"shaders[{index}]"
        if not isinstance(shader, dict):
            continue
        if verify_lowering_root is not None:
            failures.extend(check_lowering_receipt(shader, shader_path, verify_lowering_root))
    return failures


def main() -> int:
    args = parse_args()
    verify_lowering_root = (
        Path(args.verify_lowering_root).resolve()
        if args.verify_lowering_root.strip()
        else None
    )
    verify_flight_recorder_root = (
        Path(args.verify_flight_recorder_root).resolve()
        if args.verify_flight_recorder_root.strip()
        else None
    )
    failures = check_shader_links(
        load_json(Path(args.links)),
        verify_flight_recorder_root=verify_flight_recorder_root,
        verify_lowering_root=verify_lowering_root,
    )
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_shader_links_check",
        "linksPath": args.links,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser shader links")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser shader links")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
