#!/usr/bin/env python3
"""Validate shader artifact manifests referenced by trace metadata."""

from __future__ import annotations

import argparse
import json
import subprocess
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
    parser.add_argument(
        "--spirv-val",
        default="",
        help="Optional spirv-val executable used to validate SPIR-V artifacts.",
    )
    parser.add_argument(
        "--require-spirv-validation",
        action="store_true",
        help="Fail when SPIR-V artifacts are present but no validator is configured.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def is_spirv_artifact_stage(stage: dict[str, Any]) -> bool:
    stage_name = stage.get("stage")
    if not isinstance(stage_name, str):
        return False
    if "spirv" not in stage_name:
        return False
    return not stage_name.endswith("validate")


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    schema = shader_contract.load_schema(Path(args.schema))

    failures: list[str] = []
    validated = 0
    spirv_validated = 0

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
                manifest = load_json(manifest_path)
                spirv_failures, spirv_count = validate_spirv_artifacts(
                    manifest,
                    args.spirv_val.strip(),
                    args.require_spirv_validation,
                )
                failures.extend(f"{workload_id}: {item}" for item in spirv_failures)
                spirv_validated += spirv_count

    if failures:
        print("FAIL: shader artifact gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print(
        f"PASS: shader artifact gate (validated={validated}, spirvValidated={spirv_validated})"
    )
    return 0


def validate_spirv_artifacts(
    manifest: dict[str, Any],
    spirv_val: str,
    require_spirv_validation: bool,
) -> tuple[list[str], int]:
    stages = manifest.get("stages")
    if not isinstance(stages, list):
        return [], 0

    failures: list[str] = []
    validated = 0
    saw_spirv_output = isinstance(manifest.get("spirvSha256"), str)
    saw_spirv_stage = False
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if not is_spirv_artifact_stage(stage):
            continue
        saw_spirv_stage = True
        artifact_path = stage.get("artifactPath")
        if not isinstance(artifact_path, str) or not artifact_path:
            if require_spirv_validation:
                failures.append("SPIR-V stage missing artifactPath for validation")
            continue
        if not spirv_val:
            if require_spirv_validation:
                failures.append("SPIR-V stage present but --spirv-val not provided")
            continue
        completed = subprocess.run(
            [spirv_val, artifact_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "spirv-val failed"
            failures.append(f"spirv-val failed for {artifact_path}: {stderr}")
            continue
        validated += 1
    if require_spirv_validation and saw_spirv_output and not saw_spirv_stage:
        failures.append("SPIR-V artifact present but manifest has no SPIR-V artifact stage")
    return failures, validated


if __name__ == "__main__":
    raise SystemExit(main())
