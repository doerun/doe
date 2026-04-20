#!/usr/bin/env cs_python
"""Stage 3a: attn_out * inv_rms2 only (no wts multiply). Pinpoints first-mul drift."""
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

SIZE = 1024; NUM_LAYERS = 2
KERNEL = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-source/stage3a_probe.csl"
COMPILE_OUT = REPO_ROOT / "bench/out/scratch/e2b-stage3a-probe"


def numpy_stage3a(rows, proj, wts, size):
    attn_out = numpy_through_stage2(rows, proj, wts, size)
    eps = np.float32(1.0e-6)
    sum_sq2 = np.float32(0.0)
    for v in attn_out: sum_sq2 = np.float32(sum_sq2 + np.float32(v)*np.float32(v))
    mean_sq2 = np.float32(sum_sq2/np.float32(size))
    rms2 = np.float32(np.sqrt(np.float32(mean_sq2+eps)))
    inv_rms2 = np.float32(1.0/rms2)
    out = np.empty(size, dtype=np.float32)
    for i in range(size): out[i] = np.float32(attn_out[i] * inv_rms2)  # FIRST MULTIPLY ONLY
    return out


def main():
    COMPILE_OUT.mkdir(parents=True, exist_ok=True)
    config = SimfabConfig(dump_core=False); platform = get_platform("", config, SdkTarget.WSE3)
    layout = SdkLayout(platform); region = layout.create_code_region(str(KERNEL), "transformer_layer_shape", 1, 1)
    rx_rows = Color("rx_ple_rows"); rx_proj = Color("rx_ple_projection"); rx_wts = Color("rx_layer_weights"); tx_act = Color("tx_activation")
    recv = RoutingPosition().set_output([Route.RAMP]); send = RoutingPosition().set_input([Route.RAMP])
    region.set_param_all("size", SIZE)
    region.set_param_all("rx_ple_rows", rx_rows); region.set_param_all("rx_ple_projection", rx_proj)
    region.set_param_all("rx_layer_weights", rx_wts); region.set_param_all("tx_activation", tx_act)
    rp = region.create_input_port(rx_rows, Edge.LEFT, [recv], SIZE); pp = region.create_input_port(rx_proj, Edge.TOP, [recv], SIZE)
    wp = region.create_input_port(rx_wts, Edge.BOTTOM, [recv], SIZE); ap = region.create_output_port(tx_act, Edge.RIGHT, [send], SIZE)
    region.place(4, 2)
    rs = layout.create_input_stream(rp, io_buffer_size=1024); ps = layout.create_input_stream(pp, io_buffer_size=1024)
    ws = layout.create_input_stream(wp, io_buffer_size=1024); as_ = layout.create_output_stream(ap, io_buffer_size=1024)
    artifacts = layout.compile(out_prefix=str(COMPILE_OUT / "stage3a_probe"))
    runtime = SdkRuntime(artifacts, platform, memcpy_required=False)
    def load(s): return np.random.default_rng(seed=s).standard_normal(size=SIZE, dtype=np.float32)
    initial_rows = np.random.default_rng(seed=1000).standard_normal(size=SIZE, dtype=np.float32)
    per_proj = [load(2000+l) for l in range(NUM_LAYERS)]; per_wts = [load(2000+l) for l in range(NUM_LAYERS)]
    rows_ref = initial_rows.copy(); s3a_exp = []
    for l_idx in range(NUM_LAYERS):
        s3a_exp.append(numpy_stage3a(rows_ref, per_proj[l_idx], per_wts[l_idx], SIZE))
        rows_ref = compute_layer_block(rows_ref, per_proj[l_idx], per_wts[l_idx], SIZE)
    runtime.load(); runtime.run()
    all_r = []; rows_curr = initial_rows.copy()
    for l_idx in range(NUM_LAYERS):
        rcv = np.empty(SIZE, dtype=np.float32)
        runtime.send(rs, rows_curr, nonblock=True); runtime.send(ps, per_proj[l_idx], nonblock=True); runtime.send(ws, per_wts[l_idx], nonblock=True)
        runtime.receive(as_, rcv, SIZE, nonblock=False); all_r.append(rcv.copy())
        if l_idx == 0: rows_curr = compute_layer_block(initial_rows, per_proj[0], per_wts[0], SIZE)
    runtime.stop()
    for l_idx in range(NUM_LAYERS):
        d = np.abs(all_r[l_idx] - s3a_exp[l_idx])
        print(f"stage3a L{l_idx+1}: max={d.max():.4e}  nonzero={(d>0).sum()}/{SIZE}  match={np.array_equal(all_r[l_idx], s3a_exp[l_idx])}")
    return 0

if __name__ == "__main__": sys.exit(main())
