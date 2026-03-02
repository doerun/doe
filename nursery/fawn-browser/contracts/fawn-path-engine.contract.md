# fawn_path_engine Contract (Draft)

## Status

`draft`

## Goal

Provide deterministic path processing for strokes/fills/clips via hybrid tessellation and SDF-assisted strategies.

## Ownership Boundary

Owns:

1. Path geometry processing and raster eligibility checks.
2. Tessellation strategy selection from explicit policy.
3. Path rendering pass outputs and diagnostics.

Does not own:

1. High-level scene semantics.
2. Text shaping semantics.
3. Browser layout decisions.

## Input Contract (Candidate)

1. `pathStream[]`
   - canonical path segments and contour markers
2. `strokeState`
   - width, joins, caps, miter limit, dash pattern
3. `fillState`
   - fill rule and opacity state
4. `clipState`
   - clip path references and transforms
5. `target`
   - render target definition

## Output Contract (Candidate)

1. `geometryStats`
   - segment counts
   - tessellated primitive counts
2. `rasterStats`
   - pass count
   - emitted draw calls
3. `fallbackStats`
   - fallback count and reason histogram
4. `traceLink`
   - hash chain anchor and module identity

## Fallback Taxonomy (Draft)

1. `geometry_pathological`
2. `dash_pattern_unsupported`
3. `join_mode_unsupported`
4. `precision_guard_triggered`
5. `resource_budget_exceeded`

## Determinism and Safety Rules

1. Strategy selection must be policy-driven, not heuristic-only.
2. Precision guards must be explicit and reason-coded.
3. Unsupported operations must fail with actionable taxonomy.

## Gates

Blocking:

1. Schema gate.
2. Correctness gate on canonical path corpus.
3. Trace gate for deterministic decision envelopes.

Advisory:

1. Performance gate for path-heavy workloads.

## KPI Candidates

1. Path correctness pass rate on canonical corpus.
2. Fallback rate by path class.
3. Tail latency trend for large path scenes.
4. Determinism rate across repeated seeded runs.

## Promotion Preconditions

1. Canonical path corpus defined and versioned.
2. Fallback thresholds documented and config-backed.
3. Output contract fields promoted with schema updates.
