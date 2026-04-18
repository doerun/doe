"""Shared helpers for governed CSL sdk-runtime-command runners."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


def parse_runtime_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--compile-dir", required=True, help="cslc -o directory")
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--cmaddr", default="", help="Optional CS system endpoint")
    return parser.parse_args()


def endpoint(raw_cmaddr: str) -> str | None:
    stripped = raw_cmaddr.strip()
    return stripped or None


def execution_target(cmaddr: str | None) -> str:
    return "system" if cmaddr else "simfabric"


def max_abs_error(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(np.max(np.abs(actual - expected)))


def write_explicit_trace(
    *,
    trace_out: str,
    kernel: str,
    cmaddr: str | None,
    width: int,
    chunk_size: int,
    total_elements: int,
    max_abs_err: float,
    sample_input: Sequence[Any],
    sample_expected: Sequence[Any],
    sample_actual: Sequence[Any],
) -> Path:
    trace = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_trace",
        "target": "wse3",
        "contract": "explicit_simulator_trace",
        "kernel": kernel,
        "executionTarget": execution_target(cmaddr),
        "width": width,
        "chunkSize": chunk_size,
        "totalElements": total_elements,
        "runtimePassed": True,
        "runtimeMaxAbsErr": max_abs_err,
        "sampleInput": list(sample_input),
        "sampleExpected": list(sample_expected),
        "sampleActual": list(sample_actual),
    }
    trace_path = Path(trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    return trace_path
