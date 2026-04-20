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
