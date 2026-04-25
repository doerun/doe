# Fused GEMV — TSIR schema fit report

Source: [`fused_gemv.wgsl`](fused_gemv.wgsl).
Hand-sketched TSIR: [`fused_gemv.tsir-semantic.json`](fused_gemv.tsir-semantic.json).

## What fits the current schema

- Two iteration axes (`i`, `k`) with symbolic bounds. `IterationAxis` accepts
  string bounds, so `"M"` / `"K"` is legal.
- Three buffer bindings with the right read/write polarity. 2-D shape on
  `W`, 1-D on `x` and `y`.
- One reduction region along axis `k` writing into `y`. `ReductionRegion.op
  = "sum"` with `strict_ordered` associativity and `f32` accumulation is a
  supported oracle dispatch path.
- The reduction's fixed left-fold is bit-exact with respect to
  `strict_ordered`; the reference interpreter's
  `trySimpleReduction` path can honor it.

## What does NOT fit the current schema

- **The elementwise multiply `W[i,k] * x[k]` before the sum is not
  representable.** `ReductionRegion` expresses a pure reduction of one
  input buffer along one axis; it cannot express "reduce the elementwise
  product of two input buffers." The reference interpreter's Phase A
  dispatch therefore cannot currently compute the kernel output value from
  this TSIR; it can only prove that the reduction shape and numerical
  contract are representable.
- There is no schema node for "elementwise op before reduction", no
  multi-input reduction contract, and no fused multiply-reduce operator.
- `logicalShape` entries use `[0, 0]` / `[0]` as placeholders because the
  schema expects concrete integers. Symbolic dims (`M`, `K`) live only in
  `IterationAxis.upperBound` as strings.

## Implied Step 3 schema extensions

The missing coverage is not "more fields on `ReductionRegion`." It is a
declared **op-body representation** that the frontend can emit and the
reference interpreter can dispatch. Options:

1. **Fused reduction with pre-op.** Extend `ReductionRegion` with an
   optional `preOp` enum (`identity`, `mul`, `square`, `abs`, ...) and a
   list of input bindings/layouts. Narrow but clear for GEMV and
   sum-of-squares.
2. **Elementwise operations as first-class TSIR nodes.** A new
   `operations: []const Operation` field on `SemanticFunction` carrying a
   small AST of elementwise ops with input/output buffer references. The
   reduction then consumes the AST's output as its "virtual input".
3. **Symbolic buffer-shape dims.** Separate from op-body work, but also
   needed here since concrete `logicalShape` integers do not exist until
   specialization. The current placeholder `[0, 0]` is a schema smell.

Option 2 is the cleanest architectural direction per the plan's parity-
oracle-first discipline: once the interpreter can walk a declared op AST,
gather / RMSNorm / other kernels become natural extensions of the same
dispatch instead of per-kernel special cases.

## Realization sketches

Sketches landed for both targets. They describe target-specific placement,
tiling, residency, and reduction-tree choices on top of the semantic, even
though the semantic itself is still incomplete on op-body representation.
The sketches are schema-valid (`doe-tsir-realization.schema.json`) and
validate under `test_every_realization_json_validates`.

- `fused_gemv.tsir-realization.wse3.json`: 8×1 PE grid, row-sliced
  `W`/`y`, replicated `x`, k-axis reduction is PE-local so no fabric
  allreduce (tree shape `linear`).
- `fused_gemv.tsir-realization.webgpu-generic.json`: single-device
  target modeled as 1×1 PE grid, all bindings `pe_replicated`,
  workgroup-local reduction.

Caveats that flow from the semantic gap above:

- These sketches describe the realization *layer* only. Until the schema
  can express the elementwise `W[i,k] * x[k]` pre-reduction, neither the
  semantic nor the realization is sufficient to drive the reference
  interpreter to a numeric output for this kernel.
- Tile factors (`[8, 16]` wse3; `[8, 16]` webgpu-generic) are placeholders
  driven by typical matmul tile shapes, not the Step 5 residency planner.
  The planner, when it lands, should reproduce these choices under the
  per-PE memory budget or reject with a recorded reason.

## Status

- `fused_gemv.wgsl`: pinned WGSL snapshot.
- `fused_gemv.tsir-semantic.json`: hand-sketched TSIR, schema-valid. The
  `SemanticBody` contract is declared (`op: fused_gemv`, binding roles
  for matrix/vector/output, axis roles for output/reduction), and the
  reference interpreter recognizes this shape end-to-end across
  `{f32, f16, bf16}` with `strict_ordered` + `associative_allowed`
  reductions. Original "semantically incomplete" framing referred to the
  pre-`SemanticBody` schema state.
- `fused_gemv.tsir-realization.wse3.json`: hand-sketched, schema-valid.
- `fused_gemv.tsir-realization.webgpu-generic.json`: hand-sketched,
  schema-valid.
