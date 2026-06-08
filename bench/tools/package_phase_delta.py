#!/usr/bin/env python3
"""Compare package WebGPU phase breakdowns from run receipts."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BENCH_ROOT))

from native_compare_modules import reporting as reporting_mod
from native_compare_modules.run_artifact import load_run_artifact

NS_PER_MS = 1_000_000.0
SETUP_BREAKDOWN_KEY = "packageSetupBreakdownNs"
STEP_BREAKDOWN_KEY = "packageStepBreakdownNs"
WRITE_BREAKDOWN_KEY = "packageWriteBreakdown"
RESIDENT_BUFFER_LOAD_BREAKDOWN_KEY = "packageResidentBufferLoadBreakdown"
WRITE_BREAKDOWN_SCALAR_FIELDS = (
    "totalCount",
    "totalBytes",
    "staticBufferLoadCount",
    "staticBufferLoadBytes",
    "dynamicWriteCount",
    "dynamicWriteBytes",
    "unbatchedWriteCount",
    "batchCallCount",
    "batchedWriteCount",
)
RESIDENT_BUFFER_LOAD_COUNT_FIELDS = ("count", "bytes")
RESIDENT_BUFFER_LOAD_NS_FIELDS = (
    "materializeTotalNs",
    "queueWriteTotalNs",
    "queueWaitTotalNs",
)
DERIVED_BREAKDOWN_SPECS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "setupTotalNs",
        (
            ("setup", "bufferCreateTotalNs"),
            ("setup", "initialDataWriteTotalNs"),
            ("setup", "shaderModuleCreateTotalNs"),
            ("setup", "bindGroupLayoutCreateTotalNs"),
            ("setup", "pipelineLayoutCreateTotalNs"),
            ("setup", "pipelineCreateTotalNs"),
            ("setup", "bindGroupCreateTotalNs"),
        ),
    ),
    (
        "setupBufferDataTotalNs",
        (
            ("setup", "bufferCreateTotalNs"),
            ("setup", "initialDataWriteTotalNs"),
        ),
    ),
    (
        "setupShaderPipelineTotalNs",
        (
            ("setup", "shaderModuleCreateTotalNs"),
            ("setup", "pipelineLayoutCreateTotalNs"),
            ("setup", "pipelineCreateTotalNs"),
        ),
    ),
    (
        "setupBindingTotalNs",
        (
            ("setup", "bindGroupLayoutCreateTotalNs"),
            ("setup", "bindGroupCreateTotalNs"),
        ),
    ),
    (
        "stepSelectedTotalNs",
        (
            ("step", "writeMaterializeTotalNs"),
            ("step", "writeQueueWriteTotalNs"),
            ("step", "dispatchEncodeApiTotalNs"),
            ("step", "copyEncodeApiTotalNs"),
            ("step", "submitCommandEncoderFinishTotalNs"),
            ("step", "submitQueueSubmitTotalNs"),
            ("step", "submitQueueWaitTotalNs"),
            ("step", "readbackTotalNs"),
        ),
    ),
    (
        "stepWriteTotalNs",
        (
            ("step", "writeMaterializeTotalNs"),
            ("step", "writeQueueWriteTotalNs"),
        ),
    ),
    (
        "stepEncodeApiTotalNs",
        (
            ("step", "dispatchEncodeApiTotalNs"),
            ("step", "copyEncodeApiTotalNs"),
        ),
    ),
    (
        "stepSubmitApiEnvelopeNs",
        (
            ("step", "submitCommandEncoderFinishTotalNs"),
            ("step", "submitQueueSubmitTotalNs"),
            ("step", "submitQueueWaitTotalNs"),
        ),
    ),
    (
        "stepDoeSubmitWrapperNs",
        (
            ("step", "submitCommandPrepTotalNs"),
            ("step", "submitAddonCallTotalNs"),
            ("step", "submitPostSubmitBookkeepingTotalNs"),
            ("step", "submitQueueWaitBookkeepingTotalNs"),
        ),
    ),
    (
        "stepDoeSubmitNativeBreakdownNs",
        (
            ("step", "submitAddonCommandReplayTotalNs"),
            ("step", "submitAddonCommandReplayPrepareTotalNs"),
            ("step", "submitAddonCommandReplayRecordTotalNs"),
            ("step", "submitAddonCommandReplayCopyTotalNs"),
            ("step", "submitAddonQueueSubmitTotalNs"),
            ("step", "submitAddonCommandBufferEndTotalNs"),
            ("step", "submitAddonSyncPrepareTotalNs"),
            ("step", "submitAddonDriverSubmitTotalNs"),
            ("step", "submitAddonFlushTotalNs"),
            ("step", "submitQueueFlushTotalNs"),
            ("step", "submitQueueFlushWaitCompletedTotalNs"),
            ("step", "submitQueueFlushDeferredCopyTotalNs"),
            ("step", "submitQueueFlushDeferredResolveTotalNs"),
        ),
    ),
    ("stepReadbackTotalNs", (("step", "readbackTotalNs"),)),
    (
        "stepReadbackApiEnvelopeNs",
        (
            ("step", "readbackMapReadCopyUnmapTotalNs"),
            ("step", "readbackMapAsyncTotalNs"),
            ("step", "readbackGetMappedRangeTotalNs"),
            ("step", "readbackHostCopyTotalNs"),
            ("step", "readbackNativeReadCopyTotalNs"),
            ("step", "readbackUnmapTotalNs"),
        ),
    ),
    (
        "stepReadbackHarnessNs",
        (
            ("step", "readbackValidationTotalNs"),
            ("step", "readbackCaptureTotalNs"),
        ),
    ),
    ("stepReadbackValidationNs", (("step", "readbackValidationTotalNs"),)),
    ("stepReadbackCaptureNs", (("step", "readbackCaptureTotalNs"),)),
)


@dataclass(frozen=True)
class ArtifactSet:
    label: str
    paths: list[Path]
    artifacts: list[dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare package setup/step phase medians between two run "
            "receipt sets."
        )
    )
    parser.add_argument(
        "--baseline-glob",
        action="append",
        default=[],
        required=True,
        help="Glob for baseline run receipts; may be repeated.",
    )
    parser.add_argument(
        "--comparison-glob",
        action="append",
        default=[],
        required=True,
        help="Glob for comparison run receipts; may be repeated.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Human-readable label for the baseline side.",
    )
    parser.add_argument(
        "--comparison-label",
        default="comparison",
        help="Human-readable label for the comparison side.",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path for the machine-readable phase delta artifact.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of largest phase gaps to print.",
    )
    return parser.parse_args()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _glob_base(pattern: str) -> str:
    candidate = Path(pattern)
    if candidate.is_absolute():
        return str(candidate)
    return str(REPO_ROOT / pattern)


def resolve_patterns(patterns: list[str]) -> list[Path]:
    """Resolve one or more receipt globs, failing if any pattern is empty."""
    if not patterns:
        raise ValueError("at least one run receipt glob is required")
    paths: list[Path] = []
    for pattern in patterns:
        matched = sorted(
            Path(path)
            for path in glob.glob(_glob_base(pattern), recursive=True)
            if Path(path).is_file()
        )
        if not matched:
            raise FileNotFoundError(f"run receipt glob matched no files: {pattern}")
        paths.extend(matched)
    deduped = sorted({path.resolve() for path in paths})
    if not deduped:
        raise FileNotFoundError("no run receipts resolved from glob set")
    return deduped


def load_artifact_set(label: str, patterns: list[str]) -> ArtifactSet:
    paths = resolve_patterns(patterns)
    artifacts = [load_run_artifact(path) for path in paths]
    return ArtifactSet(label=label, paths=paths, artifacts=artifacts)


def _successful_samples(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    samples = artifact.get("samples", [])
    if not isinstance(samples, list):
        return []
    return [
        sample
        for sample in samples
        if isinstance(sample, dict) and sample.get("success") is True
    ]


def _trace_meta(sample: dict[str, Any]) -> dict[str, Any]:
    trace_meta = sample.get("traceMeta", {})
    return trace_meta if isinstance(trace_meta, dict) else {}


def _sample_timing_divisor(sample: dict[str, Any]) -> float:
    value = reporting_mod.safe_float(sample.get("timingNormalizationDivisor"))
    if value is None:
        timing = sample.get("timing", {})
        if isinstance(timing, dict):
            value = reporting_mod.safe_float(timing.get("timingNormalizationDivisor"))
    return value if value is not None and value > 0.0 else 1.0


def _add_breakdown_values(
    target: dict[str, list[float]],
    breakdown: Any,
    divisor: float,
) -> None:
    if not isinstance(breakdown, dict):
        return
    for raw_name, raw_value in breakdown.items():
        value = reporting_mod.safe_float(raw_value)
        if value is None:
            continue
        target.setdefault(str(raw_name), []).append((value / NS_PER_MS) / divisor)


def _add_write_breakdown_values(
    target: dict[str, list[float]],
    breakdown: Any,
    divisor: float,
) -> None:
    if not isinstance(breakdown, dict):
        return
    for field in WRITE_BREAKDOWN_SCALAR_FIELDS:
        value = reporting_mod.safe_float(breakdown.get(field))
        if value is not None:
            target.setdefault(field, []).append(value / divisor)
    for section in ("byDataKind", "bySemanticPhase"):
        buckets = breakdown.get(section, {})
        if not isinstance(buckets, dict):
            continue
        for raw_name, raw_bucket in buckets.items():
            if not isinstance(raw_bucket, dict):
                continue
            for field in ("count", "bytes"):
                value = reporting_mod.safe_float(raw_bucket.get(field))
                if value is not None:
                    target.setdefault(f"{section}.{raw_name}.{field}", []).append(value / divisor)


def _add_resident_buffer_load_breakdown_values(
    count_target: dict[str, list[float]],
    timing_target: dict[str, list[float]],
    amortized_count_target: dict[str, list[float]],
    amortized_timing_target: dict[str, list[float]],
    breakdown: Any,
    divisor: float,
) -> None:
    if not isinstance(breakdown, dict):
        return
    for field in RESIDENT_BUFFER_LOAD_COUNT_FIELDS:
        value = reporting_mod.safe_float(breakdown.get(field))
        if value is not None:
            count_target.setdefault(field, []).append(value)
            amortized_count_target.setdefault(field, []).append(value / divisor)
    for field in RESIDENT_BUFFER_LOAD_NS_FIELDS:
        value = reporting_mod.safe_float(breakdown.get(field))
        if value is not None:
            timing_target.setdefault(field, []).append(value / NS_PER_MS)
            amortized_timing_target.setdefault(field, []).append((value / NS_PER_MS) / divisor)


def _breakdown_ns(breakdown: Any, field: str) -> float:
    if not isinstance(breakdown, dict):
        return 0.0
    value = reporting_mod.safe_float(breakdown.get(field))
    return value if value is not None else 0.0


def _derived_breakdown_values(
    setup_breakdown: Any,
    step_breakdown: Any,
    divisor: float = 1.0,
) -> dict[str, float]:
    breakdowns = {
        "setup": setup_breakdown,
        "step": step_breakdown,
    }
    derived: dict[str, float] = {}
    for name, parts in DERIVED_BREAKDOWN_SPECS:
        total_ns = 0.0
        for section, field in parts:
            total_ns += _breakdown_ns(breakdowns.get(section), field)
        derived[name] = (total_ns / NS_PER_MS) / divisor
    return derived


def _stats(values: list[float]) -> dict[str, float]:
    return reporting_mod.format_stats(values)


def _distribution_stats(values: list[float]) -> dict[str, float]:
    return reporting_mod.format_distribution(values)


def _workload_id(artifact: dict[str, Any], path: Path) -> str:
    workload = artifact.get("workload", {})
    if not isinstance(workload, dict):
        raise ValueError(f"run receipt missing workload object: {path}")
    workload_id = str(workload.get("id", "")).strip()
    if not workload_id:
        raise ValueError(f"run receipt missing workload.id: {path}")
    return workload_id


def summarize_artifact_set(artifact_set: ArtifactSet) -> dict[str, Any]:
    """Summarize timing and package phase medians by workload."""
    workload_groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, artifact in zip(artifact_set.paths, artifact_set.artifacts):
        workload_id = _workload_id(artifact, path)
        workload_groups.setdefault(workload_id, []).append((path, artifact))

    workloads: dict[str, dict[str, Any]] = {}
    for workload_id, group in sorted(workload_groups.items()):
        measured_ms: list[float] = []
        wall_ms: list[float] = []
        setup_breakdowns: dict[str, list[float]] = {}
        step_breakdowns: dict[str, list[float]] = {}
        derived_breakdowns: dict[str, list[float]] = {}
        write_breakdowns: dict[str, list[float]] = {}
        resident_buffer_load_breakdowns: dict[str, list[float]] = {}
        resident_buffer_load_timing_breakdowns: dict[str, list[float]] = {}
        resident_buffer_load_amortized_breakdowns: dict[str, list[float]] = {}
        resident_buffer_load_amortized_timing_breakdowns: dict[str, list[float]] = {}
        sample_count = 0
        for _path, artifact in group:
            successful_samples = _successful_samples(artifact)
            sample_count += len(successful_samples)
            for sample in successful_samples:
                measured = reporting_mod.safe_float(sample.get("measuredMs"))
                if measured is not None:
                    measured_ms.append(measured)
                wall = reporting_mod.safe_float(sample.get("wallMs"))
                if wall is not None:
                    wall_ms.append(wall)
                trace_meta = _trace_meta(sample)
                divisor = _sample_timing_divisor(sample)
                _add_breakdown_values(
                    setup_breakdowns,
                    trace_meta.get(SETUP_BREAKDOWN_KEY),
                    divisor,
                )
                _add_breakdown_values(
                    step_breakdowns,
                    trace_meta.get(STEP_BREAKDOWN_KEY),
                    divisor,
                )
                _add_write_breakdown_values(
                    write_breakdowns,
                    trace_meta.get(WRITE_BREAKDOWN_KEY),
                    divisor,
                )
                _add_resident_buffer_load_breakdown_values(
                    resident_buffer_load_breakdowns,
                    resident_buffer_load_timing_breakdowns,
                    resident_buffer_load_amortized_breakdowns,
                    resident_buffer_load_amortized_timing_breakdowns,
                    trace_meta.get(RESIDENT_BUFFER_LOAD_BREAKDOWN_KEY),
                    divisor,
                )
                for name, value in _derived_breakdown_values(
                    trace_meta.get(SETUP_BREAKDOWN_KEY),
                    trace_meta.get(STEP_BREAKDOWN_KEY),
                    divisor,
                ).items():
                    derived_breakdowns.setdefault(name, []).append(value)

        paths = [path for path, _artifact in group]
        first_artifact = group[0][1]
        workloads[workload_id] = {
            "path": rel(paths[0]),
            "paths": [rel(path) for path in paths],
            "artifactCount": len(paths),
            "sampleCount": sample_count,
            "timing": {
                "measuredMs": _stats(measured_ms),
                "wallMs": _stats(wall_ms),
            },
            "setupBreakdownMs": {
                name: _stats(values)
                for name, values in sorted(setup_breakdowns.items())
            },
            "stepBreakdownMs": {
                name: _stats(values)
                for name, values in sorted(step_breakdowns.items())
            },
            "derivedBreakdownMs": {
                name: _stats(values)
                for name, values in sorted(derived_breakdowns.items())
            },
            "writeBreakdown": {
                name: _distribution_stats(values)
                for name, values in sorted(write_breakdowns.items())
            },
            "residentBufferLoadBreakdown": {
                name: _distribution_stats(values)
                for name, values in sorted(resident_buffer_load_breakdowns.items())
            },
            "residentBufferLoadBreakdownMs": {
                name: _stats(values)
                for name, values in sorted(resident_buffer_load_timing_breakdowns.items())
            },
            "residentBufferLoadBreakdownAmortized": {
                name: _distribution_stats(values)
                for name, values in sorted(resident_buffer_load_amortized_breakdowns.items())
            },
            "residentBufferLoadBreakdownAmortizedMs": {
                name: _stats(values)
                for name, values in sorted(
                    resident_buffer_load_amortized_timing_breakdowns.items()
                )
            },
            "runtimeIdentity": first_artifact.get("runtimeIdentity", {}),
            "hostIdentity": first_artifact.get("hostIdentity", {}),
        }
    return {
        "label": artifact_set.label,
        "pathCount": len(artifact_set.paths),
        "paths": [rel(path) for path in artifact_set.paths],
        "workloads": dict(sorted(workloads.items())),
    }


def _p50(stats: dict[str, Any]) -> float:
    value = reporting_mod.safe_float(stats.get("p50Ms"))
    return value if value is not None else 0.0


def _pct_of_comparison(
    comparison_minus_baseline_ms: float,
    comparison_ms: float,
) -> float | None:
    if comparison_ms == 0.0:
        return None
    return (comparison_minus_baseline_ms / comparison_ms) * 100.0


def _delta_record(
    *,
    workload_id: str,
    section: str,
    phase: str,
    baseline_stats: dict[str, Any],
    comparison_stats: dict[str, Any],
) -> dict[str, Any]:
    baseline_p50 = _p50(baseline_stats)
    comparison_p50 = _p50(comparison_stats)
    delta = comparison_p50 - baseline_p50
    return {
        "workloadId": workload_id,
        "section": section,
        "phase": phase,
        "baselineP50Ms": baseline_p50,
        "comparisonP50Ms": comparison_p50,
        "comparisonMinusBaselineP50Ms": delta,
        "baselineDeltaPctOfComparison": _pct_of_comparison(
            delta,
            comparison_p50,
        ),
        "positiveMeansBaselineLower": True,
    }


def _compare_phase_maps(
    *,
    workload_id: str,
    section: str,
    baseline_phases: dict[str, Any],
    comparison_phases: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for phase in sorted(set(baseline_phases) | set(comparison_phases)):
        records.append(
            _delta_record(
                workload_id=workload_id,
                section=section,
                phase=phase,
                baseline_stats=baseline_phases.get(phase, {}),
                comparison_stats=comparison_phases.get(phase, {}),
            )
        )
    return records


def compare_summaries(
    baseline: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    baseline_workloads = baseline.get("workloads", {})
    comparison_workloads = comparison.get("workloads", {})
    if not isinstance(baseline_workloads, dict):
        raise ValueError("baseline summary missing workloads object")
    if not isinstance(comparison_workloads, dict):
        raise ValueError("comparison summary missing workloads object")

    baseline_ids = set(baseline_workloads)
    comparison_ids = set(comparison_workloads)
    if baseline_ids != comparison_ids:
        missing_from_baseline = sorted(comparison_ids - baseline_ids)
        missing_from_comparison = sorted(baseline_ids - comparison_ids)
        raise ValueError(
            "workload sets do not match: "
            f"missingFromBaseline={missing_from_baseline}, "
            f"missingFromComparison={missing_from_comparison}"
        )

    workloads: dict[str, Any] = {}
    phase_gaps: list[dict[str, Any]] = []
    for workload_id in sorted(baseline_ids):
        baseline_row = baseline_workloads[workload_id]
        comparison_row = comparison_workloads[workload_id]
        timing_delta = _delta_record(
            workload_id=workload_id,
            section="timing",
            phase="measuredMs",
            baseline_stats=baseline_row["timing"]["measuredMs"],
            comparison_stats=comparison_row["timing"]["measuredMs"],
        )
        setup_deltas = _compare_phase_maps(
            workload_id=workload_id,
            section="setup",
            baseline_phases=baseline_row["setupBreakdownMs"],
            comparison_phases=comparison_row["setupBreakdownMs"],
        )
        step_deltas = _compare_phase_maps(
            workload_id=workload_id,
            section="step",
            baseline_phases=baseline_row["stepBreakdownMs"],
            comparison_phases=comparison_row["stepBreakdownMs"],
        )
        derived_deltas = _compare_phase_maps(
            workload_id=workload_id,
            section="derived",
            baseline_phases=baseline_row.get("derivedBreakdownMs", {}),
            comparison_phases=comparison_row.get("derivedBreakdownMs", {}),
        )
        resident_buffer_load_deltas = _compare_phase_maps(
            workload_id=workload_id,
            section="residentBufferLoad",
            baseline_phases=baseline_row.get("residentBufferLoadBreakdownMs", {}),
            comparison_phases=comparison_row.get("residentBufferLoadBreakdownMs", {}),
        )
        resident_buffer_load_amortized_deltas = _compare_phase_maps(
            workload_id=workload_id,
            section="residentBufferLoadAmortized",
            baseline_phases=baseline_row.get("residentBufferLoadBreakdownAmortizedMs", {}),
            comparison_phases=comparison_row.get("residentBufferLoadBreakdownAmortizedMs", {}),
        )
        workloads[workload_id] = {
            "timing": timing_delta,
            "setup": setup_deltas,
            "step": step_deltas,
            "derived": derived_deltas,
            "residentBufferLoad": resident_buffer_load_deltas,
            "residentBufferLoadAmortized": resident_buffer_load_amortized_deltas,
        }
        phase_gaps.extend([
            timing_delta,
            *setup_deltas,
            *step_deltas,
            *derived_deltas,
            *resident_buffer_load_deltas,
            *resident_buffer_load_amortized_deltas,
        ])

    phase_gaps.sort(
        key=lambda row: (
            abs(float(row["comparisonMinusBaselineP50Ms"])),
            row["workloadId"],
            row["section"],
            row["phase"],
        ),
        reverse=True,
    )
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_package_phase_delta",
        "baseline": baseline,
        "comparison": comparison,
        "workloads": workloads,
        "phaseGaps": phase_gaps,
    }


def _format_ms(value: Any) -> str:
    parsed = reporting_mod.safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.3f}"


def _format_pct(value: Any) -> str:
    parsed = reporting_mod.safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:+.1f}%"


def format_text_report(report: dict[str, Any], top: int) -> str:
    lines = [
        (
            "baseline "
            f"{report['baseline']['label']} vs comparison "
            f"{report['comparison']['label']}"
        ),
        (
            "positive delta means baseline has the lower p50 for that "
            "timing or phase"
        ),
        (
            "workload | section | phase | baseline p50 ms | comparison "
            "p50 ms | delta ms | delta %"
        ),
    ]
    for row in report["phaseGaps"][: max(top, 0)]:
        lines.append(
            " | ".join(
                [
                    str(row["workloadId"]),
                    str(row["section"]),
                    str(row["phase"]),
                    _format_ms(row["baselineP50Ms"]),
                    _format_ms(row["comparisonP50Ms"]),
                    _format_ms(row["comparisonMinusBaselineP50Ms"]),
                    _format_pct(row["baselineDeltaPctOfComparison"]),
                ]
            )
        )
    return "\n".join(lines)


def write_json_report(report: dict[str, Any], out_path: str) -> Path:
    path = Path(out_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    args = parse_args()
    try:
        baseline = summarize_artifact_set(
            load_artifact_set(args.baseline_label, args.baseline_glob)
        )
        comparison = summarize_artifact_set(
            load_artifact_set(args.comparison_label, args.comparison_glob)
        )
        report = compare_summaries(baseline, comparison)
        print(format_text_report(report, args.top))
        if args.json_out:
            path = write_json_report(report, args.json_out)
            print(f"wrote {rel(path)}")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
