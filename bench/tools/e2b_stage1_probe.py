#!/usr/bin/env cs_python
"""Stage-1 (pre-attn RMSNorm) isolation probe for L2 drift.

Runs the stage1-only CSL probe kernel at bench/out/streaming-
executor/e2b-layer-block-source/stage1_probe.csl over a 2-layer
chain, using the same seeded-RNG inputs as e2b_layer_block_smoke.py.
Compares each layer's CSL output against numpy's stage-1 output
(compute_layer_block's stage 1 slice). If L2 stage-1 is bit-exact,
the drift is in stages 2/3/4. If L2 stage-1 drifts, the bug is in
stage 1 (or in how L1's output is fed back as L2's input).
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import compute_layer_block

from cerebras.sdk.runtime.sdkruntimepybind import (
    Color, Edge, Route, RoutingPosition,
    SdkLayout, SdkRuntime, SdkTarget, SimfabConfig, get_platform,
)

SIZE = 1024
NUM_LAYERS = 2
INITIAL_ROWS_SEED = 1000
PER_LAYER_BASE = 2000
KERNEL = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-source/stage1_probe.csl"
COMPILE_OUT = REPO_ROOT / "bench/out/scratch/e2b-stage1-probe"


def numpy_stage1(rows, proj, size):
    """Numpy scalar-f32 mirror of CSL stage 1 only."""
    assert size % 4 == 0
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


def main():
    COMPILE_OUT.mkdir(parents=True, exist_ok=True)
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform("", config, target)
    layout = SdkLayout(platform)
    region = layout.create_code_region(str(KERNEL), "transformer_layer_shape", 1, 1)

    rx_rows = Color("rx_ple_rows")
    rx_proj = Color("rx_ple_projection")
    rx_wts  = Color("rx_layer_weights")
    tx_act  = Color("tx_activation")
    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("size", SIZE)
    region.set_param_all("rx_ple_rows", rx_rows)
    region.set_param_all("rx_ple_projection", rx_proj)
    region.set_param_all("rx_layer_weights", rx_wts)
    region.set_param_all("tx_activation", tx_act)

    rp = region.create_input_port(rx_rows, Edge.LEFT, [recv], SIZE)
    pp = region.create_input_port(rx_proj, Edge.TOP, [recv], SIZE)
    wp = region.create_input_port(rx_wts,  Edge.BOTTOM, [recv], SIZE)
    ap = region.create_output_port(tx_act, Edge.RIGHT, [send], SIZE)
    region.place(4, 2)

    iobs = 1024
    rows_stream = layout.create_input_stream(rp, io_buffer_size=iobs)
    proj_stream = layout.create_input_stream(pp, io_buffer_size=iobs)
    wts_stream  = layout.create_input_stream(wp, io_buffer_size=iobs)
    act_stream  = layout.create_output_stream(ap, io_buffer_size=iobs)

    artifacts = layout.compile(out_prefix=str(COMPILE_OUT / "stage1_probe"))
    runtime = SdkRuntime(artifacts, platform, memcpy_required=False)

    def load(seed):
        return np.random.default_rng(seed=seed).standard_normal(size=SIZE, dtype=np.float32)

    rng_init = np.random.default_rng(seed=INITIAL_ROWS_SEED)
    initial_rows = rng_init.standard_normal(size=SIZE, dtype=np.float32)
    per_layer_proj = [load(PER_LAYER_BASE + l) for l in range(NUM_LAYERS)]
    per_layer_wts  = [load(PER_LAYER_BASE + l) for l in range(NUM_LAYERS)]

    # Numpy reference: L1 uses initial_rows. L2 uses L1 full-stage output
    # (since that's what the runner chain feeds back), but stage-1 output
    # is still a function of (L2_rows, L2_proj) where L2_rows = L1 FULL
    # output. So reference[l].stage1 = stage1(rows_at_layer_l, proj_at_layer_l).
    rows_ref = initial_rows.copy()
    stage1_expected = []
    for l_idx in range(NUM_LAYERS):
        s1 = numpy_stage1(rows_ref, per_layer_proj[l_idx], SIZE)
        stage1_expected.append(s1)
        # advance rows_ref via full-stage numpy so chain matches runner
        rows_ref = compute_layer_block(rows_ref, per_layer_proj[l_idx], per_layer_wts[l_idx], SIZE)

    runtime.load()
    runtime.run()
    all_received = []
    rows_curr = initial_rows.copy()
    for l_idx in range(NUM_LAYERS):
        received = np.empty(SIZE, dtype=np.float32)
        runtime.send(rows_stream, rows_curr, nonblock=True)
        runtime.send(proj_stream, per_layer_proj[l_idx], nonblock=True)
        runtime.send(wts_stream,  per_layer_wts[l_idx],  nonblock=True)
        runtime.receive(act_stream, received, SIZE, nonblock=False)
        all_received.append(received.copy())
        # CRITICAL: for L2 the "rows" must be L1 FULL-stage output (what
        # the smoke runner feeds), NOT L1 stage-1 output. Otherwise we
        # change the input chain and can't compare stage-1 alignment
        # vs the smoke runner's drift.
        # So for L2 we would need the FULL-layer CSL output from the
        # main smoke runner. But the stage1 probe only emits stage-1.
        # Workaround: use numpy's FULL L1 output as L2 rows (since the
        # runner says L1 CSL == L1 numpy, so L1 full output numpy ==
        # L1 full output CSL byte-identical).
        if l_idx == 0:
            rows_curr = rows_ref.copy() if False else compute_layer_block(
                initial_rows, per_layer_proj[0], per_layer_wts[0], SIZE
            )
    runtime.stop()

    for l_idx in range(NUM_LAYERS):
        diff = np.abs(all_received[l_idx] - stage1_expected[l_idx])
        print(f"stage1 L{l_idx+1}: max_abs={diff.max():.6e}  nonzero={(diff!=0).sum()}/{SIZE}  match={np.array_equal(all_received[l_idx], stage1_expected[l_idx])}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
