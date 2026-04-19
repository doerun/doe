"""Single source of truth for the E2B layer-block numpy reference.

compute_layer_block(rows, proj, wts, size) is the bit-exact numpy
mirror of the CSL kernel at
bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl

All operations mirror the CSL kernel's in-order scalar f32
accumulations so np.array_equal serves as the bit-exact pass gate
between the CSL device output and the numpy reference. The rope
table and poly_c1 helpers are 9-decimal-digit literals that round-
trip to identical f32 bit patterns in CSL and numpy under IEEE-754.

Both consumers — the generated SDK runner at
bench/runners/csl-runners/e2b_layer_block_smoke.py and the numpy-
only synthetic-trace tool at
bench/tools/emit_e2b_layer_block_synthetic_trace.py — import this
module so there is one canonical compute path. Any change here is
the bit-exact divergence point that the parity-contract gate
depends on; treat edits as kernel-shape changes that require
regenerating both the runner and the synthetic trace.
"""

from __future__ import annotations

import numpy as np


# --- rope table indexed by (position, pair_index). head_dim=8, base=10000 ---
# theta_d = 10000^(-2d/head_dim) for d in [0, 4):
#   theta_0 = 1.0   theta_1 = 0.1   theta_2 = 0.01   theta_3 = 0.001
# Positions 0..3 are KV entries; position 4 is Q (= kv_len_per_head).
def rope_cos_at(p, d):
    if d == 0:
        if p == 0: return np.float32(1.0)
        if p == 1: return np.float32(0.540302277)
        if p == 2: return np.float32(-0.416146845)
        if p == 3: return np.float32(-0.989992499)
        return np.float32(-0.653643608)
    if d == 1:
        if p == 0: return np.float32(1.0)
        if p == 1: return np.float32(0.995004177)
        if p == 2: return np.float32(0.980066597)
        if p == 3: return np.float32(0.955336511)
        return np.float32(0.921060979)
    if d == 2:
        if p == 0: return np.float32(1.0)
        if p == 1: return np.float32(0.999949992)
        if p == 2: return np.float32(0.999800026)
        if p == 3: return np.float32(0.999550045)
        return np.float32(0.999200106)
    # d == 3
    if p == 0: return np.float32(1.0)
    if p == 1: return np.float32(0.999999523)
    if p == 2: return np.float32(0.999997973)
    if p == 3: return np.float32(0.999995530)
    return np.float32(0.999992013)


def rope_sin_at(p, d):
    if d == 0:
        if p == 0: return np.float32(0.0)
        if p == 1: return np.float32(0.841470957)
        if p == 2: return np.float32(0.909297407)
        if p == 3: return np.float32(0.141120002)
        return np.float32(-0.756802499)
    if d == 1:
        if p == 0: return np.float32(0.0)
        if p == 1: return np.float32(0.0998334140)
        if p == 2: return np.float32(0.198669329)
        if p == 3: return np.float32(0.295520216)
        return np.float32(0.389418334)
    if d == 2:
        if p == 0: return np.float32(0.0)
        if p == 1: return np.float32(0.00999983307)
        if p == 2: return np.float32(0.0199986659)
        if p == 3: return np.float32(0.029995501)
        return np.float32(0.0399893336)
    # d == 3
    if p == 0: return np.float32(0.0)
    if p == 1: return np.float32(0.000999999815)
    if p == 2: return np.float32(0.00199999870)
    if p == 3: return np.float32(0.00299999560)
    return np.float32(0.00399998948)


# --- piecewise-polynomial GELU approximation, C^1-continuous at +/- 1 ---
def act_poly_c1(x):
    x = np.float32(x)
    if x >= np.float32(1.0):
        return x
    if x <= np.float32(-1.0):
        return np.float32(0.0)
    xp1 = np.float32(x + np.float32(1.0))
    sq = np.float32(xp1 * xp1)
    return np.float32(np.float32(0.25) * sq)


def compute_layer_block(rows, proj, wts, size):
    """One layer-block of compute. Bit-exact mirror of the CSL kernel.

    All four input slots are size-element f32 arrays. layer_weights is
    reshaped four back-to-back quarters [gamma2, per_head_KV, gate_w,
    up_w] (qs = size/4). Returns the size-element activation_out.
    """
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

    # Stage 2: 8-head MHA, head_dim=8, kv_len=4, multi-pair rope.
    num_heads = 8
    head_dim = 8
    kv_len_per_head = 4
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

    attn_vals = np.zeros(attn_flat_len, dtype=np.float32)
    for h in range(num_heads):
        base_h = qs + h * per_head_stride
        q_base = h * head_dim

        # Rope-rotate Q_h once per head at position kv_len_per_head.
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

    # Stage 3: post-attn RMSNorm with gamma2 = wts[0..qs) broadcast 4x.
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

    # Stage 4: gated MLP. gate_w/up_w each qs/2 elems.
    mlp_len = qs // 2
    gate_base = 3 * qs
    up_base = gate_base + mlp_len
    gate = np.float32(0.0)
    for k in range(mlp_len):
        gate = np.float32(
            gate + np.float32(wts[gate_base + k]) * np.float32(post_norm[k])
        )
    up = np.float32(0.0)
    for k in range(mlp_len):
        up = np.float32(
            up + np.float32(wts[up_base + k])
            * np.float32(post_norm[mlp_len + k])
        )
    expected = np.empty(size, dtype=np.float32)
    for i in range(size):
        pre_act = np.float32(up * np.float32(post_norm[i]))
        act = act_poly_c1(pre_act)
        expected[i] = np.float32(
            np.float32(gate * act) + np.float32(post_norm[i])
        )
    return expected
