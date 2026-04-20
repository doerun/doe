#!/usr/bin/env cs_python
"""Stage-3 (post-attn RMSNorm, a.k.a. post_norm) isolation probe for L2 drift."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import compute_layer_block

sys.path.insert(0, str(REPO_ROOT / "bench" / "tools"))
from e2b_stage2_probe import numpy_through_stage2

from cerebras.sdk.runtime.sdkruntimepybind import (
    Color, Edge, Route, RoutingPosition,
    SdkLayout, SdkRuntime, SdkTarget, SimfabConfig, get_platform,
)

SIZE = 1024
NUM_LAYERS = 2
INITIAL_ROWS_SEED = 1000
PER_LAYER_BASE = 2000
KERNEL = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-source/stage3_probe.csl"
COMPILE_OUT = REPO_ROOT / "bench/out/scratch/e2b-stage3-probe"


def numpy_through_stage3(rows, proj, wts, size):
    """Continue through stage 3: post-attn RMSNorm with gamma2 broadcast 4x."""
    attn_out = numpy_through_stage2(rows, proj, wts, size)
    qs = size // 4
    eps = np.float32(1.0e-6)
    sum_sq2 = np.float32(0.0)
    for v in attn_out:
        sum_sq2 = np.float32(sum_sq2 + np.float32(v) * np.float32(v))
    mean_sq2 = np.float32(sum_sq2 / np.float32(size))
    rms2 = np.float32(np.sqrt(np.float32(mean_sq2 + eps)))
    inv_rms2 = np.float32(np.float32(1.0) / rms2)
    post_norm = np.empty(size, dtype=np.float32)
    for i in range(size):
        g_idx = i
        while g_idx >= qs:
            g_idx -= qs
        post_norm[i] = np.float32(np.float32(attn_out[i] * inv_rms2) * np.float32(wts[g_idx]))
    return post_norm


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
    artifacts = layout.compile(out_prefix=str(COMPILE_OUT / "stage3_probe"))
    runtime = SdkRuntime(artifacts, platform, memcpy_required=False)

    def load(seed):
        return np.random.default_rng(seed=seed).standard_normal(size=SIZE, dtype=np.float32)
    rng_init = np.random.default_rng(seed=INITIAL_ROWS_SEED)
    initial_rows = rng_init.standard_normal(size=SIZE, dtype=np.float32)
    per_layer_proj = [load(PER_LAYER_BASE + l) for l in range(NUM_LAYERS)]
    per_layer_wts = [load(PER_LAYER_BASE + l) for l in range(NUM_LAYERS)]

    rows_ref = initial_rows.copy()
    stage3_expected = []
    for l_idx in range(NUM_LAYERS):
        s3 = numpy_through_stage3(rows_ref, per_layer_proj[l_idx], per_layer_wts[l_idx], SIZE)
        stage3_expected.append(s3)
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
        if l_idx == 0:
            rows_curr = compute_layer_block(initial_rows, per_layer_proj[0], per_layer_wts[0], SIZE)
    runtime.stop()
    # Save L2 received output for offline analysis.
    import numpy as _np
    _np.save('bench/out/scratch/e2b-stage3-probe-L2-received.npy', all_received[1])
    _np.save('bench/out/scratch/e2b-stage3-probe-L2-expected.npy', stage3_expected[1])

    for l_idx in range(NUM_LAYERS):
        diff = np.abs(all_received[l_idx] - stage3_expected[l_idx])
        print(f"stage3 L{l_idx+1}: max_abs={diff.max():.6e}  nonzero={(diff!=0).sum()}/{SIZE}  match={np.array_equal(all_received[l_idx], stage3_expected[l_idx])}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
