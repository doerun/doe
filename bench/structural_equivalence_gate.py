#!/usr/bin/env python3
"""Structural work equivalence gate for Dawn-vs-Doe comparison reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import report_conformance


_PHASE_ASYMMETRY_THRESHOLD = 0.10
_MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC = 500_000_000_000

_UPLOAD_SIZE_SUFFIXES = {
    "1kb": 1024,
    "4kb": 4096,
    "16kb": 16384,
    "64kb": 65536,
    "256kb": 262144,
    "1mb": 1048576,
    "4mb": 4194304,
    "16mb": 16777216,
    "64mb": 67108864,
    "256mb": 268435456,
    "1gb": 1073741824,
    "4gb": 4294967296,
    "16gb": 17179869184,
}


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid report format: expected object in {path}")
    return payload


def load_report_contract_rows(
    *, report_path: Path, report_payload: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    workload_contract = report_payload.get("workloadContract")
    if not isinstance(workload_contract, dict):
        return {}
    raw_contract_path = workload_contract.get("path")
    if not isinstance(raw_contract_path, str) or not raw_contract_path.strip():
        return {}
    repo_root = Path(__file__).resolve().parent.parent
    resolved_path = report_conformance.resolve_contract_path(
        report_path=report_path,
        repo_root=repo_root,
        raw_contract_path=raw_contract_path,
    )
    if not resolved_path.exists():
        return {}
    return report_conformance.load_contract_workloads_by_id(resolved_path)


def collect_phase_fractions(command_samples: list[dict[str, Any]]) -> dict[str, list[float]]:
    fractions: dict[str, list[float]] = {"setup": [], "encode": [], "submitWait": []}
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        trace_meta = sample.get("traceMeta", {})
        if not isinstance(trace_meta, dict):
            continue
        total = safe_int(trace_meta.get("executionTotalNs"), default=0)
        if total <= 0:
            continue
        fractions["setup"].append(
            safe_int(trace_meta.get("executionSetupTotalNs"), default=0) / total
        )
        fractions["encode"].append(
            safe_int(trace_meta.get("executionEncodeTotalNs"), default=0) / total
        )
        fractions["submitWait"].append(
            safe_int(trace_meta.get("executionSubmitWaitTotalNs"), default=0) / total
        )
    return fractions


def check_dispatch_parity(workload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    left_samples = workload.get("left", {}).get("commandSamples", [])
    right_samples = workload.get("right", {}).get("commandSamples", [])

    left_dispatches: set[int] = set()
    right_dispatches: set[int] = set()
    for sample in left_samples:
        trace_meta = sample.get("traceMeta", {})
        if isinstance(trace_meta, dict):
            left_dispatches.add(safe_int(trace_meta.get("executionDispatchCount"), default=-1))
    for sample in right_samples:
        trace_meta = sample.get("traceMeta", {})
        if isinstance(trace_meta, dict):
            right_dispatches.add(safe_int(trace_meta.get("executionDispatchCount"), default=-1))

    left_dispatches.discard(-1)
    right_dispatches.discard(-1)
    if not left_dispatches or not right_dispatches:
        return failures
    if left_dispatches != right_dispatches:
        failures.append(
            f"dispatch count mismatch: left={sorted(left_dispatches)} "
            f"right={sorted(right_dispatches)}"
        )
    return failures


def check_phase_equivalence(workload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    phase_fields = {
        "setup": "executionSetupTotalNs",
        "encode": "executionEncodeTotalNs",
        "submitWait": "executionSubmitWaitTotalNs",
    }
    left_fracs = collect_phase_fractions(workload.get("left", {}).get("commandSamples", []))
    right_fracs = collect_phase_fractions(workload.get("right", {}).get("commandSamples", []))

    for phase_key, field_name in phase_fields.items():
        left_vals = left_fracs.get(phase_key, [])
        right_vals = right_fracs.get(phase_key, [])
        if not left_vals or not right_vals:
            continue
        left_median = sorted(left_vals)[len(left_vals) // 2]
        right_median = sorted(right_vals)[len(right_vals) // 2]
        if left_median == 0.0 and right_median >= _PHASE_ASYMMETRY_THRESHOLD:
            failures.append(
                f"phase asymmetry: left reports zero {field_name} but right spends "
                f"{right_median:.1%} of execution there"
            )
        elif right_median == 0.0 and left_median >= _PHASE_ASYMMETRY_THRESHOLD:
            failures.append(
                f"phase asymmetry: right reports zero {field_name} but left spends "
                f"{left_median:.1%} of execution there"
            )
    return failures


def check_throughput_plausibility(workload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if workload.get("domain") != "upload":
        return failures
    workload_id = str(workload.get("id", ""))
    upload_bytes = None
    for suffix, size in _UPLOAD_SIZE_SUFFIXES.items():
        if workload_id.endswith(suffix):
            upload_bytes = size
            break
    if upload_bytes is None:
        return failures

    timing_interpretation = workload.get("timingInterpretation", {})
    headline = (
        timing_interpretation.get("headlineProcessWall", {})
        if isinstance(timing_interpretation, dict)
        else {}
    )
    headline_left_p50 = safe_float(headline.get("leftStatsMs", {}).get("p50Ms"))
    headline_right_p50 = safe_float(headline.get("rightStatsMs", {}).get("p50Ms"))

    for side_name in ("left", "right"):
        p50_ms = safe_float(workload.get(side_name, {}).get("stats", {}).get("p50Ms"))
        headline_p50_ms = headline_left_p50 if side_name == "left" else headline_right_p50
        if p50_ms is None or p50_ms <= 0.0:
            continue
        throughput = upload_bytes / (p50_ms / 1000.0)
        if (
            throughput > _MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC
            and headline_p50_ms is not None
            and headline_p50_ms > 0.0
        ):
            headline_throughput = upload_bytes / (headline_p50_ms / 1000.0)
            if headline_throughput <= _MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC:
                continue
        if throughput > _MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC:
            failures.append(
                f"{side_name} implies {throughput / 1e9:.0f} GB/s for "
                f"{upload_bytes / (1024**2):.0f} MB upload at p50={p50_ms:.4f}ms; "
                f"exceeds {_MAX_PLAUSIBLE_THROUGHPUT_BYTES_PER_SEC / 1e9:.0f} GB/s ceiling"
            )
    return failures


def path_asymmetry_details(
    workload: dict[str, Any], contract_rows: dict[str, dict[str, Any]]
) -> tuple[bool, str]:
    if not workload_is_dawn_vs_doe(workload):
        return False, ""
    if workload.get("pathAsymmetry") is True:
        note = workload.get("pathAsymmetryNote")
        return True, str(note) if isinstance(note, str) else ""
    workload_id = workload.get("id")
    contract_row = contract_rows.get(str(workload_id), {})
    if bool(contract_row.get("pathAsymmetry", False)):
        return True, str(contract_row.get("pathAsymmetryNote", ""))
    return False, ""


def check_path_asymmetry(
    workload: dict[str, Any], contract_rows: dict[str, dict[str, Any]]
) -> list[str]:
    path_asymmetry, note = path_asymmetry_details(workload, contract_rows)
    if not path_asymmetry:
        return []
    reason = (
        "workload contract marks pathAsymmetry=true: left/right use hardware-specific "
        "execution paths that are not structurally equivalent"
    )
    if note:
        reason += f" ({note})"
    return [reason]


def workload_is_dawn_vs_doe(workload: dict[str, Any]) -> bool:
    def collect_execution_backends(side_payload: Any) -> set[str]:
        if not isinstance(side_payload, dict):
            return set()
        samples = side_payload.get("commandSamples")
        if not isinstance(samples, list):
            return set()
        return {
            str(trace_meta.get("executionBackend"))
            for sample in samples
            if isinstance(sample, dict)
            for trace_meta in [sample.get("traceMeta", {})]
            if isinstance(trace_meta, dict) and trace_meta.get("executionBackend")
        }

    left_backends = collect_execution_backends(workload.get("left"))
    right_backends = collect_execution_backends(workload.get("right"))
    left_dawn = "dawn_delegate" in left_backends or "dawn-perf-tests" in left_backends
    right_dawn = "dawn_delegate" in right_backends or "dawn-perf-tests" in right_backends
    left_doe = any(
        backend in left_backends
        for backend in ("doe_metal", "doe_vulkan", "doe_d3d12", "webgpu-ffi", "native")
    )
    right_doe = any(
        backend in right_backends
        for backend in ("doe_metal", "doe_vulkan", "doe_d3d12", "webgpu-ffi", "native")
    )
    return (left_dawn and right_doe) or (left_doe and right_dawn)


def main() -> int:
    parser = argparse.ArgumentParser(description="Structural work equivalence gate")
    parser.add_argument("--report", required=True, help="Dawn-vs-Doe comparison report JSON")
    parser.add_argument(
        "--require-all-pass",
        action="store_true",
        help="Exit non-zero if any comparable-by-contract workload fails structural checks.",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"FAIL: report not found: {report_path}")
        return 1

    try:
        report_payload = load_report(report_path)
        contract_rows = load_report_contract_rows(
            report_path=report_path, report_payload=report_payload
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    workloads = report_payload.get("workloads", [])
    if not isinstance(workloads, list):
        print("FAIL: report workloads must be a list")
        return 1

    total_failures = 0
    workload_results: list[dict[str, Any]] = []

    for workload in workloads:
        if not isinstance(workload, dict):
            continue
        workload_id = str(workload.get("id", "?"))
        workload_comparable = workload.get("workloadComparable") is True
        claimable = workload.get("claimability", {}).get("claimable") is True

        failures: list[str] = []
        failures.extend(check_dispatch_parity(workload))
        failures.extend(check_phase_equivalence(workload))
        failures.extend(check_throughput_plausibility(workload))
        failures.extend(check_path_asymmetry(workload, contract_rows))

        structural_status = "pass" if not failures else "fail"
        workload_results.append(
            {
                "workloadId": workload_id,
                "workloadComparable": workload_comparable,
                "claimable": claimable,
                "structuralEquivalence": structural_status,
                "failures": failures,
            }
        )

        if failures:
            blocking = workload_comparable
            label = "BLOCK" if blocking else "WARN"
            print(f"[{label}] {workload_id}:")
            for failure in failures:
                print(f"  - {failure}")
            if blocking:
                total_failures += 1

    pass_count = sum(
        1 for item in workload_results if item["structuralEquivalence"] == "pass"
    )
    fail_count = sum(
        1 for item in workload_results if item["structuralEquivalence"] == "fail"
    )
    print(
        f"\nStructural equivalence: {pass_count} pass, {fail_count} fail "
        f"({total_failures} blocking)"
    )

    if args.require_all_pass and total_failures > 0:
        print(
            "FAIL: "
            f"{total_failures} comparable-by-contract workload(s) failed structural equivalence"
        )
        return 1

    print("PASS: structural equivalence gate completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
