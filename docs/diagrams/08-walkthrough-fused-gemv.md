# 08 - Kernel walkthrough: `fused_gemv`

## Purpose

Show that the same body-preserving surface handles a multi-axis reduction, not
only elementwise or scalar-looking kernels.

## Slide content

- Doppler WGSL: matrix/vector read and accumulated output.
- TSIR: `row` axis, `col` axis, reduction over `col`, body op
  `fused_gemv`.
- Doe CSL: local multiply-accumulate plus fabric reduction.
- Cerebras mapping: rows and columns become PE-grid coordinates.

## Visual spec

- Four panes: WGSL (`doppler.red`), TSIR (`doe.blue`), CSL (`doe.blue`),
  PE grid (`cerebras.orange`).
- Draw `row` horizontally and `col` vertically; draw reduction arrows in
  `cerebras.orange`.

## Scope guard

- Do not present this as the SUMMA/tiled matmul scaling story.
- Do not claim the shown PE assignment is optimal.
- Do not compare GPU and Cerebras performance.

## Evidence sources

- `runtime/zig/tests/tsir/real/fused_gemv/`
- `runtime/zig/src/doe_wgsl/emit_csl_fused.zig`
- `docs/cerebras-north-star.md`
