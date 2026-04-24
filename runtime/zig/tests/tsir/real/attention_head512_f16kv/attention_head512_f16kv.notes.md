# Preliminary real-kernel attention_head512_f16kv fixture

**Status: PRELIMINARY (D2 sketch, held pre-B merge).**

Companion to `attention_head256_f16kv`. Same preliminary shape, same
schema gaps. See `tests/tsir/real/attention_head256_f16kv/attention_head256_f16kv.notes.md`
for the full list of schema gaps, regeneration checklist, and baseline-pin
rationale — they apply to this fixture identically.

## Target kernel

Doppler's `src/gpu/kernels/attention_head512_f16kv.wgsl`, entry `main`,
workgroup size 16, `HEAD_DIM=512`, `HEAD_DIM_VECS=128`, `BLOCK_SIZE=16`,
`enable f16`. Same 7-binding layout as the head256 variant (u, Q, K, V,
output, kv_len_buffer, page_table).

Gemma 3 1B Q4K does not bind this kernel — it uses `attn_head256` only.
`attention_head512_f16kv` is reserved for larger-head Gemma variants
(and other model families with HEAD_DIM=512). This fixture is authored
alongside head256 so workstream B's emitter fixes can be validated
against both fixed-shape prefill geometries the Doppler kernel registry
ships today, and so D3's attention body-op schema extension has a
second validation target at a different per-block geometry
(BLOCK_SIZE=16 vs head256's BLOCK_SIZE=32).

## What differs from head256

- `HEAD_DIM`: 512 (vs 256)
- `HEAD_DIM_VECS`: 128 (vs 64)
- `BLOCK_SIZE`: 16 (vs 32) — halved so the workgroup-scoped shared
  block still fits: head256 uses 32 × 64 × 8 bytes = 16 KiB, head512
  uses 16 × 128 × 8 bytes = 16 KiB. Same workgroup memory budget.
- `workgroupSize`: 16 (vs 32) — matches `BLOCK_SIZE`.

All other structural properties are identical at the TSIR-semantic
level. The residency plan on WSE-3 under D3 will pick different
chunk sizes for K/V fabric-streaming because the per-step block
geometry differs, but the pe_replicated Q / fabric_streamed K,V /
pe_sliced output shape is the same.

## Regeneration

Follow the checklist in
`attention_head256_f16kv.notes.md § Regeneration checklist (D3 post-B)`
but substitute the head512 filenames and register
`attention_head512_f16kv` in `REAL_KERNEL_FIXTURES` at the same time as
`attention_head256_f16kv`.
