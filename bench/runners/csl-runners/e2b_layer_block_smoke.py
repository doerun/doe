#!/usr/bin/env cs_python
"""GENERATED — first E2B layer-block smoke runner.

Produced by bench/tools/generate_e2b_layer_block_runner.py from
bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json (layer 0). Do not hand-edit; rerun the
generator instead.

Plan stream contract for this layer:
//   region:  transformer_layer_shape
//   layer:   0
//   input:   ple_rows_stream (2 bytes/PE)
//   input:   ple_projection_stream (23 bytes/PE)
//   input:   layer_weights_stream (2166 bytes/PE)

Smoke path: each stream carries 256 f32 values. The kernel
runs the full 4-stage layer block (pre-attn RMSNorm; MHA with vector
Q/K/V, real-cos/sin rope, poly_c1 softmax; post-attn RMSNorm; gated
MLP with poly_c1 activation), and the runner CHAINS num_layers (=2
by default) invocations of that kernel via the streaming runtime —
activation_out of layer L is fed back as ple_rows of layer L+1 (the
residual stream pattern of a transformer block tower), with distinct
per-layer ple_projection and layer_weights. The bit-exact host numpy
reference replays the same chain. Pass requires every layer to match
under np.array_equal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (
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

REPO_ROOT = Path(__file__).resolve().parents[3]
KERNEL_SOURCE = REPO_ROOT / "bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=256)
    p.add_argument(
        "--num-layers", type=int, default=35,
        help="How many layer-block invocations to chain (residual stream). "
             "Default = manifest.modelConfig.numLayers (35).",
    )
    p.add_argument(
        "--compile-out",
        default="bench/out/streaming-executor/e2b-layer-block-smoke",
    )
    p.add_argument(
        "--trace-out",
        default="bench/out/streaming-executor/e2b-layer-block-smoke-trace.json",
    )
    p.add_argument("--cmaddr", default="")
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else REPO_ROOT / p


def main() -> int:
    args = parse_args()
    compile_out = resolve(args.compile_out)
    compile_out.mkdir(parents=True, exist_ok=True)

    compile_start = time.time()
    config = SimfabConfig(dump_core=False)
    target = SdkTarget.WSE3
    platform = get_platform(args.cmaddr.strip(), config, target)
    layout = SdkLayout(platform)

    region = layout.create_code_region(
        str(KERNEL_SOURCE), "transformer_layer_shape", 1, 1
    )

    rx_ple_rows = Color("rx_ple_rows")
    rx_ple_projection = Color("rx_ple_projection")
    rx_layer_weights = Color("rx_layer_weights")
    tx_activation = Color("tx_activation")

    recv = RoutingPosition().set_output([Route.RAMP])
    send = RoutingPosition().set_input([Route.RAMP])

    region.set_param_all("size", args.size)
    region.set_param_all("rx_ple_rows", rx_ple_rows)
    region.set_param_all("rx_ple_projection", rx_ple_projection)
    region.set_param_all("rx_layer_weights", rx_layer_weights)
    region.set_param_all("tx_activation", tx_activation)

    rows_port = region.create_input_port(rx_ple_rows, Edge.LEFT, [recv], args.size)
    proj_port = region.create_input_port(rx_ple_projection, Edge.TOP, [recv], args.size)
    wts_port  = region.create_input_port(rx_layer_weights, Edge.BOTTOM, [recv], args.size)
    act_port  = region.create_output_port(tx_activation, Edge.RIGHT, [send], args.size)

    region.place(4, 2)

    io_buffer_size = 1024  # SdkLayout default; exposed for the receipt.
    rows_stream = layout.create_input_stream(rows_port, io_buffer_size=io_buffer_size)
    proj_stream = layout.create_input_stream(proj_port, io_buffer_size=io_buffer_size)
    wts_stream  = layout.create_input_stream(wts_port, io_buffer_size=io_buffer_size)
    act_stream  = layout.create_output_stream(act_port, io_buffer_size=io_buffer_size)

    compile_prefix = str(compile_out / "transformer_layer_shape")
    compile_artifacts = layout.compile(out_prefix=compile_prefix)
    compile_elapsed_ms = (time.time() - compile_start) * 1000.0

    run_start = time.time()
    runtime = SdkRuntime(compile_artifacts, platform, memcpy_required=False)
    num_layers_smoke = args.num_layers
    max_abs_err = -1.0
    per_layer_max_abs_err = [-1.0] * num_layers_smoke
    per_layer_elapsed_ms = [-1.0] * num_layers_smoke
    passed = False

    # Reference numpy implementation of the full 4-stage layer block.
    # Lifted into a helper so the multi-layer chain below can call it
    # once per layer with distinct per-layer ple_projection and
    # layer_weights. All operations mirror the CSL kernel's in-order
    # scalar f32 accumulations so np.array_equal serves as the
    # bit-exact pass gate.
    def compute_layer_block(rows, proj, wts, size):
        # layer_weights reshape: four back-to-back quarters
        # [gamma2, per_head_KV, gate_w, up_w].
        assert size % 4 == 0, "kernel requires size % 4 == 0"
        qs = size // 4
        rmsnorm_eps = np.float32(1.0e-6)
        # Stage 1: pre-attn RMSNorm.
        sum_sq = np.float32(0.0)
        for v in rows:
            sum_sq = np.float32(sum_sq + np.float32(v) * np.float32(v))
        mean_sq = np.float32(sum_sq / np.float32(size))
        rms = np.float32(np.sqrt(np.float32(mean_sq + rmsnorm_eps)))
        inv_rms = np.float32(np.float32(1.0) / rms)
        rmsnorm_out = np.empty(size, dtype=np.float32)
        for i in range(size):
            rmsnorm_out[i] = np.float32(
                np.float32(rows[i] * inv_rms) * np.float32(proj[i])
            )
        # Stage 2: multi-head attention with PER-HEAD VECTOR Q/K/V
        # and ROPE positional encoding.
        #   num_heads = 2, head_dim = 2, kv_len_per_head = 2
        #   per_head_K_len = head_dim * kv_len_per_head = 4
        #   per_head_stride = 2 * per_head_K_len = 8
        #   rope table: actual cos(p), sin(p) for p in [0, 1, 2], as
        #     9-decimal-digit literals that round-trip to identical
        #     f32 bit patterns in both CSL and numpy (IEEE-754).
        num_heads = 8
        head_dim = 4
        kv_len_per_head = 2
        num_pairs = head_dim // 2
        per_head_K_len = head_dim * kv_len_per_head
        per_head_stride = 2 * per_head_K_len
        attn_flat_len = num_heads * head_dim
        assert size % attn_flat_len == 0, (
            "size must be divisible by num_heads * head_dim"
        )
        assert qs * 2 >= num_heads * per_head_stride, (
            "per_head_KV region (2*qs) too small for vector per-head KV"
        )

        # Rope table indexed by (position, pair_index). head_dim=4 has
        # 2 rope pairs at theta_d = base^(-2d/head_dim) with base=100,
        # so theta_0=1.0 and theta_1=0.1. 9-decimal-digit literals
        # round-trip to identical f32 bit patterns in both CSL and
        # numpy under IEEE-754 correct rounding.
        def rope_cos_at(p, d):
            if d == 0:
                if p == 0: return np.float32(1.0)
                if p == 1: return np.float32(0.540302277)   # cos(1)
                return np.float32(-0.416146845)              # cos(2)
            # d == 1, theta = 0.1
            if p == 0: return np.float32(1.0)
            if p == 1: return np.float32(0.995004177)        # cos(0.1)
            return np.float32(0.980066597)                   # cos(0.2)

        def rope_sin_at(p, d):
            if d == 0:
                if p == 0: return np.float32(0.0)
                if p == 1: return np.float32(0.841470957)    # sin(1)
                return np.float32(0.909297407)               # sin(2)
            # d == 1, theta = 0.1
            if p == 0: return np.float32(0.0)
            if p == 1: return np.float32(0.0998334140)       # sin(0.1)
            return np.float32(0.198669329)                   # sin(0.2)

        attn_vals = np.zeros(attn_flat_len, dtype=np.float32)
        for h in range(num_heads):
            base_h = qs + h * per_head_stride
            q_base = h * head_dim

            # Rope-rotate Q_h once per head at position kv_len_per_head.
            # head_dim=4 has 2 rope pairs (each pair covers 2 dims).
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

            # Pass 1: max logit. Seed lmax from j=0 so the accumulation
            # pattern matches CSL (0.0-init, per-d accumulation).
            k_rot = np.zeros(head_dim, dtype=np.float32)
            lmax = np.float32(0.0)
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
                l_seed = np.float32(
                    l_seed + np.float32(q_rot[dd] * k_rot[dd])
                )
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

            # Pass 2: poly_c1 softmax weights + per-d weighted V.
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
                        wts[base_h + per_head_K_len + j * head_dim + dd]
                    )
                    weighted_v[dd] = np.float32(
                        weighted_v[dd] + np.float32(wj * v_hjd)
                    )
            for dd in range(head_dim):
                attn_vals[q_base + dd] = np.float32(weighted_v[dd] / sum_w)
        attn_out = np.empty(size, dtype=np.float32)
        for i in range(size):
            k_idx = i - (i // attn_flat_len) * attn_flat_len
            attn_out[i] = np.float32(
                np.float32(attn_vals[k_idx]) + np.float32(rows[i])
            )
        # Stage 3: post-attn RMSNorm with gamma2 = wts[0..qs)
        # broadcast 4x over the full token.
        sum_sq2 = np.float32(0.0)
        for v in attn_out:
            sum_sq2 = np.float32(sum_sq2 + np.float32(v) * np.float32(v))
        mean_sq2 = np.float32(sum_sq2 / np.float32(size))
        rms2 = np.float32(np.sqrt(np.float32(mean_sq2 + rmsnorm_eps)))
        inv_rms2 = np.float32(np.float32(1.0) / rms2)
        post_norm = np.empty(size, dtype=np.float32)
        for i in range(size):
            g_idx = i
            while g_idx >= qs:
                g_idx -= qs
            post_norm[i] = np.float32(
                np.float32(attn_out[i] * inv_rms2) * np.float32(wts[g_idx])
            )
        # Stage 4: gated MLP. gate_w and up_w are now qs/2 elems each
        # (shrunken to make room for per-head KV in stage 2).
        #   gate = wts[3qs..3qs+qs/2) . post_norm[0..qs/2)
        #   up   = wts[3qs+qs/2..4qs) . post_norm[qs/2..qs)
        # Activation is the shared piecewise-polynomial GELU (act_poly_c1).
        mlp_len = qs // 2
        gate_base = 3 * qs
        up_base = gate_base + mlp_len
        gate = np.float32(0.0)
        for k in range(mlp_len):
            gate = np.float32(
                gate + np.float32(wts[gate_base + k])
                * np.float32(post_norm[k])
            )
        up = np.float32(0.0)
        for k in range(mlp_len):
            up = np.float32(
                up + np.float32(wts[up_base + k])
                * np.float32(post_norm[mlp_len + k])
            )
        # Piecewise-polynomial GELU approximation, C^1-continuous at
        # the break points +/- 1. Explicitly parenthesized so CSL and
        # numpy compute the identical f32 op sequence.
        def act_poly_c1(x):
            x = np.float32(x)
            if x >= np.float32(1.0):
                return x
            if x <= np.float32(-1.0):
                return np.float32(0.0)
            xp1 = np.float32(x + np.float32(1.0))
            sq = np.float32(xp1 * xp1)
            return np.float32(np.float32(0.25) * sq)
        expected = np.empty(size, dtype=np.float32)
        for i in range(size):
            pre_act = np.float32(up * np.float32(post_norm[i]))
            act = act_poly_c1(pre_act)
            expected[i] = np.float32(
                np.float32(gate * act) + np.float32(post_norm[i])
            )
        return expected

    # Multi-layer chain. Each layer reads its own ple_projection and
    # layer_weights; activation_out of layer L is fed back as ple_rows
    # of layer L+1 (the residual stream pattern of a transformer block
    # tower). The same SdkLayout compile artifacts are reused across
    # layers via the streaming-runtime send/receive primitives — no
    # recompile per layer.
    try:
        runtime.load()
        runtime.run()

        # Per-layer-index deterministic seeds. Pinning each layer's
        # data source independently lets a future loader (manifest
        # weights, Doppler-exported slice) swap in real per-layer
        # tensors one layer at a time without disturbing the bit-
        # exact gate on the remaining synthetic layers.
        INITIAL_ROWS_SEED = 1000
        PER_LAYER_BASE    = 2000
        rng_init = np.random.default_rng(seed=INITIAL_ROWS_SEED)
        initial_rows = rng_init.standard_normal(size=args.size, dtype=np.float32)
        per_layer_proj: list = []
        per_layer_wts:  list = []
        per_layer_seeds: list = []
        for l_idx in range(num_layers_smoke):
            seed_l = PER_LAYER_BASE + l_idx
            rng_l = np.random.default_rng(seed=seed_l)
            per_layer_proj.append(
                rng_l.standard_normal(size=args.size, dtype=np.float32)
            )
            per_layer_wts.append(
                rng_l.standard_normal(size=args.size, dtype=np.float32)
            )
            per_layer_seeds.append(seed_l)

        # Numpy reference: chain compute_layer_block num_layers_smoke
        # times, threading expected[L] -> rows for L+1.
        all_expected = []
        rows_ref = initial_rows.copy()
        for l_idx in range(num_layers_smoke):
            expected_l = compute_layer_block(
                rows_ref, per_layer_proj[l_idx], per_layer_wts[l_idx], args.size
            )
            all_expected.append(expected_l)
            rows_ref = expected_l

        # Device chain: same loop, threading received[L] -> rows for L+1.
        # Per-layer elapsed-ms is recorded so timing scales visibly when
        # the chain depth grows (e.g. 35 layers for full E2B).
        all_received = []
        rows_curr = initial_rows.copy()
        for l_idx in range(num_layers_smoke):
            layer_start = time.time()
            received = np.empty(args.size, dtype=np.float32)
            runtime.send(rows_stream, rows_curr, nonblock=True)
            runtime.send(proj_stream, per_layer_proj[l_idx], nonblock=True)
            runtime.send(wts_stream,  per_layer_wts[l_idx],  nonblock=True)
            runtime.receive(act_stream, received, args.size, nonblock=True)
            per_layer_elapsed_ms[l_idx] = (time.time() - layer_start) * 1000.0
            all_received.append(received.copy())
            rows_curr = received

        runtime.stop()

        # Per-layer parity. Pass requires every layer to be bit-exact.
        layer_passed = []
        for l_idx in range(num_layers_smoke):
            err = float(np.max(np.abs(all_received[l_idx] - all_expected[l_idx])))
            per_layer_max_abs_err[l_idx] = err
            layer_passed.append(
                bool(np.array_equal(all_received[l_idx], all_expected[l_idx]))
            )
        max_abs_err = max(per_layer_max_abs_err) if per_layer_max_abs_err else -1.0
        passed = bool(all(layer_passed))
        run_status = "succeeded" if passed else "mismatch"
    except Exception as exc:  # pylint: disable=broad-except
        run_status = f"failed:" + type(exc).__name__ + ":" + str(exc)[:160]
    run_elapsed_ms = (time.time() - run_start) * 1000.0

    trace = {
        "schemaVersion": 1,
        "artifactKind": "doe_streaming_executor_trace",
        "target": "wse3",
        "modelId": "gemma-4-e2b-it-text-q4k-ehf16-af32",
        "executorIteration": 8,
        "sourcePlan": {
            "streamGraphPath": "",
            "executionPlanPath": "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
            "kernelSourcePath": "bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl",
        },
        "region": {
            "regionId": "transformer_layer_shape_L00",
            "width": 1,
            "height": 1,
            "peCount": 1,
        },
        "executedCompile": {
            "compilePrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "elapsedMs": compile_elapsed_ms,
            "status": "succeeded",
        },
        "executedRun": {
            "status": run_status,
            "elapsedMs": run_elapsed_ms,
            "numLayersChained": num_layers_smoke,
            "perLayerElapsedMs": per_layer_elapsed_ms,
            "observedBytesTransferredPerPe":
                args.size * 4 * 4 * num_layers_smoke,
            "observedBytesTransferredTotal":
                args.size * 4 * 4 * num_layers_smoke,
            "dataSource": {
                "kind": "synthetic_seeded_rng",
                "initialRowsSeed": INITIAL_ROWS_SEED,
                "perLayerBase": PER_LAYER_BASE,
                "perLayerSeeds": per_layer_seeds,
                "swapBoundary": (
                    "Each layer's projection and weights derive from "
                    "rng_l = default_rng(PER_LAYER_BASE + l_idx). A "
                    "future weight loader can replace the per_layer_proj/"
                    "per_layer_wts arrays one layer at a time without "
                    "changing the bit-exact gate on the remaining "
                    "synthetic layers."
                ),
            },
            "numericalParity": {
                "maxAbsErr": max_abs_err,
                "perLayerMaxAbsErr": per_layer_max_abs_err,
                "atol": 0,
                "passed": passed,
            },
        },
        "streams": [
            {"role": "input",  "color": "rx_ple_rows",        "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_ple_projection",  "size": args.size, "dtype": "float32"},
            {"role": "input",  "color": "rx_layer_weights",   "size": args.size, "dtype": "float32"},
            {"role": "output", "color": "tx_activation",      "size": args.size, "dtype": "float32"},
        ],
        "layerBlockSmoke": {
            "planPath": "bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json",
            "planSha256": "e8fa1420ddcac5700338b9a1b96071d3403c95618c5c6ea536f24e581a505729",
            "layerIndex": 0,
            "regionName": "transformer_layer_shape",
            "kernelSourcePath": "bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl",
            "kernelSourceSha256": "d32eb224684a5ce39f1e06fd7b139380fafb4117afee9c0255dd93457b1a4042",
            "kernelIsStub": False,
            "combineRule": (
                "rmsnorm[i] = (ple_rows[i] / sqrt(mean(ple_rows^2) + 1e-6)) * ple_projection[i]; "
                "num_heads = 8; head_dim = 4; kv_len_per_head = 2; num_pairs = head_dim/2; "
                "per_head_K_len = head_dim * kv_len_per_head; stride = 2*per_head_K_len; "
                "flat_len = num_heads*head_dim; mlp_len = qs/2; "
                "rope_table[p,d]: pair d=0 at theta_0=1 -> "
                "(1,0),(0.540302277,0.841470957),(-0.416146845,0.909297407); "
                "pair d=1 at theta_1=0.1 -> "
                "(1,0),(0.995004177,0.0998334140),(0.980066597,0.198669329); "
                "rope_rot(x0,x1,p,d) = (cos[p,d]*x0 - sin[p,d]*x1, "
                "sin[p,d]*x0 + cos[p,d]*x1); "
                "for h in [0, num_heads): "
                "Q_h[d] = rmsnorm[h*head_dim + d]; "
                "for d in [0, num_pairs): "
                "(Q_r[2d], Q_r[2d+1]) = rope_rot(Q_h[2d], Q_h[2d+1], "
                "kv_len_per_head, d); "
                "base_h = qs + h*stride; "
                "K_h[j][d] = layer_weights[base_h + j*head_dim + d]; "
                "(K_r[j][2d], K_r[j][2d+1]) = rope_rot(K_h[j][2d], "
                "K_h[j][2d+1], j, d); "
                "V_h[j][d] = layer_weights[base_h + per_head_K_len + j*head_dim + d]; "
                "logits_h[j] = sum_d Q_r[d] * K_r[j][d]; "
                "m_h = max_j logits_h[j]; "
                "w_h[j] = poly_c1(logits_h[j] - m_h); "
                "attn_val[h][d] = sum_j (w_h[j]/sum_j w_h[j]) * V_h[j][d]; "
                "attn_out[i] = attn_val_flat[i mod flat_len] + ple_rows[i]; "
                "post_norm[i] = (attn_out[i] / sqrt(mean(attn_out^2) + 1e-6)) "
                "* layer_weights[i mod qs]; "
                "gate = sum_k layer_weights[3*qs + k] * post_norm[k]     (k in [0, mlp_len)); "
                "up   = sum_k layer_weights[3*qs + mlp_len + k] * post_norm[mlp_len + k]; "
                "poly_c1(x) = 0 if x<=-1, x if x>=1, 0.25*(x+1)^2 otherwise; "
                "activation_out[i] = gate * poly_c1(up * post_norm[i]) + post_norm[i]"
            ),
            "kernelStage": (
                "pre_attn_rmsnorm+mha_8head_hd4_multi_pair_rope_real"
                "_poly_c1_softmax+residual"
                "+post_attn_rmsnorm+gated_mlp_poly_c1_gelu"
                "+multi_layer_chain"
            ),
            "status": run_status,
            "targetMode": "local_simfabric",
            "compileArtifactDir": str(compile_out.relative_to(REPO_ROOT)),
            "compileArtifactPrefix": str(Path(compile_prefix).relative_to(REPO_ROOT)),
            "connectionGraph": {
                "region": "transformer_layer_shape",
                "grid": {"width": 1, "height": 1, "peCount": 1, "place": [4, 2]},
                "inputPorts": [
                    {"color": "rx_ple_rows",       "edge": "LEFT",   "size": args.size},
                    {"color": "rx_ple_projection", "edge": "TOP",    "size": args.size},
                    {"color": "rx_layer_weights",  "edge": "BOTTOM", "size": args.size},
                ],
                "outputPorts": [
                    {"color": "tx_activation",     "edge": "RIGHT",  "size": args.size},
                ],
                "crossRegionConnections": [],
            },
            "hostIoLayout": [
                {"streamId": "ple_rows_stream",       "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 2},
                {"streamId": "ple_projection_stream", "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 23},
                {"streamId": "layer_weights_stream",  "role": "input",  "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 2166},
                {"streamId": "activation_out_stream", "role": "output", "elementsPerPe": args.size,
                  "dtype": "float32", "order": "row_major", "roi": [4, 2, 1, 1],
                  "tileBehavior": "stream", "planPayloadBytes": 0},
            ],
            "ioBufferSizes": {
                "rows": io_buffer_size,
                "proj": io_buffer_size,
                "wts":  io_buffer_size,
                "activation": io_buffer_size,
            },
            "sendReceiveCounts": {"sends": 3, "receives": 1},
            "simulatorArtifactPaths": {
                "compileDir": str(compile_out.relative_to(REPO_ROOT)),
                "runLogs": [],
                "coreFile": None,
            },
            "sourceModelReceiptPath": "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json",
            "perKernelShapes": [
    {
        "pattern": "gather",
        "emitter": "emitGatherLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:237)",
        "emitterWidened2D": True,
        "paramsShape": {
            "width": 256,
            "height": 1,
            "hidden_size": 1536,
            "rows_per_pe": 8,
            "num_tokens": 256
        },
        "cslcParamsString": "width:256,height:1,hidden_size:1536,rows_per_pe:8,num_tokens:256",
        "derivationSource": "width/num_tokens from --size smoke arg; hidden_size from manifest.modelConfig.hiddenDim; height=1 for smoke (2-D needed for 31B full-grid per layout-2d-needs audit); rows_per_pe is the emitter default with no manifest override yet.",
        "manifestSteps": [
            "embed_tokens",
            "ple_gather",
            "ple_gather"
        ],
        "fixtureEquivalentCslcParamsString": "width:4,height:1"
    },
    {
        "pattern": "rope",
        "emitter": "emitRoPELayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:263)",
        "emitterWidened2D": False,
        "paramsShape": {
            "width": 256,
            "head_dim": 512,
            "num_pairs": 256
        },
        "cslcParamsString": "width:256,head_dim:512,num_pairs:256",
        "derivationSource": "width = num_tokens from --size (1-D layout, per-token \u2014 layout-2d-needs audit keeps rope 1-D since num_tokens<=i16); head_dim from manifest.modelConfig.headDim; num_pairs is the standard RoPE half-head_dim convention (cos+sin pair count).",
        "manifestSteps": [
            "rope_q",
            "rope_k",
            "rope_q",
            "rope_k"
        ],
        "fixtureEquivalentCslcParamsString": "width:4,height:1"
    },
    {
        "pattern": "tiled_matmul",
        "emitter": "emitMatmulLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:168)",
        "emitterWidened2D": True,
        "invocations": [
            {
                "stepName": "q_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 768,
                    "Nt": 2048
                },
                "cslcParamsString": "P:2,Mt:128,Kt:768,Nt:2048",
                "weightMatrixShape": "M=256 K=1536 N=4096"
            },
            {
                "stepName": "k_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 768,
                    "Nt": 2048
                },
                "cslcParamsString": "P:2,Mt:128,Kt:768,Nt:2048",
                "weightMatrixShape": "M=256 K=1536 N=4096"
            },
            {
                "stepName": "v_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 768,
                    "Nt": 2048
                },
                "cslcParamsString": "P:2,Mt:128,Kt:768,Nt:2048",
                "weightMatrixShape": "M=256 K=1536 N=4096"
            },
            {
                "stepName": "o_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 2048,
                    "Nt": 768
                },
                "cslcParamsString": "P:2,Mt:128,Kt:2048,Nt:768",
                "weightMatrixShape": "M=256 K=4096 N=1536"
            },
            {
                "stepName": "gate_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 768,
                    "Nt": 3072
                },
                "cslcParamsString": "P:2,Mt:128,Kt:768,Nt:3072",
                "weightMatrixShape": "M=256 K=1536 N=6144"
            },
            {
                "stepName": "up_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 768,
                    "Nt": 3072
                },
                "cslcParamsString": "P:2,Mt:128,Kt:768,Nt:3072",
                "weightMatrixShape": "M=256 K=1536 N=6144"
            },
            {
                "stepName": "down_proj",
                "paramsShape": {
                    "P": 2,
                    "Mt": 128,
                    "Kt": 3072,
                    "Nt": 768
                },
                "cslcParamsString": "P:2,Mt:128,Kt:3072,Nt:768",
                "weightMatrixShape": "M=256 K=6144 N=1536"
            }
        ],
        "derivationSource": "P = 2 for smoke (even SUMMA partition; real deployment picks P from memory-plan); Mt/Kt/Nt = weight-matrix dim // P. Weight matrix M/K/N derived from manifest.modelConfig: M = num_tokens (--size), K/N chosen per step \u2014 hiddenDim for projection inputs and output (q/k/v/o), intermediate = hiddenDim * ffnExpansionFactor for FFN gate/up N-dim and down K-dim, qkv_out_dim = numHeads * headDim for QKV N-dim. This per-invocation shape emission is the pattern the 4 audit-blocked emitters (dequant/sample/fused_gemv/fused_ffn) will also use.",
        "manifestSteps": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj"
        ],
        "fixtureEquivalentCslcParamsString": "width:2,height:2,P:2,Mt:8,Kt:8,Nt:8"
    },
    {
        "pattern": "attention_tiled",
        "emitter": "emitTiledAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:403)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "attention",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "kv_len": 4096,
                    "q_len": 256
                },
                "cslcParamsString": "width:256,head_dim:512,kv_len:4096,q_len:256"
            }
        ],
        "derivationSource": "width/q_len = num_tokens from --size (1-D per-tile row); head_dim from manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen as the prefill upper bound (4096 for both E2B and 31B \u2014 well under i16). Per the layout-2d-needs audit, attention_tiled stays 1-D.",
        "manifestSteps": [
            "attention"
        ],
        "fixtureEquivalentCslcParamsString": "width:4,height:1,head_dim:32,kv_len:64,q_len:32"
    },
    {
        "pattern": "attention_decode",
        "emitter": "emitDecodeAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:379)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "attention_sliding",
                "variant": "sliding",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "kv_chunk": 2
                },
                "cslcParamsString": "width:256,head_dim:512,kv_chunk:2",
                "kvLenBound": 512
            },
            {
                "stepName": "attention_global",
                "variant": "global",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "kv_chunk": 16
                },
                "cslcParamsString": "width:256,head_dim:512,kv_chunk:16",
                "kvLenBound": 4096
            }
        ],
        "derivationSource": "width = num_tokens from --size (1-D per-head-per-chunk); head_dim from manifest.modelConfig.headDim; kv_chunk = kv_len_bound // width with kv_len_bound = slidingWindowSize for the sliding variant and maxSeqLen for the global decode. Both bounds stay well under i16 at Gemma-4 shapes. Per the layout-2d-needs audit, attention_decode stays 1-D.",
        "manifestSteps": [
            "attention_sliding",
            "attention_global"
        ],
        "fixtureEquivalentCslcParamsString": "width:4,height:1,head_dim:32,kv_len:64,q_len:1"
    },
    {
        "pattern": "dequant",
        "emitter": "emitDequantLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:305)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 256,
                    "num_blocks": 1
                },
                "cslcParamsString": "width:256,num_blocks:1"
            }
        ],
        "derivationSource": "width = --size smoke arg; num_blocks = 1 fallback (no manifest step drives this). Gemma-4 fuses dequant into fused_gemv_dequant rather than issuing standalone dequant \u2014 this emitter stays live for future models that separate the two.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "fused_ffn",
        "emitter": "emitFusedFfnLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:557)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 256,
                    "in_dim": 1536,
                    "out_dim": 6144,
                    "in_per_pe": 6
                },
                "cslcParamsString": "width:256,in_dim:1536,out_dim:6144,in_per_pe:6"
            }
        ],
        "derivationSource": "width = --size; in_dim = hiddenDim; out_dim = intermediate = hiddenDim*ffnExpansionFactor; in_per_pe = in_dim // width. No manifest step \u2014 Gemma-4 runs the FFN as three separate matmul steps (gate_proj / up_proj / down_proj) rather than fusing into one kernel, so this entry covers emitter presence only.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "sample",
        "emitter": "emitSampleLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:428)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "sample",
                "paramsShape": {
                    "width": 256,
                    "chunk_size": 1024
                },
                "cslcParamsString": "width:256,chunk_size:1024",
                "vocabSize": 262144
            }
        ],
        "derivationSource": "width = --size smoke arg; chunk_size = vocabSize // width (vocabSize from manifest.modelConfig.vocabSize = 262,144 for Gemma-4). Smoke partitions evenly but deployment will pick a chunk_size that balances per-PE SRAM budget against reduce-chain hop count \u2014 that choice lives in the step-1 generator, so this entry is flagged audit_needs_deployment_generator.",
        "manifestSteps": [
            "sample"
        ],
        "status": "audit_needs_deployment_generator",
        "fixtureEquivalentCslcParamsString": "width:4,height:1,chunk_size:1024"
    },
    {
        "pattern": "fused_gemv_dequant",
        "emitter": "emitFusedGemvLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:448)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "q_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 4096,
                    "in_dim_per_pe": 6,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:4096,in_dim_per_pe:6,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=1536 N=4096 (decode row-vector)"
            },
            {
                "stepName": "k_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 4096,
                    "in_dim_per_pe": 6,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:4096,in_dim_per_pe:6,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=1536 N=4096 (decode row-vector)"
            },
            {
                "stepName": "v_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 4096,
                    "in_dim_per_pe": 6,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:4096,in_dim_per_pe:6,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=1536 N=4096 (decode row-vector)"
            },
            {
                "stepName": "o_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 1536,
                    "in_dim_per_pe": 16,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:1536,in_dim_per_pe:16,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=4096 N=1536 (decode row-vector)"
            },
            {
                "stepName": "gate_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 6144,
                    "in_dim_per_pe": 6,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:6144,in_dim_per_pe:6,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=1536 N=6144 (decode row-vector)"
            },
            {
                "stepName": "up_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 6144,
                    "in_dim_per_pe": 6,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:6144,in_dim_per_pe:6,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=1536 N=6144 (decode row-vector)"
            },
            {
                "stepName": "down_proj",
                "paramsShape": {
                    "width": 256,
                    "out_dim": 1536,
                    "in_dim_per_pe": 24,
                    "num_blocks_per_row": 1
                },
                "cslcParamsString": "width:256,out_dim:1536,in_dim_per_pe:24,num_blocks_per_row:1",
                "weightMatrixShape": "M=1 K=6144 N=1536 (decode row-vector)"
            }
        ],
        "derivationSource": "width = --size smoke arg (deployment picks per-weight-matrix width from memory-plan budgets; the audit flags this pattern as needs2DFor31B=likely pending step-1 generator output). out_dim per step from manifest.modelConfig: hiddenDim, qkv_out_dim = numHeads*headDim, or intermediate = hiddenDim*ffnExpansionFactor. in_dim_per_pe = in_dim // width. num_blocks_per_row = in_dim_per_pe // 32 (Q4K GGML block).",
        "manifestSteps": [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj"
        ],
        "status": "audit_needs_deployment_generator",
        "fixtureEquivalentCslcParamsString": "width:4,height:1,out_dim:64,in_dim_per_pe:512,num_blocks_per_row:2"
    },
    {
        "pattern": "attention_streaming",
        "emitter": "emitStreamingAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:357)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "kv_len": 4096
                },
                "cslcParamsString": "width:256,head_dim:512,kv_len:4096"
            }
        ],
        "derivationSource": "width = num_tokens from --size; head_dim from manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen. Pattern is dormant in Gemma-4 \u2014 no manifest step has op=attention_streaming.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "attention_linear",
        "emitter": "emitLinearAttentionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:489)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "kv_len": 4096
                },
                "cslcParamsString": "width:256,head_dim:512,kv_len:4096"
            }
        ],
        "derivationSource": "width = num_tokens from --size; head_dim from manifest.modelConfig.headDim; kv_len = manifest.modelConfig.maxSeqLen. Pattern is dormant in Gemma-4 \u2014 no manifest step has op=attention_linear.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step",
        "fixtureEquivalentCslcParamsString": "width:4,height:1"
    },
    {
        "pattern": "kv_write",
        "emitter": "emitKvWriteLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:512)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "kv_write",
                "variant": "standard",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "max_seq_len": 4096
                },
                "cslcParamsString": "width:256,head_dim:512,max_seq_len:4096"
            },
            {
                "stepName": "kv_write_shared",
                "variant": "shared",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "max_seq_len": 4096
                },
                "cslcParamsString": "width:256,head_dim:512,max_seq_len:4096"
            }
        ],
        "derivationSource": "width = num_tokens from --size (1-D per-head). head_dim from manifest.modelConfig.headDim; max_seq_len is the KV-cache capacity bound from manifest.modelConfig.maxSeqLen. Shared variant uses the same --params shape; the shared/standard split is surfaced via the invocation's `variant` field for downstream routing.",
        "manifestSteps": [
            "kv_write",
            "kv_write_shared"
        ],
        "fixtureEquivalentCslcParamsString": "width:4,height:1,head_dim:32,max_seq_len:64"
    },
    {
        "pattern": "kv_read",
        "emitter": "emitKvReadLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:535)",
        "emitterWidened2D": False,
        "invocations": [
            {
                "stepName": "(dormant)",
                "paramsShape": {
                    "width": 256,
                    "head_dim": 512,
                    "read_len": 256
                },
                "cslcParamsString": "width:256,head_dim:512,read_len:256"
            }
        ],
        "derivationSource": "width = num_tokens from --size; head_dim from manifest.modelConfig.headDim; read_len defaults to num_tokens for the smoke case \u2014 the dormant pattern has no manifest step driving its shape. If a future graph adds an explicit kv_read step, derivation should key on that step's payload.",
        "manifestSteps": [],
        "status": "dormant_pattern_no_manifest_step"
    },
    {
        "pattern": "reduction",
        "emitter": "emitReductionLayout (runtime/zig/src/doe_wgsl/emit_csl_layout.zig:112)",
        "emitterWidened2D": False,
        "paramsShape": {
            "width": 256,
            "hidden_size": 1536
        },
        "cslcParamsString": "width:256",
        "derivationSource": "width = num_tokens from --size (reduction emitter declares only `param width` at layout level; pe_id/num_pes/reduce_color are set per-tile by the layout not via --params). Single-PE mode per emit_csl_reduction.zig: each PE processes one full token \u2014 width <= max_seq_len <= i16, so 1-D stays fine. hidden_size is a PE-program param carried here for the predicted-footprint per-PE element derivation only.",
        "manifestSteps": [
            "ple_norm",
            "input_norm",
            "post_attn_norm",
            "ple_norm",
            "input_norm",
            "post_attn_norm"
        ],
        "fixtureEquivalentCslcParamsString": "width:4,height:1"
    }
],
        },
        "notes": (
            "GENERATED from bench/tools/generate_e2b_layer_block_runner.py. "
            "First SdkLayout runner emitted from the E2B stream-execution-plan. "
            "Stage 1 = pre-attn RMSNorm (ple_rows, ple_projection); stage 2 "
            "= single-head attention: Q = rmsnorm[0]; K[j] = wts[qs+j], "
            "V[j] = wts[qs+kv_len+j] with kv_len = qs/2; logits = Q*K; "
            "max-centered poly_c1 softmax; attn_val = sum sm[j]*V[j]; "
            "attn_out[i] = attn_val + ple_rows[i]; stage 3 = post-attn "
            "RMSNorm with gamma2 = wts[0..qs) broadcast 4x; stage 4 = "
            "gated MLP with gate = wts[2qs..3qs)·post_norm[0..qs), "
            "up = wts[3qs..4qs)·post_norm[qs..2qs), and activation_out = "
            "gate * poly_c1(up * post_norm) + post_norm. poly_c1 is the "
            "shared C^1 polynomial (0 for x<=-1, x for x>=1, 0.25*(x+1)^2 "
            "otherwise) used by both the stage-2 softmax weighting and "
            "the stage-4 activation — no transcendentals, bit-exact "
            "reproducible in both CSL and numpy. layer_weights reshape: "
            "[gamma2, attn_scale=(K,V), gate_w, up_w] (four back-to-back "
            "quarters of size/4). Remaining stages (multi-head with "
            "multiple heads, longer KV, rope) land in follow-up ticks."
        ),
    }

    trace_path = resolve(args.trace_out)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    print(
        "e2b layer-block smoke (L00): "
        f"compile={compile_elapsed_ms:.1f}ms, run={run_elapsed_ms:.1f}ms, "
        f"run_status={run_status!r}, passed={passed}, "
        f"max_abs_err={max_abs_err:.3e} -> {trace_path}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
