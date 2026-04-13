#!/usr/bin/env python3
"""Run the native Doe ORT plugin EP session smoke as a bench executor."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_KIND = "vendor-native-benchmark-scenario"
SCENARIO_SCHEMA_VERSION = 1
BENCHMARK_LANE = "native-ort-doe-ep-smoke"
EXECUTION_BACKEND = "ort_native_doe_ep"
EXECUTION_PROVIDER = "doe"
EXECUTION_PROVIDER_NAME = "Doe ORT plugin EP"


def _default_plugin_path() -> Path:
    if sys.platform == "darwin":
        filename = "libonnxruntime_doe_ep.dylib"
    elif sys.platform == "win32":
        filename = "onnxruntime_doe_ep.dll"
    else:
        filename = "libonnxruntime_doe_ep.so"
    return REPO_ROOT / "runtime" / "zig" / "zig-out" / "lib" / filename


def _default_smoke_binary_path() -> Path:
    executable = "doe-ort-ep-session-smoke.exe" if sys.platform == "win32" else "doe-ort-ep-session-smoke"
    return REPO_ROOT / "runtime" / "zig" / "zig-out" / "bin" / executable


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _resolve_from_scenario_dir(base_dir: Path, value: str, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    raw = value.strip()
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _resolve_optional_path(base_dir: Path, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return str(_resolve_from_scenario_dir(base_dir, value, "scenario path"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--trace-meta", required=True)
    parser.add_argument("--trace-jsonl", required=True)
    parser.add_argument("--workload", required=True)
    return parser.parse_args(argv)


def load_scenario(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError(f"native ORT EP scenario {path} must be a JSON array with exactly one entry")
    scenario = payload[0]
    if not isinstance(scenario, dict):
        raise ValueError(f"native ORT EP scenario {path} must contain an object entry")
    if scenario.get("kind") != SCENARIO_KIND:
        raise ValueError(f"scenario.kind must be {SCENARIO_KIND}")
    if scenario.get("schemaVersion") != SCENARIO_SCHEMA_VERSION:
        raise ValueError(f"scenario.schemaVersion must be {SCENARIO_SCHEMA_VERSION}")

    scenario_dir = path.resolve().parent
    smoke_binary_path = (
        _resolve_from_scenario_dir(scenario_dir, scenario["smokeBinaryPath"], "scenario.smokeBinaryPath")
        if isinstance(scenario.get("smokeBinaryPath"), str) and scenario["smokeBinaryPath"].strip()
        else _default_smoke_binary_path()
    )
    plugin_path = (
        _resolve_from_scenario_dir(scenario_dir, scenario["pluginPath"], "scenario.pluginPath")
        if isinstance(scenario.get("pluginPath"), str) and scenario["pluginPath"].strip()
        else _default_plugin_path()
    )
    case_name = scenario.get("caseName")
    if not isinstance(case_name, str) or not case_name.strip():
        raise ValueError("scenario.caseName must be a non-empty string")
    scenario_id = scenario.get("scenarioId")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise ValueError("scenario.scenarioId must be a non-empty string")

    return {
        "scenarioPath": str(path.resolve()),
        "scenarioId": scenario_id.strip(),
        "caseName": case_name.strip(),
        "smokeBinaryPath": str(smoke_binary_path),
        "pluginPath": str(plugin_path),
        "ortLibPath": _resolve_optional_path(scenario_dir, scenario.get("ortLibPath")),
        "registrationName": str(scenario.get("registrationName", "DoeExecutionProvider")).strip() or "DoeExecutionProvider",
        "notes": str(scenario.get("notes", "")).strip(),
    }


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    _ensure_parent(path)
    body = "\n".join(json.dumps(row) for row in rows)
    path.write_text(body + ("\n" if body else ""), encoding="utf-8")


def _select_case(report: dict[str, Any], case_name: str) -> dict[str, Any]:
    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("session smoke report missing cases array")
    for entry in raw_cases:
        if isinstance(entry, dict) and entry.get("caseName") == case_name:
            return entry
    raise ValueError(f"session smoke report did not include requested case {case_name!r}")


def _adapter_info_from_report(report: dict[str, Any]) -> dict[str, Any]:
    selected_ep = report.get("selectedEp", {})
    if not isinstance(selected_ep, dict):
        selected_ep = {}
    return {
        "vendor": str(selected_ep.get("vendor", "")).strip(),
        "device": str(selected_ep.get("name", "")).strip(),
        "architecture": "",
        "description": str(selected_ep.get("hardwareDeviceType", "")).strip(),
    }


def _build_success_trace_meta(
    *,
    workload_id: str,
    scenario: dict[str, Any],
    process_wall_ms: float,
    report: dict[str, Any],
    case_result: dict[str, Any],
) -> dict[str, Any]:
    plugin_debug = report.get("pluginDebug", {})
    if not isinstance(plugin_debug, dict):
        plugin_debug = {}
    final_counters = plugin_debug.get("finalCounters", {})
    if not isinstance(final_counters, dict):
        final_counters = {}
    return {
        "traceMetaVersion": 1,
        "runtimeHost": "native",
        "benchmarkLane": BENCHMARK_LANE,
        "workloadId": workload_id,
        "scenarioId": scenario["scenarioId"],
        "executionBackend": EXECUTION_BACKEND,
        "executionLabel": "Native ONNX Runtime Doe plugin EP session smoke",
        "executionProvider": EXECUTION_PROVIDER,
        "executionProviderName": EXECUTION_PROVIDER_NAME,
        "processWallMs": process_wall_ms,
        "timingMs": process_wall_ms,
        "timingSource": "wall-time",
        "adapterInfo": _adapter_info_from_report(report),
        "executionRowCount": 1,
        "executionSuccessCount": 1,
        "executionErrorCount": 0,
        "executionSkippedCount": 0,
        "executionUnsupportedCount": 0,
        "nativeOrtCaseName": scenario["caseName"],
        "nativeOrtPluginPath": report.get("pluginPath", scenario["pluginPath"]),
        "nativeOrtLibraryPath": report.get("ortLibraryPath", scenario["ortLibPath"]),
        "nativeOrtRuntimeVersion": report.get("ortRuntimeVersion", ""),
        "nativeOrtApiVersionRequested": report.get("ortApiVersionRequested", 0),
        "nativeOrtCase": case_result,
        "pluginDebug": {
            "symbolsLoaded": plugin_debug.get("symbolsLoaded", False),
            "finalCounters": final_counters,
        },
        "smokeOperations": report.get("operations", {}),
    }


def _build_failure_trace_meta(
    *,
    workload_id: str,
    scenario: dict[str, Any],
    process_wall_ms: float,
    report: dict[str, Any],
    error_message: str,
) -> dict[str, Any]:
    return {
        "traceMetaVersion": 1,
        "runtimeHost": "native",
        "benchmarkLane": BENCHMARK_LANE,
        "workloadId": workload_id,
        "scenarioId": scenario["scenarioId"],
        "executionBackend": EXECUTION_BACKEND,
        "executionLabel": "Native ONNX Runtime Doe plugin EP session smoke",
        "executionProvider": EXECUTION_PROVIDER,
        "executionProviderName": EXECUTION_PROVIDER_NAME,
        "processWallMs": process_wall_ms,
        "timingMs": process_wall_ms,
        "timingSource": "wall-time",
        "adapterInfo": _adapter_info_from_report(report),
        "executionRowCount": 0,
        "executionSuccessCount": 0,
        "executionErrorCount": 1,
        "executionSkippedCount": 0,
        "executionUnsupportedCount": 0,
        "nativeOrtCaseName": scenario["caseName"],
        "nativeOrtPluginPath": report.get("pluginPath", scenario["pluginPath"]),
        "nativeOrtLibraryPath": report.get("ortLibraryPath", scenario["ortLibPath"]),
        "nativeOrtRuntimeVersion": report.get("ortRuntimeVersion", ""),
        "nativeOrtApiVersionRequested": report.get("ortApiVersionRequested", 0),
        "terminalFailureCaptured": True,
        "failureMessage": error_message,
        "pluginDebug": report.get("pluginDebug", {}),
        "smokeOperations": report.get("operations", {}),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scenario_path = Path(args.scenario)
    trace_meta_path = Path(args.trace_meta)
    trace_jsonl_path = Path(args.trace_jsonl)
    scenario = load_scenario(scenario_path)

    command = [
        scenario["smokeBinaryPath"],
        "--plugin-path",
        scenario["pluginPath"],
        "--registration-name",
        scenario["registrationName"],
        "--case",
        scenario["caseName"],
    ]
    if scenario["ortLibPath"]:
        command.extend(["--ort-lib-path", scenario["ortLibPath"]])

    with tempfile.TemporaryDirectory(prefix="doe-native-ort-ep-bench-") as tmpdir:
        report_path = Path(tmpdir) / "session-smoke.json"
        command.extend(["--output", str(report_path)])
        start = time.perf_counter()
        proc = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        process_wall_ms = (time.perf_counter() - start) * 1000.0

        report: dict[str, Any]
        if report_path.exists():
            report = _json_object(report_path)
        else:
            report = {}
            if proc.stdout.strip():
                try:
                    parsed = json.loads(proc.stdout)
                    if isinstance(parsed, dict):
                        report = parsed
                except json.JSONDecodeError:
                    report = {}

    error_message = ""
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        failure_reason = str(report.get("failureReason", "")).strip() if isinstance(report, dict) else ""
        error_message = failure_reason or stderr or f"native ORT EP smoke exited with rc={proc.returncode}"
    else:
        try:
            case_result = _select_case(report, scenario["caseName"])
            if report.get("success") is not True:
                error_message = str(report.get("failureReason", "")).strip() or "native ORT EP smoke reported failure"
            elif case_result.get("success") is not True:
                error_message = str(case_result.get("failureReason", "")).strip() or "requested native ORT EP case failed"
        except Exception as exc:
            error_message = str(exc)

    if error_message:
        trace_meta = _build_failure_trace_meta(
            workload_id=args.workload,
            scenario=scenario,
            process_wall_ms=process_wall_ms,
            report=report,
            error_message=error_message,
        )
        rows = [
            {
                "traceFormat": "vendor-native-benchmark-v1",
                "status": "error",
                "executionBackend": EXECUTION_BACKEND,
                "workloadId": args.workload,
                "scenarioId": scenario["scenarioId"],
                "caseName": scenario["caseName"],
                "processWallMs": process_wall_ms,
                "errorMessage": error_message,
            }
        ]
        _write_json(trace_meta_path, trace_meta)
        _write_ndjson(trace_jsonl_path, rows)
        print(error_message, file=sys.stderr)
        return 1

    case_result = _select_case(report, scenario["caseName"])
    trace_meta = _build_success_trace_meta(
        workload_id=args.workload,
        scenario=scenario,
        process_wall_ms=process_wall_ms,
        report=report,
        case_result=case_result,
    )
    rows = [
        {
            "traceFormat": "vendor-native-benchmark-v1",
            "status": "success",
            "executionBackend": EXECUTION_BACKEND,
            "workloadId": args.workload,
            "scenarioId": scenario["scenarioId"],
            "caseName": scenario["caseName"],
            "processWallMs": process_wall_ms,
            "routedThroughDoe": case_result.get("routedThroughDoe", False),
            "outputsMatch": case_result.get("outputsMatch", False),
            "expectedClaimedNodes": case_result.get("expectedClaimedNodes", 0),
            "debugCountersDelta": case_result.get("debugCountersDelta", {}),
            "expectedOutput": case_result.get("expectedOutput", []),
            "actualOutput": case_result.get("actualOutput", []),
        }
    ]
    _write_json(trace_meta_path, trace_meta)
    _write_ndjson(trace_jsonl_path, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
