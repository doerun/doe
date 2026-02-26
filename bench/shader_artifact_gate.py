#!/usr/bin/env python3
"""Validate shader artifact manifests referenced by trace metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_dawn_vs_doe_modules import shader_contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/dawn-vs-doe.json")
    parser.add_argument("--schema", default="config/shader-artifact.schema.json")
    parser.add_argument(
        "--require-manifest",
        action="store_true",
        help="Fail when shader manifest is missing for successful left-side samples.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    schema = shader_contract.load_schema(Path(args.schema))

    shader_commands = {
        "dispatch",
        "kernel_dispatch",
        "render_draw",
        "async_diagnostics",
    }

    failures: list[str] = []
    validated = 0

    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        print("FAIL: invalid report workloads")
        return 1

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = str(workload.get("id", "unknown"))
        left = workload.get("left")
        if not isinstance(left, dict):
            continue
        samples = left.get("commandSamples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            if sample.get("returnCode") != 0:
                continue
            trace_meta = sample.get("traceMeta")
            if not isinstance(trace_meta, dict):
                continue

            command = str(trace_meta.get("command", "")).strip()
            if command and command not in shader_commands:
                continue

            manifest_path_raw = trace_meta.get("shaderArtifactManifestPath")
            if not isinstance(manifest_path_raw, str) or not manifest_path_raw:
                if args.require_manifest:
                    failures.append(f"{workload_id}: missing shaderArtifactManifestPath")
                continue
            manifest_path = Path(manifest_path_raw)
            manifest_errors = shader_contract.validate_manifest(manifest_path, schema)
            if manifest_errors:
                for err in manifest_errors:
                    failures.append(f"{workload_id}: {err}")
            else:
                validated += 1

    if failures:
        print("FAIL: shader artifact gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print(f"PASS: shader artifact gate (validated={validated})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
