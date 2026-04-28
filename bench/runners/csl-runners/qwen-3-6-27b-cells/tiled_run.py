#!/usr/bin/env cs_python
"""Qwen 3.6 27B tiled (SUMMA matmul) kernel — simfabric end-to-end run.

Compiles small-shape (P=2, Mt=4, Kt=4, Nt=4) version of the
manifest-shape Qwen tiled CSL, runs it under simfabric, and verifies
C = A @ B against numpy.

Manifest scale: Qwen attention/FFN matmuls (e.g. q_proj / k_proj /
v_proj / o_proj / gate_proj / up_proj / down_proj) ride this kernel
on a P × P PE grid via SUMMA-style row+column broadcasts. This
canary uses P=2 (smallest grid that exercises the broadcast chain)
and Mt=Kt=Nt=4 (smallest tile that fills a single fmac column).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from cerebras.sdk.runtime.sdkruntimepybind import (
    SdkRuntime,
    MemcpyDataType,
    MemcpyOrder,
)

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="compiled")
parser.add_argument("--cmaddr", default=None)
parser.add_argument("--out-receipt", default="receipt.json")
args = parser.parse_args()

P = 2
Mt = 4
Kt = 4
Nt = 4
M_total = P * Mt
K_total = P * Kt
N_total = P * Nt

rng = np.random.default_rng(seed=27)
A_full = rng.standard_normal(size=(M_total, K_total)).astype(np.float32)
B_full = rng.standard_normal(size=(K_total, N_total)).astype(np.float32)
C_ref = (A_full @ B_full).astype(np.float32)

# Distribute matrices the same way the existing tiled_matmul_sim_runner
# does: A_per_pe is K-major (Kt, Mt) per PE; B_per_pe is N-major
# (Nt, Kt) per PE. The kernel reads A via `|i|{Mt} -> A_tile[i]`
# (M-stride, advanced by Mt per k) and B via `b_val = Bp[j*Kt + k]`
# (N-major). PE-grid axes: pe_y indexes M-block of A and K-block of B;
# pe_x indexes K-block of A and N-block of B.
A_per_pe = (
    A_full.reshape(P, Mt, P, Kt).transpose(0, 2, 3, 1).reshape(P, P, Mt * Kt)
)
B_per_pe = (
    B_full.reshape(P, Kt, P, Nt).transpose(0, 2, 3, 1).reshape(P, P, Kt * Nt)
)

runner = SdkRuntime(args.name, cmaddr=args.cmaddr) if args.cmaddr else SdkRuntime(args.name)
a_sym = runner.get_id("a")
b_sym = runner.get_id("b")
c_sym = runner.get_id("c")

runner.load()
runner.run()

runner.memcpy_h2d(a_sym, A_per_pe.ravel(), 0, 0, P, P, Mt * Kt,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.memcpy_h2d(b_sym, B_per_pe.ravel(), 0, 0, P, P, Nt * Kt,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.launch("compute", nonblock=False)

c_flat = np.zeros(P * P * Mt * Nt, dtype=np.float32)
runner.memcpy_d2h(c_flat, c_sym, 0, 0, P, P, Mt * Nt,
    streaming=False, order=MemcpyOrder.ROW_MAJOR,
    data_type=MemcpyDataType.MEMCPY_32BIT, nonblock=False)
runner.stop()

# C output: PE (pe_x=px, pe_y=py) accumulated C[py*Mt:(py+1)*Mt,
# px*Nt:(px+1)*Nt] in N-major (Nt, Mt) layout per the fmac chain.
# Reshape exactly as the existing tiled_matmul_sim_runner does.
c_tiles = c_flat.reshape(P, P, Nt, Mt).transpose(0, 3, 1, 2)
C_actual = c_tiles.reshape(M_total, N_total)

max_abs = float(np.max(np.abs(C_actual - C_ref)))
max_rel = float(np.max(np.abs(C_actual - C_ref) / (np.abs(C_ref) + 1e-9)))
ok = bool(np.allclose(C_actual, C_ref, rtol=1e-3, atol=1e-3))
print(f"shape: P={P} Mt={Mt} Kt={Kt} Nt={Nt} (M={M_total}, K={K_total}, N={N_total})")
print(f"DBG C_actual[0, :4] = {C_actual[0, :4]}")
print(f"DBG C_ref   [0, :4] = {C_ref[0, :4]}")
print(f"max_abs_diff={max_abs:.6e} max_rel_diff={max_rel:.6e} parity={'OK' if ok else 'FAIL'}")

receipt = {
    "schemaVersion": 1,
    "artifactKind": "doe_qwen_3_6_27b_tiled_simfabric_cell",
    "kernel": "tiled",
    "modelId": "qwen-3-6-27b-q4k-ehaf16",
    "executionTarget": "simfabric",
    "verdict": "pass" if ok else "fail",
    "shape": {"P": P, "Mt": Mt, "Kt": Kt, "Nt": Nt,
              "M_total": M_total, "K_total": K_total, "N_total": N_total},
    "parityMaxAbsDiff": max_abs,
    "parityMaxRelDiff": max_rel,
    "rngSeed": 27,
    "claim": {
        "scope": (
            "Qwen 3.6 27B tiled (SUMMA matmul) kernel CSL (sourced "
            "from the manifest-shape host plan) compiles via cslc "
            f"2.10.0 at P={P}, Mt={Mt}, Kt={Kt}, Nt={Nt} "
            f"(M={M_total}, K={K_total}, N={N_total}) and runs "
            "end-to-end on simfabric. C = A @ B.T matches numpy "
            "within float32 precision. Validates the SUMMA row+"
            "column broadcast chain (collectives_2d) end-to-end."
        ),
        "notWhat": (
            "Not a hardware run. Not a manifest-shape run — Qwen "
            "manifest matmuls run on much larger P (typically a "
            "16×16 or larger SUMMA tile) and Mt/Kt/Nt that consume "
            "real per-PE budget. The smallest P=2 canary verifies "
            "the broadcast chain mechanism, not production tile "
            "geometry."
        ),
    },
}
Path(args.out_receipt).write_text(json.dumps(receipt, indent=2) + "\n")
print(f"wrote {args.out_receipt}")
sys.exit(0 if ok else 1)
