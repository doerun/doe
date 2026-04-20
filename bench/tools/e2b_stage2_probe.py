#!/usr/bin/env cs_python
"""Stage-2 (RMSNorm + MHA + residual) isolation probe for L2 drift."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import compute_layer_block, rope_cos_at, rope_sin_at, act_poly_c1

from cerebras.sdk.runtime.sdkruntimepybind import (
    Color, Edge, Route, RoutingPosition,
    SdkLayout, SdkRuntime, SdkTarget, SimfabConfig, get_platform,
)

SIZE = 1024
NUM_LAYERS = 2
INITIAL_ROWS_SEED = 1000
PER_LAYER_BASE = 2000
KERNEL = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-source/stage2_probe.csl"
COMPILE_OUT = REPO_ROOT / "bench/out/scratch/e2b-stage2-probe"


def numpy_through_stage2(rows, proj, wts, size):
    """Compute buf_out at end of stage 2 (attn_out) matching the CSL kernel
    in-order scalar f32 operations."""
    assert size % 4 == 0
    qs = size // 4
    eps = np.float32(1.0e-6)
    sum_sq = np.float32(0.0)
    for v in rows:
        sum_sq = np.float32(sum_sq + np.float32(v) * np.float32(v))
    mean_sq = np.float32(sum_sq / np.float32(size))
    rms = np.float32(np.sqrt(np.float32(mean_sq + eps)))
    inv_rms = np.float32(np.float32(1.0) / rms)
    rmsnorm_out = np.empty(size, dtype=np.float32)
    for i in range(size):
        rmsnorm_out[i] = np.float32(np.float32(rows[i] * inv_rms) * np.float32(proj[i]))

    num_heads = 8; head_dim = 8; kv_len_per_head = 4
    num_pairs = head_dim // 2
    per_head_K_len = head_dim * kv_len_per_head
    per_head_stride = 2 * per_head_K_len
    attn_flat_len = num_heads * head_dim

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
            q_rot[a + 0] = np.float32(np.float32(qc * q0) - np.float32(qs_ * q1))
            q_rot[a + 1] = np.float32(np.float32(qs_ * q0) + np.float32(qc * q1))
        k_rot = np.zeros(head_dim, dtype=np.float32)
        lmax = np.float32(0.0)
        for d in range(num_pairs):
            a = 2 * d
            k0 = np.float32(wts[base_h + a + 0])
            k1 = np.float32(wts[base_h + a + 1])
            kc = rope_cos_at(0, d); ks = rope_sin_at(0, d)
            k_rot[a + 0] = np.float32(np.float32(kc * k0) - np.float32(ks * k1))
            k_rot[a + 1] = np.float32(np.float32(ks * k0) + np.float32(kc * k1))
        l_seed = np.float32(0.0)
        for dd in range(head_dim):
            l_seed = np.float32(l_seed + np.float32(q_rot[dd] * k_rot[dd]))
        lmax = l_seed
        for j in range(kv_len_per_head):
            for d in range(num_pairs):
                a = 2 * d
                k0 = np.float32(wts[base_h + j * head_dim + a + 0])
                k1 = np.float32(wts[base_h + j * head_dim + a + 1])
                kc = rope_cos_at(j, d); ks = rope_sin_at(j, d)
                k_rot[a + 0] = np.float32(np.float32(kc * k0) - np.float32(ks * k1))
                k_rot[a + 1] = np.float32(np.float32(ks * k0) + np.float32(kc * k1))
            l = np.float32(0.0)
            for dd in range(head_dim):
                l = np.float32(l + np.float32(q_rot[dd] * k_rot[dd]))
            if l > lmax: lmax = l
        sum_w = np.float32(0.0)
        weighted_v = np.zeros(head_dim, dtype=np.float32)
        for j in range(kv_len_per_head):
            for d in range(num_pairs):
                a = 2 * d
                k0 = np.float32(wts[base_h + j * head_dim + a + 0])
                k1 = np.float32(wts[base_h + j * head_dim + a + 1])
                kc = rope_cos_at(j, d); ks = rope_sin_at(j, d)
                k_rot[a + 0] = np.float32(np.float32(kc * k0) - np.float32(ks * k1))
                k_rot[a + 1] = np.float32(np.float32(ks * k0) + np.float32(kc * k1))
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
                v_hjd = np.float32(wts[base_h + per_head_K_len + j * head_dim + dd])
                weighted_v[dd] = np.float32(weighted_v[dd] + np.float32(wj * v_hjd))
        for dd in range(head_dim):
            attn_vals[q_base + dd] = np.float32(weighted_v[dd] / sum_w)

    out = np.empty(size, dtype=np.float32)
    for i in range(size):
        k_idx = i - (i // attn_flat_len) * attn_flat_len
        out[i] = np.float32(np.float32(attn_vals[k_idx]) + np.float32(rows[i]))
    return out


def main():
    COMPILE_OUT.mkdir(parents=True, exist_ok=True)
    config = SimfabConfig(dump_core=False)
    platform = get_platform("", config, SdkTarget.WSE3)
    layout = SdkLayout(platform)
    region = layout.create_code_region(str(KERNEL), "transformer_layer_shape", 1, 1)
    rx_rows = Color("rx_ple_rows"); rx_proj = Color("rx_ple_projection")
    rx_wts = Color("rx_layer_weights"); tx_act = Color("tx_activation")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])
    region.set_param_all("size", SIZE)
    region.set_param_all("rx_ple_rows", rx_rows); region.set_param_all("rx_ple_projection", rx_proj)
    region.set_param_all("rx_layer_weights", rx_wts); region.set_param_all("tx_activation", tx_act)
    rp = region.create_input_port(rx_rows, Edge.LEFT, [recv], SIZE)
    pp = region.create_input_port(rx_proj, Edge.TOP, [recv], SIZE)
    wp = region.create_input_port(rx_wts, Edge.BOTTOM, [recv], SIZE)
    ap = region.create_output_port(tx_act, Edge.RIGHT, [send], SIZE)
    region.place(4, 2)
    rs = layout.create_input_stream(rp, io_buffer_size=1024)
    ps = layout.create_input_stream(pp, io_buffer_size=1024)
    ws = layout.create_input_stream(wp, io_buffer_size=1024)
    as_ = layout.create_output_stream(ap, io_buffer_size=1024)
    artifacts = layout.compile(out_prefix=str(COMPILE_OUT / "stage2_probe"))
    runtime = SdkRuntime(artifacts, platform, memcpy_required=False)

    def load(seed):
        return np.random.default_rng(seed=seed).standard_normal(size=SIZE, dtype=np.float32)
    rng_init = np.random.default_rng(seed=INITIAL_ROWS_SEED)
    initial_rows = rng_init.standard_normal(size=SIZE, dtype=np.float32)
    per_layer_proj = [load(PER_LAYER_BASE + l) for l in range(NUM_LAYERS)]
    per_layer_wts = [load(PER_LAYER_BASE + l) for l in range(NUM_LAYERS)]

    # Per-layer stage-2 reference. For L2 rows_ref must be L1 FULL output
    # (numpy == CSL byte-identical at L1).
    rows_ref = initial_rows.copy()
    stage2_expected = []
    for l_idx in range(NUM_LAYERS):
        s2 = numpy_through_stage2(rows_ref, per_layer_proj[l_idx], per_layer_wts[l_idx], SIZE)
        stage2_expected.append(s2)
        rows_ref = compute_layer_block(rows_ref, per_layer_proj[l_idx], per_layer_wts[l_idx], SIZE)

    runtime.load(); runtime.run()
    all_received = []
    rows_curr = initial_rows.copy()
    for l_idx in range(NUM_LAYERS):
        received = np.empty(SIZE, dtype=np.float32)
        runtime.send(rs, rows_curr, nonblock=True)
        runtime.send(ps, per_layer_proj[l_idx], nonblock=True)
        runtime.send(ws, per_layer_wts[l_idx], nonblock=True)
        runtime.receive(as_, received, SIZE, nonblock=False)
        all_received.append(received.copy())
        # for L2, rows_curr must be L1 FULL-STAGE output (same as smoke runner)
        if l_idx == 0:
            rows_curr = compute_layer_block(initial_rows, per_layer_proj[0], per_layer_wts[0], SIZE)
    runtime.stop()

    for l_idx in range(NUM_LAYERS):
        diff = np.abs(all_received[l_idx] - stage2_expected[l_idx])
        print(f"stage2 L{l_idx+1}: max_abs={diff.max():.6e}  nonzero={(diff!=0).sum()}/{SIZE}  match={np.array_equal(all_received[l_idx], stage2_expected[l_idx])}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
