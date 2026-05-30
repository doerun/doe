#!/usr/bin/env python3
"""Validate browser GPU scheduler probe coverage."""

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


REQUIRED_SURFACES = {
    "webgpu",
    "canvas",
    "video",
    "css_effects",
    "local_ai",
    "compositor_adjacent",
}
REQUIRED_PROBES = {
    "priority",
    "fairness",
    "frame_deadline",
    "origin_quota",
    "device_loss",
    "fallback_behavior",
}
EXPECTED_KIND = "browser_gpu_scheduler_probe"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, help="browser_gpu_scheduler_probe JSON path.")
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


def check_probe(
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
    work_classes = payload.get("workClasses", [])
    failures.extend(
        check_unique_ids(
            work_classes,
            field="workClassId",
            path="workClasses",
            code="duplicate_work_class_id",
            label="workClassId",
        )
    )
    work_class_ids = {
        item.get("workClassId")
        for item in work_classes
        if isinstance(item, dict)
    }
    surfaces = {
        item.get("surface")
        for item in work_classes
        if isinstance(item, dict)
    }
    for surface in sorted(REQUIRED_SURFACES - surfaces):
        failures.append(failure("missing_surface", "workClasses", f"missing surface {surface}"))

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
        item.get("probeKind")
        for item in probes
        if isinstance(item, dict)
    }
    for probe_kind in sorted(REQUIRED_PROBES - probe_kinds):
        failures.append(failure("missing_probe_kind", "probes", f"missing probe kind {probe_kind}"))

    for probe_index, probe in enumerate(probes):
        if not isinstance(probe, dict):
            continue
        for class_index, work_class_id in enumerate(probe.get("workClassIds", [])):
            if work_class_id not in work_class_ids:
                failures.append(
                    failure(
                        "unknown_work_class",
                        f"probes[{probe_index}].workClassIds[{class_index}]",
                        f"probe references unknown work class {work_class_id!r}",
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
    if not isinstance(privacy, dict) or privacy.get("originScoped") is not True or privacy.get("rawPageDataIncluded") is not False:
        failures.append(
            failure("unsafe_privacy_policy", "privacy", "scheduler probe must be origin-scoped and exclude raw page data")
        )

    return failures


def main() -> int:
    args = parse_args()
    runtime_identity_root = (
        Path(args.runtime_identity_root).resolve()
        if args.runtime_identity_root.strip()
        else None
    )
    failures = check_probe(load_json(Path(args.probe)), runtime_identity_root)
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_gpu_scheduler_check",
        "probePath": args.probe,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser GPU scheduler probe")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser GPU scheduler probe")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
