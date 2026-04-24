# Preliminary real-kernel attention_head256_f16kv fixture (Gemma 3 1B Q4K)

**Status: PRELIMINARY (D2 sketch, held pre-B merge).**

Per the workstream plan, workstream D runs in parallel with workstream B
(WGSL→SPIR-V emitter fixes: B1 `.if_` termination propagation, B2
scalar/vector coercion in `coerce_binary_operand`). Final attention TSIR
digests cannot be computed until B merges — otherwise the emitter/coercion
fixes would silently invalidate any digests computed against the pre-B
emitter. This fixture lands the pre-B structural shape (pinned WGSL
snapshot, schema-valid placeholder JSON, explicit schema gaps in
`rejections[]`) so the planner and emitter work under D3 has a concrete
regeneration target post-B.

## Target kernel

Doppler's `src/gpu/kernels/attention_head256_f16kv.wgsl`, entry `main`,
workgroup size 32, `HEAD_DIM=256`, `HEAD_DIM_VECS=64`, `BLOCK_SIZE=32`,
`enable f16`. Bound in Gemma 3 1B Q4K as kernel-path key `attn_head256`
with digest
`sha256:4ecdc079e322a770350414244cb383d72ae7ffa47ed620c64ff425c93413e97a`
and `precision.kvDtype="f16"`
(`doppler/src/inference/config/conversion/gemma3/gemma-3-1b-it-q4k-ehf16-af32.json`).

## Schema gaps captured here

The preliminary semantic and realization JSONs are schema-valid (they
validate against `doe/config/doe-tsir-semantic.schema.json` and
`doe/config/doe-tsir-realization.schema.json`) but deliberately hold
placeholder values where the schema cannot yet express the real shape.
The gaps are:

1. **No attention body op.** The `bodyOp` enum in
   `doe-tsir-semantic.schema.json` today is `["unknown", "fused_gemv",
   "rms_norm", "gather"]`. The preliminary fixture pins `body.op="unknown"`.
   D3 must add `attention_scores` (or a finer-grained variant set) plus
   the corresponding `bindingRole` entries for Q/K/V/output and the axis
   roles for query-position, key-position, head-index, and head-dim.
2. **No softmax reduction representation.** The `reductions[]` array today
   supports single-axis `sum`/`max`/`min`/etc. Attention softmax is
   two-pass (max for stabilization, then exp/sum), with the exp and sum
   happening on the same sequence axis after a running max. D3 must
   extend the reduction contract to cover this compound reduction or
   decompose it into two sequential reduction entries in the schema.
3. **No sequence-axis collective for softmax.** The `collectiveKind`
   enum covers workgroup/fabric broadcasts and all-reduces but does not
   express the attention-specific pattern of "compute max over BLOCK_SIZE
   keys, broadcast, compute exp/sum over BLOCK_SIZE keys, broadcast".
   D3 must either add an attention-specific collective or decompose
   this into existing primitives.
4. **Binding roles for kv_len_buffer and page_table.** Bindings 5 and 6
   (dynamic KV length plus paged KV lookup table) are control-plane
   inputs, not tensor participants. The `bindingRole` enum today is
   `["matrix", "vector", "input", "scale", "indices", "table",
   "output"]`. D3 must either reuse `indices`/`table` for these (with a
   documented semantic) or add a control-plane role.
5. **kv_layout polymorphism.** The same kernel serves three KV layouts
   (dense, sliding-window, paged) selected by `u.kv_layout`. The
   realization residency for K and V differs by layout (chunk sizing,
   fabric-color scheduling). D3 must decide whether this is one semantic
   with three realizations, or a semantic-level specialization.

The `rejections[]` entries in the semantic and realization JSONs record
these gaps using the existing rejection taxonomy so the
`doe_tsir_convert_lowering.py` orchestrator can report them without
inventing a new vocabulary.

## What this fixture does NOT land

- **Frontend recovery.** Even when the semantic schema is extended, the
  frontend code that lifts this WGSL into TSIR semantic IR is
  `frontend.zig` extension work outside the fixture.
- **Planner realization.** The wse3 realization is placeholder-shaped
  (`peGrid width=1`, `shards=1`). The real realization will plan Q
  pe_replicated per head, K and V fabric_streamed on separate colors
  with kv_layout-aware chunk sizing, output pe_sliced on the query
  axis, and workgroup-scoped softmax reductions mapped to fabric
  collectives.
- **CSL emitter body.** Attention body emission is a new body family
  for `emit_kernel_body.zig`; the bootstrap path (gather, fused_gemv,
  rms_norm) does not cover it.
- **Parity receipt.** Scheduled for D3 post-B merge plus simfabric
  execution plus Doppler-side per-kernel probe capture.
- **Registration in `REAL_KERNEL_FIXTURES`.** Per the baseline pin,
  this fixture is not registered in
  `bench/tools/doe_tsir_convert_lowering.py REAL_KERNEL_FIXTURES` until
  the schema extensions land and digests are regenerated.

## What this fixture DOES land

- A pinned WGSL snapshot of the production source, with a fixture
  header that calls out the preliminary status.
- Schema-valid preliminary semantic and realization JSONs so the D2
  output is not a directory of stubs that breaks schema-aware tooling.
- Explicit rejection-taxonomy entries in `rejections[]` that make the
  schema gaps machine-readable.
- This notes file, documenting exactly what D3 must change post-B.

## Regeneration checklist (D3 post-B)

1. Extend `doe-tsir-semantic.schema.json` with the attention body op,
   the missing binding/axis roles, and the softmax reduction/collective
   extensions. Bump `contractVersion` if the change is breaking.
2. Fill `body.op`, `bindingRoles[]`, `axisRoles[]`, and `reductions[]`
   in `attention_head256_f16kv.tsir-semantic.json` with the real
   mapping. Clear the corresponding `rejections[]` entries.
3. Fill real `tiles.perAxis`, `peGrid`, `residency[]`, `collectives[]`,
   and `reductions[]` in the wse3 realization. Clear the `rejections[]`
   entry.
4. Run the `doe-tsir-bootstrap-oracle` (or the attention equivalent
   added in D3) to compute `sourceDigest`, `targetDescriptorHash`, and
   `emitterDigest` against the post-B emitter. Replace all
   placeholder zero/one digests.
5. Register `attention_head256_f16kv` in `REAL_KERNEL_FIXTURES` in
   `bench/tools/doe_tsir_convert_lowering.py`.
6. Generate the parity receipt under
   `doe_parity.py --kernel attention_head256_f16kv --doppler-transcript <t> --doppler-kernel-probe-hash <h>`.

## Pair with attention_head512_f16kv

This fixture's companion, `attention_head512_f16kv`, is authored with
the same preliminary shape and the same schema gaps. Gemma 3 1B uses
`head256` only; `head512` exists in the Doppler kernel registry for
larger-head variants and is covered here for completeness so workstream
B's emitter fixes can be exercised against both fixed-shape prefill
geometries.
