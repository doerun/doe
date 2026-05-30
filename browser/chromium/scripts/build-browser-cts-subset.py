#!/usr/bin/env python3
"""Build browser CTS subset diagnostics from paired Playwright smoke output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROWS = [
    ("webgpu:api,operation,adapter,requestAdapter:*", "adapter"),
    ("webgpu:api,operation,buffers,map:*", "buffer"),
    ("webgpu:api,operation,command_buffer,basic:*", "command_buffer"),
    ("webgpu:api,operation,queue,writeBuffer:*", "queue"),
    ("webgpu:api,validation,error_scope:*", "validation"),
    ("webgpu:shader,execution,expression,call,builtin,textureDimensions:*", "shader_execution"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Paired Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_cts_subset JSON to this path.")
    parser.add_argument("--subset-id", default="browser-cts-subset-smoke")
    parser.add_argument("--cts-source", default="browser/chromium/scripts/webgpu-playwright-smoke.mjs")
    parser.add_argument("--cts-revision", default="smoke-derived")
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


def mode_results(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for row in report.get("modeResults", []):
        if isinstance(row, dict) and row.get("mode") in {"dawn", "doe"}:
            results[str(row["mode"])] = row
    return results


def runtime_disqualified(mode_result: dict[str, Any] | None) -> bool:
    if not isinstance(mode_result, dict):
        return False
    selection = mode_result.get("runtimeSelection")
    return isinstance(selection, dict) and (
        selection.get("fallbackApplied") is True
        or selection.get("hiddenFallbackAllowed") is True
    )


def smoke_entry(mode_result: dict[str, Any] | None, *path: str) -> Any:
    current: Any = mode_result
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def pass_bool(mode_result: dict[str, Any] | None, *path: str) -> bool | None:
    entry = smoke_entry(mode_result, *path)
    if isinstance(entry, dict) and isinstance(entry.get("pass"), bool):
        return bool(entry["pass"])
    return None


def bucket_status(mode_result: dict[str, Any] | None, bucket: str) -> str:
    if not isinstance(mode_result, dict):
        return "not_run"
    if runtime_disqualified(mode_result):
        return "fail"
    if bucket == "adapter":
        if mode_result.get("webgpuAvailable") is True and mode_result.get("adapterAvailable") is True:
            return "pass"
        if mode_result.get("webgpuAvailable") is False or mode_result.get("adapterAvailable") is False:
            return "fail"
        return "not_run"
    if bucket in {"buffer", "queue", "command_buffer", "shader_execution"}:
        passed = pass_bool(mode_result, "smoke", "computeIncrement")
        if passed is None:
            return "not_run"
        return "pass" if passed else "fail"
    if bucket == "validation":
        passed = pass_bool(mode_result, "smoke", "recovery", "validationError")
        if passed is None:
            return "not_run"
        return "pass" if passed else "fail"
    return "not_run"


def parity_status(dawn_status: str, doe_status: str) -> str:
    if "not_run" in {dawn_status, doe_status}:
        return "diagnostic"
    if dawn_status == doe_status:
        return "match"
    return "mismatch"


def reason_code(dawn_status: str, doe_status: str, parity: str) -> str:
    if parity == "mismatch":
        return "dawn_forced_doe_status_mismatch"
    if parity == "diagnostic":
        return "smoke_bucket_not_fully_exercised"
    return ""


def build_subset(
    report: dict[str, Any],
    report_path: Path,
    subset_id: str,
    cts_source: str,
    cts_revision: str,
) -> dict[str, Any]:
    results = mode_results(report)
    report_ref = repo_relative(report_path)
    rows: list[dict[str, Any]] = []
    for query, bucket in ROWS:
        dawn_status = bucket_status(results.get("dawn"), bucket)
        doe_status = bucket_status(results.get("doe"), bucket)
        parity = parity_status(dawn_status, doe_status)
        row: dict[str, Any] = {
            "query": query,
            "bucket": bucket,
            "dawnStatus": dawn_status,
            "forcedDoeStatus": doe_status,
            "parityStatus": parity,
            "hiddenFallbackAllowed": False,
            "artifactPath": f"{report_ref}#ctsBucket.{bucket}",
        }
        reason = reason_code(dawn_status, doe_status, parity)
        if reason:
            row["reasonCode"] = reason
        rows.append(row)

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_cts_subset",
        "subsetId": subset_id,
        "ctsSource": cts_source,
        "ctsRevision": cts_revision,
        "browserArtifacts": {
            "dawnArtifactPath": f"{report_ref}#modeResults[dawn]",
            "forcedDoeArtifactPath": f"{report_ref}#modeResults[doe]",
        },
        "rows": rows,
        "fallbackPolicy": {
            "hiddenFallbackAllowed": False,
            "reasonCodeRequired": True,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_subset(
        load_json(report_path),
        report_path,
        args.subset_id,
        args.cts_source,
        args.cts_revision,
    )
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
