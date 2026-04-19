#!/usr/bin/env python3
"""Golden-value unit test for the canonical compute_layer_block.

Locks in the bit-exact behavior of
bench/runners/csl-runners/_e2b_layer_block_compute.py against three
known-good input fixtures at size=1024 (the smallest valid size for
the hardcoded num_heads=8 * head_dim=8 * kv_len=4 layout):

  zeros:    rows = proj = wts = all zeros
            -> output exactly zero everywhere

  ones:     rows = proj = wts = all ones
            -> uniform input + uniform weights produces uniform
               output; entire array equals one f32 value, captured
               as a hex bit pattern. NOTE: this fixture is
               INSENSITIVE to rope changes because softmax is
               summed over a constant V; included as a structural
               sanity, not a rope-drift catch.

  varying:  rows = proj = ones, wts = arange(SIZE)/SIZE
            -> non-uniform wts makes V vary with absolute index, so
               softmax weights matter, so rope rotation matters,
               so any rope-table change moves the output bits.
               This fixture is the actual rope-drift catcher.

Goldens are stored as f32 hex bit patterns at sentinel indices.
Any change to compute_layer_block (intentional or accidental)
trips this test. When an intentional change to compute_layer_block
lands, recompute the goldens via the standalone PRINT_GOLDENS=1
runner mode.

Runnable two ways:
    python3 -m pytest bench/tools/test_e2b_layer_block_compute.py
    python3 bench/tools/test_e2b_layer_block_compute.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "runners" / "csl-runners"))
from _e2b_layer_block_compute import compute_layer_block  # noqa: E402

SIZE = 1024
SENTINELS = (0, 1, 7, 63, 64, 127, 128, 256, 511, 512, 768, SIZE - 1)

# All-ones golden: uniform input -> uniform output.
ONES_GOLDEN_HEX = 0x468001FE  # +16384.9960938 f32

# Varying-wts goldens at SENTINEL indices. wts[i] = i/SIZE makes V
# non-uniform across (j, d), so softmax matters, so rope matters,
# so each entry in the rope table affects these output bits.
VARYING_GOLDEN_HEX = {
    0:    0x3FD8AB9D,  # +1.6927372
    1:    0x3FE10931,  # +1.7580930
    7:    0x400B6253,  # +2.1778762
    63:   0x412E02C3,  # +10.8756742
    64:   0x4103A9E2,  # +8.2289753
    127:  0x41AF644D,  # +21.9239750
    128:  0x4183A9E2,  # +16.4579506
    256:  0x3FD8AB9D,  # +1.6927372 (matches index 0 — multi_layer_chain
                      # broadcast pattern from the attn_flat_len=64
                      # repeat over size=1024)
    511:  0x42301514,  # +44.0205841
    512:  0x3FD8AB9D,
    768:  0x3FD8AB9D,
    1023: 0x42301514,
}


def _hex(x: np.float32) -> int:
    return int(np.float32(x).view("uint32"))


def fixture_zeros() -> np.ndarray:
    z = np.zeros(SIZE, dtype=np.float32)
    return compute_layer_block(z, z, z, SIZE)


def fixture_ones() -> np.ndarray:
    o = np.ones(SIZE, dtype=np.float32)
    return compute_layer_block(o, o, o, SIZE)


def fixture_varying() -> np.ndarray:
    o = np.ones(SIZE, dtype=np.float32)
    wts = np.arange(SIZE, dtype=np.float32) / np.float32(SIZE)
    return compute_layer_block(o, o, wts, SIZE)


def test_zeros_input_yields_zeros_output() -> None:
    out = fixture_zeros()
    assert out.dtype == np.float32
    assert np.array_equal(out, np.zeros(SIZE, dtype=np.float32)), (
        "all-zeros input should produce all-zeros output; got "
        f"max_abs={float(np.max(np.abs(out)))}"
    )


def test_ones_input_yields_uniform_golden() -> None:
    out = fixture_ones()
    assert out.dtype == np.float32
    actual = out.view(np.uint32)
    diff = np.where(actual != ONES_GOLDEN_HEX)[0]
    if diff.size > 0:
        first = int(diff[0])
        raise AssertionError(
            f"all-ones output should equal hex 0x{ONES_GOLDEN_HEX:08x} "
            f"at every index; first divergent index = {first}, "
            f"got hex 0x{int(actual[first]):08x}"
        )


def test_varying_wts_input_matches_rope_sensitive_goldens() -> None:
    out = fixture_varying()
    assert out.dtype == np.float32
    bad = []
    for i, expected_hex in VARYING_GOLDEN_HEX.items():
        actual_hex = _hex(out[i])
        if actual_hex != expected_hex:
            bad.append(
                f"i={i}: expected 0x{expected_hex:08x}, "
                f"got 0x{actual_hex:08x} (val {float(out[i])})"
            )
    if bad:
        raise AssertionError(
            "varying-wts fixture diverged from rope-sensitive goldens; "
            "if compute_layer_block changed intentionally, regenerate "
            "the VARYING_GOLDEN_HEX table via "
            "`PRINT_GOLDENS=1 python3 bench/tools/test_e2b_layer_block_compute.py`. "
            "Divergences:\n  " + "\n  ".join(bad)
        )


def main() -> int:
    """Standalone runner. Set PRINT_GOLDENS=1 to dump live values."""
    if os.environ.get("PRINT_GOLDENS") == "1":
        out_z = fixture_zeros()
        out_o = fixture_ones()
        out_v = fixture_varying()
        print(
            f"# zeros: all-zero? "
            f"{np.array_equal(out_z, np.zeros(SIZE, dtype=np.float32))}"
        )
        print(
            f"ONES_GOLDEN_HEX = 0x{_hex(out_o[0]):08x}  "
            f"# {float(out_o[0]):+.7f}"
        )
        print("VARYING_GOLDEN_HEX = {")
        for i in SENTINELS:
            print(
                f"    {i:5}: 0x{_hex(out_v[i]):08x},  "
                f"# {float(out_v[i]):+.7f}"
            )
        print("}")
        return 0

    failures: list[str] = []
    for name, fn in [
        ("zeros_input_yields_zeros_output",
         test_zeros_input_yields_zeros_output),
        ("ones_input_yields_uniform_golden",
         test_ones_input_yields_uniform_golden),
        ("varying_wts_input_matches_rope_sensitive_goldens",
         test_varying_wts_input_matches_rope_sensitive_goldens),
    ]:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            print(f"  FAIL  {name}")
            for line in str(e).splitlines():
                print(f"        {line}")
            failures.append(name)

    if failures:
        print(f"\n{len(failures)} failure(s): {failures}")
        return 1
    print(f"\nALL PASS — compute_layer_block bit-exactness locked at size={SIZE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
