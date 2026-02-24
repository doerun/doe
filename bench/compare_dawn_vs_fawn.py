#!/usr/bin/env python3
"""
Dawn/Fawn side-by-side benchmark runner.

This script executes shared workload command templates for both runtimes and emits
timing traces where available, with wall-time as a fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import time
import resource as py_resource
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import shlex
import output_paths

from compare_dawn_vs_fawn_modules import claimability as claimability_mod
from compare_dawn_vs_fawn_modules import comparability as comparability_mod
from compare_dawn_vs_fawn_modules import reporting as reporting_mod
from compare_dawn_vs_fawn_modules import timing_selection as timing_selection_mod

MAX_RSS_MARKER = "__FAWN_MAXRSS_KB__:"
DEFAULT_WORKLOADS_PATH = "fawn/bench/workloads.json"
DEFAULT_LEFT_NAME = "fawn"
DEFAULT_RIGHT_NAME = "dawn"
DEFAULT_LEFT_COMMAND_TEMPLATE = (
    "fawn/zig/zig-out/bin/fawn-zig-runtime "
    "--commands {commands} --quirks {quirks} "
    "--vendor {vendor} --api {api} --family {family} --driver {driver} "
    "--trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}"
)
DEFAULT_ITERATIONS = 3
DEFAULT_WARMUP = 1
DEFAULT_OUT_PATH = "fawn/bench/out/dawn-vs-fawn.json"
DEFAULT_WORKSPACE_PATH = "fawn/bench/out/runtime-comparisons"
DEFAULT_WORKLOAD_FILTER = ""
DEFAULT_COMPARABILITY_MODE = "strict"
DEFAULT_REQUIRED_TIMING_CLASS = "operation"
DEFAULT_RESOURCE_PROBE = "none"
DEFAULT_RESOURCE_SAMPLE_MS = 100
DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT = 0
DEFAULT_CLAIMABILITY_MODE = "off"
DEFAULT_CLAIM_MIN_TIMED_SAMPLES = 0
DEFAULT_BENCHMARK_POLICY_PATH = ""
DEFAULT_BENCHMARK_POLICY_CANDIDATES = (
    "config/benchmark-methodology-thresholds.json",
    "fawn/config/benchmark-methodology-thresholds.json",
)
VALID_COMPARABILITY_MODES = {"strict", "warn", "off"}
VALID_REQUIRED_TIMING_CLASSES = {"any", "operation", "process-wall"}
VALID_RESOURCE_PROBES = {"none", "rocm-smi"}
VALID_CLAIMABILITY_MODES = {"off", "local", "release"}
VALID_UPLOAD_BUFFER_USAGES = {"copy-dst-copy-src", "copy-dst"}
NON_APPLES_TO_APPLES_DOMAINS = {
    "pipeline-async",
    "p1-capability",
    "p1-resource-table",
    "p1-capability-macro",
    "p2-lifecycle",
    "p2-lifecycle-macro",
    "p0-resource",
    "p0-compute",
    "p0-render",
    "surface",
}
FAWN_UPLOAD_RUNTIME_SOURCE_PATHS = (
    Path("zig/src/main.zig"),
    Path("zig/src/execution.zig"),
    Path("zig/src/wgpu_commands.zig"),
    Path("zig/src/webgpu_ffi.zig"),
)
NATIVE_EXECUTION_OPERATION_TIMING_SOURCES = {
    "fawn-execution-total-ns",
    "fawn-execution-row-total-ns",
    "fawn-execution-dispatch-window-ns",
    "fawn-execution-encode-ns",
    "fawn-execution-gpu-timestamp-ns",
}
RENDER_ENCODE_TIMING_DOMAINS = {"render", "render-bundle"}


@dataclass
class Workload:
    id: str
    name: str
    description: str
    domain: str
    comparability_notes: str
    commands_path: str
    quirks_path: str
    vendor: str
    api: str
    family: str
    driver: str
    extra_args: list[str]
    left_command_repeat: int
    right_command_repeat: int
    left_ignore_first_ops: int
    right_ignore_first_ops: int
    left_upload_buffer_usage: str
    right_upload_buffer_usage: str
    left_upload_submit_every: int
    right_upload_submit_every: int
    dawn_filter: str
    comparable: bool
    allow_left_no_execution: bool
    include_by_default: bool
    left_timing_divisor: float
    right_timing_divisor: float
    timing_normalization_note: str


@dataclass(frozen=True)
class BenchmarkMethodologyPolicy:
    source_path: str
    min_dispatch_window_ns_without_encode: int
    min_dispatch_window_coverage_percent_without_encode: float
    local_claim_min_timed_samples: int
    release_claim_min_timed_samples: int


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def collect_trace_meta_hashes(command_samples: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_path: dict[str, str] = {}
    for sample in command_samples:
        if not isinstance(sample, dict):
            continue
        raw_path = sample.get("traceMetaPath")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        path = raw_path.strip()
        if path in by_path:
            continue
        trace_meta_path = Path(path)
        if not trace_meta_path.exists():
            continue
        by_path[path] = file_sha256(trace_meta_path)
    return [{"path": path, "sha256": by_path[path]} for path in sorted(by_path.keys())]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="",
        help=(
            "JSON config for benchmark run. When provided, missing CLI fields are "
            "loaded from config (for example left/right command templates)."
        ),
    )
    parser.add_argument("--workloads", default=DEFAULT_WORKLOADS_PATH)
    parser.add_argument(
        "--left-name",
        default=DEFAULT_LEFT_NAME,
    )
    parser.add_argument(
        "--right-name",
        default=DEFAULT_RIGHT_NAME,
    )
    parser.add_argument(
        "--left-command-template",
        default=DEFAULT_LEFT_COMMAND_TEMPLATE,
        help=(
            "Python format template. Supported keys: commands, quirks, vendor, api, family, "
            "driver, workload, dawn_filter, trace_jsonl, trace_meta, extra_args"
        ),
    )
    parser.add_argument(
        "--right-command-template",
        default="",
        help=(
            "Dawn command template using the same placeholders as --left-command-template. "
            "Must target the same workload semantics."
        ),
    )
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--out", default=DEFAULT_OUT_PATH)
    parser.add_argument(
        "--workspace",
        default=DEFAULT_WORKSPACE_PATH,
        help="Directory for per-run trace/meta artifacts",
    )
    parser.add_argument(
        "--workload-filter",
        default=DEFAULT_WORKLOAD_FILTER,
        help="Comma-separated workload IDs to include",
    )
    parser.add_argument(
        "--include-extended-workloads",
        action="store_true",
        help="Include workloads marked with default=false in workloads.json.",
    )
    parser.add_argument(
        "--include-noncomparable-workloads",
        action="store_true",
        help="Include workloads marked as non-comparable in workloads.json.",
    )
    parser.add_argument(
        "--comparability",
        choices=("strict", "warn", "off"),
        default=DEFAULT_COMPARABILITY_MODE,
        help="How to handle non-comparable timing sources between left/right runs.",
    )
    parser.add_argument(
        "--require-timing-class",
        choices=("any", "operation", "process-wall"),
        default=DEFAULT_REQUIRED_TIMING_CLASS,
        help="Required timing class for both sides to consider a workload comparable.",
    )
    parser.add_argument(
        "--allow-left-no-execution",
        action="store_true",
        help="Allow left samples without explicit execution evidence in trace-meta.",
    )
    parser.add_argument(
        "--resource-probe",
        choices=("none", "rocm-smi"),
        default=DEFAULT_RESOURCE_PROBE,
        help=(
            "Optional resource probe applied equally to both sides. "
            "'rocm-smi' samples global VRAM usage via rocm-smi --showmeminfo vram --json."
        ),
    )
    parser.add_argument(
        "--resource-sample-ms",
        type=int,
        default=DEFAULT_RESOURCE_SAMPLE_MS,
        help="Sampling interval in milliseconds for process/resource probes (>=1).",
    )
    parser.add_argument(
        "--resource-sample-target-count",
        type=int,
        default=DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT,
        help=(
            "Fixed probe sample target per run for strict N-vs-N resource comparability. "
            "When >0, each run records exactly this many samples; short runs are padded, "
            "and long runs are marked truncated."
        ),
    )
    parser.add_argument(
        "--claimability",
        choices=("off", "local", "release"),
        default=DEFAULT_CLAIMABILITY_MODE,
        help=(
            "Enable reliability checks for claimable faster/slower statements. "
            "local: require min samples + positive p50/p95. "
            "release: require min samples + positive p50/p95/p99."
        ),
    )
    parser.add_argument(
        "--claim-min-timed-samples",
        type=int,
        default=DEFAULT_CLAIM_MIN_TIMED_SAMPLES,
        help=(
            "Minimum timed samples required per side for claimability checks. "
            "When 0, defaults by claimability mode (local=7, release=15)."
        ),
    )
    parser.add_argument(
        "--benchmark-policy",
        default=DEFAULT_BENCHMARK_POLICY_PATH,
        help=(
            "Benchmark methodology threshold config. "
            "Defaults to config/benchmark-methodology-thresholds.json."
        ),
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for artifact paths (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp report/workspace artifact paths with a UTC timestamp suffix.",
    )
    parser.add_argument("--emit-shell", action="store_true", help="Print resolved commands instead of running")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_nested(payload: dict[str, Any], path: str) -> Any:
    cursor: Any = payload
    for segment in path.split("."):
        if not isinstance(cursor, dict):
            return None
        if segment not in cursor:
            return None
        cursor = cursor[segment]
    return cursor


def first_config_value(payload: dict[str, Any], candidates: list[str]) -> Any:
    for candidate in candidates:
        value = get_nested(payload, candidate)
        if value is not None:
            return value
    return None


def as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid config value for {field}: expected string")
    return value


def as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid config value for {field}: expected integer")
    return value


def as_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid config value for {field}: expected number")
    return float(value)


def as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"invalid config value for {field}: expected boolean")
    return value


def apply_config_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if not args.config:
        return args

    config_path = Path(args.config)
    payload = load_json(config_path)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid config: expected top-level object in {config_path}")

    if args.workloads == DEFAULT_WORKLOADS_PATH:
        value = first_config_value(payload, ["workloads"])
        if value is not None:
            args.workloads = as_str(value, field="workloads")

    if args.left_name == DEFAULT_LEFT_NAME:
        value = first_config_value(payload, ["left.name", "leftName"])
        if value is not None:
            args.left_name = as_str(value, field="left.name")
    if args.right_name == DEFAULT_RIGHT_NAME:
        value = first_config_value(payload, ["right.name", "rightName"])
        if value is not None:
            args.right_name = as_str(value, field="right.name")

    if args.left_command_template == DEFAULT_LEFT_COMMAND_TEMPLATE:
        value = first_config_value(payload, ["left.commandTemplate", "leftCommandTemplate"])
        if value is not None:
            args.left_command_template = as_str(value, field="left.commandTemplate")
    if args.right_command_template == "":
        value = first_config_value(payload, ["right.commandTemplate", "rightCommandTemplate"])
        if value is not None:
            args.right_command_template = as_str(value, field="right.commandTemplate")

    if args.iterations == DEFAULT_ITERATIONS:
        value = first_config_value(payload, ["run.iterations", "iterations"])
        if value is not None:
            args.iterations = as_int(value, field="run.iterations")
    if args.warmup == DEFAULT_WARMUP:
        value = first_config_value(payload, ["run.warmup", "warmup"])
        if value is not None:
            args.warmup = as_int(value, field="run.warmup")
    if args.out == DEFAULT_OUT_PATH:
        value = first_config_value(payload, ["run.out", "out"])
        if value is not None:
            args.out = as_str(value, field="run.out")
    if args.workspace == DEFAULT_WORKSPACE_PATH:
        value = first_config_value(payload, ["run.workspace", "workspace"])
        if value is not None:
            args.workspace = as_str(value, field="run.workspace")
    if args.workload_filter == DEFAULT_WORKLOAD_FILTER:
        value = first_config_value(payload, ["run.workloadFilter", "workloadFilter"])
        if value is not None:
            args.workload_filter = as_str(value, field="run.workloadFilter")

    if args.include_extended_workloads is False:
        value = first_config_value(
            payload,
            ["run.includeExtendedWorkloads", "includeExtendedWorkloads"],
        )
        if value is not None:
            args.include_extended_workloads = as_bool(
                value,
                field="run.includeExtendedWorkloads",
            )
    if args.include_noncomparable_workloads is False:
        value = first_config_value(
            payload,
            ["run.includeNoncomparableWorkloads", "includeNoncomparableWorkloads"],
        )
        if value is not None:
            args.include_noncomparable_workloads = as_bool(
                value,
                field="run.includeNoncomparableWorkloads",
            )

    if args.comparability == DEFAULT_COMPARABILITY_MODE:
        value = first_config_value(payload, ["comparability.mode", "comparabilityMode"])
        if value is not None:
            candidate = as_str(value, field="comparability.mode")
            if candidate not in VALID_COMPARABILITY_MODES:
                raise ValueError(
                    f"invalid config comparability.mode={candidate}, expected one of {sorted(VALID_COMPARABILITY_MODES)}"
                )
            args.comparability = candidate
    if args.require_timing_class == DEFAULT_REQUIRED_TIMING_CLASS:
        value = first_config_value(
            payload,
            ["comparability.requireTimingClass", "requireTimingClass"],
        )
        if value is not None:
            candidate = as_str(value, field="comparability.requireTimingClass")
            if candidate not in VALID_REQUIRED_TIMING_CLASSES:
                raise ValueError(
                    "invalid config comparability.requireTimingClass="
                    f"{candidate}, expected one of {sorted(VALID_REQUIRED_TIMING_CLASSES)}"
                )
            args.require_timing_class = candidate
    if args.allow_left_no_execution is False:
        value = first_config_value(
            payload,
            ["comparability.allowLeftNoExecution", "allowLeftNoExecution"],
        )
        if value is not None:
            args.allow_left_no_execution = as_bool(
                value,
                field="comparability.allowLeftNoExecution",
            )

    if args.resource_probe == DEFAULT_RESOURCE_PROBE:
        value = first_config_value(payload, ["resource.probe", "resourceProbe"])
        if value is not None:
            candidate = as_str(value, field="resource.probe")
            if candidate not in VALID_RESOURCE_PROBES:
                raise ValueError(
                    f"invalid config resource.probe={candidate}, expected one of {sorted(VALID_RESOURCE_PROBES)}"
                )
            args.resource_probe = candidate
    if args.resource_sample_ms == DEFAULT_RESOURCE_SAMPLE_MS:
        value = first_config_value(payload, ["resource.sampleMs", "resourceSampleMs"])
        if value is not None:
            args.resource_sample_ms = as_int(value, field="resource.sampleMs")
    if args.resource_sample_target_count == DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT:
        value = first_config_value(
            payload,
            ["resource.sampleTargetCount", "resourceSampleTargetCount"],
        )
        if value is not None:
            args.resource_sample_target_count = as_int(
                value,
                field="resource.sampleTargetCount",
            )
    if args.claimability == DEFAULT_CLAIMABILITY_MODE:
        value = first_config_value(
            payload,
            ["claimability.mode", "claimabilityMode"],
        )
        if value is not None:
            candidate = as_str(value, field="claimability.mode")
            if candidate not in VALID_CLAIMABILITY_MODES:
                raise ValueError(
                    f"invalid config claimability.mode={candidate}, expected one of {sorted(VALID_CLAIMABILITY_MODES)}"
                )
            args.claimability = candidate
    if args.claim_min_timed_samples == DEFAULT_CLAIM_MIN_TIMED_SAMPLES:
        value = first_config_value(
            payload,
            ["claimability.minTimedSamples", "claimMinTimedSamples"],
        )
        if value is not None:
            args.claim_min_timed_samples = as_int(
                value,
                field="claimability.minTimedSamples",
            )
    if args.benchmark_policy == DEFAULT_BENCHMARK_POLICY_PATH:
        value = first_config_value(
            payload,
            ["benchmarkPolicy.path", "benchmarkPolicyPath"],
        )
        if value is not None:
            args.benchmark_policy = as_str(value, field="benchmarkPolicy.path")

    if args.emit_shell is False:
        value = first_config_value(payload, ["run.emitShell", "emitShell"])
        if value is not None:
            args.emit_shell = as_bool(value, field="run.emitShell")

    return args


def resolve_benchmark_policy_path(explicit_path: str) -> Path:
    if explicit_path:
        candidate = Path(explicit_path)
        if candidate.exists():
            return candidate
        raise ValueError(f"missing benchmark policy config: {candidate}")

    for raw in DEFAULT_BENCHMARK_POLICY_CANDIDATES:
        candidate = Path(raw)
        if candidate.exists():
            return candidate
    raise ValueError(
        "missing benchmark policy config; checked "
        f"{', '.join(DEFAULT_BENCHMARK_POLICY_CANDIDATES)}"
    )


def load_benchmark_methodology_policy(explicit_path: str) -> BenchmarkMethodologyPolicy:
    path = resolve_benchmark_policy_path(explicit_path)
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid benchmark policy config: expected object in {path}")

    dispatch_ns = as_int(
        first_config_value(payload, ["timingSelection.minDispatchWindowNsWithoutEncode"]),
        field="timingSelection.minDispatchWindowNsWithoutEncode",
    )
    dispatch_coverage = as_float(
        first_config_value(
            payload,
            ["timingSelection.minDispatchWindowCoveragePercentWithoutEncode"],
        ),
        field="timingSelection.minDispatchWindowCoveragePercentWithoutEncode",
    )
    local_min_samples = as_int(
        first_config_value(payload, ["claimabilityDefaults.localMinTimedSamples"]),
        field="claimabilityDefaults.localMinTimedSamples",
    )
    release_min_samples = as_int(
        first_config_value(payload, ["claimabilityDefaults.releaseMinTimedSamples"]),
        field="claimabilityDefaults.releaseMinTimedSamples",
    )

    if dispatch_ns < 0:
        raise ValueError("timingSelection.minDispatchWindowNsWithoutEncode must be >= 0")
    if dispatch_coverage < 0.0:
        raise ValueError(
            "timingSelection.minDispatchWindowCoveragePercentWithoutEncode must be >= 0"
        )
    if local_min_samples < 0:
        raise ValueError("claimabilityDefaults.localMinTimedSamples must be >= 0")
    if release_min_samples < 0:
        raise ValueError("claimabilityDefaults.releaseMinTimedSamples must be >= 0")

    return BenchmarkMethodologyPolicy(
        source_path=str(path),
        min_dispatch_window_ns_without_encode=dispatch_ns,
        min_dispatch_window_coverage_percent_without_encode=dispatch_coverage,
        local_claim_min_timed_samples=local_min_samples,
        release_claim_min_timed_samples=release_min_samples,
    )


def maybe_override_render_encode_timing(
    *,
    workload: Workload,
    measured_ms: float,
    measured_source: str,
    measured_meta: dict[str, Any],
    trace_meta: dict[str, Any],
    required_timing_class: str,
) -> tuple[float, str, dict[str, Any]]:
    if required_timing_class == "process-wall":
        return measured_ms, measured_source, measured_meta
    if workload.domain not in RENDER_ENCODE_TIMING_DOMAINS:
        return measured_ms, measured_source, measured_meta
    if measured_source not in (
        "fawn-execution-dispatch-window-ns",
        "fawn-execution-total-ns",
        "fawn-execution-row-total-ns",
    ):
        return measured_ms, measured_source, measured_meta
    execution_encode_total_ns = safe_int(trace_meta.get("executionEncodeTotalNs"), default=-1)
    execution_dispatch_count = safe_int(trace_meta.get("executionDispatchCount"), default=0)
    if execution_encode_total_ns <= 0 or execution_dispatch_count <= 0:
        return measured_ms, measured_source, measured_meta

    encode_ms = float(execution_encode_total_ns) / 1_000_000.0
    timing_meta = dict(measured_meta)
    timing_meta.update(
        {
            "timingSelectionPolicy": "render-encode-only",
            "renderEncodeTimingDomain": workload.domain,
            "renderEncodeTimingBaseSource": measured_source,
            "renderEncodeTotalNs": execution_encode_total_ns,
            "traceMetaSource": "fawn-execution-encode-ns",
            "traceMetaTimingMs": encode_ms,
        }
    )
    return encode_ms, "fawn-execution-encode-ns", timing_meta


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def percent_delta(left: float, right: float) -> float:
    if right == 0.0:
        return 0.0
    return ((right - left) / right) * 100.0


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            try:
                return int(text)
            except ValueError:
                return None
    return None


def dawn_metric_median_ms(trace_meta: dict[str, Any], metric_name: str) -> float | None:
    medians = trace_meta.get("dawnMetricMediansMs")
    if not isinstance(medians, dict):
        return None
    value = safe_float(medians.get(metric_name))
    if value is None or value < 0.0:
        return None
    return value


def extract_timing_metrics_ms(
    trace_meta: dict[str, Any],
    *,
    wall_ms: float,
    cpu_ms: float,
) -> dict[str, float | None]:
    dawn_wall_ms = dawn_metric_median_ms(trace_meta, "wall_time")
    dawn_cpu_ms = dawn_metric_median_ms(trace_meta, "cpu_time")
    dawn_gpu_ms = dawn_metric_median_ms(trace_meta, "gpu_time")

    fawn_gpu_total_ns = safe_int(trace_meta.get("executionGpuTimestampTotalNs"), default=0)
    fawn_gpu_ms = (
        float(fawn_gpu_total_ns) / 1_000_000.0
        if fawn_gpu_total_ns > 0
        else None
    )

    return {
        "wall_time": dawn_wall_ms if dawn_wall_ms is not None else wall_ms,
        "cpu_time": dawn_cpu_ms if dawn_cpu_ms is not None else cpu_ms,
        "gpu_time": dawn_gpu_ms if dawn_gpu_ms is not None else fawn_gpu_ms,
    }


def normalize_timing_metrics_ms(
    metrics_ms: dict[str, float | None],
    divisor: float,
) -> dict[str, float | None]:
    normalized: dict[str, float | None] = {}
    for key, value in metrics_ms.items():
        if value is None:
            normalized[key] = None
            continue
        normalized[key] = value / divisor if divisor > 0.0 else value
    return normalized


def read_process_rss_kb(pid: int) -> int:
    status_path = Path("/proc") / str(pid) / "status"
    try:
        lines = status_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        if not line.startswith("VmRSS:"):
            continue
        parts = line.split()
        if len(parts) < 2:
            return 0
        parsed = parse_int(parts[1])
        return parsed if parsed is not None else 0
    return 0


def read_rocm_vram_snapshot() -> tuple[dict[str, int] | None, str | None]:
    cmd = ["rocm-smi", "--showmeminfo", "vram", "--json"]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=2.0,
        )
    except FileNotFoundError:
        return None, "rocm-smi not found"
    except subprocess.TimeoutExpired:
        return None, "rocm-smi timeout"

    if proc.returncode != 0:
        err = proc.stderr.strip() or f"rocm-smi exited with rc={proc.returncode}"
        return None, err

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, "rocm-smi returned invalid JSON"

    if not isinstance(payload, dict):
        return None, "rocm-smi returned non-object payload"

    used_total = 0
    total_total = 0
    card_count = 0
    for card_payload in payload.values():
        if not isinstance(card_payload, dict):
            continue
        used = parse_int(card_payload.get("VRAM Total Used Memory (B)"))
        total = parse_int(card_payload.get("VRAM Total Memory (B)"))
        if used is None or total is None:
            continue
        used_total += used
        total_total += total
        card_count += 1

    if card_count == 0:
        return None, "rocm-smi payload missing VRAM totals"

    return {
        "usedBytes": used_total,
        "totalBytes": total_total,
        "cardCount": card_count,
    }, None


def assert_json_object(payload: Any, *, context: str, path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context}: invalid JSON object in {path}")
    return payload


def parse_trace_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return assert_json_object(load_json(path), context="trace-meta", path=path)
    except json.JSONDecodeError:
        return {}
    except ValueError:
        return {}


def materialize_repeated_commands(
    commands_path: str,
    *,
    repeat: int,
    out_dir: Path,
    side_name: str,
) -> str:
    if repeat <= 1:
        return commands_path

    source_path = Path(commands_path)
    if not source_path.exists():
        raise ValueError(
            f"command repeat requested but commands file does not exist: {commands_path}"
        )

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid commands JSON for repeat expansion ({commands_path}): {exc}"
        ) from exc

    if not isinstance(payload, list):
        raise ValueError(
            f"command repeat requires a JSON array of commands, got {type(payload).__name__} in {commands_path}"
        )

    expanded = payload * repeat
    generated = out_dir / f"{side_name}.commands.repeat{repeat}.json"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(json.dumps(expanded, indent=2) + "\n", encoding="utf-8")
    return str(generated)


def command_for(
    template: str,
    *,
    workload: Workload,
    workload_id: str,
    commands_path: str,
    trace_jsonl: Path,
    trace_meta: Path,
    extra_args: list[str],
) -> list[str]:
    ctx = {
        "commands": shlex.quote(commands_path),
        "quirks": shlex.quote(workload.quirks_path),
        "vendor": shlex.quote(workload.vendor),
        "api": shlex.quote(workload.api),
        "family": shlex.quote(workload.family),
        "driver": shlex.quote(workload.driver),
        "workload": shlex.quote(workload_id),
        "dawn_filter": shlex.quote(workload.dawn_filter),
        "trace_jsonl": shlex.quote(str(trace_jsonl)),
        "trace_meta": shlex.quote(str(trace_meta)),
        "extra_args": shlex.join(extra_args),
    }
    resolved = template.format(**ctx)
    return shlex.split(resolved)


def run_once(
    command: list[str],
    *,
    gpu_memory_probe: str,
    resource_sample_ms: int,
    resource_sample_target_count: int,
) -> tuple[float, float, int, dict[str, Any]]:
    wrapped_command = command
    time_bin = Path("/usr/bin/time")
    if time_bin.exists():
        wrapped_command = [str(time_bin), "-f", f"{MAX_RSS_MARKER}%M", *command]

    cpu_usage_before = py_resource.getrusage(py_resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+b") as stdout_capture, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_capture:
        popen = subprocess.Popen(
            wrapped_command,
            stdout=stdout_capture,
            stderr=stderr_capture,
        )

        sample_interval_s = max(resource_sample_ms, 1) / 1000.0
        process_peak_rss_kb = 0
        sample_count = 0
        sampling_truncated = False

        gpu_probe_error: str | None = None
        gpu_before: dict[str, int] | None = None
        gpu_peak: dict[str, int] | None = None

        if gpu_memory_probe == "rocm-smi":
            gpu_before, gpu_probe_error = read_rocm_vram_snapshot()
            if gpu_before is not None:
                gpu_peak = dict(gpu_before)

        while True:
            process_running = popen.poll() is None
            if process_running:
                process_peak_rss_kb = max(process_peak_rss_kb, read_process_rss_kb(popen.pid))
            sample_count += 1

            if gpu_memory_probe == "rocm-smi":
                snapshot, err = read_rocm_vram_snapshot()
                if snapshot is not None:
                    if gpu_peak is None:
                        gpu_peak = dict(snapshot)
                    elif snapshot.get("usedBytes", 0) > gpu_peak.get("usedBytes", 0):
                        gpu_peak = dict(snapshot)
                elif gpu_probe_error is None and err:
                    gpu_probe_error = err

            if resource_sample_target_count > 0 and sample_count >= resource_sample_target_count:
                if process_running:
                    sampling_truncated = True
                    popen.wait()
                break

            if resource_sample_target_count <= 0 and not process_running:
                break

            if resource_sample_target_count > 0:
                time.sleep(sample_interval_s)
                continue

            try:
                popen.wait(timeout=sample_interval_s)
            except subprocess.TimeoutExpired:
                pass

        popen.wait()
        stdout_capture.seek(0)
        stderr_capture.seek(0)
        stdout = stdout_capture.read().decode("utf-8", errors="replace")
        stderr = stderr_capture.read().decode("utf-8", errors="replace")

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        cpu_usage_after = py_resource.getrusage(py_resource.RUSAGE_CHILDREN)
        process_cpu_ms = max(
            0.0,
            (
                (cpu_usage_after.ru_utime + cpu_usage_after.ru_stime)
                - (cpu_usage_before.ru_utime + cpu_usage_before.ru_stime)
            )
            * 1000.0,
        )

        stderr_lines: list[str] = []
        stderr_text = stderr if isinstance(stderr, str) else ""
        for raw_line in stderr_text.splitlines():
            line = raw_line.strip()
            if line.startswith(MAX_RSS_MARKER):
                parsed_rss = parse_int(line[len(MAX_RSS_MARKER):].strip())
                if parsed_rss is not None:
                    process_peak_rss_kb = max(process_peak_rss_kb, parsed_rss)
                continue
            stderr_lines.append(raw_line)
        sanitized_stderr = "\n".join(stderr_lines).strip()

        gpu_after: dict[str, int] | None = None
        if gpu_memory_probe == "rocm-smi":
            gpu_after, err = read_rocm_vram_snapshot()
            if gpu_after is not None:
                if gpu_peak is None or gpu_after.get("usedBytes", 0) > gpu_peak.get("usedBytes", 0):
                    gpu_peak = dict(gpu_after)
            elif gpu_probe_error is None and err:
                gpu_probe_error = err

        resource: dict[str, Any] = {
            "resourceSampleMs": max(resource_sample_ms, 1),
            "resourceSampleCount": sample_count,
            "resourceSampleTargetCount": max(resource_sample_target_count, 0),
            "resourceSamplingTruncated": sampling_truncated,
            "processWallMs": elapsed_ms,
            "processCpuMs": process_cpu_ms,
            "processPeakRssKb": process_peak_rss_kb,
            "gpuMemoryProbe": gpu_memory_probe,
            "gpuMemoryProbeAvailable": False,
        }

        if gpu_memory_probe == "rocm-smi":
            resource["gpuMemoryProbeError"] = gpu_probe_error or ""
            if gpu_before is not None:
                resource["gpuVramUsedBeforeBytes"] = gpu_before.get("usedBytes", 0)
                resource["gpuVramTotalBytes"] = gpu_before.get("totalBytes", 0)
                resource["gpuVramCardCount"] = gpu_before.get("cardCount", 0)
            if gpu_after is not None:
                resource["gpuVramUsedAfterBytes"] = gpu_after.get("usedBytes", 0)
                if "gpuVramTotalBytes" not in resource:
                    resource["gpuVramTotalBytes"] = gpu_after.get("totalBytes", 0)
                    resource["gpuVramCardCount"] = gpu_after.get("cardCount", 0)
            if gpu_peak is not None:
                resource["gpuVramUsedPeakBytes"] = gpu_peak.get("usedBytes", 0)
            if gpu_before is not None and gpu_peak is not None:
                resource["gpuVramDeltaPeakFromBeforeBytes"] = max(
                    0,
                    gpu_peak.get("usedBytes", 0) - gpu_before.get("usedBytes", 0),
                )
                resource["gpuMemoryProbeAvailable"] = True

        if popen.returncode != 0:
            stdout_text = stdout.strip() if isinstance(stdout, str) else ""
            raise RuntimeError(
                f"command failed (rc={popen.returncode}): {' '.join(command)}\n"
                f"stdout={stdout_text}\nstderr={sanitized_stderr}"
            )

        return elapsed_ms, process_cpu_ms, popen.returncode, resource


def run_workload(
    name: str,
    template: str,
    workload: Workload,
    iterations: int,
    warmup: int,
    out_dir: Path,
    gpu_memory_probe: str,
    resource_sample_ms: int,
    resource_sample_target_count: int,
    timing_divisor: float,
    command_repeat: int,
    ignore_first_ops: int,
    upload_buffer_usage: str,
    upload_submit_every: int,
    inject_upload_runtime_flags: bool,
    required_timing_class: str,
    benchmark_policy: BenchmarkMethodologyPolicy,
    emit_shell: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    commands_path = materialize_repeated_commands(
        workload.commands_path,
        repeat=command_repeat,
        out_dir=out_dir,
        side_name=name,
    )
    timings: list[float] = []
    run_records: list[dict[str, Any]] = []
    sample_meta: dict[str, Any] = {}
    last_meta = {}

    for run_idx in range(max(iterations, 0)):
        trace_jsonl = out_dir / f"{name}.run{run_idx:03d}.ndjson"
        trace_meta = out_dir / f"{name}.run{run_idx:03d}.meta.json"
        effective_extra_args = list(workload.extra_args)
        if inject_upload_runtime_flags and workload.domain == "upload" and "fawn-zig-runtime" in template:
            effective_extra_args.extend(
                [
                    "--upload-buffer-usage",
                    upload_buffer_usage,
                    "--upload-submit-every",
                    str(upload_submit_every),
                ]
            )
        command = command_for(
            template,
            workload=workload,
            workload_id=workload.id,
            commands_path=commands_path,
            trace_jsonl=trace_jsonl,
            trace_meta=trace_meta,
            extra_args=effective_extra_args,
        )
        if emit_shell:
            run_records.append(
                {
                    "runIndex": run_idx,
                    "command": " ".join(command),
                    "commandRepeat": command_repeat,
                    "uploadIgnoreFirstOps": ignore_first_ops,
                    "uploadBufferUsage": upload_buffer_usage,
                    "uploadSubmitEvery": upload_submit_every,
                    "timingNormalizationDivisor": timing_divisor,
                }
            )
            continue

        if run_idx < warmup:
            run_once(
                command,
                gpu_memory_probe=gpu_memory_probe,
                resource_sample_ms=resource_sample_ms,
                resource_sample_target_count=resource_sample_target_count,
            )
            continue

        elapsed_ms, process_cpu_ms, rc, resource = run_once(
            command,
            gpu_memory_probe=gpu_memory_probe,
            resource_sample_ms=resource_sample_ms,
            resource_sample_target_count=resource_sample_target_count,
        )
        sample_meta = parse_trace_meta(trace_meta)
        measured_ms, measured_source, measured_meta = pick_measured_timing_ms(
            wall_ms=elapsed_ms,
            trace_meta=sample_meta,
            trace_jsonl=trace_jsonl,
            required_timing_class=required_timing_class,
            benchmark_policy=benchmark_policy,
        )
        measured_ms, measured_source, measured_meta = maybe_override_render_encode_timing(
            workload=workload,
            measured_ms=measured_ms,
            measured_source=measured_source,
            measured_meta=measured_meta,
            trace_meta=sample_meta,
            required_timing_class=required_timing_class,
        )
        ignore_meta: dict[str, Any] = {}
        if required_timing_class != "process-wall" and ignore_first_ops > 0:
            measured_ms, measured_source, ignore_meta = maybe_adjust_timing_for_ignored_first_ops(
                measured_ms=measured_ms,
                measured_source=measured_source,
                trace_jsonl=trace_jsonl,
                ignore_first_ops=ignore_first_ops,
            )
        measured_raw_ms = measured_ms
        effective_timing_divisor = timing_divisor
        if required_timing_class == "process-wall":
            effective_timing_divisor = 1.0
        measured_ms = measured_raw_ms / effective_timing_divisor
        timing_metrics_raw_ms = extract_timing_metrics_ms(
            sample_meta,
            wall_ms=elapsed_ms,
            cpu_ms=process_cpu_ms,
        )
        timing_metrics_normalized_ms = normalize_timing_metrics_ms(
            timing_metrics_raw_ms,
            effective_timing_divisor,
        )
        measured_meta["timingNormalizationDivisor"] = effective_timing_divisor
        measured_meta["timingConfiguredDivisor"] = timing_divisor
        measured_meta["timingRawMs"] = measured_raw_ms
        measured_meta["timingNormalizedMs"] = measured_ms
        measured_meta["uploadBufferUsage"] = upload_buffer_usage
        measured_meta["uploadSubmitEvery"] = upload_submit_every
        if ignore_meta:
            measured_meta.update(ignore_meta)
        timings.append(measured_ms)
        run_records.append(
            {
                "runIndex": run_idx,
                "command": command,
                "elapsedMs": elapsed_ms,
                "measuredRawMs": measured_raw_ms,
                "measuredMs": measured_ms,
                "timingSource": measured_source,
                "timing": measured_meta,
                "traceJsonlPath": str(trace_jsonl),
                "traceMetaPath": str(trace_meta),
                "returnCode": rc,
                "resource": resource,
                "timingMetricsRawMs": timing_metrics_raw_ms,
                "timingMetricsNormalizedMs": timing_metrics_normalized_ms,
                "traceMeta": sample_meta,
                "commandRepeat": command_repeat,
                "uploadIgnoreFirstOps": ignore_first_ops,
                "uploadBufferUsage": upload_buffer_usage,
                "uploadSubmitEvery": upload_submit_every,
                "timingNormalizationDivisor": timing_divisor,
            }
        )
        last_meta = sample_meta

    if emit_shell:
        return {
            "commandSamples": run_records,
            "stats": format_stats([]),
            "timingsMs": [],
            "lastMeta": {},
            "resourceStats": summarize_resource_stats(run_records),
            "timingMetricsRawStatsMs": summarize_timing_metric_stats(run_records, "timingMetricsRawMs"),
            "timingMetricsNormalizedStatsMs": summarize_timing_metric_stats(run_records, "timingMetricsNormalizedMs"),
        }

    if not timings:
        return {
            "commandSamples": run_records,
            "stats": format_stats([]),
            "lastMeta": last_meta,
            "resourceStats": summarize_resource_stats(run_records),
            "timingMetricsRawStatsMs": summarize_timing_metric_stats(run_records, "timingMetricsRawMs"),
            "timingMetricsNormalizedStatsMs": summarize_timing_metric_stats(run_records, "timingMetricsNormalizedMs"),
        }

    timing_sources = sorted({str(sample.get("timingSource", "")) for sample in run_records})
    timing_classes = sorted(
        {
            classify_timing_source(str(sample.get("timingSource", "")))
            for sample in run_records
            if isinstance(sample.get("timingSource"), str)
        }
    )
    return {
        "commandSamples": run_records,
        "stats": format_stats(timings),
        "timingsMs": timings,
        "lastMeta": last_meta,
        "timingSources": timing_sources,
        "timingClasses": timing_classes,
        "resourceStats": summarize_resource_stats(run_records),
        "timingMetricsRawStatsMs": summarize_timing_metric_stats(run_records, "timingMetricsRawMs"),
        "timingMetricsNormalizedStatsMs": summarize_timing_metric_stats(run_records, "timingMetricsNormalizedMs"),
    }


def load_workloads(
    path: Path,
    workload_filter: str,
    include_noncomparable: bool,
    include_extended: bool,
) -> list[Workload]:
    cfg = load_json(path)
    if not isinstance(cfg, dict):
        raise ValueError(f"invalid workload file: expected top-level object at {path}")
    raw_workloads = cfg.get("workloads", [])
    selected = {w.strip() for w in workload_filter.split(",") if w.strip()} if workload_filter else set()
    if workload_filter and not selected:
        raise ValueError(f"invalid workload filter: {workload_filter}")
    result: list[Workload] = []
    for item in raw_workloads:
        if not isinstance(item, dict):
            raise ValueError(f"invalid workload entry in {path}: expected object")
        apples_to_apples_vetted = bool(item.get("applesToApplesVetted", False))
        workload = Workload(
            id=item["id"],
            name=item.get("name", item["id"]),
            description=item.get("description", ""),
            domain=item.get("domain", "uncategorized"),
            comparability_notes=item.get("comparabilityNotes", ""),
            commands_path=item.get("commandsPath", ""),
            quirks_path=item.get("quirksPath", ""),
            vendor=item.get("vendor", "intel"),
            api=item.get("api", "vulkan"),
            family=item.get("family", "gen12"),
            driver=item.get("driver", "31.0.101"),
            extra_args=item.get("extraArgs", []),
            left_command_repeat=parse_int(item.get("leftCommandRepeat")) or 1,
            right_command_repeat=parse_int(item.get("rightCommandRepeat")) or 1,
            left_ignore_first_ops=parse_int(item.get("leftIgnoreFirstOps")) or 0,
            right_ignore_first_ops=parse_int(item.get("rightIgnoreFirstOps")) or 0,
            left_upload_buffer_usage=str(
                item.get("leftUploadBufferUsage", "copy-dst-copy-src")
            ),
            right_upload_buffer_usage=str(
                item.get("rightUploadBufferUsage", "copy-dst-copy-src")
            ),
            left_upload_submit_every=(
                1
                if parse_int(item.get("leftUploadSubmitEvery")) is None
                else int(parse_int(item.get("leftUploadSubmitEvery")) or 0)
            ),
            right_upload_submit_every=(
                1
                if parse_int(item.get("rightUploadSubmitEvery")) is None
                else int(parse_int(item.get("rightUploadSubmitEvery")) or 0)
            ),
            dawn_filter=item.get("dawnFilter", ""),
            comparable=bool(item.get("comparable", False)),
            allow_left_no_execution=bool(item.get("allowLeftNoExecution", False)),
            include_by_default=bool(item.get("default", True)),
            left_timing_divisor=float(item.get("leftTimingDivisor", 1.0)),
            right_timing_divisor=float(item.get("rightTimingDivisor", 1.0)),
            timing_normalization_note=item.get("timingNormalizationNote", ""),
        )
        if workload.left_timing_divisor <= 0.0:
            raise ValueError(
                f"invalid workload {workload.id}: leftTimingDivisor must be > 0"
            )
        if workload.right_timing_divisor <= 0.0:
            raise ValueError(
                f"invalid workload {workload.id}: rightTimingDivisor must be > 0"
            )
        if workload.left_command_repeat < 1:
            raise ValueError(
                f"invalid workload {workload.id}: leftCommandRepeat must be >= 1"
            )
        if workload.right_command_repeat < 1:
            raise ValueError(
                f"invalid workload {workload.id}: rightCommandRepeat must be >= 1"
            )
        if workload.left_ignore_first_ops < 0:
            raise ValueError(
                f"invalid workload {workload.id}: leftIgnoreFirstOps must be >= 0"
            )
        if workload.right_ignore_first_ops < 0:
            raise ValueError(
                f"invalid workload {workload.id}: rightIgnoreFirstOps must be >= 0"
            )
        if workload.left_upload_buffer_usage not in VALID_UPLOAD_BUFFER_USAGES:
            raise ValueError(
                f"invalid workload {workload.id}: leftUploadBufferUsage must be one of "
                f"{sorted(VALID_UPLOAD_BUFFER_USAGES)}"
            )
        if workload.right_upload_buffer_usage not in VALID_UPLOAD_BUFFER_USAGES:
            raise ValueError(
                f"invalid workload {workload.id}: rightUploadBufferUsage must be one of "
                f"{sorted(VALID_UPLOAD_BUFFER_USAGES)}"
            )
        if workload.left_upload_submit_every < 1:
            raise ValueError(
                f"invalid workload {workload.id}: leftUploadSubmitEvery must be >= 1"
            )
        if workload.right_upload_submit_every < 1:
            raise ValueError(
                f"invalid workload {workload.id}: rightUploadSubmitEvery must be >= 1"
            )
        if (
            workload.comparable
            and workload.domain in NON_APPLES_TO_APPLES_DOMAINS
            and (not apples_to_apples_vetted)
        ):
            raise ValueError(
                f"invalid workload {workload.id}: domain={workload.domain} must be "
                "directional (comparable=false) unless applesToApplesVetted=true"
            )
        description_lower = workload.description.strip().lower()
        notes_lower = workload.comparability_notes.strip().lower()
        if workload.comparable and description_lower.startswith("directional "):
            raise ValueError(
                f"invalid workload {workload.id}: comparable=true conflicts with "
                "directional description; mark comparable=false or provide an apples-to-apples description"
            )
        if workload.comparable and "closest draw-call throughput proxy" in notes_lower:
            raise ValueError(
                f"invalid workload {workload.id}: comparable=true conflicts with proxy mapping note "
                "(closest draw-call throughput proxy); mark comparable=false"
            )
        if selected and workload.id not in selected:
            continue
        if not selected and (not include_extended) and (not workload.include_by_default):
            continue
        if (not include_noncomparable) and (not workload.comparable):
            continue
        result.append(workload)

    return result


format_stats = reporting_mod.format_stats
format_distribution = reporting_mod.format_distribution
summarize_timing_metric_stats = reporting_mod.summarize_timing_metric_stats
summarize_resource_stats = reporting_mod.summarize_resource_stats

parse_trace_rows = timing_selection_mod.parse_trace_rows
parse_execution_duration_ns_rows = timing_selection_mod.parse_execution_duration_ns_rows
maybe_adjust_timing_for_ignored_first_ops = timing_selection_mod.maybe_adjust_timing_for_ignored_first_ops
canonical_timing_source = timing_selection_mod.canonical_timing_source
classify_timing_source = timing_selection_mod.classify_timing_source
pick_measured_timing_ms = timing_selection_mod.pick_measured_timing_ms

is_dawn_writebuffer_upload_workload = comparability_mod.is_dawn_writebuffer_upload_workload
validate_upload_apples_to_apples = comparability_mod.validate_upload_apples_to_apples
compare_assessment = comparability_mod.compare_assessment

default_claim_min_timed_samples = claimability_mod.default_claim_min_timed_samples
required_positive_percentiles = claimability_mod.required_positive_percentiles
assess_upload_timing_scope_consistency = claimability_mod.assess_upload_timing_scope_consistency
assess_claimability = claimability_mod.assess_claimability


def main() -> int:
    args = parse_args()
    args = apply_config_defaults(args)

    if args.iterations < 0 or args.warmup < 0:
        raise ValueError("--iterations and --warmup must be >= 0")
    if args.resource_sample_ms < 1:
        raise ValueError("--resource-sample-ms must be >= 1")
    if args.resource_sample_target_count < 0:
        raise ValueError("--resource-sample-target-count must be >= 0")
    if args.claim_min_timed_samples < 0:
        raise ValueError("--claim-min-timed-samples must be >= 0")
    if not args.right_command_template:
        raise ValueError(
            "missing right command template: pass --right-command-template or "
            "--config with right.commandTemplate"
        )
    benchmark_policy = load_benchmark_methodology_policy(args.benchmark_policy)

    workloads_path = Path(args.workloads)
    workloads = load_workloads(
        workloads_path,
        args.workload_filter,
        include_noncomparable=bool(args.include_noncomparable_workloads),
        include_extended=bool(args.include_extended_workloads),
    )
    if not workloads:
        hint = ""
        if not args.include_noncomparable_workloads or not args.include_extended_workloads:
            hint = (
                " (selected workloads may be filtered by comparable=false/default=false; "
                "use --include-noncomparable-workloads and/or --include-extended-workloads)"
            )
        print(f"FAIL: no workloads selected{hint}")
        return 1

    if (
        not args.emit_shell
        and args.comparability == "strict"
        and args.require_timing_class == "operation"
    ):
        strict_upload_workload = next(
            (workload for workload in workloads if is_dawn_writebuffer_upload_workload(workload)),
            None,
        )
        if strict_upload_workload is not None:
            comparability_mod.verify_fawn_upload_runtime_contract(
                template=args.left_command_template,
                workload=strict_upload_workload,
                command_for_fn=command_for,
                runtime_source_paths=FAWN_UPLOAD_RUNTIME_SOURCE_PATHS,
            )

    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    workspace = output_paths.with_timestamp(
        args.workspace,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    out = output_paths.with_timestamp(
        args.out,
        output_timestamp,
        enabled=args.timestamp_output,
    )
    report: dict[str, Any] = {
        "schemaVersion": 4,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "outputTimestamp": output_timestamp,
        "outPath": str(out),
        "workspacePath": str(workspace),
        "runParameters": {
            "iterations": args.iterations,
            "warmup": args.warmup,
        },
        "left": {"name": args.left_name},
        "right": {"name": args.right_name},
        "deltaPercentConvention": {
            "baseline": "right",
            "formula": "((rightMs - leftMs) / rightMs) * 100",
            "positive": "left faster",
            "negative": "left slower",
            "zero": "parity",
        },
        "comparabilityPolicy": {
            "mode": args.comparability,
            "requiredTimingClass": args.require_timing_class,
            "allowLeftNoExecution": bool(args.allow_left_no_execution),
            "resourceProbe": args.resource_probe,
            "resourceSampleMs": args.resource_sample_ms,
            "resourceSampleTargetCount": args.resource_sample_target_count,
            "requireNativeExecutionTimingForLeftOperation": (
                args.require_timing_class == "operation"
            ),
            "obligationContract": {
                "schemaVersion": comparability_mod.OBLIGATION_SCHEMA_VERSION,
                "blockingFailureFailsComparability": True,
            },
            "dispatchWindowSelectionThresholds": {
                "minDispatchWindowNsWithoutEncode": benchmark_policy.min_dispatch_window_ns_without_encode,
                "minDispatchWindowCoveragePercentWithoutEncode": benchmark_policy.min_dispatch_window_coverage_percent_without_encode,
            },
        },
        "claimabilityPolicy": {
            "mode": args.claimability,
            "minTimedSamples": (
                args.claim_min_timed_samples
                if args.claim_min_timed_samples > 0
                else default_claim_min_timed_samples(args.claimability, benchmark_policy)
            ),
            "requiredPositivePercentiles": required_positive_percentiles(args.claimability),
            "defaults": {
                "localMinTimedSamples": benchmark_policy.local_claim_min_timed_samples,
                "releaseMinTimedSamples": benchmark_policy.release_claim_min_timed_samples,
            },
        },
        "benchmarkPolicy": {
            "path": benchmark_policy.source_path,
            "schemaVersion": 1,
            "sha256": file_sha256(Path(benchmark_policy.source_path)),
        },
        "workloadContract": {
            "path": str(workloads_path),
            "sha256": file_sha256(workloads_path),
        },
        "workloads": [],
    }
    if args.config:
        config_path = Path(args.config).resolve()
        report["configPath"] = str(config_path)
        if config_path.exists():
            report["configContract"] = {
                "path": str(config_path),
                "sha256": file_sha256(config_path),
            }

    overall_left = []
    overall_right = []
    comparability_failures: list[dict[str, Any]] = []
    claimability_failures: list[dict[str, Any]] = []
    previous_claim_row_hash = "0" * 64
    claim_row_hashes: list[str] = []

    for workload in workloads:
        validate_upload_apples_to_apples(
            workload,
            comparability_mode=args.comparability,
        )
        workload_dir = workspace / workload.id
        left = run_workload(
            name=args.left_name,
            template=args.left_command_template,
            workload=workload,
            iterations=args.iterations,
            warmup=args.warmup,
            out_dir=workload_dir / "left",
            gpu_memory_probe=args.resource_probe,
            resource_sample_ms=args.resource_sample_ms,
            resource_sample_target_count=args.resource_sample_target_count,
            timing_divisor=workload.left_timing_divisor,
            command_repeat=workload.left_command_repeat,
            ignore_first_ops=workload.left_ignore_first_ops,
            upload_buffer_usage=workload.left_upload_buffer_usage,
            upload_submit_every=workload.left_upload_submit_every,
            inject_upload_runtime_flags=True,
            required_timing_class=args.require_timing_class,
            benchmark_policy=benchmark_policy,
            emit_shell=args.emit_shell,
        )
        right = run_workload(
            name=args.right_name,
            template=args.right_command_template,
            workload=workload,
            iterations=args.iterations,
            warmup=args.warmup,
            out_dir=workload_dir / "right",
            gpu_memory_probe=args.resource_probe,
            resource_sample_ms=args.resource_sample_ms,
            resource_sample_target_count=args.resource_sample_target_count,
            timing_divisor=workload.right_timing_divisor,
            command_repeat=workload.right_command_repeat,
            ignore_first_ops=workload.right_ignore_first_ops,
            upload_buffer_usage=workload.right_upload_buffer_usage,
            upload_submit_every=workload.right_upload_submit_every,
            inject_upload_runtime_flags=False,
            required_timing_class=args.require_timing_class,
            benchmark_policy=benchmark_policy,
            emit_shell=args.emit_shell,
        )

        left_stats = left["stats"]
        right_stats = right["stats"]
        left_timings = left.get("timingsMs", [])
        right_timings = right.get("timingsMs", [])
        if not isinstance(left_timings, list):
            left_timings = []
        if not isinstance(right_timings, list):
            right_timings = []
        delta = {
            "p10Percent": percent_delta(safe_float(left_stats["p10Ms"]) or 0.0, safe_float(right_stats["p10Ms"]) or 0.0),
            "p50Percent": percent_delta(safe_float(left_stats["p50Ms"]) or 0.0, safe_float(right_stats["p50Ms"]) or 0.0),
            "p95Percent": percent_delta(safe_float(left_stats["p95Ms"]) or 0.0, safe_float(right_stats["p95Ms"]) or 0.0),
            "p99Percent": percent_delta(safe_float(left_stats["p99Ms"]) or 0.0, safe_float(right_stats["p99Ms"]) or 0.0),
            "meanPercent": percent_delta(safe_float(left_stats["meanMs"]) or 0.0, safe_float(right_stats["meanMs"]) or 0.0),
        }
        comparability = compare_assessment(
            workload_comparable=workload.comparable,
            workload_domain=workload.domain,
            left=left,
            right=right,
            required_timing_class=args.require_timing_class,
            allow_left_no_execution=(
                args.allow_left_no_execution or workload.allow_left_no_execution
            ),
            resource_probe=args.resource_probe,
            comparability_mode=args.comparability,
            resource_sample_target_count=args.resource_sample_target_count,
        )
        claimability = assess_claimability(
            mode=args.claimability,
            min_timed_samples=args.claim_min_timed_samples,
            workload=workload,
            left=left,
            right=right,
            delta=delta,
            comparability=comparability,
            benchmark_policy=benchmark_policy,
        )
        if not comparability["comparable"]:
            comparability_failures.append(
                {
                    "workloadId": workload.id,
                    "failedBlockingObligations": comparability.get(
                        "blockingFailedObligations", []
                    ),
                    "reasons": comparability["reasons"],
                }
            )
        if claimability.get("evaluated") is True and not claimability.get("claimable", False):
            claimability_failures.append(
                {
                    "workloadId": workload.id,
                    "reasons": claimability.get("reasons", []),
                }
            )

        if left_stats["count"] > 0:
            overall_left.extend([safe_float(v) for v in left_timings if safe_float(v) is not None])
        if right_stats["count"] > 0:
            overall_right.extend([safe_float(v) for v in right_timings if safe_float(v) is not None])

        left_trace_meta_hashes = collect_trace_meta_hashes(left.get("commandSamples", []))
        right_trace_meta_hashes = collect_trace_meta_hashes(right.get("commandSamples", []))
        claim_row_context = {
            "workloadId": workload.id,
            "workloadContractSha256": report["workloadContract"]["sha256"],
            "configContractSha256": (
                report.get("configContract", {}).get("sha256", "")
                if isinstance(report.get("configContract"), dict)
                else ""
            ),
            "benchmarkPolicySha256": report["benchmarkPolicy"]["sha256"],
            "leftTraceMetaSha256": [entry["sha256"] for entry in left_trace_meta_hashes],
            "rightTraceMetaSha256": [entry["sha256"] for entry in right_trace_meta_hashes],
            "deltaPercent": delta,
            "comparability": {
                "comparable": comparability.get("comparable"),
                "blockingFailedObligations": comparability.get(
                    "blockingFailedObligations", []
                ),
            },
            "claimability": {
                "evaluated": claimability.get("evaluated"),
                "claimable": claimability.get("claimable"),
                "reasons": claimability.get("reasons", []),
            },
        }
        claim_row_hash = json_sha256(
            {
                "previousHash": previous_claim_row_hash,
                "context": claim_row_context,
            }
        )

        report["workloads"].append(
            {
                "id": workload.id,
                "name": workload.name,
                "description": workload.description,
                "domain": workload.domain,
                "comparabilityNotes": workload.comparability_notes,
                "timingNormalization": {
                    "leftDivisor": workload.left_timing_divisor,
                    "rightDivisor": workload.right_timing_divisor,
                    "leftCommandRepeat": workload.left_command_repeat,
                    "rightCommandRepeat": workload.right_command_repeat,
                    "leftIgnoreFirstOps": workload.left_ignore_first_ops,
                    "rightIgnoreFirstOps": workload.right_ignore_first_ops,
                    "leftUploadBufferUsage": workload.left_upload_buffer_usage,
                    "rightUploadBufferUsage": workload.right_upload_buffer_usage,
                    "leftUploadSubmitEvery": workload.left_upload_submit_every,
                    "rightUploadSubmitEvery": workload.right_upload_submit_every,
                    "note": workload.timing_normalization_note,
                },
                "workloadComparable": workload.comparable,
                "workloadAllowLeftNoExecution": workload.allow_left_no_execution,
                "workloadDefault": workload.include_by_default,
                "left": left,
                "right": right,
                "deltaPercent": delta,
                "comparability": comparability,
                "claimability": claimability,
                "traceMetaHashes": {
                    "left": left_trace_meta_hashes,
                    "right": right_trace_meta_hashes,
                },
                "claimRowHash": {
                    "algorithm": "sha256",
                    "previousHash": previous_claim_row_hash,
                    "hash": claim_row_hash,
                    "context": claim_row_context,
                },
            }
        )
        claim_row_hashes.append(claim_row_hash)
        previous_claim_row_hash = claim_row_hash

    if overall_left and overall_right:
        overall_left_stats = format_stats(overall_left)
        overall_right_stats = format_stats(overall_right)
        report["overall"] = {
            "left": overall_left_stats,
            "right": overall_right_stats,
            "deltaPercent": {
                "p10Approx": percent_delta(
                    safe_float(overall_left_stats["p10Ms"]) or 0.0,
                    safe_float(overall_right_stats["p10Ms"]) or 0.0,
                ),
                "p50Approx": percent_delta(
                    safe_float(overall_left_stats["p50Ms"]) or 0.0,
                    safe_float(overall_right_stats["p50Ms"]) or 0.0,
                ),
                "p95Approx": percent_delta(
                    safe_float(overall_left_stats["p95Ms"]) or 0.0,
                    safe_float(overall_right_stats["p95Ms"]) or 0.0,
                ),
                "p99Approx": percent_delta(
                    safe_float(overall_left_stats["p99Ms"]) or 0.0,
                    safe_float(overall_right_stats["p99Ms"]) or 0.0,
                ),
            },
        }

    obligation_failure_counts: dict[str, int] = {}
    for failure in comparability_failures:
        failed_obligations = failure.get("failedBlockingObligations", [])
        if not isinstance(failed_obligations, list):
            continue
        for obligation_id in failed_obligations:
            if not isinstance(obligation_id, str) or not obligation_id:
                continue
            obligation_failure_counts[obligation_id] = (
                obligation_failure_counts.get(obligation_id, 0) + 1
            )

    report["comparabilitySummary"] = {
        "workloadCount": len(workloads),
        "nonComparableCount": len(comparability_failures),
        "nonComparableWorkloads": comparability_failures,
        "failedBlockingObligationCounts": dict(sorted(obligation_failure_counts.items())),
    }
    report["comparisonStatus"] = "comparable" if not comparability_failures else "unreliable"
    report["claimabilitySummary"] = {
        "workloadCount": len(workloads),
        "nonClaimableCount": len(claimability_failures),
        "nonClaimableWorkloads": claimability_failures,
    }
    report["claimRowHashChain"] = {
        "algorithm": "sha256",
        "count": len(claim_row_hashes),
        "startPreviousHash": "0" * 64,
        "finalHash": claim_row_hashes[-1] if claim_row_hashes else "",
    }
    if args.claimability == "off":
        report["claimStatus"] = "not-evaluated"
    else:
        report["claimStatus"] = "claimable" if not claimability_failures else "diagnostic"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    run_status = "passed"
    if comparability_failures and args.comparability == "strict":
        run_status = "failed"
    elif args.claimability != "off" and claimability_failures:
        run_status = "failed"
    elif comparability_failures and args.comparability == "warn":
        run_status = "diagnostic"
    output_paths.write_run_manifest_for_outputs(
        [out, workspace],
        {
            "runType": "compare_dawn_vs_fawn",
            "config": str(Path(args.config)) if args.config else "",
            "fullRun": not args.emit_shell,
            "claimGateRan": False,
            "dropinGateRan": False,
            "reportPath": str(out),
            "workspacePath": str(workspace),
            "status": run_status,
        },
    )
    if args.emit_shell:
        print(json.dumps({"resolvedCommandsOnly": True, "out": str(out)}, indent=2))
        return 0

    if comparability_failures and args.comparability in ("strict", "warn"):
        summary = {
            "out": str(out),
            "workloadCount": len(workloads),
            "comparisonStatus": report["comparisonStatus"],
            "nonComparableCount": len(comparability_failures),
            "nonComparableWorkloads": comparability_failures,
            "claimStatus": report["claimStatus"],
        }
        print(json.dumps(summary, indent=2))
        if args.comparability == "strict":
            return 2
        return 0

    if args.claimability != "off" and claimability_failures:
        summary = {
            "out": str(out),
            "workloadCount": len(workloads),
            "comparisonStatus": report["comparisonStatus"],
            "claimStatus": report["claimStatus"],
            "nonClaimableCount": len(claimability_failures),
            "nonClaimableWorkloads": claimability_failures,
        }
        print(json.dumps(summary, indent=2))
        return 3

    print(
        json.dumps(
            {
                "out": str(out),
                "workloadCount": len(workloads),
                "comparisonStatus": report["comparisonStatus"],
                "claimStatus": report["claimStatus"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
