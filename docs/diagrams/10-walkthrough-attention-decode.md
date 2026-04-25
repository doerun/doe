# 10 - Kernel walkthrough: `attention_decode`

## Purpose

Show the highest-value decode example: multiple axes, cache reads, masking, and
reduction all need explicit placement.

## Slide content

- Doppler source: one decode step reads query, key cache, and value cache.
- TSIR shape: head axis, kv-position axis, head-dim axis, softmax/reduction
  structure.
- Doe CSL: PE-grid attention with cache reads and fabric reductions.
- Cerebras mapping: heads, kv chunks, and local head-dim slices map to grid
  structure.

## Visual spec

- Four panes: WGSL/source (`doppler.red`), TSIR (`doe.blue`), CSL
  (`doe.blue`), PE-grid attention map (`cerebras.orange`).
- Show sliding-window/global-window as a small toggle, not a second diagram.

## Scope guard

- Do not claim optimal attention layout.
- Do not claim full-depth simfabric is the target; hardware is the proof
  target for model-scale execution.
- If the receipt is not present in the send bundle, mark this as expected
  evidence rather than in-hand evidence.

## Evidence sources

- `runtime/zig/src/doe_wgsl/emit_csl_attention.zig`
- `runtime/zig/tests/tsir/real/attention_head256_f16kv/`
- `docs/cerebras-north-star.md`
