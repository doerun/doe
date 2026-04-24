# TSIR bootstrap kernel catalog

This directory pins a deliberately small catalog of WGSL kernel snapshots and
their hand-sketched expected TSIR shapes. It is a design artifact, not
frontend test fixtures. Its purpose is to validate — before any frontend
code is written — that the TSIR schema, the parity oracle's reference
semantics, and the target descriptors can actually represent the first
three nontrivial kernel families the project intends to lower.

See [`docs/tsir-lowering-plan.md`](../../../../../docs/tsir-lowering-plan.md)
§ Step 1.5 for the rationale.

## What's here

One entry per kernel family:

- `<family>.wgsl` — pinned WGSL source snapshot. Never a live reference into
  another repo; copies are explicit so schema-gap analysis is reproducible.
- `<family>.tsir-semantic.json` — hand-sketched expected TSIR semantic
  (canonical JSON form). Validated by
  `config/doe-tsir-semantic.schema.json` as far as the current schema can
  express the kernel.
- `<family>.tsir-realization.wse3.json` / `.webgpu-generic.json` —
  hand-sketched realization sketches per target descriptor. Follow the
  same format as semantic.
- `<family>.notes.md` — schema-fit report. Lists what the current schema
  can and cannot express for this kernel. Schema gaps surfaced here drive
  future Step 3 extensions.

## Bootstrap families (per plan priority)

1. **Fused GEMV** — `y[i] = sum_k(W[i,k] * x[k])`. Exercises fused
   multiply-reduce and 2-D input with 1-D output.
2. **RMSNorm** — `rms = sqrt(mean(x²) + eps); out = x / rms * weight`.
   Exercises elementwise square, reduction-with-scalar-tail, and
   elementwise normalization.
3. **Gather** — `out[i] = table[indices[i]]`. Exercises pure index
   lookup with no arithmetic in the per-element kernel body.

## Contract

- WGSL snapshots are pinned. When Doppler upstream changes a kernel, the
  snapshot here is updated in the same commit as the corresponding TSIR
  hand-sketch so the pair stays coherent.
- TSIR JSON that cannot be expressed in the current schema is recorded in
  `<family>.notes.md` with a precise description of the missing field or
  node type. These notes drive Step 3 schema extensions.
- Once the frontend lands, these entries become regression fixtures for the
  nightly parity canary (step 8).
