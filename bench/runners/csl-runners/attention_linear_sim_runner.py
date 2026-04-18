#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the attention_linear kernel."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compile-dir", required=True)
    parser.add_argument("--trace-out", required=True)
    parser.add_argument("--cmaddr", default="")
    args = parser.parse_args()

    width = 4
    head_dim = 64
    kv_len = 16
    scale = 0.125

    rng = np.random.default_rng(seed=13)
    Q_host = rng.standard_normal(size=(width, head_dim), dtype=np.float32)
    K_host = rng.standard_normal(size=(width, kv_len, head_dim), dtype=np.float32)
    V_host = rng.standard_normal(size=(width, kv_len, head_dim), dtype=np.float32)
    expected = np.zeros((width, head_dim), dtype=np.float32)
    for pe in range(width):
        for kv in range(kv_len):
            s = float(np.dot(Q_host[pe], K_host[pe, kv]) * scale)
            expected[pe] += s * V_host[pe, kv]

    cmaddr = args.cmaddr.strip() or None
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    q_sym = runner.get_id("query"); k_sym = runner.get_id("key")
    v_sym = runner.get_id("val"); o_sym = runner.get_id("output")
    runner.load(); runner.run()
    runner.memcpy_h2d(q_sym, Q_host.flatten(), 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(k_sym, K_host.reshape(width, -1).flatten(), 0, 0, width, 1, kv_len * head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(v_sym, V_host.reshape(width, -1).flatten(), 0, 0, width, 1, kv_len * head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)
    actual_flat = np.zeros(width * head_dim, dtype=np.float32)
    runner.memcpy_d2h(actual_flat, o_sym, 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    actual = actual_flat.reshape(width, head_dim)
    max_abs_err = float(np.max(np.abs(actual - expected)))
    passed = bool(np.allclose(actual, expected, atol=1e-3, rtol=1e-3))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err}")
        return 1

    trace = {
        "schemaVersion": 1,
        "artifactKind": "csl_simulator_trace",
        "target": "wse3",
        "contract": "explicit_simulator_trace",
        "kernel": "attention-linear",
        "executionTarget": "system" if cmaddr else "simfabric",
        "width": width,
        "chunkSize": head_dim,
        "totalElements": width * head_dim,
        "runtimePassed": True,
        "runtimeMaxAbsErr": max_abs_err,
        "sampleInput": Q_host[0, :4].tolist(),
        "sampleExpected": expected[0, :4].tolist(),
        "sampleActual": actual[0, :4].tolist(),
    }
    Path(args.trace_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.trace_out).write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: attention_linear head_dim={head_dim} kv_len={kv_len}, max_abs_err={max_abs_err:.3e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
