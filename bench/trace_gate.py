#!/usr/bin/env python3
"""
Release hard-gate for trace replay validity.

Validates every successful trace artifact in a dawn-vs-doe comparison report
with the replay checker.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPLAY_SCRIPT = Path(__file__).resolve().parents[1] / "trace" / "replay.py"
COMPARE_SCRIPT = Path(__file__).resolve().parents[1] / "trace" / "compare_dispatch_traces.py"
DOE_MODULE_PREFIX = "doe-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default="bench/out/dawn-vs-doe.json",
        help="Comparison report produced by compare_dawn_vs_doe.py",
    )
    parser.add_argument(
        "--semantic-parity-mode",
        choices=["off", "auto", "required"],
        default="auto",
        help=(
            "Semantic parity check mode for left/right trace pairs. "
            "off: skip parity checks, auto: compare only when both sides are doe runtime traces, "
            "required: fail when no semantic-eligible pairs are found."
        ),
    )
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fail(message: str) -> None:
    print(f"FAIL: {message}")


def run_replay_check(meta_path: Path, trace_jsonl: Path) -> tuple[bool, str]:
    cmd = [sys.executable, str(REPLAY_SCRIPT), "--trace-meta", str(meta_path), "--trace-jsonl", str(trace_jsonl)]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode == 0:
        return True, result.stdout.strip()
    return (
        False,
        (result.stdout or result.stderr).strip(),
    )


def run_semantic_parity_check(left_jsonl: Path, right_jsonl: Path) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(COMPARE_SCRIPT),
        "--left",
        str(left_jsonl),
        "--right",
        str(right_jsonl),
    ]
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode == 0:
        return True, result.stdout.strip()
    return (
        False,
        (result.stdout or result.stderr).strip(),
    )


def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def sample_trace_meta(sample: dict[str, Any]) -> dict[str, Any] | None:
    inline = sample.get("traceMeta")
    if isinstance(inline, dict):
        return inline

    trace_meta_path = sample.get("traceMetaPath")
    if not isinstance(trace_meta_path, str) or not trace_meta_path:
        return None
    path = Path(trace_meta_path)
    if not path.exists():
        return None
    return load_json_file(path)


def sample_module_name(sample: dict[str, Any]) -> str:
    meta = sample_trace_meta(sample)
    if not isinstance(meta, dict):
        return ""
    module_name = meta.get("module")
    if isinstance(module_name, str):
        return module_name
    return ""


def sample_trace_path(sample: dict[str, Any]) -> Path | None:
    trace_jsonl = sample.get("traceJsonlPath")
    if not isinstance(trace_jsonl, str) or not trace_jsonl:
        return None
    return Path(trace_jsonl)


def sample_return_code(sample: dict[str, Any]) -> int | None:
    return_code = sample.get("returnCode")
    if isinstance(return_code, int):
        return return_code
    return None


def semantic_pair_eligible(left_sample: dict[str, Any], right_sample: dict[str, Any]) -> tuple[bool, str]:
    left_module = sample_module_name(left_sample)
    right_module = sample_module_name(right_sample)
    if not left_module or not right_module:
        return False, "missing trace meta module"
    if not left_module.startswith(DOE_MODULE_PREFIX) or not right_module.startswith(DOE_MODULE_PREFIX):
        return False, f"non-doe-runtime modules left={left_module or 'unknown'} right={right_module or 'unknown'}"

    left_trace = sample_trace_path(left_sample)
    right_trace = sample_trace_path(right_sample)
    if left_trace is None or right_trace is None:
        return False, "missing trace jsonl path"
    if not left_trace.exists() or not right_trace.exists():
        return False, f"missing trace file left={left_trace} right={right_trace}"

    return True, ""


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        fail(f"missing report: {report_path}")
        return 1

    try:
        report = load_json(args.report)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        fail(f"invalid report: {exc}")
        return 1

    if not isinstance(report, dict):
        fail(f"invalid report format: {args.report}")
        return 1

    workloads = report.get("workloads")
    if not isinstance(workloads, list):
        fail("invalid report format: missing workloads list")
        return 1

    failures: list[str] = []
    checks = 0
    semantic_checks = 0
    semantic_eligible_pairs = 0
    for workload_idx, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            failures.append(f"workloads[{workload_idx}] is not an object")
            continue
        workload_id = workload.get("id", "unknown")
        for side in ("left", "right"):
            side_payload = workload.get(side, {})
            if not isinstance(side_payload, dict):
                continue
            for sample_idx, sample in enumerate(side_payload.get("commandSamples", [])):
                if not isinstance(sample, dict):
                    continue
                return_code = sample.get("returnCode")
                if not isinstance(return_code, int):
                    failures.append(
                        f"{workload_id}/{side} sample {sample_idx} missing or invalid returnCode (expected int)"
                    )
                    continue
                if return_code != 0:
                    continue

                trace_meta = sample.get("traceMetaPath")
                trace_jsonl = sample.get("traceJsonlPath")
                if not trace_meta or not trace_jsonl:
                    msg = (
                        f"{workload_id}/{side} sample {sample_idx} missing trace artifact paths "
                        "(expected traceMetaPath and traceJsonlPath)"
                    )
                    failures.append(msg)
                    continue

                meta_path = Path(trace_meta)
                jsonl_path = Path(trace_jsonl)
                if not meta_path.exists() or not jsonl_path.exists():
                    failures.append(
                        f"{workload_id}/{side} sample {sample_idx} missing trace files: "
                        f"meta={meta_path} jsonl={jsonl_path}"
                    )
                    continue

                checks += 1
                ok, output = run_replay_check(meta_path, jsonl_path)
                if not ok:
                    failures.append(
                        f"{workload_id}/{side} sample {sample_idx} trace replay check failed:\n{output}"
                    )
                meta_payload = sample_trace_meta(sample)
                if isinstance(meta_payload, dict):
                    module_name = str(meta_payload.get("module", ""))
                    execution_backend = str(meta_payload.get("executionBackend", ""))
                    if module_name.startswith(DOE_MODULE_PREFIX) and execution_backend in {
                        "dawn_delegate",
                        "doe_metal",
                        "doe_vulkan",
                        "doe_d3d12",
                    }:
                        backend_id = meta_payload.get("backendId")
                        if not isinstance(backend_id, str) or not backend_id:
                            failures.append(
                                f"{workload_id}/{side} sample {sample_idx} missing backendId in trace meta"
                            )
                        selection_reason = meta_payload.get("backendSelectionReason")
                        if selection_reason is not None and not isinstance(selection_reason, str):
                            failures.append(
                                f"{workload_id}/{side} sample {sample_idx} backendSelectionReason must be string"
                            )
                        fallback_used = meta_payload.get("fallbackUsed")
                        if fallback_used is not None and not isinstance(fallback_used, bool):
                            failures.append(
                                f"{workload_id}/{side} sample {sample_idx} fallbackUsed must be bool"
                            )

        if args.semantic_parity_mode == "off":
            continue

        left_payload = workload.get("left")
        right_payload = workload.get("right")
        if not isinstance(left_payload, dict) or not isinstance(right_payload, dict):
            if args.semantic_parity_mode == "required":
                failures.append(f"{workload_id} missing left/right payloads for semantic parity checks")
            continue
        left_samples = left_payload.get("commandSamples", [])
        right_samples = right_payload.get("commandSamples", [])
        if not isinstance(left_samples, list) or not isinstance(right_samples, list):
            if args.semantic_parity_mode == "required":
                failures.append(f"{workload_id} invalid commandSamples payload for semantic parity checks")
            continue

        pair_count = min(len(left_samples), len(right_samples))
        for sample_idx in range(pair_count):
            left_sample = left_samples[sample_idx]
            right_sample = right_samples[sample_idx]
            if not isinstance(left_sample, dict) or not isinstance(right_sample, dict):
                if args.semantic_parity_mode == "required":
                    failures.append(f"{workload_id} pair {sample_idx} invalid sample object")
                continue
            left_return_code = sample_return_code(left_sample)
            right_return_code = sample_return_code(right_sample)
            if left_return_code is None or right_return_code is None:
                if args.semantic_parity_mode == "required":
                    failures.append(
                        f"{workload_id} pair {sample_idx} missing returnCode values for semantic parity checks"
                    )
                continue
            if left_return_code != 0 or right_return_code != 0:
                continue

            eligible, reason = semantic_pair_eligible(left_sample, right_sample)
            if not eligible:
                if args.semantic_parity_mode == "required":
                    failures.append(f"{workload_id} pair {sample_idx} semantic parity ineligible: {reason}")
                continue

            semantic_eligible_pairs += 1
            left_trace = sample_trace_path(left_sample)
            right_trace = sample_trace_path(right_sample)
            assert left_trace is not None
            assert right_trace is not None
            semantic_checks += 1
            ok, output = run_semantic_parity_check(left_trace, right_trace)
            if not ok:
                failures.append(
                    f"{workload_id} pair {sample_idx} semantic parity check failed:\n{output}"
                )

    if failures:
        fail("trace gate failed")
        for item in failures:
            print(item)
        return 1

    if not checks:
        fail("no successful trace samples found")
        return 1

    if args.semantic_parity_mode == "required":
        if semantic_eligible_pairs == 0:
            fail("semantic parity required but no eligible successful sample pairs were found")
            return 1
        if semantic_checks == 0:
            fail("semantic parity required but zero semantic checks executed")
            return 1

    print(
        "PASS: replay-validated {checks} trace samples"
        " (semantic parity checks: {semantic_checks}, mode={mode})".format(
            checks=checks,
            semantic_checks=semantic_checks,
            mode=args.semantic_parity_mode,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
