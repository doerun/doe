# 02 - Problem: "Cerebras needs the body, not just the op name"

## Purpose

Explain the structural reason this deck exists. Spatial compute needs exposed
axes, bindings, and reductions before it can place work on a PE grid.

## Slide content

- Left: opaque operator graph. It preserves signatures such as `MatMul(x, w)`
  but hides the loop body and memory roles.
- Right: body-preserving lowering. It exposes axes, bindings, reductions, body
  op, and launch identity.
- Caption: **Operator graphs preserve signatures. Doe's Cerebras slice must
  preserve bodies and identities.**

## Visual spec

- Two equal columns.
- Opaque operator graph uses `contrast.gray`.
- Doppler source snippets use `doppler.red`; Doe lowering boxes use
  `doe.blue`; Cerebras PE-grid target uses `cerebras.orange`.
- Right column has a four-slot TSIR/semantic box: `axes`, `bindings`,
  `reduction`, `body op`, followed by HostPlan identity badges.

## Scope guard

- Do not say ONNX is bad. It is useful on its target hardware.
- Do not say TSIR is unique. The claim is narrower: exposed-body IR is the
  shape Doe's Cerebras lowering needs.
- Do not use measured multipliers unless the evidence ledger cites them.

## Evidence sources

- `runtime/zig/src/tsir/schema.zig`
- `runtime/zig/src/tsir/emit_kernel_body.zig`
- `docs/csl-architecture.md`
