#!/usr/bin/env python3
"""Synthesize the local simfabric ceiling receipt for Gemma 4 31B af16."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_PHASE_TRACE = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/"
    "scratch/lm_head_prefill_width_tile_x0_w32/phase-trace.log"
)
DEFAULT_KERNEL_RECEIPT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/"
    "lm_head_prefill_width_tile_x0_w32.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-af16-local-simfabric-ceiling/receipt.json"
)


def rel(path: Path | str) -> str:
    path = Path(path)
    if path.is_absolute() and str(path).startswith(str(REPO_ROOT)):
        return str(path.relative_to(REPO_ROOT))
    return str(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_phase_line(line: str) -> dict:
    line = line.strip()
    if not line:
        return {}
    parts = line.split()
    event = parts[0]
    payload: dict[str, object] = {"event": event.removeprefix("phase:")}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if value.lstrip("-").isdigit():
            payload[key] = int(value)
        else:
            payload[key] = value
    return payload


def parse_phase_trace(path: Path) -> list[dict]:
    return [
        parsed
        for parsed in (parse_phase_line(line) for line in path.read_text().splitlines())
        if parsed
    ]


def has_event(events: list[dict], event_name: str, **fields: object) -> bool:
    for event in events:
        if event.get("event") != event_name:
            continue
        if all(event.get(key) == value for key, value in fields.items()):
            return True
    return False


def first_event(events: list[dict], event_name: str) -> dict | None:
    for event in events:
        if event.get("event") == event_name:
            return event
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase-trace", type=Path, default=DEFAULT_PHASE_TRACE)
    p.add_argument("--kernel-receipt", type=Path, default=DEFAULT_KERNEL_RECEIPT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.phase_trace.is_file():
        sys.stderr.write(f"missing phase trace: {rel(args.phase_trace)}\n")
        return 2
    if not args.kernel_receipt.is_file():
        sys.stderr.write(f"missing kernel receipt: {rel(args.kernel_receipt)}\n")
        return 2

    events = parse_phase_trace(args.phase_trace)
    kernel_receipt = json.loads(args.kernel_receipt.read_text(encoding="utf-8"))
    d2h_start = first_event(events, "memcpy_d2h_start")
    observed = {
        "h2dActivationComplete": has_event(
            events, "memcpy_h2d_complete", symbol="activation"
        ),
        "h2dWeightComplete": has_event(
            events, "memcpy_h2d_complete", symbol="weight"
        ),
        "computeLaunchComplete": has_event(
            events, "launch_complete", function="compute"
        ),
        "d2hCopybackStarted": d2h_start is not None,
        "d2hCopybackCompleted": has_event(events, "memcpy_d2h_complete"),
    }
    receipt = {
        "schemaVersion": 1,
        "artifactKind": "gemma4_31b_af16_local_simfabric_ceiling_receipt",
        "modelId": "gemma-4-31b-it-text-q4k-ehf16-af16",
        "target": "wse3",
        "kernel": kernel_receipt.get("kernel")
        or "lm_head_prefill_width_tile_x0_w32",
        "verdict": "blocked",
        "blocker": "simfabric_d2h_copyback_stall_after_launch_complete",
        "sourcePhaseTrace": rel(args.phase_trace),
        "phaseTraceSha256": sha256_file(args.phase_trace),
        "sourceKernelReceipt": rel(args.kernel_receipt),
        "kernelReceiptSha256": sha256_file(args.kernel_receipt),
        "kernelReceiptBlocker": kernel_receipt.get("blocker"),
        "kernelReceiptVerdict": kernel_receipt.get("verdict"),
        "lastPhaseReached": kernel_receipt.get("lastPhaseReached"),
        "failurePhase": kernel_receipt.get("failurePhase"),
        "dispatchTimedOut": bool(kernel_receipt.get("dispatchTimedOut")),
        "observed": observed,
        "d2hCopybackStart": d2h_start,
        "phaseSequence": [event.get("event") for event in events],
        "claim": {
            "scope": (
                "Local simfabric reaches activation H2D, weight H2D, and "
                "compute launch for the Gemma 4 31B af16 lm-head width tile, "
                "then blocks at D2H copyback."
            ),
            "notWhat": (
                "Not a hardware receipt, not a performance receipt, and not "
                "a token/logit/KV transcript."
            ),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {rel(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
