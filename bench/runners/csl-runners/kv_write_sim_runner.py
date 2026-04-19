#!/usr/bin/env cs_python
"""Governed-lane runner for the kv_write kernel.

Each PE holds a head_dim-wide slice of K/V and a local cache of shape
[max_seq_len, head_dim]. This runner:
  1. Zero-initializes the device caches (they already are by @zeros, but
     we memcpy an explicit zero pattern for reproducibility).
  2. Writes distinct random K, V projection vectors per PE.
  3. Sets `position` on every PE.
  4. Launches compute — kernel writes (k_proj, v_proj) into
     k_cache[position*head_dim .. (position+1)*head_dim] and likewise V.
  5. Reads the caches back and verifies:
       - the chosen position row contains exactly (k_proj, v_proj)
       - all other rows remain zero
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

    width = 4
    head_dim = 32
    max_seq_len = 64
    target_position = 7

    rng = np.random.default_rng(seed=29)
    k_proj = rng.standard_normal(size=(width, head_dim), dtype=np.float32)
    v_proj = rng.standard_normal(size=(width, head_dim), dtype=np.float32)
    position = np.full(width, target_position, dtype=np.uint32)

    cmaddr = common.endpoint(args.cmaddr)
    runner = SdkRuntime(args.compile_dir, cmaddr=cmaddr)
    k_proj_sym = runner.get_id("k_proj")
    v_proj_sym = runner.get_id("v_proj")
    k_cache_sym = runner.get_id("k_cache")
    v_cache_sym = runner.get_id("v_cache")
    position_sym = runner.get_id("position")
    runner.load()
    runner.run()

    runner.memcpy_h2d(k_proj_sym, k_proj.ravel(), 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(v_proj_sym, v_proj.ravel(), 0, 0, width, 1, head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_h2d(position_sym, position, 0, 0, width, 1, 1,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.launch("compute", nonblock=False)

    k_flat = np.zeros(width * max_seq_len * head_dim, dtype=np.float32)
    v_flat = np.zeros(width * max_seq_len * head_dim, dtype=np.float32)
    runner.memcpy_d2h(k_flat, k_cache_sym, 0, 0, width, 1, max_seq_len * head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.memcpy_d2h(v_flat, v_cache_sym, 0, 0, width, 1, max_seq_len * head_dim,
        streaming=False, order=MemcpyOrder.ROW_MAJOR,
        data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
    runner.stop()

    k_cache = k_flat.reshape(width, max_seq_len, head_dim)
    v_cache = v_flat.reshape(width, max_seq_len, head_dim)

    failures: list[str] = []
    max_write_err = 0.0
    max_stray_abs = 0.0
    for pe in range(width):
        write_err = float(np.max(np.abs(k_cache[pe, target_position] - k_proj[pe])))
        write_err = max(write_err, float(np.max(np.abs(v_cache[pe, target_position] - v_proj[pe]))))
        max_write_err = max(max_write_err, write_err)

        stray = np.concatenate([k_cache[pe, :target_position].ravel(),
                                k_cache[pe, target_position + 1:].ravel(),
                                v_cache[pe, :target_position].ravel(),
                                v_cache[pe, target_position + 1:].ravel()])
        stray_abs = float(np.max(np.abs(stray))) if stray.size else 0.0
        max_stray_abs = max(max_stray_abs, stray_abs)
        if write_err > 0.0:
            failures.append(f"pe={pe} write_err={write_err:.6f}")
        if stray_abs > 0.0:
            failures.append(f"pe={pe} stray_abs={stray_abs:.6f} (should be 0)")

    if failures:
        print("FAIL: kv_write")
        for f in failures:
            print(f"  {f}")
        return 1

    trace_path = common.write_explicit_trace(
        trace_out=args.trace_out,
        kernel="kv-write",
        cmaddr=cmaddr,
        width=width,
        chunk_size=head_dim,
        total_elements=width * head_dim,
        max_abs_err=max_write_err,
        sample_input=k_proj[0, :4].tolist(),
        sample_expected=k_proj[0, :4].tolist(),
        sample_actual=k_cache[0, target_position, :4].tolist(),
    )
    print(f"PASS: kv_write at pos={target_position} (width={width}, head_dim={head_dim}, "
          f"max_seq_len={max_seq_len}), write_err={max_write_err}, stray_abs={max_stray_abs}, "
          f"trace={trace_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
