#!/usr/bin/env python3
"""Blocking schema/correctness/trace gate for promoted modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema
import output_paths


PROMOTED_MODULES = {
    "fawn_2d_sdf_renderer": {
        "schema": "config/sdf-renderer.schema.json",
        "policy": "config/sdf-renderer.policy.json",
        "cases": [
            {
                "id": "happy_path",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-2d-sdf-renderer.request.json",
                "expectEquals": {
                    "qualityStats.fallbackCount": 0,
                    "renderStats.passCount": 1,
                },
            },
            {
                "id": "unsupported_sample_count",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-2d-sdf-renderer.edge.unsupported-sample-count.request.json",
                "expectEquals": {
                    "qualityStats.fallbackCount": 1,
                    "qualityStats.fallbackReasonHistogram.required_capability_missing": 1,
                    "renderStats.passCount": 0,
                },
            },
        ],
    },
    "fawn_compute_services": {
        "schema": "config/compute-services.schema.json",
        "policy": "config/compute-services.policy.json",
        "cases": [
            {
                "id": "happy_path",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-compute-services.request.json",
                "expectEquals": {
                    "serviceResult.status": "ok",
                    "failureDetails.code": "none",
                },
            },
            {
                "id": "input_contract_invalid",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-compute-services.edge.input-contract-invalid.request.json",
                "expectEquals": {
                    "serviceResult.status": "fallback",
                    "failureDetails.code": "input_contract_invalid",
                },
            },
        ],
    },
    "fawn_effects_pipeline": {
        "schema": "config/effects-pipeline.schema.json",
        "policy": "config/effects-pipeline.policy.json",
        "cases": [
            {
                "id": "happy_path",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-effects-pipeline.request.json",
                "expectEquals": {
                    "fallbackStats.fallbackCount": 0,
                    "executionStats.passCount": 2,
                },
            },
            {
                "id": "unsupported_op",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-effects-pipeline.edge.unsupported-op.request.json",
                "expectEquals": {
                    "fallbackStats.fallbackCount": 1,
                    "fallbackStats.fallbackReasonHistogram.effect_op_unsupported": 1,
                    "executionStats.passCount": 0,
                },
            },
        ],
    },
    "fawn_path_engine": {
        "schema": "config/path-engine.schema.json",
        "policy": "config/path-engine.policy.json",
        "cases": [
            {
                "id": "happy_path",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-path-engine.request.json",
                "expectEquals": {
                    "fallbackStats.fallbackCount": 0,
                    "rasterStats.passCount": 1,
                },
            },
            {
                "id": "dash_pattern_unsupported",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-path-engine.edge.dash-pattern.request.json",
                "expectEquals": {
                    "fallbackStats.fallbackCount": 1,
                    "fallbackStats.fallbackReasonHistogram.dash_pattern_unsupported": 1,
                    "rasterStats.passCount": 0,
                },
            },
        ],
    },
    "fawn_resource_scheduler": {
        "schema": "config/resource-scheduler.schema.json",
        "policy": "config/resource-scheduler.policy.json",
        "cases": [
            {
                "id": "happy_path",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-resource-scheduler.request.json",
                "expectEquals": {
                    "fallbackStats.fallbackCount": 0,
                    "submitStats.cadenceModeUsed": "deferred",
                },
            },
            {
                "id": "invalid_cadence",
                "fixture": "nursery/fawn-browser/module-incubation/fixtures/fawn-resource-scheduler.edge.invalid-cadence.request.json",
                "expectEquals": {
                    "fallbackStats.fallbackCount": 1,
                    "fallbackStats.fallbackReasonHistogram.cadence_policy_invalid": 1,
                    "submitStats.cadenceModeUsed": "per_draw",
                },
            },
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="Repository root. Auto-detected when omitted.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    parser.add_argument("--report", default="", help="Optional JSON report path.")
    return parser.parse_args()


def detect_repo_root(explicit_root: str) -> Path:
    if explicit_root:
        return Path(explicit_root).resolve()
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(schema_path: Path, payload: dict[str, Any]) -> list[str]:
    schema = load_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    return [
        f"{'.'.join(str(part) for part in err.absolute_path) or '<root>'}: {err.message}"
        for err in errors
    ]


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def recompute_result_hash(payload: dict[str, Any]) -> str:
    result_core = {key: value for key, value in payload.items() if key != "traceLink"}
    return stable_hash(result_core)


def build_runner(root: Path) -> Path:
    subprocess.run(
        ["zig", "build", "dropin", "module-core-runner"],
        cwd=root / "zig",
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return root / "zig/zig-out/bin/module-core-runner"


def run_module(runner_path: Path, root: Path, module_id: str, fixture_path: Path, policy_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            str(runner_path),
            "--module",
            module_id,
            "--request",
            str(fixture_path),
            "--policy",
            str(policy_path),
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def deep_get(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted_path)
        current = current[part]
    return current


def main() -> int:
    args = parse_args()
    root = detect_repo_root(args.root)
    failures: list[str] = []
    module_rows: list[dict[str, Any]] = []
    runner_path = build_runner(root)

    for module_id, paths in PROMOTED_MODULES.items():
        schema_path = root / paths["schema"]
        policy_path = root / paths["policy"]
        policy_payload = load_json(policy_path)
        module_failures: list[str] = []
        case_rows: list[dict[str, Any]] = []
        schema_failures = validate_payload(schema_path, policy_payload)

        for case in paths["cases"]:
            case_id = case["id"]
            fixture_path = root / case["fixture"]
            fixture_payload = load_json(fixture_path)

            case_schema_failures = list(schema_failures)
            case_schema_failures.extend(validate_payload(schema_path, fixture_payload))

            first = run_module(runner_path, root, module_id, fixture_path, policy_path)
            second = run_module(runner_path, root, module_id, fixture_path, policy_path)

            result_failures = []
            result_failures.extend(validate_payload(schema_path, first))
            result_failures.extend(validate_payload(schema_path, second))
            if first != second:
                result_failures.append("determinism failure: repeated executions produced different payloads")

            trace = first.get("traceLink", {})
            request_hash = trace.get("requestHash")
            policy_hash = trace.get("policyHash")
            result_hash = trace.get("resultHash")
            expected_request_hash = stable_hash(fixture_payload)
            expected_policy_hash = stable_hash(policy_payload)
            if not request_hash:
                result_failures.append("traceLink.requestHash missing")
            elif request_hash != expected_request_hash:
                result_failures.append("traceLink.requestHash does not match request fixture hash")
            if not policy_hash:
                result_failures.append("traceLink.policyHash missing")
            elif policy_hash != expected_policy_hash:
                result_failures.append("traceLink.policyHash does not match policy hash")
            if not result_hash:
                result_failures.append("traceLink.resultHash missing")
            elif result_hash != recompute_result_hash(first):
                result_failures.append("traceLink.resultHash does not match recomputed result payload hash")

            for dotted_path, expected_value in case.get("expectEquals", {}).items():
                try:
                    actual_value = deep_get(first, dotted_path)
                except KeyError:
                    result_failures.append(f"missing expected path: {dotted_path}")
                    continue
                if actual_value != expected_value:
                    result_failures.append(
                        f"{dotted_path} expected {expected_value!r}, got {actual_value!r}"
                    )

            if case_schema_failures or result_failures:
                for failure in case_schema_failures:
                    module_failures.append(f"{case_id} schema: {failure}")
                for failure in result_failures:
                    module_failures.append(f"{case_id} gate: {failure}")

            case_rows.append(
                {
                    "caseId": case_id,
                    "fixture": str(fixture_path.relative_to(root)),
                    "schemaOk": not case_schema_failures,
                    "correctnessOk": first == second,
                    "traceOk": not any("traceLink" in failure or "resultHash" in failure for failure in result_failures),
                    "resultHash": first.get("traceLink", {}).get("resultHash", ""),
                }
            )

        if module_failures:
            for failure in module_failures:
                failures.append(f"{module_id}: {failure}")

        module_rows.append(
            {
                "moduleId": module_id,
                "schemaOk": not any(not case_row["schemaOk"] for case_row in case_rows),
                "correctnessOk": all(case_row["correctnessOk"] for case_row in case_rows),
                "traceOk": all(case_row["traceOk"] for case_row in case_rows),
                "caseCount": len(case_rows),
                "cases": case_rows,
            }
        )

    payload = {
        "ok": not failures,
        "moduleCount": len(PROMOTED_MODULES),
        "modules": module_rows,
        "failures": failures,
    }

    report_path: Path | None = None
    if args.report:
        report_path = (root / args.report).resolve() if not Path(args.report).is_absolute() else Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        output_paths.write_run_manifest_for_outputs(
            [report_path],
            {
                "runType": "module-gate",
                "fullRun": True,
                "claimGateRan": False,
                "status": "pass" if payload["ok"] else "fail",
                "moduleCount": len(PROMOTED_MODULES),
            },
        )

    if args.emit_json or True:
        print(json.dumps(payload, indent=2))

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
