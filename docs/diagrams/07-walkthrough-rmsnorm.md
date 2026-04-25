# 07 - Kernel walkthrough: `rms_norm`

## Purpose

Use the simplest kernel to show the body-preserving pattern end to end.

## Slide content

- Doppler WGSL computes mean square over hidden dimension.
- TSIR names the hidden axis, `input`, `weight`, `output`, reduction, and
  `rms_norm` body op.
- Doe emits CSL with sum-of-squares, sqrt, Gemma `(1 + w)` scale, and local
  output writes.
- Cerebras mapping: hidden chunks live on PEs; reduction crosses the PE grid.

## Visual spec

- Four panes: WGSL (`doppler.red`), TSIR (`doe.blue`), CSL (`doe.blue`),
  PE grid (`cerebras.orange`).
- Use one highlighted path across all panes: `d in [0, hidden_size)`.

## Scope guard

- Do not claim performance.
- Do not claim runtime parity from this slide alone.
- Do not imply the PE count comes from TSIR; HostPlan/layout chooses it.

## Evidence sources

- `runtime/zig/tests/tsir/real/rmsnorm/`
- `runtime/zig/src/tsir/emit_kernel_body.zig`
- `runtime/zig/src/tsir/reference_interpreter.zig`
