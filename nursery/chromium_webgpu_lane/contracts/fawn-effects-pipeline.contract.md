# fawn_effects_pipeline Contract (Draft)

## Status

`draft`

## Goal

Provide deterministic execution of selected effect graphs (blur, color transforms, masks, compositing operations) via WebGPU render/compute passes.

## Ownership Boundary

Owns:

1. Effect graph execution order for contract-defined operations.
2. Intermediate resource allocation policy.
3. Output artifact and diagnostics.

Does not own:

1. Effect authoring UI/semantics outside contract.
2. Browser-level scene graph policy.
3. OS compositor responsibility.

## Input Contract (Candidate)

1. `effectGraph`
   - DAG of effect nodes with explicit op types
2. `inputs`
   - source textures and metadata
3. `executionPolicy`
   - pass ordering constraints
   - precision class
4. `target`
   - output render target and format info

## Output Contract (Candidate)

1. `outputArtifact`
   - final texture/surface identity
2. `executionStats`
   - node count
   - pass count
   - temporary allocation stats
3. `timingStats`
   - setup/encode/submit-wait totals
4. `fallbackStats`
   - fallback counts and reason codes
5. `traceLink`
   - module identity and hash chain anchors

## Fallback Taxonomy (Draft)

1. `effect_op_unsupported`
2. `color_space_mode_unsupported`
3. `intermediate_budget_exceeded`
4. `precision_policy_violation`
5. `required_capability_missing`

## Determinism Rules

1. Graph execution order is explicit and stable.
2. Intermediate allocation strategy is deterministic for fixed input.
3. Unsupported nodes produce explicit taxonomy and fallback behavior.

## Gates

Blocking:

1. Schema gate.
2. Correctness gate using effect golden corpus.
3. Trace gate for pass ordering and hash continuity.

Advisory:

1. Performance gate on representative effect chains.

## KPI Candidates

1. Golden-corpus correctness pass rate.
2. Intermediate allocation churn trend.
3. p50/p95 latency per effect class.
4. Fallback frequency by node type.

## Promotion Preconditions

1. Effect op registry is explicit and versioned.
2. Fallback reasons are schema-backed.
3. Canonical effect corpus and expected outputs are versioned.
