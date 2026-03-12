"""Config and workload helpers for compare_dawn_vs_doe."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compare_dawn_vs_doe_modules import runner as runner_mod

DEFAULT_WORKLOADS_PATH = "bench/workloads.json"
DEFAULT_LEFT_NAME = "doe"
DEFAULT_RIGHT_NAME = "dawn"
DEFAULT_LEFT_COMMAND_TEMPLATE = (
    "zig/zig-out/bin/doe-zig-runtime "
    "--commands {commands} --quirks {quirks} "
    "--vendor {vendor} --api {api} --family {family} --driver {driver} "
    "--trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}"
)
DEFAULT_ITERATIONS = 3
DEFAULT_WARMUP = 1
DEFAULT_OUT_PATH = "bench/out/dawn-vs-doe.json"
DEFAULT_WORKSPACE_PATH = "bench/out/runtime-comparisons"
DEFAULT_WORKLOAD_FILTER = ""
DEFAULT_WORKLOAD_COHORT = "all"
DEFAULT_COMPARABILITY_MODE = "strict"
DEFAULT_REQUIRED_TIMING_CLASS = "operation"
DEFAULT_RESOURCE_PROBE = "none"
DEFAULT_RESOURCE_SAMPLE_MS = 100
DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT = 0
DEFAULT_WORKLOAD_COOLDOWN_MS = 0
DEFAULT_CLAIMABILITY_MODE = "off"
DEFAULT_CLAIM_MIN_TIMED_SAMPLES = 0
DEFAULT_BENCHMARK_POLICY_PATH = ""
DEFAULT_BENCHMARK_POLICY_CANDIDATES = (
    "config/benchmark-methodology-thresholds.json",
)
VALID_COMPARABILITY_MODES = {"strict", "warn", "off"}
VALID_REQUIRED_TIMING_CLASSES = {"any", "operation", "process-wall"}
VALID_RESOURCE_PROBES = {"none", "rocm-smi"}
VALID_CLAIMABILITY_MODES = {"off", "local", "release"}
VALID_UPLOAD_BUFFER_USAGES = {"copy-dst-copy-src", "copy-dst"}
VALID_WORKLOAD_COHORTS = {"all", "comparability-candidates"}
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
    "doe-execution-total-ns",
    "doe-execution-row-total-ns",
    "doe-execution-dispatch-window-ns",
    "doe-execution-encode-ns",
    "doe-execution-gpu-timestamp-ns",
}
KNOWN_GPU_BACKENDS = {"vulkan", "metal", "d3d12", "webgpu"}
GPU_BACKEND_ALIASES = {
    "dx12": "d3d12",
    "direct3d12": "d3d12",
}
HOST_ALLOWED_GPU_BACKENDS = {
    "darwin": {"metal", "webgpu"},
    "linux": {"vulkan", "webgpu"},
    "windows": {"vulkan", "d3d12", "webgpu"},
}


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
    benchmark_class: str
    allow_left_no_execution: bool
    include_by_default: bool
    left_timing_divisor: float
    right_timing_divisor: float
    timing_normalization_note: str
    async_diagnostics_mode: str
    comparability_candidate: bool
    comparability_candidate_tier: str
    comparability_candidate_notes: str
    path_asymmetry: bool
    path_asymmetry_note: str
    strict_normalization_unit: str


@dataclass(frozen=True)
class BenchmarkMethodologyPolicy:
    source_path: str
    min_dispatch_window_ns_without_encode: int
    min_dispatch_window_coverage_percent_without_encode: float
    local_claim_min_timed_samples: int
    release_claim_min_timed_samples: int
    min_operation_wall_coverage_ratio: float
    max_operation_wall_coverage_asymmetry_ratio: float

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
        "--workload-cohort",
        choices=("all", "comparability-candidates"),
        default=DEFAULT_WORKLOAD_COHORT,
        help=(
            "Optional workload cohort selector. "
            "'comparability-candidates' keeps workloads marked "
            "comparabilityCandidate.enabled=true."
        ),
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
        "--workload-cooldown-ms",
        type=int,
        default=DEFAULT_WORKLOAD_COOLDOWN_MS,
        help=(
            "Optional host settling delay between workloads in milliseconds (>=0). "
            "Applies equally between left/right workload pairs and the next workload."
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
    if args.workload_cohort == DEFAULT_WORKLOAD_COHORT:
        value = first_config_value(payload, ["run.workloadCohort", "workloadCohort"])
        if value is not None:
            candidate = as_str(value, field="run.workloadCohort")
            if candidate not in VALID_WORKLOAD_COHORTS:
                raise ValueError(
                    "invalid config run.workloadCohort="
                    f"{candidate}, expected one of {sorted(VALID_WORKLOAD_COHORTS)}"
                )
            args.workload_cohort = candidate

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
    if args.workload_cooldown_ms == DEFAULT_WORKLOAD_COOLDOWN_MS:
        value = first_config_value(
            payload,
            ["run.workloadCooldownMs", "workloadCooldownMs"],
        )
        if value is not None:
            args.workload_cooldown_ms = as_int(
                value,
                field="run.workloadCooldownMs",
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
    min_operation_wall_coverage_ratio = as_float(
        first_config_value(payload, ["timingScopeSanity.minOperationWallCoverageRatio"]),
        field="timingScopeSanity.minOperationWallCoverageRatio",
    )
    max_operation_wall_coverage_asymmetry_ratio = as_float(
        first_config_value(
            payload,
            ["timingScopeSanity.maxOperationWallCoverageAsymmetryRatio"],
        ),
        field="timingScopeSanity.maxOperationWallCoverageAsymmetryRatio",
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
    if min_operation_wall_coverage_ratio < 0.0:
        raise ValueError("timingScopeSanity.minOperationWallCoverageRatio must be >= 0")
    if max_operation_wall_coverage_asymmetry_ratio < 1.0:
        raise ValueError(
            "timingScopeSanity.maxOperationWallCoverageAsymmetryRatio must be >= 1"
        )

    return BenchmarkMethodologyPolicy(
        source_path=str(path),
        min_dispatch_window_ns_without_encode=dispatch_ns,
        min_dispatch_window_coverage_percent_without_encode=dispatch_coverage,
        local_claim_min_timed_samples=local_min_samples,
        release_claim_min_timed_samples=release_min_samples,
        min_operation_wall_coverage_ratio=min_operation_wall_coverage_ratio,
        max_operation_wall_coverage_asymmetry_ratio=max_operation_wall_coverage_asymmetry_ratio,
    )


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def percent_delta(left: float, right: float) -> float:
    if left <= 0.0:
        return 0.0
    return ((right / left) - 1.0) * 100.0


def parse_extra_args(value: Any, *, workload_id: str) -> list[str]:
    if isinstance(value, list):
        args: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise ValueError(
                    f"invalid workload {workload_id}: extraArgs[{index}] must be a string"
                )
            text = item.strip()
            if text:
                args.append(text)
        return args

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return shlex.split(text)

    raise ValueError(
        f"invalid workload {workload_id}: extraArgs must be a string or string[]"
    )


def parse_comparability_candidate(
    value: Any,
    *,
    workload_id: str,
) -> tuple[bool, str, str]:
    if value is None:
        return False, "", ""
    if not isinstance(value, dict):
        raise ValueError(
            f"invalid workload {workload_id}: comparabilityCandidate must be an object"
        )
    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError(
            f"invalid workload {workload_id}: comparabilityCandidate.enabled must be boolean"
        )
    raw_tier = value.get("tier", "")
    raw_notes = value.get("notes", "")
    if not isinstance(raw_tier, str):
        raise ValueError(
            f"invalid workload {workload_id}: comparabilityCandidate.tier must be string"
        )
    if not isinstance(raw_notes, str):
        raise ValueError(
            f"invalid workload {workload_id}: comparabilityCandidate.notes must be string"
        )
    tier = raw_tier.strip()
    notes = raw_notes.strip()
    if enabled and not tier:
        raise ValueError(
            f"invalid workload {workload_id}: comparabilityCandidate.enabled=true requires non-empty comparabilityCandidate.tier"
        )
    return enabled, tier, notes


def safe_float(value: Any) -> float | None:
    return runner_mod.safe_float(value)

def parse_int(value: Any) -> int | None:
    return runner_mod.parse_int(value)

def dawn_metric_median_ms(trace_meta: dict[str, Any], metric_name: str) -> float | None:
    return runner_mod.dawn_metric_median_ms(trace_meta, metric_name)

def extract_timing_metrics_ms(
    trace_meta: dict[str, Any],
    *,
    wall_ms: float,
    cpu_ms: float,
) -> dict[str, float | None]:
    return runner_mod.extract_timing_metrics_ms(trace_meta, wall_ms=wall_ms, cpu_ms=cpu_ms)

def normalize_timing_metrics_ms(
    metrics_ms: dict[str, float | None],
    divisor: float,
) -> dict[str, float | None]:
    return runner_mod.normalize_timing_metrics_ms(metrics_ms, divisor)

def read_process_rss_kb(pid: int) -> int:
    return runner_mod.read_process_rss_kb(pid)

def read_rocm_vram_snapshot() -> tuple[dict[str, int] | None, str | None]:
    return runner_mod.read_rocm_vram_snapshot()

def assert_json_object(payload: Any, *, context: str, path: Path) -> dict[str, Any]:
    return runner_mod.assert_json_object(payload, context=context, path=path)

def parse_trace_meta(path: Path) -> dict[str, Any]:
    return runner_mod.parse_trace_meta(path)

def materialize_repeated_commands(
    commands_path: str,
    *,
    repeat: int,
    out_dir: Path,
    side_name: str,
) -> str:
    return runner_mod.materialize_repeated_commands(commands_path, repeat=repeat, out_dir=out_dir, side_name=side_name)

def command_for(
    template: str,
    *,
    workload: Any,
    workload_id: str,
    commands_path: str,
    trace_jsonl: Path,
    trace_meta: Path,
    queue_sync_mode: str,
    upload_buffer_usage: str,
    upload_submit_every: int,
    extra_args: list[str],
) -> list[str]:
    return runner_mod.command_for(
        template,
        workload=workload,
        workload_id=workload_id,
        commands_path=commands_path,
        trace_jsonl=trace_jsonl,
        trace_meta=trace_meta,
        queue_sync_mode=queue_sync_mode,
        upload_buffer_usage=upload_buffer_usage,
        upload_submit_every=upload_submit_every,
        extra_args=extra_args,
    )

def max_rss_time_prefix() -> tuple[str, ...]:
    return runner_mod.max_rss_time_prefix()

def run_once(
    command: list[str],
    *,
    gpu_memory_probe: str,
    resource_sample_ms: int,
    resource_sample_target_count: int,
) -> tuple[float, float, int, dict[str, Any]]:
    return runner_mod.run_once(command, gpu_memory_probe=gpu_memory_probe, resource_sample_ms=resource_sample_ms, resource_sample_target_count=resource_sample_target_count)

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
    comparability_mode: str,
    benchmark_policy: BenchmarkMethodologyPolicy,
    emit_shell: bool,
) -> dict[str, Any]:
    return runner_mod.run_workload(
        name=name,
        template=template,
        workload=workload,
        iterations=iterations,
        warmup=warmup,
        out_dir=out_dir,
        gpu_memory_probe=gpu_memory_probe,
        resource_sample_ms=resource_sample_ms,
        resource_sample_target_count=resource_sample_target_count,
        timing_divisor=timing_divisor,
        command_repeat=command_repeat,
        ignore_first_ops=ignore_first_ops,
        upload_buffer_usage=upload_buffer_usage,
        upload_submit_every=upload_submit_every,
        inject_upload_runtime_flags=inject_upload_runtime_flags,
        required_timing_class=required_timing_class,
        comparability_mode=comparability_mode,
        benchmark_policy=benchmark_policy,
        emit_shell=emit_shell,
    )


def load_workloads(
    path: Path,
    workload_filter: str,
    include_noncomparable: bool,
    include_extended: bool,
    workload_cohort: str,
) -> list[Workload]:
    if workload_cohort not in VALID_WORKLOAD_COHORTS:
        raise ValueError(
            f"invalid workload cohort {workload_cohort!r}: expected one of {sorted(VALID_WORKLOAD_COHORTS)}"
        )
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
        workload_id = str(item.get("id", "")).strip()
        if not workload_id:
            raise ValueError(f"invalid workload entry in {path}: missing id")
        (
            comparability_candidate,
            comparability_candidate_tier,
            comparability_candidate_notes,
        ) = parse_comparability_candidate(
            item.get("comparabilityCandidate"),
            workload_id=workload_id,
        )
        apples_to_apples_vetted = bool(item.get("applesToApplesVetted", False))
        workload_domain = str(item.get("domain", "uncategorized")).strip().lower()
        left_command_repeat = parse_int(item.get("leftCommandRepeat")) or 1
        right_command_repeat_raw = parse_int(item.get("rightCommandRepeat"))
        right_command_repeat = (
            left_command_repeat
            if right_command_repeat_raw is None and workload_domain == "upload"
            else (1 if right_command_repeat_raw is None else int(right_command_repeat_raw or 0))
        )
        left_ignore_first_ops = parse_int(item.get("leftIgnoreFirstOps")) or 0
        right_ignore_first_ops_raw = parse_int(item.get("rightIgnoreFirstOps"))
        right_ignore_first_ops = (
            left_ignore_first_ops
            if right_ignore_first_ops_raw is None and workload_domain == "upload"
            else (0 if right_ignore_first_ops_raw is None else int(right_ignore_first_ops_raw or 0))
        )
        left_timing_divisor = float(item.get("leftTimingDivisor", 1.0))
        left_upload_buffer_usage = str(
            item.get("leftUploadBufferUsage", "copy-dst-copy-src")
        )
        left_upload_submit_every_raw = parse_int(item.get("leftUploadSubmitEvery"))
        left_upload_submit_every = (
            1
            if left_upload_submit_every_raw is None
            else int(left_upload_submit_every_raw or 0)
        )
        right_upload_submit_every_raw = parse_int(item.get("rightUploadSubmitEvery"))
        comparable = bool(item.get("comparable", False))
        benchmark_class_raw = item.get("benchmarkClass")
        if benchmark_class_raw is None:
            benchmark_class = "comparable" if comparable else "directional"
        else:
            benchmark_class = str(benchmark_class_raw).strip().lower()
        if benchmark_class not in {"comparable", "directional"}:
            raise ValueError(
                f"invalid workload {workload_id}: benchmarkClass must be one of "
                "['comparable', 'directional']"
            )
        if benchmark_class == "comparable" and not comparable:
            raise ValueError(
                f"invalid workload {workload_id}: benchmarkClass=comparable requires comparable=true"
            )
        if benchmark_class == "directional" and comparable:
            raise ValueError(
                f"invalid workload {workload_id}: benchmarkClass=directional requires comparable=false"
            )
        workload = Workload(
            id=workload_id,
            name=item.get("name", workload_id),
            description=item.get("description", ""),
            domain=item.get("domain", "uncategorized"),
            comparability_notes=item.get("comparabilityNotes", ""),
            commands_path=item.get("commandsPath", ""),
            quirks_path=item.get("quirksPath", ""),
            vendor=item.get("vendor", "intel"),
            api=item.get("api", "vulkan"),
            family=item.get("family", "gen12"),
            driver=item.get("driver", "31.0.101"),
            extra_args=parse_extra_args(item.get("extraArgs", []), workload_id=workload_id),
            left_command_repeat=left_command_repeat,
            right_command_repeat=right_command_repeat,
            left_ignore_first_ops=left_ignore_first_ops,
            right_ignore_first_ops=right_ignore_first_ops,
            left_upload_buffer_usage=left_upload_buffer_usage,
            right_upload_buffer_usage=str(
                item.get("rightUploadBufferUsage", left_upload_buffer_usage)
            ),
            left_upload_submit_every=left_upload_submit_every,
            right_upload_submit_every=(
                left_upload_submit_every
                if right_upload_submit_every_raw is None
                else int(right_upload_submit_every_raw or 0)
            ),
            dawn_filter=item.get("dawnFilter", ""),
            comparable=comparable,
            benchmark_class=benchmark_class,
            allow_left_no_execution=bool(item.get("allowLeftNoExecution", False)),
            include_by_default=bool(item.get("default", True)),
            left_timing_divisor=left_timing_divisor,
            right_timing_divisor=float(item.get("rightTimingDivisor", 1.0)),
            timing_normalization_note=item.get("timingNormalizationNote", ""),
            async_diagnostics_mode=str(item.get("asyncDiagnosticsMode", "")).strip(),
            comparability_candidate=comparability_candidate,
            comparability_candidate_tier=comparability_candidate_tier,
            comparability_candidate_notes=comparability_candidate_notes,
            path_asymmetry=bool(item.get("pathAsymmetry", False)),
            path_asymmetry_note=str(item.get("pathAsymmetryNote", "")),
            strict_normalization_unit=str(item.get("strictNormalizationUnit", "")).strip().lower(),
        )
        if workload.strict_normalization_unit not in {"", "command", "dispatch", "cycle"}:
            raise ValueError(
                f"invalid workload {workload.id}: strictNormalizationUnit must be one of "
                "['command', 'dispatch', 'cycle'] when present"
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
        if workload.comparable and workload_domain == "upload":
            required_upload_contract_fields = (
                "rightCommandRepeat",
                "rightIgnoreFirstOps",
                "rightUploadBufferUsage",
                "rightUploadSubmitEvery",
                "rightTimingDivisor",
            )
            missing_upload_contract_fields = [
                field for field in required_upload_contract_fields if field not in item
            ]
            if missing_upload_contract_fields:
                raise ValueError(
                    f"invalid workload {workload.id}: comparable upload workloads must "
                    "declare explicit right-side normalization fields; missing "
                    + ", ".join(missing_upload_contract_fields)
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
        if workload.comparability_candidate and workload.comparable:
            raise ValueError(
                f"invalid workload {workload.id}: comparabilityCandidate.enabled=true "
                "requires comparable=false until parity promotion is complete"
            )
        if selected and workload.id not in selected:
            continue
        if not selected and (not include_extended) and (not workload.include_by_default):
            continue
        if workload_cohort == "comparability-candidates" and (not workload.comparability_candidate):
            continue
        if (not include_noncomparable) and (not workload.comparable):
            continue
        result.append(workload)

    return result
