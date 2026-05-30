#!/usr/bin/env python3
"""Validate browser CTS subset artifact coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


REQUIRED_BUCKETS = {
    "adapter",
    "buffer",
    "command_buffer",
    "queue",
    "validation",
    "shader_execution",
}
EXPECTED_KIND = "browser_cts_subset"
EXPECTED_SCHEMA_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", required=True, help="browser_cts_subset JSON path.")
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


def check_path(path_text: Any, path: str, label: str) -> list[dict[str, str]]:
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


def check_subset(payload: dict[str, Any]) -> list[dict[str, str]]:
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
    browser_artifacts = payload.get("browserArtifacts", {})
    if not isinstance(browser_artifacts, dict) or not browser_artifacts.get("dawnArtifactPath"):
        failures.append(failure("missing_browser_lane", "browserArtifacts.dawnArtifactPath", "missing Dawn CTS artifact path"))
    elif isinstance(browser_artifacts, dict):
        failures.extend(
            check_path(
                browser_artifacts.get("dawnArtifactPath"),
                "browserArtifacts.dawnArtifactPath",
                "Dawn CTS artifact path",
            )
        )
    if not isinstance(browser_artifacts, dict) or not browser_artifacts.get("forcedDoeArtifactPath"):
        failures.append(
            failure("missing_browser_lane", "browserArtifacts.forcedDoeArtifactPath", "missing forced-Doe CTS artifact path")
        )
    elif isinstance(browser_artifacts, dict):
        failures.extend(
            check_path(
                browser_artifacts.get("forcedDoeArtifactPath"),
                "browserArtifacts.forcedDoeArtifactPath",
                "forced-Doe CTS artifact path",
            )
        )

    rows = payload.get("rows", [])
    buckets = {
        row.get("bucket")
        for row in rows
        if isinstance(row, dict)
    }
    for bucket in sorted(REQUIRED_BUCKETS - buckets):
        failures.append(failure("missing_cts_bucket", "rows", f"missing CTS bucket {bucket}"))

    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_path = f"rows[{row_index}]"
        failures.extend(check_path(row.get("artifactPath"), f"{row_path}.artifactPath", "CTS row artifact path"))
        if row.get("hiddenFallbackAllowed") is not False:
            failures.append(
                failure("hidden_fallback_allowed", f"{row_path}.hiddenFallbackAllowed", "hidden fallback must be false")
            )
        if row.get("parityStatus") in {"diagnostic", "mismatch"} and not row.get("reasonCode"):
            failures.append(
                failure("missing_reason_code", f"{row_path}.reasonCode", "diagnostic or mismatch row requires reasonCode")
            )
        if row.get("parityStatus") == "match" and row.get("dawnStatus") != row.get("forcedDoeStatus"):
            failures.append(
                failure(
                    "cts_parity_status_mismatch",
                    f"{row_path}.parityStatus",
                    "match parity requires identical Dawn and forced-Doe statuses",
                )
            )

    fallback_policy = payload.get("fallbackPolicy", {})
    if not isinstance(fallback_policy, dict) or fallback_policy.get("hiddenFallbackAllowed") is not False:
        failures.append(
            failure("hidden_fallback_allowed", "fallbackPolicy.hiddenFallbackAllowed", "hidden fallback must be false")
        )

    return failures


def main() -> int:
    args = parse_args()
    failures = check_subset(load_json(Path(args.subset)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_cts_subset_check",
        "subsetPath": args.subset,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser CTS subset")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser CTS subset")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
