# 14 - ONNX-shaped comparison: "Opaque ops multiply backend work"

## Purpose

Make the strategic contrast without attacking ONNX. The issue is not whether
operator graphs are useful; it is whether opaque op bodies carry enough shape
for Cerebras placement.

## Slide content

- Left: opaque operator graph -> backend-specific kernels per op.
- Right: raw WGSL/Doe semantic lowering -> backend emitters with exposed axes,
  bindings, reductions, and HostPlan identity.
- Caption: **The cost is structural: opaque bodies force per-op backend work;
  exposed bodies can be retargeted.**

## Visual spec

- Two columns.
- ONNX/opaque side uses `contrast.gray`.
- Doppler source snippets use `doppler.red`.
- Doe lowering uses `doe.blue`.
- Cerebras target uses `cerebras.orange`.

## Scope guard

- Do not claim ONNX is obsolete or unmaintained.
- Do not claim Doe is the only body-preserving approach.
- Do not show fake quantitative multipliers without evidence.

## Evidence sources

- `runtime/zig/src/tsir/`
- `runtime/zig/src/doe_wgsl/`
- `docs/csl-architecture.md`
