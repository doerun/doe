#!/usr/bin/env python3
"""Build browser media-path probe artifacts from Playwright smoke output."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="Playwright smoke report JSON path.")
    parser.add_argument("--out", help="Write browser_media_path_probe JSON to this path.")
    parser.add_argument("--mode", default="doe", choices=("dawn", "doe"), help="Mode result to extract.")
    parser.add_argument("--probe-set-id", default="browser-media-path-smoke")
    parser.add_argument(
        "--capture-policy",
        default="config/browser-capture-policy.json",
        help="Browser capture policy governing media probe artifacts.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def digest(value: Any) -> dict[str, str]:
    return {
        "algorithm": "sha256",
        "value": stable_hash(value),
    }


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


def smoke_status(smoke_entry: dict[str, Any], unsupported_needles: tuple[str, ...] = ()) -> tuple[str, str]:
    if smoke_entry.get("pass") is True:
        return "pass", ""
    error = str(smoke_entry.get("error") or "")
    lowered = error.lower()
    if any(needle in lowered for needle in unsupported_needles):
        return "unsupported", "browser_capability_unavailable"
    return "fail", "browser_probe_failed"


def build_probe(
    report: dict[str, Any],
    report_path: Path,
    mode: str,
    probe_set_id: str,
    capture_policy_path: Path = Path("config/browser-capture-policy.json"),
) -> dict[str, Any]:
    mode_result = find_mode_result(report, mode)
    smoke = mode_result.get("smoke", {})
    if not isinstance(smoke, dict):
        smoke = {}

    copy_external = smoke.get("copyExternalImageToTexture", {})
    if not isinstance(copy_external, dict):
        copy_external = {}
    import_external = smoke.get("importExternalTexture", {})
    if not isinstance(import_external, dict):
        import_external = {}

    report_ref = repo_relative(report_path)
    runtime_identity = {
        "runtimeIdentityPath": report_ref,
        "selectedRuntime": selected_runtime(mode_result),
        "fallbackApplied": fallback_applied(mode_result),
    }
    media_sources = [
        {
            "mediaSourceId": "media:video-frame",
            "sourceKind": "video_frame",
            "sourcePath": f"{report_ref}#modeResults[{mode}].smoke.importExternalTexture.source",
            "sourceDigest": digest({
                "kind": "video_frame",
                "centerRgba": import_external.get("centerRgba"),
                "error": import_external.get("error"),
            }),
        },
        {
            "mediaSourceId": "media:image-bitmap",
            "sourceKind": "image_bitmap",
            "sourcePath": f"{report_ref}#modeResults[{mode}].smoke.copyExternalImageToTexture.source",
            "sourceDigest": digest({
                "kind": "image_bitmap",
                "sourceType": copy_external.get("sourceType"),
                "attempts": copy_external.get("attempts", []),
            }),
        },
        {
            "mediaSourceId": "media:shared-texture",
            "sourceKind": "shared_texture",
            "sourcePath": f"{report_ref}#modeResults[{mode}].smoke.sharedTextureImport",
            "sourceDigest": digest({
                "kind": "shared_texture",
                "status": "not_reported_by_smoke",
            }),
        },
    ]

    copy_status, copy_reason = smoke_status(copy_external, ("is not a function", "unavailable", "unsupported"))
    import_status, import_reason = smoke_status(import_external, ("videoframe is unavailable", "is not a function", "unsupported"))
    probes = [
        {
            "probeId": "probe:gpu-external-texture",
            "probeKind": "gpu_external_texture",
            "mediaSourceIds": ["media:video-frame"],
            "status": import_status,
            "outputDigest": digest({
                "probeKind": "gpu_external_texture",
                "centerRgba": import_external.get("centerRgba"),
                "error": import_external.get("error"),
            }),
            "fallbackApplied": False,
            "hiddenFallbackAllowed": False,
            "evidencePath": f"{report_ref}#modeResults[{mode}].smoke.importExternalTexture",
        },
        {
            "probeId": "probe:copy-external-image",
            "probeKind": "copy_external_image_to_texture",
            "mediaSourceIds": ["media:image-bitmap"],
            "status": copy_status,
            "outputDigest": digest({
                "probeKind": "copy_external_image_to_texture",
                "topLeftRgba": copy_external.get("topLeftRgba"),
                "sourceType": copy_external.get("sourceType"),
                "attempts": copy_external.get("attempts", []),
                "error": copy_external.get("error"),
            }),
            "fallbackApplied": False,
            "hiddenFallbackAllowed": False,
            "evidencePath": f"{report_ref}#modeResults[{mode}].smoke.copyExternalImageToTexture",
        },
        {
            "probeId": "probe:shared-texture-import",
            "probeKind": "shared_texture_import",
            "mediaSourceIds": ["media:shared-texture"],
            "status": "unsupported",
            "outputDigest": digest({
                "probeKind": "shared_texture_import",
                "status": "not_reported_by_smoke",
            }),
            "fallbackApplied": False,
            "hiddenFallbackAllowed": False,
            "reasonCode": "not_reported_by_smoke",
            "evidencePath": f"{report_ref}#modeResults[{mode}].smoke",
        },
    ]
    if import_reason:
        probes[0]["reasonCode"] = import_reason
    if copy_reason:
        probes[1]["reasonCode"] = copy_reason

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_media_path_probe",
        "probeSetId": probe_set_id,
        "runtimeIdentity": runtime_identity,
        "capturePolicy": {
            "capturePolicyPath": repo_relative(capture_policy_path),
            "surfaceId": "media_path_probe",
        },
        "mediaSources": media_sources,
        "probes": probes,
        "fallbackPolicy": {
            "hiddenFallbackAllowed": False,
            "reasonCodeRequired": True,
        },
        "privacy": {
            "originScoped": True,
            "rawMediaIncluded": False,
        },
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    artifact = build_probe(
        load_json(report_path),
        report_path,
        args.mode,
        args.probe_set_id,
        Path(args.capture_policy),
    )
    encoded = json.dumps(artifact, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
