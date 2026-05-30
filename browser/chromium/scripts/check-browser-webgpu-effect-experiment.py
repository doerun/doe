#!/usr/bin/env python3
"""Validate browser WebGPU effect experiment boundaries."""

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


REQUIRED_PROBES = {
    "output_hash",
    "semantics_boundary",
    "fallback_behavior",
    "frame_timing",
    "security_policy",
}
EXPECTED_KIND = "browser_webgpu_effect_experiment"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True, help="browser_webgpu_effect_experiment JSON path.")
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


def check_experiment(
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
    surfaces = payload.get("surfaces", [])
    failures.extend(
        check_unique_ids(
            surfaces,
            field="surfaceId",
            path="surfaces",
            code="duplicate_surface_id",
            label="surfaceId",
        )
    )
    surface_ids = {
        surface.get("surfaceId")
        for surface in surfaces
        if isinstance(surface, dict)
    }

    for surface_index, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            continue
        base_path = f"surfaces[{surface_index}]"
        if surface.get("webgpuBacked") is not True:
            failures.append(
                failure("surface_not_webgpu_backed", f"{base_path}.webgpuBacked", "effect surface must be WebGPU-backed")
            )
        if surface.get("doeBoundary") != "visual_effect_only":
            failures.append(
                failure("invalid_doe_boundary", f"{base_path}.doeBoundary", "Doe boundary must stay visual_effect_only")
            )
        for owner_field in ("layoutOwner", "accessibilityOwner", "securityOwner"):
            if surface.get(owner_field) != "browser":
                failures.append(
                    failure(
                        "browser_semantics_escaped",
                        f"{base_path}.{owner_field}",
                        f"{owner_field} must remain browser-owned",
                    )
                )

    pipelines = payload.get("pipelines", [])
    failures.extend(
        check_unique_ids(
            pipelines,
            field="pipelineId",
            path="pipelines",
            code="duplicate_pipeline_id",
            label="pipelineId",
        )
    )
    for pipeline_index, pipeline in enumerate(pipelines):
        if not isinstance(pipeline, dict):
            continue
        for surface_index, surface_id in enumerate(pipeline.get("surfaceIds", [])):
            if surface_id not in surface_ids:
                failures.append(
                    failure(
                        "unknown_pipeline_surface",
                        f"pipelines[{pipeline_index}].surfaceIds[{surface_index}]",
                        f"pipeline references unknown surface {surface_id!r}",
                    )
                )

    probes = payload.get("probes", [])
    failures.extend(
        check_unique_ids(
            probes,
            field="probeId",
            path="probes",
            code="duplicate_probe_id",
            label="probeId",
        )
    )
    probe_kinds = {
        probe.get("probeKind")
        for probe in probes
        if isinstance(probe, dict)
    }
    for probe_kind in sorted(REQUIRED_PROBES - probe_kinds):
        failures.append(failure("missing_probe_kind", "probes", f"missing probe kind {probe_kind}"))

    for probe_index, probe in enumerate(probes):
        if not isinstance(probe, dict):
            continue
        for surface_index, surface_id in enumerate(probe.get("surfaceIds", [])):
            if surface_id not in surface_ids:
                failures.append(
                    failure(
                        "unknown_probe_surface",
                        f"probes[{probe_index}].surfaceIds[{surface_index}]",
                        f"probe references unknown surface {surface_id!r}",
                    )
                )
        if probe.get("probeKind") == "fallback_behavior" and not probe.get("reasonCode"):
            failures.append(
                failure(
                    "missing_fallback_reason",
                    f"probes[{probe_index}].reasonCode",
                    "fallback behavior probe requires reasonCode",
                )
            )

    fallback_policy = payload.get("fallbackPolicy", {})
    if not isinstance(fallback_policy, dict) or fallback_policy.get("hiddenFallbackAllowed") is not False:
        failures.append(
            failure("hidden_fallback_allowed", "fallbackPolicy.hiddenFallbackAllowed", "hidden fallback must be false")
        )

    privacy = payload.get("privacy", {})
    if (
        not isinstance(privacy, dict)
        or privacy.get("originScoped") is not True
        or privacy.get("rawDomIncluded") is not False
        or privacy.get("rawPageDataIncluded") is not False
    ):
        failures.append(
            failure(
                "unsafe_privacy_policy",
                "privacy",
                "effect experiments must be origin-scoped and exclude raw DOM/page data",
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
    failures = check_experiment(load_json(Path(args.experiment)), runtime_identity_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_webgpu_effect_experiment_check",
        "experimentPath": args.experiment,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser WebGPU effect experiment")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser WebGPU effect experiment")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
