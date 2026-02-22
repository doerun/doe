#!/usr/bin/env python3
"""
Dawn/Fawn side-by-side benchmark runner.

This script executes shared workload command templates for both runtimes and emits
timing traces where available, with wall-time as a fallback.
"""

from __future__ import annotations

import argparse
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
VALID_COMPARABILITY_MODES = {"strict", "warn", "off"}
VALID_REQUIRED_TIMING_CLASSES = {"any", "operation", "process-wall"}
VALID_RESOURCE_PROBES = {"none", "rocm-smi"}
VALID_CLAIMABILITY_MODES = {"off", "local", "release"}
VALID_UPLOAD_BUFFER_USAGES = {"copy-dst-copy-src", "copy-dst"}
MIN_DISPATCH_WINDOW_NS_WITHOUT_ENCODE = 100_000
MIN_DISPATCH_WINDOW_TOTAL_COVERAGE_PERCENT_WITHOUT_ENCODE = 1.0
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
    "fawn-execution-gpu-timestamp-ns",
}


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
    include_by_default: bool
    left_timing_divisor: float
    right_timing_divisor: float
    timing_normalization_note: str


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

    if args.emit_shell is False:
        value = first_config_value(payload, ["run.emitShell", "emitShell"])
        if value is not None:
            args.emit_shell = as_bool(value, field="run.emitShell")

    return args


def format_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "minMs": 0.0,
            "maxMs": 0.0,
            "p5Ms": 0.0,
            "p50Ms": 0.0,
            "p95Ms": 0.0,
            "p99Ms": 0.0,
            "meanMs": 0.0,
            "stdevMs": 0.0,
        }

    sorted_values = sorted(values)
    def percentile(p: float) -> float:
        if not sorted_values:
            return 0.0
        index = int((len(sorted_values) - 1) * p)
        return sorted_values[index]

    return {
        "count": len(values),
        "minMs": min(values),
        "maxMs": max(values),
        "p5Ms": percentile(0.05),
        "p50Ms": percentile(0.5),
        "p95Ms": percentile(0.95),
        "p99Ms": percentile(0.99),
        "meanMs": statistics.fmean(values),
        "stdevMs": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def format_distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "p5": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "mean": 0.0,
            "stdev": 0.0,
        }

    sorted_values = sorted(values)

    def percentile(p: float) -> float:
        if not sorted_values:
            return 0.0
        index = int((len(sorted_values) - 1) * p)
        return sorted_values[index]

    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "p5": percentile(0.05),
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "mean": statistics.fmean(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def parse_trace_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            print(f"WARN: invalid trace jsonl row in {path}: {exc}")
            return []
    return rows


def parse_execution_duration_ns_rows(path: Path) -> list[int]:
    rows = parse_trace_rows(path)
    durations: list[int] = []
    for row in rows:
        duration_ns = safe_int(row.get("executionDurationNs"), default=-1)
        if duration_ns >= 0:
            durations.append(duration_ns)
    return durations


def maybe_adjust_timing_for_ignored_first_ops(
    *,
    measured_ms: float,
    measured_source: str,
    trace_jsonl: Path,
    ignore_first_ops: int,
) -> tuple[float, str, dict[str, Any]]:
    if ignore_first_ops <= 0:
        return measured_ms, measured_source, {
            "uploadIgnoreFirstOps": 0,
            "uploadIgnoreFirstApplied": False,
        }

    durations_ns = parse_execution_duration_ns_rows(trace_jsonl)
    if not durations_ns:
        return measured_ms, measured_source, {
            "uploadIgnoreFirstOps": ignore_first_ops,
            "uploadIgnoreFirstApplied": False,
            "uploadIgnoreFirstReason": "trace has no executionDurationNs rows",
        }

    if len(durations_ns) <= ignore_first_ops:
        return measured_ms, measured_source, {
            "uploadIgnoreFirstOps": ignore_first_ops,
            "uploadIgnoreFirstApplied": False,
            "uploadIgnoreFirstReason": (
                "trace row count is not greater than ignore count "
                f"({len(durations_ns)} <= {ignore_first_ops})"
            ),
        }

    adjusted_ns = sum(durations_ns[ignore_first_ops:])
    adjusted_ms = float(adjusted_ns) / 1_000_000.0
    # Ignore-first is computed from row-level executionDurationNs, so we expose
    # the adjusted source explicitly instead of inheriting the pre-adjustment source.
    adjusted_source = "fawn-execution-row-total-ns+ignore-first-ops"
    return adjusted_ms, adjusted_source, {
        "uploadIgnoreFirstOps": ignore_first_ops,
        "uploadIgnoreFirstApplied": True,
        "uploadIgnoreFirstBaseTimingSource": measured_source,
        "uploadIgnoreFirstAdjustedTimingSource": "fawn-execution-row-total-ns",
        "uploadRowsTotal": len(durations_ns),
        "uploadRowsIncluded": len(durations_ns) - ignore_first_ops,
        "uploadTimingRawMsBeforeIgnore": measured_ms,
        "uploadTimingRawMsAfterIgnore": adjusted_ms,
    }


def is_dawn_writebuffer_upload_workload(workload: Workload) -> bool:
    if workload.domain != "upload":
        return False
    return (
        "BufferUploadPerf.Run/" in workload.dawn_filter
        and "WriteBuffer" in workload.dawn_filter
    )


def validate_upload_apples_to_apples(
    workload: Workload,
    *,
    comparability_mode: str,
) -> None:
    if workload.left_upload_submit_every < 1:
        raise ValueError(
            f"invalid workload {workload.id}: leftUploadSubmitEvery must be >= 1"
        )
    if workload.right_upload_submit_every < 1:
        raise ValueError(
            f"invalid workload {workload.id}: rightUploadSubmitEvery must be >= 1"
        )
    if workload.left_command_repeat % workload.left_upload_submit_every != 0:
        raise ValueError(
            f"invalid workload {workload.id}: leftCommandRepeat ({workload.left_command_repeat}) "
            f"must be divisible by leftUploadSubmitEvery ({workload.left_upload_submit_every})"
        )
    if workload.right_command_repeat % workload.right_upload_submit_every != 0:
        raise ValueError(
            f"invalid workload {workload.id}: rightCommandRepeat ({workload.right_command_repeat}) "
            f"must be divisible by rightUploadSubmitEvery ({workload.right_upload_submit_every})"
        )

    if not is_dawn_writebuffer_upload_workload(workload):
        return

    if comparability_mode == "strict" and workload.left_upload_buffer_usage != "copy-dst":
        raise ValueError(
            "strict upload comparability requires leftUploadBufferUsage=copy-dst "
            f"for Dawn WriteBuffer workload {workload.id}; got {workload.left_upload_buffer_usage}"
        )


def find_fawn_runtime_index(command: list[str]) -> int | None:
    for idx, token in enumerate(command):
        if Path(token).name == "fawn-zig-runtime":
            return idx
    return None


def subprocess_combined_output(proc: subprocess.CompletedProcess[str]) -> str:
    stdout = proc.stdout if isinstance(proc.stdout, str) else ""
    stderr = proc.stderr if isinstance(proc.stderr, str) else ""
    return f"{stdout}\n{stderr}".strip()


def assert_runtime_not_stale(runtime_binary: Path) -> None:
    if not runtime_binary.exists():
        return
    runtime_mtime = runtime_binary.stat().st_mtime
    stale_sources = [
        str(path)
        for path in FAWN_UPLOAD_RUNTIME_SOURCE_PATHS
        if path.exists() and path.stat().st_mtime > runtime_mtime
    ]
    if stale_sources:
        raise ValueError(
            "strict upload comparability requires a rebuilt fawn-zig-runtime binary; "
            "binary appears older than runtime sources: "
            + ", ".join(stale_sources)
        )


def verify_fawn_upload_runtime_contract(
    *,
    template: str,
    workload: Workload,
) -> None:
    queue_wait_mode_value: str | None = None
    for idx, arg in enumerate(workload.extra_args):
        if arg != "--queue-wait-mode":
            continue
        if idx + 1 >= len(workload.extra_args):
            raise ValueError(
                f"invalid workload {workload.id}: --queue-wait-mode requires a value"
            )
        queue_wait_mode_value = str(workload.extra_args[idx + 1])
        if queue_wait_mode_value not in ("process-events", "wait-any"):
            raise ValueError(
                f"invalid workload {workload.id}: --queue-wait-mode must be process-events|wait-any"
            )

    preflight_trace_jsonl = Path("/tmp/fawn-upload-preflight.ndjson")
    preflight_trace_meta = Path("/tmp/fawn-upload-preflight.meta.json")
    preflight_extra_args = list(workload.extra_args)
    preflight_extra_args.extend(
        [
            "--upload-buffer-usage",
            workload.left_upload_buffer_usage,
            "--upload-submit-every",
            str(workload.left_upload_submit_every),
        ]
    )
    command = command_for(
        template,
        workload=workload,
        workload_id=workload.id,
        commands_path=workload.commands_path,
        trace_jsonl=preflight_trace_jsonl,
        trace_meta=preflight_trace_meta,
        extra_args=preflight_extra_args,
    )
    runtime_index = find_fawn_runtime_index(command)
    if runtime_index is None:
        return

    runtime_token = command[runtime_index]
    runtime_binary = Path(runtime_token)
    if not runtime_binary.is_absolute():
        runtime_binary = Path.cwd() / runtime_binary
    assert_runtime_not_stale(runtime_binary)

    runtime_prefix = command[: runtime_index + 1]
    help_proc = subprocess.run(
        [*runtime_prefix, "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    help_output = subprocess_combined_output(help_proc)
    required_flags = ["--upload-buffer-usage", "--upload-submit-every"]
    if queue_wait_mode_value is not None:
        required_flags.append("--queue-wait-mode")
    missing_flags = [flag for flag in required_flags if flag not in help_output]
    if missing_flags:
        raise ValueError(
            "strict upload comparability requires runtime upload knobs to be supported by the "
            f"executed fawn-zig-runtime binary; missing help flags: {', '.join(missing_flags)}"
        )

    capability_checks = [
        (
            ["--upload-buffer-usage", "invalid-value", "--help"],
            "invalid --upload-buffer-usage",
        ),
        (
            ["--upload-submit-every", "0", "--help"],
            "invalid --upload-submit-every",
        ),
    ]
    if queue_wait_mode_value is not None:
        capability_checks.append(
            (
                ["--queue-wait-mode", "invalid-value", "--help"],
                "invalid --queue-wait-mode",
            )
        )
    for probe_args, expected_fragment in capability_checks:
        probe_proc = subprocess.run(
            [*runtime_prefix, *probe_args],
            text=True,
            capture_output=True,
            check=False,
        )
        probe_output = subprocess_combined_output(probe_proc)
        if expected_fragment not in probe_output:
            raise ValueError(
                "strict upload comparability requires runtime validation of upload knobs; "
                f"missing expected probe output '{expected_fragment}' for command: "
                f"{' '.join([*runtime_prefix, *probe_args])}"
            )


def canonical_timing_source(source: str) -> str:
    if not source:
        return ""
    # Derived timing sources preserve the base source plus explicit modifiers.
    return source.split("+", 1)[0]


def classify_timing_source(source: str) -> str:
    canonical = canonical_timing_source(source)
    if canonical in (
        "fawn-execution-total-ns",
        "fawn-execution-row-total-ns",
        "fawn-execution-dispatch-window-ns",
        "fawn-execution-gpu-timestamp-ns",
        "dawn-perf-wall-time",
        "dawn-perf-cpu-time",
        "dawn-perf-gpu-time",
        "dawn-perf-wall-ns",
        "fawn-trace-window",
    ):
        return "operation"
    if canonical == "wall-time":
        return "process-wall"
    return "unknown"


def pick_measured_timing_ms(
    wall_ms: float,
    trace_meta: dict[str, Any],
    trace_jsonl: Path,
    required_timing_class: str,
) -> tuple[float, str, dict[str, Any]]:
    if required_timing_class == "process-wall":
        timing_meta = {
            "source": "wall-time",
            "wallTimeMs": wall_ms,
            "timingSelectionPolicy": "forced-process-wall",
        }
        return wall_ms, "wall-time", timing_meta

    meta_timing_ms = safe_float(trace_meta.get("timingMs"))
    meta_source = trace_meta.get("timingSource")
    if meta_timing_ms is not None and meta_timing_ms >= 0.0:
        source = meta_source if isinstance(meta_source, str) and meta_source else "trace-meta"
        if source == "wall-time":
            timing_meta = {
                "source": "wall-time",
                "traceMetaSource": "wall-time",
                "traceMetaTimingMs": meta_timing_ms,
                "wallTimeMs": wall_ms,
                "timingSelectionPolicy": "outer-process-wall-time",
            }
            return wall_ms, "wall-time", timing_meta
        timing_meta = {
            "source": "trace-meta",
            "traceMetaSource": source,
            "traceMetaTimingMs": meta_timing_ms,
            "wallTimeMs": wall_ms,
        }
        return meta_timing_ms, source, timing_meta

    execution_total_ns = safe_int(trace_meta.get("executionTotalNs"), default=-1)
    execution_encode_total_ns = safe_int(trace_meta.get("executionEncodeTotalNs"), default=-1)
    execution_submit_wait_total_ns = safe_int(
        trace_meta.get("executionSubmitWaitTotalNs"), default=-1
    )
    execution_dispatch_count = safe_int(trace_meta.get("executionDispatchCount"), default=0)
    execution_row_count = safe_int(trace_meta.get("executionRowCount"), default=0)
    execution_success_count = safe_int(trace_meta.get("executionSuccessCount"), default=0)

    gpu_timestamp_total_ns = safe_int(
        trace_meta.get("executionGpuTimestampTotalNs"), default=-1
    )
    if gpu_timestamp_total_ns > 0:
        measured_ms = float(gpu_timestamp_total_ns) / 1_000_000.0
        timing_meta = {
            "source": "trace-meta",
            "traceMetaSource": "fawn-execution-gpu-timestamp-ns",
            "traceMetaTimingMs": measured_ms,
            "executionGpuTimestampTotalNs": gpu_timestamp_total_ns,
            "executionDispatchCount": execution_dispatch_count,
            "wallTimeMs": wall_ms,
        }
        return measured_ms, "fawn-execution-gpu-timestamp-ns", timing_meta

    has_execution_evidence = (
        execution_dispatch_count > 0
        or execution_row_count > 0
        or execution_success_count > 0
    )
    dispatch_window_ns = -1
    dispatch_window_rejected: dict[str, Any] | None = None
    if execution_encode_total_ns >= 0 and execution_submit_wait_total_ns >= 0:
        dispatch_window_ns = execution_encode_total_ns + execution_submit_wait_total_ns
        if dispatch_window_ns > 0 and has_execution_evidence:
            # If encode and dispatch are both absent, a tiny submit-only window is
            # usually queue flush bookkeeping noise, not workload operation time.
            # Keep dispatch-window timing only when it is meaningfully non-trivial.
            if (
                execution_dispatch_count == 0
                and execution_encode_total_ns == 0
                and execution_total_ns > 0
            ):
                coverage_percent = (
                    float(dispatch_window_ns) / float(execution_total_ns)
                ) * 100.0
                if (
                    dispatch_window_ns
                    < MIN_DISPATCH_WINDOW_NS_WITHOUT_ENCODE
                    and coverage_percent
                    < MIN_DISPATCH_WINDOW_TOTAL_COVERAGE_PERCENT_WITHOUT_ENCODE
                ):
                    dispatch_window_rejected = {
                        "reason": "dispatch-window-too-small-without-encode",
                        "dispatchWindowNs": dispatch_window_ns,
                        "dispatchWindowCoveragePercentOfExecutionTotal": coverage_percent,
                        "minDispatchWindowNs": MIN_DISPATCH_WINDOW_NS_WITHOUT_ENCODE,
                        "minDispatchWindowCoveragePercentOfExecutionTotal": MIN_DISPATCH_WINDOW_TOTAL_COVERAGE_PERCENT_WITHOUT_ENCODE,
                    }
                else:
                    measured_ms = float(dispatch_window_ns) / 1_000_000.0
                    timing_meta = {
                        "source": "trace-meta",
                        "traceMetaSource": "fawn-execution-dispatch-window-ns",
                        "traceMetaTimingMs": measured_ms,
                        "executionEncodeTotalNs": execution_encode_total_ns,
                        "executionSubmitWaitTotalNs": execution_submit_wait_total_ns,
                        "executionDispatchCount": execution_dispatch_count,
                        "executionRowCount": execution_row_count,
                        "executionSuccessCount": execution_success_count,
                        "wallTimeMs": wall_ms,
                    }
                    return measured_ms, "fawn-execution-dispatch-window-ns", timing_meta
            else:
                measured_ms = float(dispatch_window_ns) / 1_000_000.0
                timing_meta = {
                    "source": "trace-meta",
                    "traceMetaSource": "fawn-execution-dispatch-window-ns",
                    "traceMetaTimingMs": measured_ms,
                    "executionEncodeTotalNs": execution_encode_total_ns,
                    "executionSubmitWaitTotalNs": execution_submit_wait_total_ns,
                    "executionDispatchCount": execution_dispatch_count,
                    "executionRowCount": execution_row_count,
                    "executionSuccessCount": execution_success_count,
                    "wallTimeMs": wall_ms,
                }
                return measured_ms, "fawn-execution-dispatch-window-ns", timing_meta

    if execution_total_ns > 0 and has_execution_evidence:
        measured_ms = float(execution_total_ns) / 1_000_000.0
        timing_meta = {
            "source": "trace-meta",
            "traceMetaSource": "fawn-execution-total-ns",
            "traceMetaTimingMs": measured_ms,
            "executionDispatchCount": execution_dispatch_count,
            "executionRowCount": execution_row_count,
            "executionSuccessCount": execution_success_count,
            "wallTimeMs": wall_ms,
        }
        if dispatch_window_rejected is not None:
            timing_meta["dispatchWindowSelectionRejected"] = dispatch_window_rejected
        return measured_ms, "fawn-execution-total-ns", timing_meta

    trace_rows = parse_trace_rows(trace_jsonl)
    timing_meta: dict[str, Any] = {
        "source": "wall-time",
        "wallTimeMs": wall_ms,
        "traceRows": len(trace_rows),
    }

    if not trace_rows:
        return wall_ms, "wall-time", timing_meta

    timestamps: list[int] = []
    for row in trace_rows:
        ts = row.get("timestampMonoNs")
        if isinstance(ts, int):
            timestamps.append(ts)

    if len(timestamps) < 2:
        timing_meta["traceRows"] = len(timestamps)
        return wall_ms, "wall-time", timing_meta

    first = min(timestamps)
    last = max(timestamps)
    measured_ms = float(last - first) / 1_000_000.0

    if measured_ms < 0:
        timing_meta["traceRows"] = len(timestamps)
        return wall_ms, "wall-time", timing_meta

    timing_meta.update(
        {
            "source": "fawn-trace-window",
            "traceWindowStartMonoNs": first,
            "traceWindowEndMonoNs": last,
            "traceRows": len(timestamps),
            "rowCount": safe_int(trace_meta.get("rowCount"), default=0),
        }
    )
    return measured_ms, "fawn-trace-window", timing_meta


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


def summarize_timing_metric_stats(
    run_records: list[dict[str, Any]],
    field: str,
) -> dict[str, dict[str, float]]:
    metric_values: dict[str, list[float]] = {
        "wall_time": [],
        "cpu_time": [],
        "gpu_time": [],
    }
    for sample in run_records:
        metrics = sample.get(field)
        if not isinstance(metrics, dict):
            continue
        for metric in metric_values:
            value = safe_float(metrics.get(metric))
            if value is None:
                continue
            metric_values[metric].append(value)
    return {metric: format_stats(values) for metric, values in metric_values.items()}


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


def summarize_resource_stats(samples: list[dict[str, Any]]) -> dict[str, Any]:
    process_peak_rss_kb_values: list[float] = []
    gpu_vram_delta_peak_bytes_values: list[float] = []
    gpu_vram_peak_bytes_values: list[float] = []
    gpu_vram_before_bytes_values: list[float] = []
    gpu_vram_after_bytes_values: list[float] = []
    probe_modes: set[str] = set()
    gpu_probe_available_count = 0
    sampling_truncated_count = 0

    for sample in samples:
        resource = sample.get("resource")
        if not isinstance(resource, dict):
            continue
        probe_mode = resource.get("gpuMemoryProbe")
        if isinstance(probe_mode, str) and probe_mode:
            probe_modes.add(probe_mode)

        rss_kb = parse_int(resource.get("processPeakRssKb"))
        if rss_kb is not None:
            process_peak_rss_kb_values.append(float(rss_kb))

        gpu_available = resource.get("gpuMemoryProbeAvailable")
        if gpu_available is True:
            gpu_probe_available_count += 1
        if resource.get("resourceSamplingTruncated") is True:
            sampling_truncated_count += 1

        peak_delta = parse_int(resource.get("gpuVramDeltaPeakFromBeforeBytes"))
        if peak_delta is not None:
            gpu_vram_delta_peak_bytes_values.append(float(peak_delta))

        peak_used = parse_int(resource.get("gpuVramUsedPeakBytes"))
        if peak_used is not None:
            gpu_vram_peak_bytes_values.append(float(peak_used))

        before_used = parse_int(resource.get("gpuVramUsedBeforeBytes"))
        if before_used is not None:
            gpu_vram_before_bytes_values.append(float(before_used))

        after_used = parse_int(resource.get("gpuVramUsedAfterBytes"))
        if after_used is not None:
            gpu_vram_after_bytes_values.append(float(after_used))

    return {
        "gpuProbeModes": sorted(probe_modes),
        "gpuProbeAvailableCount": gpu_probe_available_count,
        "samplingTruncatedCount": sampling_truncated_count,
        "processPeakRssKb": format_distribution(process_peak_rss_kb_values),
        "gpuVramDeltaPeakFromBeforeBytes": format_distribution(gpu_vram_delta_peak_bytes_values),
        "gpuVramUsedPeakBytes": format_distribution(gpu_vram_peak_bytes_values),
        "gpuVramUsedBeforeBytes": format_distribution(gpu_vram_before_bytes_values),
        "gpuVramUsedAfterBytes": format_distribution(gpu_vram_after_bytes_values),
    }


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


def compare_assessment(
    *,
    workload_comparable: bool,
    left: dict[str, Any],
    right: dict[str, Any],
    required_timing_class: str,
    allow_left_no_execution: bool,
    resource_probe: str,
    comparability_mode: str,
    resource_sample_target_count: int,
) -> dict[str, Any]:
    left_samples = left.get("commandSamples", [])
    right_samples = right.get("commandSamples", [])

    left_sources = sorted({str(sample.get("timingSource", "")) for sample in left_samples})
    right_sources = sorted({str(sample.get("timingSource", "")) for sample in right_samples})
    left_classes = sorted({classify_timing_source(source) for source in left_sources if source})
    right_classes = sorted({classify_timing_source(source) for source in right_sources if source})
    reasons: list[str] = []

    if not workload_comparable:
        reasons.append("workload is marked non-comparable by workload contract")

    if not left_samples:
        reasons.append("left side has no measured samples")
    if not right_samples:
        reasons.append("right side has no measured samples")

    if len(left_classes) != 1:
        reasons.append(f"left side uses mixed timing classes: {left_classes}")
    if len(right_classes) != 1:
        reasons.append(f"right side uses mixed timing classes: {right_classes}")

    left_class = left_classes[0] if len(left_classes) == 1 else "mixed"
    right_class = right_classes[0] if len(right_classes) == 1 else "mixed"

    if required_timing_class == "operation":
        invalid_native_execution_sources: set[str] = set()
        for sample in left_samples:
            trace_meta = sample.get("traceMeta", {})
            if not isinstance(trace_meta, dict):
                continue
            if str(trace_meta.get("executionBackend", "")) != "webgpu-ffi":
                continue
            execution_dispatch = safe_int(trace_meta.get("executionDispatchCount"), default=0)
            execution_success = safe_int(trace_meta.get("executionSuccessCount"), default=0)
            execution_rows = safe_int(trace_meta.get("executionRowCount"), default=0)
            if execution_dispatch <= 0 and execution_success <= 0 and execution_rows <= 0:
                continue
            timing_source_raw = sample.get("timingSource")
            if not isinstance(timing_source_raw, str) or not timing_source_raw:
                invalid_native_execution_sources.add("<missing>")
                continue
            canonical_source = canonical_timing_source(timing_source_raw)
            if canonical_source not in NATIVE_EXECUTION_OPERATION_TIMING_SOURCES:
                invalid_native_execution_sources.add(canonical_source)
        if invalid_native_execution_sources:
            reasons.append(
                "left side uses non-native operation timing source(s) for webgpu-ffi execution: "
                + ", ".join(sorted(invalid_native_execution_sources))
            )

    if required_timing_class != "any":
        if left_class != required_timing_class:
            reasons.append(f"left timing class is {left_class}, required {required_timing_class}")
        if right_class != required_timing_class:
            reasons.append(f"right timing class is {right_class}, required {required_timing_class}")

    if left_class != "mixed" and right_class != "mixed" and left_class != right_class:
        reasons.append(f"left/right timing class mismatch: {left_class} vs {right_class}")

    if not allow_left_no_execution:
        left_has_execution = False
        left_successful_execution = False
        for sample in left_samples:
            trace_meta = sample.get("traceMeta", {})
            execution_success = safe_int(trace_meta.get("executionSuccessCount"), default=0)
            execution_rows = safe_int(trace_meta.get("executionRowCount"), default=0)
            if execution_success > 0 or execution_rows > 0:
                left_has_execution = True
            if execution_success > 0:
                left_successful_execution = True
        if not left_has_execution:
            reasons.append("left side has no execution evidence (executionSuccessCount/executionRowCount)")
        if not left_successful_execution:
            reasons.append("left side has no successful execution samples (executionSuccessCount=0)")

    left_execution_error_samples = 0
    right_execution_error_samples = 0
    for sample in left_samples:
        trace_meta = sample.get("traceMeta", {})
        if safe_int(trace_meta.get("executionErrorCount"), default=0) > 0:
            left_execution_error_samples += 1
    for sample in right_samples:
        trace_meta = sample.get("traceMeta", {})
        if safe_int(trace_meta.get("executionErrorCount"), default=0) > 0:
            right_execution_error_samples += 1
    if left_execution_error_samples > 0:
        reasons.append(
            f"left side reported execution errors in {left_execution_error_samples}/{len(left_samples)} samples"
        )
    if right_execution_error_samples > 0:
        reasons.append(
            f"right side reported execution errors in {right_execution_error_samples}/{len(right_samples)} samples"
        )

    resource_reasons: list[str] = []
    left_resource_sample_counts: list[int] = []
    right_resource_sample_counts: list[int] = []
    left_resource_probe_available = 0
    right_resource_probe_available = 0
    left_resource_truncated = 0
    right_resource_truncated = 0

    for sample in left_samples:
        resource = sample.get("resource", {})
        if isinstance(resource, dict):
            count = parse_int(resource.get("resourceSampleCount"))
            if count is not None:
                left_resource_sample_counts.append(count)
            if resource.get("gpuMemoryProbeAvailable") is True:
                left_resource_probe_available += 1
            if resource.get("resourceSamplingTruncated") is True:
                left_resource_truncated += 1

    for sample in right_samples:
        resource = sample.get("resource", {})
        if isinstance(resource, dict):
            count = parse_int(resource.get("resourceSampleCount"))
            if count is not None:
                right_resource_sample_counts.append(count)
            if resource.get("gpuMemoryProbeAvailable") is True:
                right_resource_probe_available += 1
            if resource.get("resourceSamplingTruncated") is True:
                right_resource_truncated += 1

    left_resource_sample_median = (
        int(statistics.median(left_resource_sample_counts))
        if left_resource_sample_counts
        else 0
    )
    right_resource_sample_median = (
        int(statistics.median(right_resource_sample_counts))
        if right_resource_sample_counts
        else 0
    )

    if resource_probe != "none":
        if left_resource_probe_available == 0:
            resource_reasons.append("left side has no successful GPU resource probe samples")
        if right_resource_probe_available == 0:
            resource_reasons.append("right side has no successful GPU resource probe samples")

        if comparability_mode == "strict":
            if resource_sample_target_count <= 0:
                resource_reasons.append(
                    "strict resource comparability requires --resource-sample-target-count > 0 for N-vs-N probing"
                )
            else:
                if left_resource_sample_median != resource_sample_target_count:
                    resource_reasons.append(
                        "left side resource sample median does not match target "
                        f"({left_resource_sample_median} vs target={resource_sample_target_count})"
                    )
                if right_resource_sample_median != resource_sample_target_count:
                    resource_reasons.append(
                        "right side resource sample median does not match target "
                        f"({right_resource_sample_median} vs target={resource_sample_target_count})"
                    )
                if left_resource_truncated > 0:
                    resource_reasons.append(
                        "left side resource probing truncated before process completion; "
                        "increase --resource-sample-target-count or reduce --resource-sample-ms"
                    )
                if right_resource_truncated > 0:
                    resource_reasons.append(
                        "right side resource probing truncated before process completion; "
                        "increase --resource-sample-target-count or reduce --resource-sample-ms"
                    )
        else:
            if left_resource_sample_median < 5:
                resource_reasons.append(
                    f"left side resource sampling too sparse (median samples={left_resource_sample_median}, require >=5)"
                )
            if right_resource_sample_median < 5:
                resource_reasons.append(
                    f"right side resource sampling too sparse (median samples={right_resource_sample_median}, require >=5)"
                )

    reasons.extend(resource_reasons)

    return {
        "comparable": len(reasons) == 0,
        "requiredTimingClass": required_timing_class,
        "leftTimingSources": left_sources,
        "rightTimingSources": right_sources,
        "leftTimingClass": left_class,
        "rightTimingClass": right_class,
        "resourceProbe": resource_probe,
        "leftResourceSampleMedian": left_resource_sample_median,
        "rightResourceSampleMedian": right_resource_sample_median,
        "leftResourceProbeAvailableCount": left_resource_probe_available,
        "rightResourceProbeAvailableCount": right_resource_probe_available,
        "resourceSampleTargetCount": max(resource_sample_target_count, 0),
        "leftResourceSamplingTruncatedCount": left_resource_truncated,
        "rightResourceSamplingTruncatedCount": right_resource_truncated,
        "leftExecutionErrorSampleCount": left_execution_error_samples,
        "rightExecutionErrorSampleCount": right_execution_error_samples,
        "resourceReasons": resource_reasons,
        "reasons": reasons,
    }


def default_claim_min_timed_samples(mode: str) -> int:
    if mode == "local":
        return 7
    if mode == "release":
        return 15
    return 0


def required_positive_percentiles(mode: str) -> list[str]:
    if mode == "release":
        return ["p50Percent", "p95Percent", "p99Percent"]
    if mode == "local":
        return ["p50Percent", "p95Percent"]
    return []


def assess_upload_timing_scope_consistency(
    *,
    side_name: str,
    command_samples: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    canonical_sources = {
        canonical_timing_source(str(sample.get("timingSource", "")))
        for sample in command_samples
        if isinstance(sample.get("timingSource"), str) and str(sample.get("timingSource", ""))
    }
    if len(canonical_sources) > 1:
        reasons.append(
            f"{side_name} upload timings use mixed canonical sources: {sorted(canonical_sources)}"
        )

    for sample in command_samples:
        timing = sample.get("timing", {})
        if not isinstance(timing, dict):
            continue
        ignore_applied = timing.get("uploadIgnoreFirstApplied") is True
        timing_source_raw = sample.get("timingSource")
        timing_source = str(timing_source_raw) if isinstance(timing_source_raw, str) else ""
        canonical = canonical_timing_source(timing_source)
        run_index = safe_int(sample.get("runIndex"), default=-1)
        run_label = f"run {run_index}" if run_index >= 0 else "sample"

        if ignore_applied and canonical != "fawn-execution-row-total-ns":
            reasons.append(
                f"{side_name} {run_label} uses ignore-first with non-row timing source "
                f"({canonical}); require fawn-execution-row-total-ns"
            )
        if "ignore-first-ops" in timing_source and not ignore_applied:
            reasons.append(
                f"{side_name} {run_label} timing source marks ignore-first but uploadIgnoreFirstApplied=false"
            )
    return reasons


def assess_claimability(
    *,
    mode: str,
    min_timed_samples: int,
    workload: Workload,
    left: dict[str, Any],
    right: dict[str, Any],
    delta: dict[str, Any],
    comparability: dict[str, Any],
) -> dict[str, Any]:
    if mode == "off":
        return {
            "mode": "off",
            "evaluated": False,
            "claimable": None,
            "minTimedSamples": 0,
            "requiredPositivePercentiles": [],
            "reasons": [],
        }

    reasons: list[str] = []
    effective_min_samples = min_timed_samples if min_timed_samples > 0 else default_claim_min_timed_samples(mode)
    required_percentiles = required_positive_percentiles(mode)

    if not comparability.get("comparable", False):
        reasons.append("workload is non-comparable; reliability claimability requires comparability")

    left_count = safe_int(left.get("stats", {}).get("count"), default=0)
    right_count = safe_int(right.get("stats", {}).get("count"), default=0)
    if left_count < effective_min_samples:
        reasons.append(
            f"left timed sample count {left_count} is below claim floor {effective_min_samples}"
        )
    if right_count < effective_min_samples:
        reasons.append(
            f"right timed sample count {right_count} is below claim floor {effective_min_samples}"
        )

    for percentile_key in required_percentiles:
        value = safe_float(delta.get(percentile_key))
        if value is None:
            reasons.append(f"missing delta percentile {percentile_key}")
            continue
        if value <= 0.0:
            reasons.append(
                f"{percentile_key}={value:.6f} is not positive (positive means left faster)"
            )

    if workload.domain == "upload":
        left_samples = left.get("commandSamples", [])
        right_samples = right.get("commandSamples", [])
        if isinstance(left_samples, list):
            reasons.extend(
                assess_upload_timing_scope_consistency(
                    side_name="left",
                    command_samples=left_samples,
                )
            )
        if isinstance(right_samples, list):
            reasons.extend(
                assess_upload_timing_scope_consistency(
                    side_name="right",
                    command_samples=right_samples,
                )
            )

    return {
        "mode": mode,
        "evaluated": True,
        "claimable": len(reasons) == 0,
        "minTimedSamples": effective_min_samples,
        "requiredPositivePercentiles": required_percentiles,
        "leftTimedSamples": left_count,
        "rightTimedSamples": right_count,
        "reasons": reasons,
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
        if selected and workload.id not in selected:
            continue
        if not selected and (not include_extended) and (not workload.include_by_default):
            continue
        if (not include_noncomparable) and (not workload.comparable):
            continue
        result.append(workload)

    return result


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

    workloads = load_workloads(
        Path(args.workloads),
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
            verify_fawn_upload_runtime_contract(
                template=args.left_command_template,
                workload=strict_upload_workload,
            )

    workspace = Path(args.workspace)
    report: dict[str, Any] = {
        "schemaVersion": 3,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
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
        },
        "claimabilityPolicy": {
            "mode": args.claimability,
            "minTimedSamples": (
                args.claim_min_timed_samples
                if args.claim_min_timed_samples > 0
                else default_claim_min_timed_samples(args.claimability)
            ),
            "requiredPositivePercentiles": required_positive_percentiles(args.claimability),
        },
        "workloads": [],
    }
    if args.config:
        report["configPath"] = str(Path(args.config))

    overall_left = []
    overall_right = []
    comparability_failures: list[dict[str, Any]] = []
    claimability_failures: list[dict[str, Any]] = []

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
            "p5Percent": percent_delta(safe_float(left_stats["p5Ms"]) or 0.0, safe_float(right_stats["p5Ms"]) or 0.0),
            "p50Percent": percent_delta(safe_float(left_stats["p50Ms"]) or 0.0, safe_float(right_stats["p50Ms"]) or 0.0),
            "p95Percent": percent_delta(safe_float(left_stats["p95Ms"]) or 0.0, safe_float(right_stats["p95Ms"]) or 0.0),
            "p99Percent": percent_delta(safe_float(left_stats["p99Ms"]) or 0.0, safe_float(right_stats["p99Ms"]) or 0.0),
            "meanPercent": percent_delta(safe_float(left_stats["meanMs"]) or 0.0, safe_float(right_stats["meanMs"]) or 0.0),
        }
        comparability = compare_assessment(
            workload_comparable=workload.comparable,
            left=left,
            right=right,
            required_timing_class=args.require_timing_class,
            allow_left_no_execution=args.allow_left_no_execution,
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
        )
        if not comparability["comparable"]:
            comparability_failures.append({"workloadId": workload.id, "reasons": comparability["reasons"]})
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
                "workloadDefault": workload.include_by_default,
                "left": left,
                "right": right,
                "deltaPercent": delta,
                "comparability": comparability,
                "claimability": claimability,
            }
        )

    if overall_left and overall_right:
        overall_left_stats = format_stats(overall_left)
        overall_right_stats = format_stats(overall_right)
        report["overall"] = {
            "left": overall_left_stats,
            "right": overall_right_stats,
            "deltaPercent": {
                "p5Approx": percent_delta(
                    safe_float(overall_left_stats["p5Ms"]) or 0.0,
                    safe_float(overall_right_stats["p5Ms"]) or 0.0,
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

    report["comparabilitySummary"] = {
        "workloadCount": len(workloads),
        "nonComparableCount": len(comparability_failures),
        "nonComparableWorkloads": comparability_failures,
    }
    report["comparisonStatus"] = "comparable" if not comparability_failures else "unreliable"
    report["claimabilitySummary"] = {
        "workloadCount": len(workloads),
        "nonClaimableCount": len(claimability_failures),
        "nonClaimableWorkloads": claimability_failures,
    }
    if args.claimability == "off":
        report["claimStatus"] = "not-evaluated"
    else:
        report["claimStatus"] = "claimable" if not claimability_failures else "diagnostic"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
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
