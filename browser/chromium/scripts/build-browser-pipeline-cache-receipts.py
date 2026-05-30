#!/usr/bin/env python3
"""Build developer-visible browser pipeline cache receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", required=True, help="browser_local_ai_workloads JSON path.")
    parser.add_argument("--out", help="Write browser_pipeline_cache_receipts JSON to this path.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def failure(code: str, message: str, path: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "error",
        "source": "browser_pipeline_cache_receipts",
        "message": message,
        "path": path,
    }


def creation_status(cache_state: str) -> str:
    if cache_state == "hit":
        return "reused"
    if cache_state == "disabled":
        return "skipped"
    return "created"


def build_cache_receipts(workloads: dict[str, Any], source_workloads_path: str = "unknown") -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    receipts: list[dict[str, Any]] = []
    for index, workload in enumerate(workloads.get("workloads", [])):
        if not isinstance(workload, dict):
            continue
        workload_path = f"workloads[{index}]"
        pipeline_cache = workload.get("pipelineCache", {})
        shader_identity = workload.get("shaderIdentity", {})
        fallback_status = workload.get("fallbackStatus", {})

        required_pairs = [
            (workload, "workloadId", workload_path),
            (workload, "workloadKind", workload_path),
            (shader_identity, "shaderId", f"{workload_path}.shaderIdentity"),
            (shader_identity, "sourceSha256", f"{workload_path}.shaderIdentity"),
            (shader_identity, "irSha256", f"{workload_path}.shaderIdentity"),
            (shader_identity, "backendOutputSha256", f"{workload_path}.shaderIdentity"),
            (pipeline_cache, "cacheKey", f"{workload_path}.pipelineCache"),
            (pipeline_cache, "cacheState", f"{workload_path}.pipelineCache"),
            (pipeline_cache, "pipelineCreationPath", f"{workload_path}.pipelineCache"),
        ]
        missing = [
            (field, path)
            for container, field, path in required_pairs
            if not isinstance(container, dict) or not container.get(field)
        ]
        if missing:
            for field, path in missing:
                failures.append(
                    failure(
                        "missing_cache_receipt_field",
                        f"missing cache receipt field {field}",
                        f"{path}.{field}",
                    )
                )
            continue

        if not isinstance(fallback_status, dict) or fallback_status.get("hiddenFallbackAllowed") is not False:
            failures.append(
                failure(
                    "hidden_fallback_allowed",
                    "hidden fallback must be false",
                    f"{workload_path}.fallbackStatus.hiddenFallbackAllowed",
                )
            )
            continue
        if fallback_status.get("fallbackApplied") is True and not fallback_status.get("reasonCode"):
            failures.append(
                failure(
                    "missing_fallback_reason",
                    "applied fallback requires reasonCode",
                    f"{workload_path}.fallbackStatus.reasonCode",
                )
            )
            continue

        receipt: dict[str, Any] = {
            "receiptId": f"cache:{workload['workloadId']}",
            "workloadId": workload["workloadId"],
            "workloadKind": workload["workloadKind"],
            "shaderId": shader_identity["shaderId"],
            "sourceSha256": shader_identity["sourceSha256"],
            "irSha256": shader_identity["irSha256"],
            "backendOutputSha256": shader_identity["backendOutputSha256"],
            "cacheKey": pipeline_cache["cacheKey"],
            "cacheState": pipeline_cache["cacheState"],
            "pipelineCreationPath": pipeline_cache["pipelineCreationPath"],
            "creationStatus": creation_status(pipeline_cache["cacheState"]),
            "fallbackApplied": fallback_status.get("fallbackApplied", False),
            "hiddenFallbackAllowed": False,
        }
        if fallback_status.get("reasonCode"):
            receipt["reasonCode"] = fallback_status["reasonCode"]
        receipts.append(receipt)

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_pipeline_cache_receipts",
        "sourceWorkloadsPath": source_workloads_path,
        "sourceWorkloadSetId": workloads.get("workloadSetId", "unknown"),
        "runtimeIdentity": workloads.get(
            "runtimeIdentity",
            {
                "runtimeIdentityPath": "unknown",
                "selectedRuntime": "unknown",
                "fallbackApplied": False,
            },
        ),
        "receiptStatus": "fail" if failures else "pass",
        "receipts": [] if failures else receipts,
        "failureCodes": failures,
    }


def main() -> int:
    args = parse_args()
    workloads_path = Path(args.workloads)
    artifact = build_cache_receipts(load_json(workloads_path), repo_relative(workloads_path))
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 1 if artifact["receiptStatus"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
