#!/usr/bin/env python3
"""Validate SdkLayout streaming trace hardening invariants."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

STREAM_BUFFER_KEYS = {
    "ple_rows_stream": "rows",
    "ple_projection_stream": "proj",
    "layer_weights_stream": "wts",
    "activation_out_stream": "activation",
}
EXPECTED_STREAM_OPERATIONS = {
    "ple_rows_stream": ("input", "send"),
    "ple_projection_stream": ("input", "send"),
    "layer_weights_stream": ("input", "send"),
    "activation_out_stream": ("output", "receive"),
}


@dataclass(frozen=True)
class CheckResult:
    checked: int
    failures: list[str]
    warnings: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trace",
        action="append",
        default=[],
        help=(
            "Layer-block streaming trace to validate. Repeat for multiple "
            "traces. Explicit traces keep the gate honest about which "
            "simfabric or hardware receipts it is enforcing."
        ),
    )
    parser.add_argument(
        "--fail-on-overalloc",
        action="store_true",
        help=(
            "Treat io_buffer_size > 4 * payloadBytes as a failure instead "
            "of a warning. Useful once stream-specific minimum buffers are "
            "known for all small control streams."
        ),
    )
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def entry_label(trace_name: str, index: int, stream_id: str) -> str:
    return f"{trace_name}:layerBlockSmoke.hostIoLayout[{index}]({stream_id})"


def stream_telemetry_label(trace_name: str, stream_id: str) -> str:
    return f"{trace_name}:executedRun.streams({stream_id})"


def check_stream_telemetry(
    trace_name: str,
    trace: dict[str, Any],
) -> CheckResult:
    failures: list[str] = []
    warnings: list[str] = []
    checked = 0

    run = as_dict(trace.get("executedRun"))
    telemetry = as_dict(run.get("streamTelemetry"))
    if not telemetry:
        failures.append(f"{trace_name}: missing executedRun.streamTelemetry")
    elif telemetry.get("measurementSource") != "host_sdk_task_handles":
        failures.append(
            f"{trace_name}: streamTelemetry.measurementSource="
            f"{telemetry.get('measurementSource')!r}, expected "
            "'host_sdk_task_handles'"
        )

    streams = as_list(run.get("streams"))
    if not streams:
        failures.append(f"{trace_name}: missing executedRun.streams")
        return CheckResult(checked=0, failures=failures, warnings=warnings)

    by_stream: dict[str, dict[str, Any]] = {}
    for raw_stream in streams:
        stream = as_dict(raw_stream)
        stream_id = str(stream.get("streamId", ""))
        if stream_id:
            by_stream[stream_id] = stream

    num_layers = as_int(run.get("numLayersChained"))
    status = run.get("status")
    for stream_id, (expected_role, expected_operation) in (
        EXPECTED_STREAM_OPERATIONS.items()
    ):
        label = stream_telemetry_label(trace_name, stream_id)
        stream = by_stream.get(stream_id)
        if stream is None:
            failures.append(f"{label}: missing telemetry entry")
            continue
        checked += 1

        if stream.get("role") != expected_role:
            failures.append(
                f"{label}: role={stream.get('role')!r}, "
                f"expected {expected_role!r}"
            )
        if stream.get("operation") != expected_operation:
            failures.append(
                f"{label}: operation={stream.get('operation')!r}, "
                f"expected {expected_operation!r}"
            )

        issued = as_int(stream.get("issuedCount"))
        completed = as_int(stream.get("completedCount"))
        pending = as_int(stream.get("pendingCount"))
        max_queue = as_int(stream.get("maxQueueDepth"))
        dropped = as_int(stream.get("droppedSendCount"))
        failures_count = as_int(stream.get("submissionFailureCount"))
        done_before_wait = as_int(stream.get("doneBeforeWaitCount"))

        required_ints = {
            "issuedCount": issued,
            "completedCount": completed,
            "pendingCount": pending,
            "maxQueueDepth": max_queue,
            "droppedSendCount": dropped,
            "submissionFailureCount": failures_count,
            "doneBeforeWaitCount": done_before_wait,
        }
        for field, value in required_ints.items():
            if value is None:
                failures.append(f"{label}: missing integer {field}")

        if not isinstance(stream.get("taskWaitTotalMs"), (int, float)):
            failures.append(f"{label}: missing numeric taskWaitTotalMs")
        if not isinstance(stream.get("taskWaitMaxMs"), (int, float)):
            failures.append(f"{label}: missing numeric taskWaitMaxMs")

        if status == "succeeded" and num_layers is not None:
            if issued != num_layers:
                failures.append(
                    f"{label}: issuedCount={issued}, expected {num_layers}"
                )
            if completed != num_layers:
                failures.append(
                    f"{label}: completedCount={completed}, expected "
                    f"{num_layers}"
                )
            if pending != 0:
                failures.append(f"{label}: pendingCount={pending}, expected 0")
            if max_queue is not None and max_queue < 1:
                failures.append(
                    f"{label}: maxQueueDepth={max_queue}, expected >= 1"
                )
            if dropped != 0:
                failures.append(
                    f"{label}: droppedSendCount={dropped}, expected 0"
                )
            if failures_count != 0:
                failures.append(
                    f"{label}: submissionFailureCount={failures_count}, "
                    "expected 0"
                )

    if status == "succeeded" and run.get("failure") is not None:
        failures.append(
            f"{trace_name}: executedRun.failure is set despite succeeded run"
        )

    events_tail = as_list(run.get("streamEventsTail"))
    if status == "succeeded" and num_layers is not None:
        if not events_tail:
            failures.append(f"{trace_name}: missing executedRun.streamEventsTail")
        expected_min_tail = min(
            64,
            num_layers * len(EXPECTED_STREAM_OPERATIONS) * 2,
        )
        if len(events_tail) < expected_min_tail:
            warnings.append(
                f"{trace_name}: streamEventsTail has {len(events_tail)} "
                f"events, expected at least {expected_min_tail}"
            )

    return CheckResult(checked=checked, failures=failures, warnings=warnings)


def check_trace(
    trace_name: str,
    trace: dict[str, Any],
    fail_on_overalloc: bool,
) -> CheckResult:
    failures: list[str] = []
    warnings: list[str] = []
    checked = 0

    layer = as_dict(trace.get("layerBlockSmoke"))
    host_io_layout = as_list(layer.get("hostIoLayout"))
    io_buffer_sizes = as_dict(layer.get("ioBufferSizes"))

    if not host_io_layout:
        failures.append(f"{trace_name}: missing layerBlockSmoke.hostIoLayout")
        return CheckResult(checked=0, failures=failures, warnings=warnings)
    if not io_buffer_sizes:
        failures.append(f"{trace_name}: missing layerBlockSmoke.ioBufferSizes")
        return CheckResult(checked=0, failures=failures, warnings=warnings)

    for index, raw_entry in enumerate(host_io_layout):
        entry = as_dict(raw_entry)
        stream_id = str(entry.get("streamId", ""))
        label = entry_label(trace_name, index, stream_id or "<missing>")
        if not stream_id:
            failures.append(f"{label}: missing streamId")
            continue

        buffer_key = STREAM_BUFFER_KEYS.get(stream_id)
        if buffer_key is None:
            failures.append(f"{label}: unknown streamId")
            continue

        payload_bytes = as_int(entry.get("planPayloadBytes"))
        if payload_bytes is None:
            failures.append(f"{label}: missing integer planPayloadBytes")
            continue

        entry_buffer_size = as_int(entry.get("ioBufferSize"))
        mapped_buffer_size = as_int(io_buffer_sizes.get(buffer_key))
        if mapped_buffer_size is None:
            failures.append(
                f"{label}: missing integer ioBufferSizes.{buffer_key}"
            )
            continue
        if entry_buffer_size is None:
            io_buffer_size = mapped_buffer_size
        else:
            io_buffer_size = entry_buffer_size
            if entry_buffer_size != mapped_buffer_size:
                failures.append(
                    f"{label}: ioBufferSize={entry_buffer_size}, "
                    f"ioBufferSizes.{buffer_key}={mapped_buffer_size}"
                )

        checked += 1
        if payload_bytes > 0 and io_buffer_size < payload_bytes:
            failures.append(
                f"{label}: io_buffer_size={io_buffer_size} is smaller "
                f"than payloadBytes={payload_bytes}"
            )
        if payload_bytes > 0 and io_buffer_size > payload_bytes * 4:
            message = (
                f"{label}: io_buffer_size={io_buffer_size} exceeds "
                f"4x payloadBytes={payload_bytes}"
            )
            if fail_on_overalloc:
                failures.append(message)
            else:
                warnings.append(message)

    telemetry_result = check_stream_telemetry(trace_name, trace)
    checked += telemetry_result.checked
    failures.extend(telemetry_result.failures)
    warnings.extend(telemetry_result.warnings)

    return CheckResult(checked=checked, failures=failures, warnings=warnings)


def load_trace(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("trace root must be a JSON object")
    return payload


def main() -> int:
    args = parse_args()
    if not args.trace:
        print("FAIL: SdkLayout streaming hardening gate")
        print("  pass at least one --trace path")
        return 1

    failures: list[str] = []
    warnings: list[str] = []
    checked = 0

    for raw_trace in args.trace:
        trace_path = resolve(raw_trace)
        try:
            trace = load_trace(trace_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"{raw_trace}: cannot load trace JSON: {exc}")
            continue
        result = check_trace(
            raw_trace,
            trace,
            fail_on_overalloc=args.fail_on_overalloc,
        )
        checked += result.checked
        failures.extend(result.failures)
        warnings.extend(result.warnings)

    if failures:
        print("FAIL: SdkLayout streaming hardening gate")
        for failure in failures:
            print(f"  {failure}")
        for warning in warnings:
            print(f"  warning: {warning}")
        return 1

    print(
        "PASS: SdkLayout streaming hardening gate "
        f"({len(args.trace)} traces, {checked} stream entries, "
        f"{len(warnings)} warnings)"
    )
    for warning in warnings:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
