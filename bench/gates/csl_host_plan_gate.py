#!/usr/bin/env python3
"""Validate DOE WGSL host-plan artifacts referenced by trace metadata."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)


import argparse
import json
from pathlib import Path
from typing import Any

from native_compare_modules import host_plan_contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="bench/out/dawn-vs-doe.json")
    parser.add_argument("--schema", default="config/doe-wgsl-host-plan.schema.json")
    parser.add_argument(
        "--require-host-plan-artifact",
        action="store_true",
        help="Fail when successful trace samples do not carry hostPlanArtifactPath.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def resolve_relative_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    report = load_json(report_path)
    schema = host_plan_contract.load_schema(Path(args.schema))

    failures: list[str] = []
    validated = 0
    hash_validated = 0

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

            artifact_path_raw = trace_meta.get("hostPlanArtifactPath")
            artifact_hash_raw = trace_meta.get("hostPlanArtifactHash")
            has_path = isinstance(artifact_path_raw, str) and bool(artifact_path_raw)
            has_hash = isinstance(artifact_hash_raw, str) and bool(artifact_hash_raw)

            if has_path != has_hash:
                failures.append(
                    f"{workload_id}: hostPlanArtifactPath and hostPlanArtifactHash must be present together"
                )
                continue

            if not has_path:
                if args.require_host_plan_artifact:
                    failures.append(f"{workload_id}: missing hostPlanArtifactPath")
                continue

            artifact_path = resolve_relative_path(report_path.parent, artifact_path_raw)
            errors = host_plan_contract.validate_artifact(
                artifact_path,
                schema,
                expected_hash=artifact_hash_raw,
            )
            if errors:
                failures.extend(f"{workload_id}: {err}" for err in errors)
                continue

            validated += 1
            hash_validated += 1

    if failures:
        print("FAIL: csl host plan gate")
        for item in failures:
            print(f"  {item}")
        return 1

    print(
        f"PASS: csl host plan gate (validated={validated}, hashValidated={hash_validated})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
