#!/usr/bin/env python3
"""Validate browser external texture and media-path probe coverage."""

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


REQUIRED_PROBES = {
    "gpu_external_texture",
    "copy_external_image_to_texture",
    "shared_texture_import",
}
EXPECTED_KIND = "browser_media_path_probe"
EXPECTED_SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[3]
MEDIA_PATH_SURFACE_ID = "media_path_probe"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, help="browser_media_path_probe JSON path.")
    parser.add_argument(
        "--capture-policy-root",
        default=str(REPO_ROOT),
        help="Repository root used to resolve the probe capturePolicy.capturePolicyPath.",
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


def check_artifact_path(path_text: Any, path: str, label: str) -> list[dict[str, str]]:
    if not isinstance(path_text, str) or not path_text:
        return []
    if safe_repo_path(path_text):
        return []
    return [
        failure(
            "unsafe_artifact_path",
            path,
            f"{label} must be repo-relative",
        )
    ]


def resolve_policy_path(root: Path, path_text: str) -> Path | None:
    if not safe_repo_path(path_text):
        return None
    resolved = root.joinpath(*PurePosixPath(path_text).parts).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def check_capture_policy(payload: dict[str, Any], root: Path) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    capture_policy = payload.get("capturePolicy")
    if not isinstance(capture_policy, dict):
        return [
            failure(
                "missing_capture_policy",
                "capturePolicy",
                "media probes must reference browser capture policy",
            )
        ]

    if capture_policy.get("surfaceId") != MEDIA_PATH_SURFACE_ID:
        failures.append(
            failure(
                "wrong_capture_surface",
                "capturePolicy.surfaceId",
                "media probes must reference media_path_probe capture surface",
            )
        )

    policy_path_text = capture_policy.get("capturePolicyPath")
    if not isinstance(policy_path_text, str) or not policy_path_text:
        failures.append(
            failure(
                "missing_capture_policy_path",
                "capturePolicy.capturePolicyPath",
                "media probes must name a browser capture policy path",
            )
        )
        return failures

    policy_path = resolve_policy_path(root, policy_path_text)
    if policy_path is None:
        failures.append(
            failure(
                "unsafe_capture_policy_path",
                "capturePolicy.capturePolicyPath",
                "capture policy path must be repo-relative",
            )
        )
        return failures
    if not policy_path.is_file():
        failures.append(
            failure(
                "missing_capture_policy_file",
                "capturePolicy.capturePolicyPath",
                f"capture policy file not found: {policy_path_text}",
            )
        )
        return failures

    try:
        policy = load_json(policy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        failures.append(
            failure(
                "invalid_capture_policy",
                "capturePolicy.capturePolicyPath",
                f"capture policy is not valid JSON object: {exc}",
            )
        )
        return failures

    if policy.get("artifactKind") != "browser_capture_policy":
        failures.append(
            failure(
                "invalid_capture_policy_kind",
                "capturePolicy.capturePolicyPath",
                "capture policy artifactKind must be browser_capture_policy",
            )
        )

    surfaces = [row for row in policy.get("surfaces", []) if isinstance(row, dict)]
    surface = next((row for row in surfaces if row.get("surfaceId") == MEDIA_PATH_SURFACE_ID), None)
    if surface is None:
        failures.append(
            failure(
                "missing_capture_surface",
                "capturePolicy.surfaceId",
                "browser capture policy must define media_path_probe surface",
            )
        )
        return failures

    expected = {
        "originScoped": True,
        "permissionGate": "secure_context_devtools_opt_in",
        "rawPageDataPolicy": "hash",
        "artifactDataPolicy": "hashes_and_redacted_metadata",
        "replayAllowed": False,
        "developerVisible": True,
    }
    for field, value in expected.items():
        if surface.get(field) != value:
            failures.append(
                failure(
                    "unsafe_capture_surface",
                    f"capturePolicy.surface.{field}",
                    f"media_path_probe capture surface requires {field}={value!r}",
                )
            )
    if not surface.get("reasonCode"):
        failures.append(
            failure(
                "missing_capture_surface_reason",
                "capturePolicy.surface.reasonCode",
                "non-replay media probe surface requires reasonCode",
            )
        )

    return failures


def check_probe(
    payload: dict[str, Any],
    capture_policy_root: Path | None = None,
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
    failures.extend(check_capture_policy(payload, capture_policy_root or REPO_ROOT))
    media_sources = payload.get("mediaSources", [])
    media_source_ids = {
        source.get("mediaSourceId")
        for source in media_sources
        if isinstance(source, dict)
    }
    for source_index, source in enumerate(media_sources):
        if not isinstance(source, dict):
            continue
        failures.extend(
            check_artifact_path(
                source.get("sourcePath"),
                f"mediaSources[{source_index}].sourcePath",
                "media source path",
            )
        )

    probes = payload.get("probes", [])
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
        failures.extend(
            check_artifact_path(
                probe.get("evidencePath"),
                f"probes[{probe_index}].evidencePath",
                "media probe evidence path",
            )
        )
        for source_index, media_source_id in enumerate(probe.get("mediaSourceIds", [])):
            if media_source_id not in media_source_ids:
                failures.append(
                    failure(
                        "unknown_media_source",
                        f"probes[{probe_index}].mediaSourceIds[{source_index}]",
                        f"probe references unknown media source {media_source_id!r}",
                    )
                )
        if probe.get("hiddenFallbackAllowed") is not False:
            failures.append(
                failure(
                    "hidden_fallback_allowed",
                    f"probes[{probe_index}].hiddenFallbackAllowed",
                    "hidden fallback must be false",
                )
            )
        if (probe.get("fallbackApplied") is True or probe.get("status") == "unsupported") and not probe.get("reasonCode"):
            failures.append(
                failure(
                    "missing_fallback_reason",
                    f"probes[{probe_index}].reasonCode",
                    "fallback or unsupported media probe requires reasonCode",
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
        or privacy.get("rawMediaIncluded") is not False
    ):
        failures.append(
            failure(
                "unsafe_privacy_policy",
                "privacy",
                "media probes must be origin-scoped and exclude raw media",
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
    failures = check_probe(
        load_json(Path(args.probe)),
        Path(args.capture_policy_root),
        runtime_identity_root,
    )
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_media_path_probe_check",
        "probePath": args.probe,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser media path probe")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser media path probe")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
