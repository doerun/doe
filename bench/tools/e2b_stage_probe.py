#!/usr/bin/env cs_python
"""Probe one E2B layer-block stage across repeated SDK invocations.

This is a diagnostic companion for e2b_layer_block_smoke.py. It runs a
stage-only CSL probe over the same two-layer seeded inputs and compares
against a scalar-f32 numpy mirror for that stage. For layer N, the input
rows are the full numpy output of layer N-1, so the probe tests the same
row distribution the real chained runner sees without depending on the
probe's partial-stage output as the next layer input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import (  # noqa: E402
    compute_layer_block,
    rope_cos_at,
    rope_sin_at,
)

from cerebras.sdk.runtime.sdkruntimepybind import (  # noqa: E402
    Color,
    Edge,
    Route,
    RoutingPosition,
    SdkLayout,
    SdkRuntime,
    SdkTarget,
    SimfabConfig,
    get_platform,
)


INITIAL_ROWS_SEED = 1000
PER_LAYER_BASE = 2000


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=int, choices=(1, 2, 3), default=2)
    p.add_argument("--size", type=int, default=1024)
    p.add_argument("--num-layers", type=int, default=2)
    p.add_argument(
        "--compile-out",
        default="bench/out/scratch/e2b-stage-probe",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


def load_seed(seed: int, size: int) -> np.ndarray:
    return np.random.default_rng(seed=seed).standard_normal(
        size=size, dtype=np.float32
    )


def numpy_stage1(rows: np.ndarray, proj: np.ndarray, size: int) -> np.ndarray:
    eps = np.float32(1.0e-6)
    sum_sq = np.float32(0.0)
    for v in rows:
        sum_sq = np.float32(sum_sq + np.float32(v) * np.float32(v))
    mean_sq = np.float32(sum_sq / np.float32(size))
    rms = np.float32(np.sqrt(np.float32(mean_sq + eps)))
    inv_rms = np.float32(np.float32(1.0) / rms)
    out = np.empty(size, dtype=np.float32)
    for i in range(size):
        out[i] = np.float32(np.float32(rows[i] * inv_rms) * np.float32(proj[i]))
    return out


def numpy_stage2(rows: np.ndarray, proj: np.ndarray, wts: np.ndarray, size: int) -> np.ndarray:
    """Numpy mirror of CSL through MHA + residual."""
    assert size % 4 == 0
    qs = size // 4
    rmsnorm_out = numpy_stage1(rows, proj, size)

    num_heads = 8
    head_dim = 8
    kv_len_per_head = 4
    num_pairs = head_dim // 2
    per_head_k_len = head_dim * kv_len_per_head
    per_head_stride = 2 * per_head_k_len
    attn_flat_len = num_heads * head_dim
    assert size % attn_flat_len == 0
    assert qs * 2 >= num_heads * per_head_stride

    attn_vals = np.zeros(attn_flat_len, dtype=np.float32)
    for h in range(num_heads):
        base_h = qs + h * per_head_stride
        q_base = h * head_dim

        q_rot = np.zeros(head_dim, dtype=np.float32)
        for d in range(num_pairs):
            a = 2 * d
            q0 = np.float32(rmsnorm_out[q_base + a + 0])
            q1 = np.float32(rmsnorm_out[q_base + a + 1])
            qc = rope_cos_at(kv_len_per_head, d)
            qs_ = rope_sin_at(kv_len_per_head, d)
            q_rot[a + 0] = np.float32(
                np.float32(qc * q0) - np.float32(qs_ * q1)
            )
            q_rot[a + 1] = np.float32(
                np.float32(qs_ * q0) + np.float32(qc * q1)
            )

        k_rot = np.zeros(head_dim, dtype=np.float32)
        for d in range(num_pairs):
            a = 2 * d
            k0 = np.float32(wts[base_h + a + 0])
            k1 = np.float32(wts[base_h + a + 1])
            kc = rope_cos_at(0, d)
            ks = rope_sin_at(0, d)
            k_rot[a + 0] = np.float32(
                np.float32(kc * k0) - np.float32(ks * k1)
            )
            k_rot[a + 1] = np.float32(
                np.float32(ks * k0) + np.float32(kc * k1)
            )
        l_seed = np.float32(0.0)
        for dd in range(head_dim):
            l_seed = np.float32(l_seed + np.float32(q_rot[dd] * k_rot[dd]))
        lmax = l_seed

        for j in range(kv_len_per_head):
            for d in range(num_pairs):
                a = 2 * d
                k0 = np.float32(wts[base_h + j * head_dim + a + 0])
                k1 = np.float32(wts[base_h + j * head_dim + a + 1])
                kc = rope_cos_at(j, d)
                ks = rope_sin_at(j, d)
                k_rot[a + 0] = np.float32(
                    np.float32(kc * k0) - np.float32(ks * k1)
                )
                k_rot[a + 1] = np.float32(
                    np.float32(ks * k0) + np.float32(kc * k1)
                )
            l = np.float32(0.0)
            for dd in range(head_dim):
                l = np.float32(l + np.float32(q_rot[dd] * k_rot[dd]))
            if l > lmax:
                lmax = l

        sum_w = np.float32(0.0)
        weighted_v = np.zeros(head_dim, dtype=np.float32)
        for j in range(kv_len_per_head):
            for d in range(num_pairs):
                a = 2 * d
                k0 = np.float32(wts[base_h + j * head_dim + a + 0])
                k1 = np.float32(wts[base_h + j * head_dim + a + 1])
                kc = rope_cos_at(j, d)
                ks = rope_sin_at(j, d)
                k_rot[a + 0] = np.float32(
                    np.float32(kc * k0) - np.float32(ks * k1)
                )
                k_rot[a + 1] = np.float32(
                    np.float32(ks * k0) + np.float32(kc * k1)
                )
            l = np.float32(0.0)
            for dd in range(head_dim):
                l = np.float32(l + np.float32(q_rot[dd] * k_rot[dd]))
            x = np.float32(l - lmax)
            if x > np.float32(-1.0):
                xp1 = np.float32(x + np.float32(1.0))
                sq = np.float32(xp1 * xp1)
                wj = np.float32(np.float32(0.25) * sq)
            else:
                wj = np.float32(0.0)
            sum_w = np.float32(sum_w + wj)
            for dd in range(head_dim):
                v_hjd = np.float32(
                    wts[base_h + per_head_k_len + j * head_dim + dd]
                )
                weighted_v[dd] = np.float32(
                    weighted_v[dd] + np.float32(wj * v_hjd)
                )
        for dd in range(head_dim):
            attn_vals[q_base + dd] = np.float32(weighted_v[dd] / sum_w)

    out = np.empty(size, dtype=np.float32)
    for i in range(size):
        k_idx = i - (i // attn_flat_len) * attn_flat_len
        out[i] = np.float32(np.float32(attn_vals[k_idx]) + np.float32(rows[i]))
    return out


def numpy_stage3(rows: np.ndarray, proj: np.ndarray, wts: np.ndarray, size: int) -> np.ndarray:
    """Numpy mirror of CSL through post-attn RMSNorm."""
    assert size % 4 == 0
    qs = size // 4
    eps = np.float32(1.0e-6)
    attn_out = numpy_stage2(rows, proj, wts, size)
    sum_sq = np.float32(0.0)
    for v in attn_out:
        sum_sq = np.float32(sum_sq + np.float32(v) * np.float32(v))
    mean_sq = np.float32(sum_sq / np.float32(size))
    rms = np.float32(np.sqrt(np.float32(mean_sq + eps)))
    inv_rms = np.float32(np.float32(1.0) / rms)
    out = np.empty(size, dtype=np.float32)
    for i in range(size):
        g_idx = i
        while g_idx >= qs:
            g_idx -= qs
        out[i] = np.float32(
            np.float32(attn_out[i] * inv_rms) * np.float32(wts[g_idx])
        )
    return out


def expected_stage(stage: int, rows: np.ndarray, proj: np.ndarray, wts: np.ndarray, size: int) -> np.ndarray:
    if stage == 1:
        return numpy_stage1(rows, proj, size)
    if stage == 2:
        return numpy_stage2(rows, proj, wts, size)
    if stage == 3:
        return numpy_stage3(rows, proj, wts, size)
    raise AssertionError(stage)


def main() -> int:
    args = parse_args()
    kernel = (
        REPO_ROOT
        / "bench/out/streaming-executor/e2b-layer-block-source"
        / f"stage{args.stage}_probe.csl"
    )
    compile_out = resolve(args.compile_out) / f"stage{args.stage}"
    compile_out.mkdir(parents=True, exist_ok=True)

    config = SimfabConfig(dump_core=False)
    platform = get_platform(args.cmaddr.strip(), config, SdkTarget.WSE3)
    layout = SdkLayout(platform)
    region = layout.create_code_region(str(kernel), "transformer_layer_shape", 1, 1)

    rx_rows = Color("rx_ple_rows")
    rx_proj = Color("rx_ple_projection")
    rx_wts = Color("rx_layer_weights")
    tx_act = Color("tx_activation")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("size", args.size)
    region.set_param_all("rx_ple_rows", rx_rows)
    region.set_param_all("rx_ple_projection", rx_proj)
    region.set_param_all("rx_layer_weights", rx_wts)
    region.set_param_all("tx_activation", tx_act)

    rows_port = region.create_input_port(rx_rows, Edge.LEFT, [recv], args.size)
    proj_port = region.create_input_port(rx_proj, Edge.TOP, [recv], args.size)
    wts_port = region.create_input_port(rx_wts, Edge.BOTTOM, [recv], args.size)
    act_port = region.create_output_port(tx_act, Edge.RIGHT, [send], args.size)
    region.place(4, 2)

    io_buffer_size = 1024
    rows_stream = layout.create_input_stream(rows_port, io_buffer_size=io_buffer_size)
    proj_stream = layout.create_input_stream(proj_port, io_buffer_size=io_buffer_size)
    wts_stream = layout.create_input_stream(wts_port, io_buffer_size=io_buffer_size)
    act_stream = layout.create_output_stream(act_port, io_buffer_size=io_buffer_size)

    artifacts = layout.compile(out_prefix=str(compile_out / f"stage{args.stage}_probe"))
    runtime = SdkRuntime(artifacts, platform, memcpy_required=False)

    initial_rows = load_seed(INITIAL_ROWS_SEED, args.size)
    per_layer_proj = [
        load_seed(PER_LAYER_BASE + l_idx, args.size)
        for l_idx in range(args.num_layers)
    ]
    per_layer_wts = [
        load_seed(PER_LAYER_BASE + l_idx, args.size)
        for l_idx in range(args.num_layers)
    ]

    stage_expected: list[np.ndarray] = []
    full_rows_by_layer: list[np.ndarray] = []
    rows_ref = initial_rows.copy()
    for l_idx in range(args.num_layers):
        full_rows_by_layer.append(rows_ref.copy())
        stage_expected.append(
            expected_stage(
                args.stage,
                rows_ref,
                per_layer_proj[l_idx],
                per_layer_wts[l_idx],
                args.size,
            )
        )
        rows_ref = compute_layer_block(
            rows_ref, per_layer_proj[l_idx], per_layer_wts[l_idx], args.size
        )

    runtime.load()
    runtime.run()
    all_received: list[np.ndarray] = []
    try:
        for l_idx in range(args.num_layers):
            received = np.empty(args.size, dtype=np.float32)
            task_rows = runtime.send(
                rows_stream, full_rows_by_layer[l_idx], nonblock=True
            )
            task_proj = runtime.send(
                proj_stream, per_layer_proj[l_idx], nonblock=True
            )
            task_wts = runtime.send(
                wts_stream, per_layer_wts[l_idx], nonblock=True
            )
            task_act = runtime.receive(
                act_stream, received, args.size, nonblock=True
            )
            runtime.task_wait(task_rows)
            runtime.task_wait(task_proj)
            runtime.task_wait(task_wts)
            runtime.task_wait(task_act)
            all_received.append(received.copy())
    finally:
        runtime.stop()

    all_match = True
    for l_idx, received in enumerate(all_received):
        diff = np.abs(received - stage_expected[l_idx])
        match = bool(np.array_equal(received, stage_expected[l_idx]))
        all_match = all_match and match
        nonzero = int(np.count_nonzero(diff))
        print(
            f"stage{args.stage} L{l_idx + 1}: "
            f"max_abs={float(diff.max()):.6e} "
            f"nonzero={nonzero}/{args.size} match={match}"
        )
        if not match:
            argmax = int(diff.argmax())
            print(
                "  argmax="
                f"{argmax} got={float(received[argmax]):.9g} "
                f"expected={float(stage_expected[l_idx][argmax]):.9g}"
            )
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
