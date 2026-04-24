#!/usr/bin/env cs_python
"""Governed-lane simulator runner for the streaming-KV attention_tiled kernel.

Drives the host side of the streaming contract emit_csl_attention.zig now
produces: per-PE query shard of size q_len_per_pe x head_dim, block-at-a-time
H2D of K_tile/V_tile, one `compute` launch per tile, and a single
`finalize` at the end. Per-PE memory stays under the ~48 KiB .data.hi
budget (see bench/out/cslc-attn-streaming-probe/probe-result.json).

Verifies the reassembled (q_len, head_dim) output against a pure-numpy
flash-attention reference with fixed-seed fixtures.
"""

from __future__ import annotations

import sys

import numpy as np

import common

from cerebras.sdk.runtime.sdkruntimepybind import (  # pylint: disable=no-name-in-module
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)


def main() -> int:
    args = common.parse_runtime_args(__doc__ or "")

    # Must match the bundle's layout.csl params: see the solver output
    # from bench/tools/int4ple_manifest_compile_params.py
    # solve_attention_streaming. Defaults below are the small-shape fixture
    # used in direct cslc smokes; real HostPlan-bound runs pass their
    # chosen (width, head_dim, q_len, q_len_per_pe, block_size) through
    # compile params and this runner reads them from the compile-dir
    # manifest when that hookup lands.
    width = 8
    head_dim = 256
    q_len = 32
    q_len_per_pe = 4
    block_size = 16
    kv_len = 32

    rng = np.random.default_rng(seed=17)
    q_full = rng.standard_normal(size=(q_len, head_dim), dtype=np.float32)
    k_full = rng.standard_normal(size=(kv_len, head_dim), dtype=np.float32)
    v_full = rng.standard_normal(size=(kv_len, head_dim), dtype=np.float32)

    expected = common.numpy_tiled_attention_reference(
        q=q_full, k=k_full, v=v_full, scale=0.125,
    )

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    runner.load()
    runner.run()

    actual = common.run_streaming_tiled_attention(
        runner=runner,
        q_global=q_full,
        k_full=k_full,
        v_full=v_full,
        width=width,
        head_dim=head_dim,
        q_len=q_len,
        q_len_per_pe=q_len_per_pe,
        kv_len=kv_len,
        block_size=block_size,
        q_symbol="Q",
        k_symbol="K",
        v_symbol="V",
        output_symbol="O",
        memcpy_data_type=MemcpyDataType,
        memcpy_order=MemcpyOrder,
    )
    runner.stop()

    max_abs_err = common.max_abs_error(actual, expected)
    passed = bool(np.allclose(actual, expected, atol=5e-4, rtol=5e-3))
    if not passed:
        print(f"FAIL: max_abs_err={max_abs_err:.6f}")
        print(f"  expected[0, :4] = {expected[0, :4]}")
        print(f"  actual[0, :4]   = {actual[0, :4]}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="attention-tiled-streaming",
        cmaddr=cmaddr,
        width=width,
        chunk_size=block_size,
        total_elements=q_len * head_dim,
        max_abs_err=max_abs_err,
        sample_input=q_full[0, :4].tolist(),
        sample_expected=expected[0, :4].tolist(),
        sample_actual=actual[0, :4].tolist(),
    )
    print(
        f"PASS: streaming flash attention "
        f"(q_len={q_len}, kv_len={kv_len}, head_dim={head_dim}, "
        f"q_len_per_pe={q_len_per_pe}, block_size={block_size}), "
        f"max_abs_err={max_abs_err:.3e}, trace={trace_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
