#!/usr/bin/env python3
"""Validate the CSL runtime fixture registry and referenced receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.lib.bench_utils import detect_repo_root, load_json_object
from native_compare_modules import contracts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="Repository root. Auto-detected when omitted.")
    parser.add_argument("--registry", default="config/csl-runtime-fixtures.json")
    parser.add_argument("--schema", default="config/csl-runtime-fixtures.schema.json")
    parser.add_argument(
        "--require-ready-receipts",
        action="store_true",
        help="For runtime_ready fixtures, require governed lane + simulator gates to pass.",
    )
    return parser.parse_args()


def resolve(root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def require_file(root: Path, raw_path: Any, label: str) -> list[str]:
    if not isinstance(raw_path, str) or not raw_path:
        return [f"{label}: missing path"]
    path = resolve(root, raw_path)
    if not path.is_file():
        return [f"{label}: missing file: {raw_path}"]
    return []


def validate_schema_payload(schema_path: Path, data_path: Path, label: str) -> list[str]:
    try:
        schema = load_json_object(schema_path)
        payload = load_json_object(data_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"{label}: parse failed: {exc}"]
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    return [f"{label}: {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in errors]


def validate_runtime_config(root: Path, raw_path: str, fixture_id: str, runtime_mode: str) -> list[str]:
    path = resolve(root, raw_path)
    try:
        payload = load_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"{fixture_id}: runtimeConfigPath parse failed: {exc}"]

    failures: list[str] = []
    mode = payload.get("mode")
    if mode != runtime_mode:
        failures.append(f"{fixture_id}: runtime-config mode={mode!r}, registry runtimeMode={runtime_mode!r}")
    if runtime_mode == "sdk-runtime-command":
        command = payload.get("command")
        if not isinstance(command, list) or not command:
            failures.append(f"{fixture_id}: sdk-runtime-command config must declare a non-empty command array")
        else:
            command_text = " ".join(str(item) for item in command)
            if "{compile_output_dir}" not in command_text:
                failures.append(f"{fixture_id}: runtime command missing {{compile_output_dir}} substitution")
            if "{trace_path}" not in command_text:
                failures.append(f"{fixture_id}: runtime command missing {{trace_path}} substitution")
    return failures


def validate_ready_report(root: Path, raw_path: str, fixture_id: str) -> list[str]:
    report_path = resolve(root, raw_path)
    report_schema = root / "config" / "csl-governed-lane-report.schema.json"
    failures = contracts.validate_artifact(report_path, contracts.load_schema(report_schema))
    if failures:
        return [f"{fixture_id}: governed report: {item}" for item in failures]
    report = contracts.load_json(report_path)
    if report.get("laneStatus") != "ready":
        failures.append(f"{fixture_id}: laneStatus={report.get('laneStatus')!r}, expected 'ready'")
    if report.get("compile", {}).get("status") != "succeeded":
        failures.append(f"{fixture_id}: compile.status={report.get('compile', {}).get('status')!r}")
    if report.get("run", {}).get("status") != "succeeded":
        failures.append(f"{fixture_id}: run.status={report.get('run', {}).get('status')!r}")
    return failures


def validate_fixture(root: Path, fixture: dict[str, Any], require_ready_receipts: bool) -> list[str]:
    fixture_id = str(fixture.get("id", "<unknown>"))
    evidence = fixture.get("evidence")
    if not isinstance(evidence, dict):
        return [f"{fixture_id}: evidence must be an object"]

    failures: list[str] = []
    for field in ("sourceWgslPath", "simulatorPlanPath", "hostPlanPath", "runtimeConfigPath"):
        failures.extend(require_file(root, evidence.get(field), f"{fixture_id}: evidence.{field}"))

    if isinstance(evidence.get("runnerPath"), str):
        failures.extend(require_file(root, evidence.get("runnerPath"), f"{fixture_id}: evidence.runnerPath"))

    sim_plan = evidence.get("simulatorPlanPath")
    if isinstance(sim_plan, str):
        failures.extend(
            validate_schema_payload(
                root / "config" / "doe-wgsl-simulator-plan.schema.json",
                resolve(root, sim_plan),
                f"{fixture_id}: simulator plan",
            )
        )

    host_plan = evidence.get("hostPlanPath")
    if isinstance(host_plan, str):
        failures.extend(
            validate_schema_payload(
                root / "config" / "doe-wgsl-host-plan.schema.json",
                resolve(root, host_plan),
                f"{fixture_id}: host plan",
            )
        )

    runtime_config = evidence.get("runtimeConfigPath")
    runtime_mode = fixture.get("runtimeMode")
    if isinstance(runtime_config, str) and isinstance(runtime_mode, str):
        failures.extend(validate_runtime_config(root, runtime_config, fixture_id, runtime_mode))

    governed_status = fixture.get("governedStatus")
    report_path = evidence.get("governedLaneReportPath")
    if governed_status == "runtime_ready":
        if not isinstance(report_path, str):
            failures.append(f"{fixture_id}: runtime_ready fixture missing governedLaneReportPath")
        elif require_ready_receipts:
            failures.extend(validate_ready_report(root, report_path, fixture_id))

    return failures


def main() -> int:
    args = parse_args()
    try:
        root = detect_repo_root(args.root)
        registry_path = resolve(root, args.registry)
        schema_path = resolve(root, args.schema)
        registry = load_json_object(registry_path)
        schema = load_json_object(schema_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: csl runtime fixture gate: {exc}")
        return 1

    failures = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(registry),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]

    fixtures = registry.get("fixtures")
    if isinstance(fixtures, list):
        seen: set[str] = set()
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            fixture_id = str(fixture.get("id", ""))
            if fixture_id in seen:
                failures.append(f"{fixture_id}: duplicate fixture id")
            seen.add(fixture_id)
            failures.extend(validate_fixture(root, fixture, args.require_ready_receipts))

    if failures:
        print("FAIL: csl runtime fixture gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"PASS: csl runtime fixture gate ({len(registry.get('fixtures', []))} fixtures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
