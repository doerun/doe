#!/usr/bin/env python3
"""Build developer-visible shader links from a browser flight-recorder artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIRED_SHADER_FIELDS = [
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
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flight-recorder", required=True, help="browser_gpu_flight_recorder JSON path.")
    parser.add_argument("--out", required=True, help="browser_shader_links JSON output path.")
    parser.add_argument("--allow-fail", action="store_true", help="Write failed artifact and exit 0.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def failure(code: str, path: str, message: str, severity: str = "error") -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "source": "browser_shader_links",
        "message": message,
        "path": path,
    }


def build_shader_links(payload: dict[str, Any], source_path: str) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    if payload.get("artifactKind") != "browser_gpu_flight_recorder":
        failures.append(
            failure(
                "invalid_flight_recorder",
                "artifactKind",
                "artifactKind must be browser_gpu_flight_recorder",
                "fatal",
            )
        )

    links: list[dict[str, Any]] = []
    for index, shader in enumerate(payload.get("shaders", [])):
        if not isinstance(shader, dict):
            failures.append(
                failure("missing_shader_anchor", f"shaders[{index}]", "shader row must be an object")
            )
            continue
        missing = [field for field in REQUIRED_SHADER_FIELDS if not shader.get(field)]
        if missing:
            failures.append(
                failure(
                    "missing_shader_anchor",
                    f"shaders[{index}]",
                    f"shader row missing anchors: {', '.join(missing)}",
                )
            )
            continue
        links.append({field: shader[field] for field in REQUIRED_SHADER_FIELDS})
        if shader.get("diagnosticStatus"):
            links[-1]["diagnosticStatus"] = shader["diagnosticStatus"]

    if not links:
        failures.append(
            failure("empty_shader_links", "shaders", "no complete shader links were found", "fatal")
        )

    return {
        "schemaVersion": 1,
        "artifactKind": "browser_shader_links",
        "captureId": str(payload.get("captureId", "")),
        "sourceFlightRecorderPath": source_path,
        "selectedRuntime": str(payload.get("runtimeIdentity", {}).get("selectedRuntime", "unknown")),
        "linkStatus": "fail" if failures else "pass",
        "shaders": links,
        "failureCodes": failures,
    }


def main() -> int:
    args = parse_args()
    source_path = Path(args.flight_recorder)
    if not source_path.is_absolute():
        source_path = (Path.cwd() / source_path).resolve()
    try:
        artifact = build_shader_links(load_json(source_path), display_path(source_path))
    except Exception as exc:
        artifact = {
            "schemaVersion": 1,
            "artifactKind": "browser_shader_links",
            "captureId": "",
            "sourceFlightRecorderPath": str(source_path),
            "selectedRuntime": "unknown",
            "linkStatus": "fail",
            "shaders": [],
            "failureCodes": [
                failure("invalid_flight_recorder", "flightRecorder", str(exc), "fatal")
            ],
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    if artifact["linkStatus"] == "pass":
        print(f"PASS: wrote browser shader links: {out_path}")
        return 0
    print(f"FAIL: wrote browser shader links: {out_path}")
    for item in artifact["failureCodes"]:
        print(f"- {item['code']}: {item['path']}: {item['message']}")
    return 0 if args.allow_fail else 1


if __name__ == "__main__":
    sys.exit(main())
