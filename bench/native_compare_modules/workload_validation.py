"""Workload command-shape validation and backend-policy enforcement."""

from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Any

from native_compare_modules.config_support import (
    Workload,
    KNOWN_GPU_BACKENDS,
    GPU_BACKEND_ALIASES,
    HOST_ALLOWED_GPU_BACKENDS,
)
from native_compare_modules.runner import parse_int, command_for


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
