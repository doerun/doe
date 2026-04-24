# Gather — TSIR schema fit report

Source: [`gather.wgsl`](gather.wgsl).
Hand-sketched TSIR: [`gather.tsir-semantic.json`](gather.tsir-semantic.json).

## What fits the current schema

- Two iteration axes (`t` for token position, `h` for hidden index).
- Three buffer bindings: `indices` (u32 1-D), `table` (f32 2-D vocab×hidden),
  `output` (f32 2-D num_tokens×hidden). All three use dtypes already
  supported by `ScalarKind` (u32 for indices, f32 for table/output).
- Empty `reductions` and `collectives` lists — gather has no arithmetic
  reduction and no cross-thread collective.

## What does NOT fit the current schema

Gather exposes a schema gap orthogonal to GEMV and RMSNorm. Those
kernels need elementwise / scalar / multi-stage op bodies. Gather needs:

1. **Indirect indexed addressing.** The core of the kernel is
   `output[t, h] = table[indices[t], h]` — one binding's value is used
   as the row index into another binding. The current `BufferBinding`
   describes a contiguous tensor with a logical shape; it has no way
   to declare "this binding's elements are indices into another
   binding's axis."
2. **No arithmetic op body.** Even with a hypothetical elementwise-op
   AST (the extension RMSNorm/GEMV imply), a pure gather has no
   reduction and no arithmetic op. The op AST would need a first-class
   `gather(source_binding, index_binding, source_axis)` node, not just
   arithmetic primitives.
3. **Index bounds policy.** The kernel guards the lookup with
   `if (row >= u.vocab) output = 0.0`. Real model code usually assumes
   valid indices, but the oracle's numerical contract has to be
   explicit about what happens on out-of-range indices (clamp, zero,
   trap, undefined). A `BoundsPolicy` field on the gather node —
   either on the source binding or the gather-op node itself.
4. **Uniform-scalar reference for bounds check.** `u.vocab` is a
   uniform scalar (same category as `eps` in RMSNorm) — used in a
   branch rather than arithmetic but structurally identical: the schema
   has no way to represent `Uniforms` struct access.

## Implied Step 3 schema extensions (specific to gather)

Beyond the op-body extensions GEMV and RMSNorm imply:

1. **`GatherNode` as a first-class operation type.** Fields: source
   binding index, axis being indexed, index binding index, optional
   bounds policy. Consumed by the elementwise-op AST (the extension
   the prior two kernels imply) as an input to later stages.
2. **Index-binding attribute.** Either a flag on `BufferBinding` or a
   convention that u32/i32 bindings can participate as index sources.
   A naming convention alone is not schema — it has to be machine-
   checkable.
3. **Bounds policy as an enum.** Options: `assume_valid`,
   `clamp_to_zero`, `trap`. Default value is part of the parity
   contract because different choices produce different output bytes
   on rogue inputs.

## Realization sketches

Sketches landed for both targets. Gather is the most consequential of
the three bootstrap realizations because it exercises a residency
class (`fabric_streamed`) that GEMV and RMSNorm do not. Schema-valid
under `doe-tsir-realization.schema.json`.

- `gather.tsir-realization.wse3.json`: 8×1 PE grid. `indices` and
  `output` row-sliced across PEs along the num-tokens axis. `table`
  declared `fabric_streamed` on color 0 with a 64 KiB chunk. This is
  the kernel that pins the Merkle-block-packaging dependency: without
  per-chunk Merkle roots on the table tensor in RDRR, the residency
  pass cannot realize `fabric_streamed` and must either reject with
  `TSIR_PE_BUDGET_EXHAUSTED` (when the table does not fit per-PE) or
  fall back to `pe_replicated` (when it does).
- `gather.tsir-realization.webgpu-generic.json`: 1×1 PE grid, all
  bindings `pe_replicated`. No fabric streaming on this target; the
  table sits in adapter memory.

Caveats that flow from the semantic gap above:

- Neither sketch represents the *indexed copy* operation itself,
  because the semantic does not. The sketches cover placement and
  residency only — what executes inside each tile remains
  unrepresentable until `GatherNode` lands on the semantic side.
- The `fabric_streamed` chunk size `65536` is a round placeholder.
  Real chunk sizing depends on the loader's range-fetch granularity
  (bounded by RDRR Merkle block size) and the fabric color budget;
  Step 5 residency planning will choose it, not the sketch.

## Cross-repo dependency

Gather on WSE-3 is the kernel that forces a Doppler-side change: RDRR
shard packaging must produce per-tensor Merkle blocks for the gathered
table tensor at a chunk granularity compatible with fabric streaming.
Today `integrityExtensions.blockMerkle.roots` exists, but at the
whole-tensor root level only. Fabric streaming wants per-chunk roots
at the planner-chosen block size. Scoping that change is out of this
iteration and belongs to Loop 3 when the gather kernel reaches its
turn in the GEMV → RMSNorm → gather sequence.

## Status

- `gather.wgsl`: pinned WGSL snapshot.
- `gather.tsir-semantic.json`: hand-sketched TSIR, schema-valid. The
  `SemanticBody` contract is declared (`op: gather`, binding roles for
  indices/table/output, axis roles for token/hidden), and the
  reference interpreter recognizes this shape end-to-end across
  `{f32, f16, bf16}` with fail-closed out-of-range index validation.
  Original "unrepresentable" framing referred to the pre-`SemanticBody`
  schema state — the indexed copy operation is now expressible via the
  body-op contract, though the broader `GatherNode` extensions this
  doc's earlier section describes (bounds policy, uniform-scalar refs)
  remain Phase B / future work.
- `gather.tsir-realization.wse3.json`: hand-sketched, schema-valid.
- `gather.tsir-realization.webgpu-generic.json`: hand-sketched,
  schema-valid.
