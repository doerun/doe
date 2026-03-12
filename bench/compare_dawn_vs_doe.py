#!/usr/bin/env python3
"""
Dawn/Doe side-by-side benchmark runner.

This script executes shared workload command templates for both runtimes and emits
timing traces where available, with wall-time as a fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import functools
import platform
import re
import statistics
import subprocess
import sys
import time
import resource as py_resource
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import output_paths
from compare_dawn_vs_doe_modules import config_support as config_support_mod
from compare_dawn_vs_doe_modules import claimability as claimability_mod
from compare_dawn_vs_doe_modules import comparability as comparability_mod
from compare_dawn_vs_doe_modules import reporting as reporting_mod
from compare_dawn_vs_doe_modules import timing_interpretation as timing_interpretation_mod
from compare_dawn_vs_doe_modules import timing_selection as timing_selection_mod
from compare_dawn_vs_doe_modules import runner as runner_mod

DEFAULT_WORKLOADS_PATH = config_support_mod.DEFAULT_WORKLOADS_PATH
DEFAULT_LEFT_NAME = config_support_mod.DEFAULT_LEFT_NAME
DEFAULT_RIGHT_NAME = config_support_mod.DEFAULT_RIGHT_NAME
DEFAULT_LEFT_COMMAND_TEMPLATE = config_support_mod.DEFAULT_LEFT_COMMAND_TEMPLATE
DEFAULT_ITERATIONS = config_support_mod.DEFAULT_ITERATIONS
DEFAULT_WARMUP = config_support_mod.DEFAULT_WARMUP
DEFAULT_OUT_PATH = config_support_mod.DEFAULT_OUT_PATH
DEFAULT_WORKSPACE_PATH = config_support_mod.DEFAULT_WORKSPACE_PATH
DEFAULT_WORKLOAD_FILTER = config_support_mod.DEFAULT_WORKLOAD_FILTER
DEFAULT_WORKLOAD_COHORT = config_support_mod.DEFAULT_WORKLOAD_COHORT
DEFAULT_COMPARABILITY_MODE = config_support_mod.DEFAULT_COMPARABILITY_MODE
DEFAULT_REQUIRED_TIMING_CLASS = config_support_mod.DEFAULT_REQUIRED_TIMING_CLASS
DEFAULT_RESOURCE_PROBE = config_support_mod.DEFAULT_RESOURCE_PROBE
DEFAULT_RESOURCE_SAMPLE_MS = config_support_mod.DEFAULT_RESOURCE_SAMPLE_MS
DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT = config_support_mod.DEFAULT_RESOURCE_SAMPLE_TARGET_COUNT
DEFAULT_WORKLOAD_COOLDOWN_MS = config_support_mod.DEFAULT_WORKLOAD_COOLDOWN_MS
DEFAULT_CLAIMABILITY_MODE = config_support_mod.DEFAULT_CLAIMABILITY_MODE
DEFAULT_CLAIM_MIN_TIMED_SAMPLES = config_support_mod.DEFAULT_CLAIM_MIN_TIMED_SAMPLES
DEFAULT_BENCHMARK_POLICY_PATH = config_support_mod.DEFAULT_BENCHMARK_POLICY_PATH
DEFAULT_BENCHMARK_POLICY_CANDIDATES = config_support_mod.DEFAULT_BENCHMARK_POLICY_CANDIDATES
VALID_COMPARABILITY_MODES = config_support_mod.VALID_COMPARABILITY_MODES
VALID_REQUIRED_TIMING_CLASSES = config_support_mod.VALID_REQUIRED_TIMING_CLASSES
VALID_RESOURCE_PROBES = config_support_mod.VALID_RESOURCE_PROBES
VALID_CLAIMABILITY_MODES = config_support_mod.VALID_CLAIMABILITY_MODES
VALID_UPLOAD_BUFFER_USAGES = config_support_mod.VALID_UPLOAD_BUFFER_USAGES
VALID_WORKLOAD_COHORTS = config_support_mod.VALID_WORKLOAD_COHORTS
NON_APPLES_TO_APPLES_DOMAINS = config_support_mod.NON_APPLES_TO_APPLES_DOMAINS
FAWN_UPLOAD_RUNTIME_SOURCE_PATHS = config_support_mod.FAWN_UPLOAD_RUNTIME_SOURCE_PATHS
NATIVE_EXECUTION_OPERATION_TIMING_SOURCES = config_support_mod.NATIVE_EXECUTION_OPERATION_TIMING_SOURCES
KNOWN_GPU_BACKENDS = config_support_mod.KNOWN_GPU_BACKENDS
GPU_BACKEND_ALIASES = config_support_mod.GPU_BACKEND_ALIASES
HOST_ALLOWED_GPU_BACKENDS = config_support_mod.HOST_ALLOWED_GPU_BACKENDS
Workload = config_support_mod.Workload
BenchmarkMethodologyPolicy = config_support_mod.BenchmarkMethodologyPolicy
parse_args = config_support_mod.parse_args
load_json = config_support_mod.load_json
get_nested = config_support_mod.get_nested
first_config_value = config_support_mod.first_config_value
as_str = config_support_mod.as_str
as_int = config_support_mod.as_int
as_float = config_support_mod.as_float
as_bool = config_support_mod.as_bool
apply_config_defaults = config_support_mod.apply_config_defaults
resolve_benchmark_policy_path = config_support_mod.resolve_benchmark_policy_path
load_benchmark_methodology_policy = config_support_mod.load_benchmark_methodology_policy
safe_int = config_support_mod.safe_int
percent_delta = config_support_mod.percent_delta
parse_extra_args = config_support_mod.parse_extra_args
parse_comparability_candidate = config_support_mod.parse_comparability_candidate
safe_float = config_support_mod.safe_float
parse_int = config_support_mod.parse_int
dawn_metric_median_ms = config_support_mod.dawn_metric_median_ms
extract_timing_metrics_ms = config_support_mod.extract_timing_metrics_ms
normalize_timing_metrics_ms = config_support_mod.normalize_timing_metrics_ms
read_process_rss_kb = config_support_mod.read_process_rss_kb
read_rocm_vram_snapshot = config_support_mod.read_rocm_vram_snapshot
assert_json_object = config_support_mod.assert_json_object
parse_trace_meta = config_support_mod.parse_trace_meta
materialize_repeated_commands = config_support_mod.materialize_repeated_commands
command_for = config_support_mod.command_for
max_rss_time_prefix = config_support_mod.max_rss_time_prefix
run_once = config_support_mod.run_once
run_workload = config_support_mod.run_workload
load_workloads = config_support_mod.load_workloads


def parse_positive_int_command_field(
    *,
    value: Any,
    workload_id: str,
    command_index: int,
    field_name: str,
) -> int:
    parsed = parse_int(value)
    if parsed is None or parsed < 1:
        raise ValueError(
            f"invalid workload {workload_id}: command[{command_index}] "
            f"{field_name} must be an integer >= 1"
        )
    return parsed


def command_shape_multiplier(
    command: dict[str, Any],
    *,
    workload_id: str,
    command_index: int,
) -> int:
    multiplier = 1
    aliases: list[tuple[str, tuple[str, ...]]] = [
        ("repeat", ("repeat",)),
        ("dispatchCount", ("dispatch_count", "dispatchCount")),
        ("drawCount", ("draw_count", "drawCount")),
        ("iterations", ("iterations", "iterationCount")),
    ]
    for canonical_name, field_aliases in aliases:
        raw_value: Any = None
        present = False
        for field_name in field_aliases:
            if field_name in command:
                raw_value = command[field_name]
                present = True
                break
        if not present:
            continue
        parsed = parse_positive_int_command_field(
            value=raw_value,
            workload_id=workload_id,
            command_index=command_index,
            field_name=canonical_name,
        )
        multiplier *= parsed
    return multiplier


def infer_command_shape_operation_count(
    *,
    commands_path: Path,
    workload_id: str,
) -> int:
    if not commands_path.exists():
        raise ValueError(
            f"invalid workload {workload_id}: commands file does not exist: {commands_path}"
        )
    try:
        payload = json.loads(commands_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid workload {workload_id}: malformed commands JSON {commands_path}: {exc}"
        ) from exc
    if not isinstance(payload, list):
        raise ValueError(
            f"invalid workload {workload_id}: commands payload must be a JSON array in {commands_path}"
        )
    if not payload:
        raise ValueError(
            f"invalid workload {workload_id}: commands payload must not be empty in {commands_path}"
        )

    total = 0
    for command_index, raw_command in enumerate(payload):
        if not isinstance(raw_command, dict):
            raise ValueError(
                f"invalid workload {workload_id}: commands[{command_index}] must be an object"
            )
        total += command_shape_multiplier(
            raw_command,
            workload_id=workload_id,
            command_index=command_index,
        )
    return total


def infer_command_shape_dispatch_count(
    *,
    commands_path: Path,
    workload_id: str,
) -> int:
    if not commands_path.exists():
        raise ValueError(
            f"invalid workload {workload_id}: commands file does not exist: {commands_path}"
        )
    try:
        payload = json.loads(commands_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid workload {workload_id}: malformed commands JSON {commands_path}: {exc}"
        ) from exc
    if not isinstance(payload, list):
        raise ValueError(
            f"invalid workload {workload_id}: commands payload must be a JSON array in {commands_path}"
        )
    if not payload:
        raise ValueError(
            f"invalid workload {workload_id}: commands payload must not be empty in {commands_path}"
        )

    total = 0
    for command_index, raw_command in enumerate(payload):
        if not isinstance(raw_command, dict):
            raise ValueError(
                f"invalid workload {workload_id}: commands[{command_index}] must be an object"
            )
        kind = str(raw_command.get("kind", "")).strip().lower()
        if kind not in {"dispatch", "dispatch_indirect", "kernel_dispatch"}:
            continue
        total += command_shape_multiplier(
            raw_command,
            workload_id=workload_id,
            command_index=command_index,
        )
    return total


def enforce_strict_command_shape_divisor_contracts(
    *,
    workloads: list[Workload],
    comparability_mode: str,
    required_timing_class: str,
    right_command_template: str,
) -> None:
    if comparability_mode != "strict" or required_timing_class == "process-wall":
        return

    lint_right_divisors = template_uses_doe_runtime(right_command_template)
    command_shape_cache: dict[str, int] = {}
    dispatch_shape_cache: dict[str, int] = {}
    failures: list[str] = []

    for workload in workloads:
        if not workload.comparable:
            continue
        commands_path = Path(workload.commands_path)
        cache_key = str(commands_path.resolve()) if commands_path.exists() else str(commands_path)
        if cache_key not in command_shape_cache:
            command_shape_cache[cache_key] = infer_command_shape_operation_count(
                commands_path=commands_path,
                workload_id=workload.id,
            )
        if cache_key not in dispatch_shape_cache:
            dispatch_shape_cache[cache_key] = infer_command_shape_dispatch_count(
                commands_path=commands_path,
                workload_id=workload.id,
            )
        per_stream_ops = command_shape_cache[cache_key]
        per_stream_dispatch_ops = dispatch_shape_cache[cache_key]
        expected_left_ops = expected_divisor_units(
            workload=workload,
            per_stream_ops=per_stream_ops,
            per_stream_dispatch_ops=per_stream_dispatch_ops,
            command_repeat=workload.left_command_repeat,
        )
        expected_right_ops = expected_divisor_units(
            workload=workload,
            per_stream_ops=per_stream_ops,
            per_stream_dispatch_ops=per_stream_dispatch_ops,
            command_repeat=workload.right_command_repeat,
        )

        if workload.left_timing_divisor > 1.0 and abs(
            workload.left_timing_divisor - float(expected_left_ops)
        ) > 1e-9:
            failures.append(
                f"{workload.id}: leftTimingDivisor={workload.left_timing_divisor} "
                f"does not match command-shape operations={expected_left_ops} "
                f"(commandsPath={workload.commands_path}, leftCommandRepeat={workload.left_command_repeat})"
            )
        if (
            lint_right_divisors
            and workload.right_timing_divisor > 1.0
            and abs(workload.right_timing_divisor - float(expected_right_ops)) > 1e-9
        ):
            failures.append(
                f"{workload.id}: rightTimingDivisor={workload.right_timing_divisor} "
                f"does not match command-shape operations={expected_right_ops} "
                f"(commandsPath={workload.commands_path}, rightCommandRepeat={workload.right_command_repeat})"
            )

    if failures:
        raise ValueError(
            "strict command-shape divisor lint failed for comparable workloads: "
            + "; ".join(failures)
        )


def template_uses_doe_runtime(template: str) -> bool:
    return "doe-zig-runtime" in template


def expected_divisor_units(
    *,
    workload: Workload,
    per_stream_ops: int,
    per_stream_dispatch_ops: int,
    command_repeat: int,
) -> int:
    if workload.strict_normalization_unit == "cycle":
        return command_repeat
    if workload.strict_normalization_unit == "dispatch":
        return per_stream_dispatch_ops * command_repeat
    if workload.domain == "surface":
        return command_repeat
    return per_stream_ops * command_repeat


def template_backend_lane(template: str) -> str:
    match = re.search(r"--backend-lane\s+([A-Za-z0-9_-]+)", template)
    if match is None:
        return ""
    return match.group(1)


def enforce_strict_doe_runtime_normalization_symmetry(
    workloads: list[Workload],
    left_command_template: str,
    right_command_template: str,
    comparability_mode: str,
) -> None:
    if comparability_mode != "strict":
        return
    if not template_uses_doe_runtime(left_command_template):
        return
    if not template_uses_doe_runtime(right_command_template):
        return
    left_lane = template_backend_lane(left_command_template)
    right_lane = template_backend_lane(right_command_template)
    if "dawn" in left_lane or "dawn" in right_lane:
        return

    failures: list[str] = []
    for workload in workloads:
        if not workload.comparable:
            continue
        mismatches: list[str] = []
        if workload.left_command_repeat != workload.right_command_repeat:
            mismatches.append(
                f"commandRepeat left={workload.left_command_repeat} right={workload.right_command_repeat}"
            )
        if workload.left_ignore_first_ops != workload.right_ignore_first_ops:
            mismatches.append(
                f"ignoreFirstOps left={workload.left_ignore_first_ops} right={workload.right_ignore_first_ops}"
            )
        if workload.left_upload_buffer_usage != workload.right_upload_buffer_usage:
            mismatches.append(
                "uploadBufferUsage "
                f"left={workload.left_upload_buffer_usage} right={workload.right_upload_buffer_usage}"
            )
        if workload.left_upload_submit_every != workload.right_upload_submit_every:
            mismatches.append(
                f"uploadSubmitEvery left={workload.left_upload_submit_every} right={workload.right_upload_submit_every}"
            )
        if workload.left_timing_divisor != workload.right_timing_divisor:
            mismatches.append(
                f"timingDivisor left={workload.left_timing_divisor} right={workload.right_timing_divisor}"
            )
        if mismatches:
            failures.append(f"{workload.id}: " + ", ".join(mismatches))

    if failures:
        details = "; ".join(failures)
        raise ValueError(
            "strict doe-vs-doe apples-to-apples requires symmetric workload normalization "
            f"(left==right) for comparable workloads: {details}"
        )


def enforce_strict_dawn_vs_doe_direct_operation_timing(
    workloads: list[Workload],
    left_command_template: str,
    right_command_template: str,
    comparability_mode: str,
    required_timing_class: str,
) -> None:
    if comparability_mode != "strict":
        return
    if required_timing_class != "operation":
        return

    left_is_doe = template_uses_doe_runtime(left_command_template)
    right_is_doe = template_uses_doe_runtime(right_command_template)
    # Dawn-vs-Doe only.
    if left_is_doe == right_is_doe:
        return

    failures: list[str] = []
    for workload in workloads:
        if not workload.comparable:
            continue
        mismatches: list[str] = []
        if workload.left_timing_divisor != 1.0:
            mismatches.append(f"leftTimingDivisor={workload.left_timing_divisor}")
        if workload.right_timing_divisor != 1.0:
            mismatches.append(f"rightTimingDivisor={workload.right_timing_divisor}")
        if mismatches:
            failures.append(f"{workload.id}: " + ", ".join(mismatches))

    if failures:
        details = "; ".join(failures)
        raise ValueError(
            "strict dawn-vs-doe operation comparability requires direct per-side timing "
            "normalization (leftTimingDivisor=1 and rightTimingDivisor=1) for comparable workloads: "
            f"{details}"
        )


def backend_from_token(value: str) -> str | None:
    normalized = value.strip().lower()
    normalized = GPU_BACKEND_ALIASES.get(normalized, normalized)
    if normalized in KNOWN_GPU_BACKENDS:
        return normalized
    return None


def infer_backend_from_lane_name(lane: str) -> str | None:
    lane_lower = lane.strip().lower()
    if "vulkan" in lane_lower:
        return "vulkan"
    if "metal" in lane_lower:
        return "metal"
    if "d3d12" in lane_lower:
        return "d3d12"
    return None


def extract_backends_from_command(command: list[str]) -> set[str]:
    backends: set[str] = set()
    index = 0
    while index < len(command):
        token = command[index]
        if token == "--backend" and index + 1 < len(command):
            backend = backend_from_token(command[index + 1])
            if backend:
                backends.add(backend)
            index += 2
            continue
        if token.startswith("--backend="):
            backend = backend_from_token(token.split("=", 1)[1])
            if backend:
                backends.add(backend)
            index += 1
            continue
        if token == "--api" and index + 1 < len(command):
            backend = backend_from_token(command[index + 1])
            if backend:
                backends.add(backend)
            index += 2
            continue
        if token.startswith("--api="):
            backend = backend_from_token(token.split("=", 1)[1])
            if backend:
                backends.add(backend)
            index += 1
            continue
        if token == "--backend-lane" and index + 1 < len(command):
            backend = infer_backend_from_lane_name(command[index + 1])
            if backend:
                backends.add(backend)
            index += 2
            continue
        if token.startswith("--backend-lane="):
            backend = infer_backend_from_lane_name(token.split("=", 1)[1])
            if backend:
                backends.add(backend)
            index += 1
            continue
        if token == "--dawn-extra-args" and index + 1 < len(command):
            extra_arg = command[index + 1]
            if extra_arg == "--backend" and index + 2 < len(command):
                backend = backend_from_token(command[index + 2])
                if backend:
                    backends.add(backend)
                index += 3
                continue
            if extra_arg.startswith("--backend="):
                backend = backend_from_token(extra_arg.split("=", 1)[1])
                if backend:
                    backends.add(backend)
            index += 2
            continue
        if token.startswith("--dawn-extra-args="):
            extra_arg = token.split("=", 1)[1]
            if extra_arg == "--backend" and index + 1 < len(command):
                backend = backend_from_token(command[index + 1])
                if backend:
                    backends.add(backend)
                index += 2
                continue
            if extra_arg.startswith("--backend="):
                backend = backend_from_token(extra_arg.split("=", 1)[1])
                if backend:
                    backends.add(backend)
            index += 1
            continue
        index += 1
    return backends


def infer_workload_queue_sync_mode(workload: Workload) -> str:
    queue_sync_mode = "per-command"
    for index, arg in enumerate(workload.extra_args):
        if arg == "--queue-sync-mode" and index + 1 < len(workload.extra_args):
            queue_sync_mode = workload.extra_args[index + 1]
    return queue_sync_mode


def infer_workload_backends(
    *,
    workload: Workload,
    left_command_template: str,
    right_command_template: str,
) -> set[str]:
    probe_root = Path("bench/out/scratch/host-backend-policy-probe")
    queue_sync_mode = infer_workload_queue_sync_mode(workload)
    left_command = command_for(
        left_command_template,
        workload=workload,
        workload_id=workload.id,
        commands_path=workload.commands_path,
        trace_jsonl=probe_root / f"{workload.id}.left.ndjson",
        trace_meta=probe_root / f"{workload.id}.left.meta.json",
        queue_sync_mode=queue_sync_mode,
        upload_buffer_usage=workload.left_upload_buffer_usage,
        upload_submit_every=workload.left_upload_submit_every,
        extra_args=workload.extra_args,
    )
    right_command = command_for(
        right_command_template,
        workload=workload,
        workload_id=workload.id,
        commands_path=workload.commands_path,
        trace_jsonl=probe_root / f"{workload.id}.right.ndjson",
        trace_meta=probe_root / f"{workload.id}.right.meta.json",
        queue_sync_mode=queue_sync_mode,
        upload_buffer_usage=workload.right_upload_buffer_usage,
        upload_submit_every=workload.right_upload_submit_every,
        extra_args=workload.extra_args,
    )
    detected = extract_backends_from_command(left_command)
    detected.update(extract_backends_from_command(right_command))
    if not detected:
        api_backend = backend_from_token(workload.api)
        if api_backend:
            detected.add(api_backend)
    return detected


def enforce_host_backend_policy(
    *,
    workloads: list[Workload],
    left_command_template: str,
    right_command_template: str,
) -> None:
    host_name = platform.system().strip()
    host_key = host_name.lower()
    allowed_backends = HOST_ALLOWED_GPU_BACKENDS.get(host_key)
    if not allowed_backends:
        return

    violations: list[str] = []
    for workload in workloads:
        detected = infer_workload_backends(
            workload=workload,
            left_command_template=left_command_template,
            right_command_template=right_command_template,
        )
        disallowed = sorted(backend for backend in detected if backend not in allowed_backends)
        if disallowed:
            violations.append(f"{workload.id}: {', '.join(disallowed)}")

    if violations:
        allowed_text = ", ".join(sorted(allowed_backends))
        raise ValueError(
            f"host/backend policy violation on {host_name}: allowed backends are [{allowed_text}]. "
            "Use an OS-appropriate benchmark config (Metal on macOS, Vulkan on Linux, D3D12 on Windows). "
            "Blocked workload backends: "
            + "; ".join(violations)
        )


format_stats = reporting_mod.format_stats
format_distribution = reporting_mod.format_distribution
summarize_timing_metric_stats = reporting_mod.summarize_timing_metric_stats
summarize_resource_stats = reporting_mod.summarize_resource_stats

command_sample_field_values_ms = timing_interpretation_mod.command_sample_field_values_ms
delta_percent_from_stats = timing_interpretation_mod.delta_percent_from_stats
build_timing_interpretation = timing_interpretation_mod.build_timing_interpretation

parse_trace_rows = timing_selection_mod.parse_trace_rows
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
    if args.workload_cooldown_ms < 0:
        raise ValueError("--workload-cooldown-ms must be >= 0")
    if args.claim_min_timed_samples < 0:
        raise ValueError("--claim-min-timed-samples must be >= 0")
    if not args.right_command_template:
        raise ValueError(
            "missing right command template: pass --right-command-template or "
            "--config with right.commandTemplate"
        )
    if (
        args.workload_cohort == "comparability-candidates"
        and (not args.include_noncomparable_workloads)
    ):
        raise ValueError(
            "workload cohort comparability-candidates requires "
            "--include-noncomparable-workloads (or run.includeNoncomparableWorkloads=true)"
        )
    benchmark_policy = load_benchmark_methodology_policy(args.benchmark_policy)

    workloads_path = Path(args.workloads)
    workloads = load_workloads(
        workloads_path,
        args.workload_filter,
        include_noncomparable=bool(args.include_noncomparable_workloads),
        include_extended=bool(args.include_extended_workloads),
        workload_cohort=args.workload_cohort,
    )
    if not workloads:
        hint = ""
        if not args.include_noncomparable_workloads or not args.include_extended_workloads:
            hint = (
                " (selected workloads may be filtered by comparable=false/default=false; "
                "use --include-noncomparable-workloads and/or --include-extended-workloads)"
            )
        if args.workload_cohort == "comparability-candidates":
            hint += (
                " (workload cohort comparability-candidates requires "
                "comparabilityCandidate.enabled=true entries)"
            )
        print(f"FAIL: no workloads selected{hint}")
        return 1
    enforce_host_backend_policy(
        workloads=workloads,
        left_command_template=args.left_command_template,
        right_command_template=args.right_command_template,
    )
    if args.claimability in {"local", "release"}:
        non_comparable_contract_ids = [
            workload.id
            for workload in workloads
            if workload.benchmark_class != "comparable"
        ]
        if non_comparable_contract_ids:
            raise ValueError(
                "claimability mode requires comparable-only workload contracts "
                "(benchmarkClass=comparable). Directional workloads selected: "
                + ", ".join(non_comparable_contract_ids)
            )
    enforce_strict_doe_runtime_normalization_symmetry(
        workloads=workloads,
        left_command_template=args.left_command_template,
        right_command_template=args.right_command_template,
        comparability_mode=args.comparability,
    )
    enforce_strict_dawn_vs_doe_direct_operation_timing(
        workloads=workloads,
        left_command_template=args.left_command_template,
        right_command_template=args.right_command_template,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
    )
    enforce_strict_command_shape_divisor_contracts(
        workloads=workloads,
        comparability_mode=args.comparability,
        required_timing_class=args.require_timing_class,
        right_command_template=args.right_command_template,
    )

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
    run_group = output_paths.derive_bench_out_group(args.out)
    workspace = output_paths.with_timestamp(
        args.workspace,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
    )
    out = output_paths.with_timestamp(
        args.out,
        output_timestamp,
        enabled=args.timestamp_output,
        group=run_group,
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
            "workloadCooldownMs": args.workload_cooldown_ms,
        },
        "left": {"name": args.left_name},
        "right": {"name": args.right_name},
        "deltaPercentConvention": {
            "baseline": "left",
            "formula": "((rightMs / leftMs) - 1) * 100",
            "positive": "left faster",
            "negative": "left slower",
            "zero": "parity",
        },
        "timingInterpretationPolicy": {
            "selectedMetricField": "deltaPercent",
            "selectedMetricUse": "methodology-selected apples-to-apples claim metric",
            "headlineMetricField": "timingInterpretation.headlineProcessWall.deltaPercent",
            "headlineMetricUse": "timed-command process-wall end-to-end ranking metric",
            "headlineMetricScope": "timed-command-process-wall",
            "narrowSelectedScopeClass": "narrow-hot-path",
            "narrowSelectedMetricEligibleForClaims": False,
            "narrowHotPathClaimMetricField": "timingInterpretation.headlineProcessWall.deltaPercent",
            "narrowHotPathClaimMetricScope": "headlineProcessWall",
            "guidance": (
                "When timingInterpretation.selectedTiming.scopeClass is narrow-hot-path, "
                "deltaPercent remains a phase-specific diagnostic. Claimability evaluates "
                "timingInterpretation.headlineProcessWall.deltaPercent when that end-to-end "
                "metric is available."
            ),
        },
        "comparabilityPolicy": {
            "mode": args.comparability,
            "requiredTimingClass": args.require_timing_class,
            "allowLeftNoExecution": bool(args.allow_left_no_execution),
            "resourceProbe": args.resource_probe,
            "resourceSampleMs": args.resource_sample_ms,
            "resourceSampleTargetCount": args.resource_sample_target_count,
            "workloadCooldownMs": args.workload_cooldown_ms,
            "workloadCohort": args.workload_cohort,
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
    overall_headline_left = []
    overall_headline_right = []
    comparability_failures: list[dict[str, Any]] = []
    claimability_failures: list[dict[str, Any]] = []
    previous_claim_row_hash = "0" * 64
    claim_row_hashes: list[str] = []

    for idx, workload in enumerate(workloads, 1):
        print(f"[{idx}/{len(workloads)}] Running workload: {workload.id}...", file=sys.stderr, flush=True)
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
            comparability_mode=args.comparability,
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
            comparability_mode=args.comparability,
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
        timing_interpretation = build_timing_interpretation(left=left, right=right)
        comparability = compare_assessment(
            workload_id=workload.id,
            workload_comparable=workload.comparable,
            workload_domain=workload.domain,
            workload_path_asymmetry=workload.path_asymmetry,
            workload_path_asymmetry_note=workload.path_asymmetry_note,
            left_command_repeat=workload.left_command_repeat,
            right_command_repeat=workload.right_command_repeat,
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
            timing_interpretation=timing_interpretation,
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

        if comparability.get("comparable"):
            if left_stats["count"] >= 7:
                overall_left.extend([safe_float(v) for v in left_timings if safe_float(v) is not None])
                overall_headline_left.extend(
                    command_sample_field_values_ms(left.get("commandSamples", []), "elapsedMs")
                )
            if right_stats["count"] >= 7:
                overall_right.extend([safe_float(v) for v in right_timings if safe_float(v) is not None])
                overall_headline_right.extend(
                    command_sample_field_values_ms(right.get("commandSamples", []), "elapsedMs")
                )

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
            "workloadPathAsymmetry": workload.path_asymmetry,
            "workloadPathAsymmetryNote": workload.path_asymmetry_note,
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
                "asyncDiagnosticsMode": workload.async_diagnostics_mode or None,
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
                "pathAsymmetry": workload.path_asymmetry,
                "pathAsymmetryNote": workload.path_asymmetry_note,
                "comparabilityCandidate": {
                    "enabled": workload.comparability_candidate,
                    "tier": workload.comparability_candidate_tier,
                    "notes": workload.comparability_candidate_notes,
                },
                "workloadAllowLeftNoExecution": workload.allow_left_no_execution,
                "workloadDefault": workload.include_by_default,
                "left": left,
                "right": right,
                "deltaPercent": delta,
                "timingInterpretation": timing_interpretation,
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
        if args.workload_cooldown_ms > 0 and idx < len(workloads):
            time.sleep(args.workload_cooldown_ms / 1000.0)

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
    if overall_headline_left and overall_headline_right:
        overall_headline_left_stats = format_stats(overall_headline_left)
        overall_headline_right_stats = format_stats(overall_headline_right)
        report["overallHeadlineProcessWall"] = {
            "scope": "timed-command-process-wall",
            "metric": "elapsedMs",
            "left": overall_headline_left_stats,
            "right": overall_headline_right_stats,
            "deltaPercent": delta_percent_from_stats(
                overall_headline_left_stats,
                overall_headline_right_stats,
            ),
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
            "runType": "compare_dawn_vs_doe",
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
