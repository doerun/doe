# RMSNorm — TSIR schema fit report

Source: [`rms_norm.wgsl`](rms_norm.wgsl).
Hand-sketched TSIR: [`rms_norm.tsir-semantic.json`](rms_norm.tsir-semantic.json).

## What fits the current schema

- Two iteration axes (`d` for the per-output-element loop, `i` for the
  reduction loop).
- Three tensor bindings (`input`, `weight`, `output`) plus the read-only
  uniform binding (`u`) that carries `hidden_size` and `eps`.
- One reduction region on axis `i` with `sum` / `strict_ordered` / `f32`
  accumulation, matching the interpreter's existing dispatch for
  single-axis strict-ordered f32 sums.
- `SemanticBody.rmsNorm` now declares the RMSNorm summary contract:
  sum-of-squares mean, epsilon add, reciprocal square-root, and output
  scaling; epsilon is sourced from `uniform:u.eps`, binding index `3`,
  byte offset `4`.
- `reductionTarget = intermediate_scalar` records that the reduction feeds
  a scalar intermediate, even though the legacy `ReductionRegion.targetBinding`
  field still points at the output binding until TSIR gains stage-local
  intermediate nodes.

## What does NOT fit the current schema

The body contract names the RMSNorm formula and the bootstrap reference
interpreter can execute that family summary directly. TSIR still lacks the
general expression graph needed to interpret or emit arbitrary RMSNorm-like
variants mechanically:

1. **Elementwise square before reduction.** The reduction computes
   `sum(x²)`, not `sum(x)`. Same category as GEMV's fused multiply:
   `ReductionRegion` has no pre-op.
2. **Scalar-tail arithmetic.** After the reduction produces `sum_sq`, the
   kernel divides by `hidden_size` (scalar reciprocal-multiply), adds
   `eps`, takes `sqrt`, and takes reciprocal. None of these operations
   exist as TSIR nodes.
3. **Elementwise multiply chain after reduction.** `output[d] = input[d]
   * inv_rms * weight[d]` is a per-element op consuming two buffers and
   one scalar. TSIR has no elementwise-op node and no scalar broadcast.
4. **Post-reduction dependency.** The output loop reads the scalar
   `inv_rms` produced by the reduction. There is no TSIR way to express
   "reduction's result feeds a subsequent elementwise pass in the same
   function."

The semantic JSON now captures the family-level RMSNorm contract, but not
the full executable dataflow. The reference interpreter must still reject
RMSNorm until those node-level semantics exist.

## Implied Step 3 schema extensions

Beyond the GEMV-implied fused pre-op, RMSNorm demands:

1. **Elementwise operation AST as a first-class TSIR node**, with
   support for chained ops (`read` → `square` → `reduce` → `div_scalar`
   → `add_scalar` → `sqrt_scalar` → `recip_scalar` → `mul` → `mul` →
   `write`). This is option (2) from the GEMV notes, now additionally
   requiring scalar intrinsics (`sqrt`, `recip`).
2. **Scalar operand generalization.** `eps` now has a symbolic source in the
   body contract plus binding/offset metadata that the oracle can execute.
   Emitters still need the matching uniform-buffer flattening before every
   backend artifact can consume the value mechanically.
3. **Multi-stage function composition.** The reduction's output is
   consumed by a later elementwise pass *in the same SemanticFunction*.
   Either the `SemanticFunction` needs an ordered list of stages
   (reduce, then elementwise), or the function must be split into two
   with an explicit dependency edge.
4. **Determinism for transcendentals.** `sqrt` is in the declared
   oracle transcendental table; `recip` is handled by either a
   dedicated intrinsic or `1.0 / x`. Parity across backends requires
   the reference interpreter to honor the sollya-bounded polynomial
   implementations declared in `reference_interpreter.zig`. This is a
   Phase B concern (per the plan's determinism requirement), but a
   Phase A kernel that uses these functions is declared
   `tolerance_bounded` with a named metric and epsilon — RMSNorm will
   be such a kernel.

## Realization sketches

Sketches landed for both targets at the realization layer. They describe
target-specific placement, tiling, and reduction-tree choices on top of
the reduction shape that *is* representable in the semantic. Schema-valid
under `doe-tsir-realization.schema.json`.

- `rms_norm.tsir-realization.wse3.json`: 8×1 PE grid, input/output row-
  sliced along the hidden axis, weight replicated. Mean-of-squares
  reduction uses a `binomial` tree across the 8 PEs (fabric reduction).
- `rms_norm.tsir-realization.webgpu-generic.json`: 1×1 PE grid, all
  bindings `pe_replicated`, reduction tree `linear` at the TSIR layer
  (subgroup shape is hardware-chosen below TSIR).

Caveats that flow from the semantic gap above:

- These sketches cover only the reduction's placement. The semantic now
  records the executable bootstrap-family RMSNorm formula, but the pre-op
  square, scalar-eps tail, sqrt/recip, and post-reduction elementwise
  normalization are not represented as reusable TSIR expression nodes yet.
  The sketches are structurally correct for the placement layer and still
  silent on those node-level execution details.
- The WSE-3 sketch declares `binomial` tree shape; this choice is a
  numerical contract once Step 6 (collective synthesis) formalizes
  reduction-tree declaration as part of the `algorithm-exact`
  equivalence.

## Status

- `rms_norm.wgsl`: pinned WGSL snapshot.
- `rms_norm.tsir-semantic.json`: hand-sketched TSIR, schema-valid, with a
  family-level `rmsNorm` body contract. The oracle can execute this
  bootstrap contract with explicit uniform epsilon bytes; the full body
  (pre-op square, scalar tail, elementwise normalization) is still not
  represented as node-level TSIR.
- `rms_norm.tsir-realization.wse3.json`: hand-sketched, schema-valid.
- `rms_norm.tsir-realization.webgpu-generic.json`: hand-sketched,
  schema-valid.
