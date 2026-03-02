# fawn_2d_sdf_renderer Contract (Draft)

## Status

`draft`

## Goal

Provide a GPU-first 2D renderer for text/vector/UI draw workloads using SDF/MSDF where quality and performance are acceptable.

CPU retains ownership of layout, shaping, bidi, accessibility semantics.

## Ownership Boundary

Owns:

1. Glyph atlas rendering and sampling policy.
2. Path/vector rasterization path for eligible primitives.
3. Render pass emission and texture outputs.
4. Quality/fallback metrics emission.

Does not own:

1. DOM/CSS layout decisions.
2. Text shaping semantics.
3. Accessibility semantics.
4. Scene graph policy outside defined input contract.

## Input Contract (Candidate)

1. `textRuns[]`
   - `fontKey`
   - `glyphIds[]`
   - `positions[]`
   - `color`
   - `transform`
2. `pathOps[]`
   - command stream (`moveTo`, `lineTo`, `curveTo`, `closePath`)
   - fill/stroke parameters
3. `paintState`
   - blend mode
   - clip state
   - global transform
4. `target`
   - width/height
   - format
   - sample count

All inputs must be deterministic and schema-valid before execution.

## Output Contract (Candidate)

1. `renderArtifact`
   - output texture/surface identifier
2. `renderStats`
   - draw call count
   - atlas hit/miss counts
   - pass count
3. `timingStats`
   - setup/encode/submit-wait totals
4. `qualityStats`
   - fallback count
   - fallback reason histogram
5. `traceLink`
   - module identifier and hash chain anchors

## Capability Contract

Required capability checks:

1. Texture format support for atlas and targets.
2. Required shader feature set.
3. Required sample count support.

If a required capability fails, return explicit unsupported taxonomy and deterministic fallback.

## Fallback Taxonomy (Draft)

1. `small_text_quality_guard`
2. `path_complexity_exceeded`
3. `unsupported_blend_mode`
4. `unsupported_clip_mode`
5. `required_capability_missing`
6. `resource_budget_exceeded`

## Determinism Requirements

1. Fixed input + fixed config yields stable output metadata.
2. Atlas eviction policy must be deterministic for fixed sequence.
3. Fallback decisions must be deterministic and reason-coded.

## Gates

Blocking for promotion:

1. Schema gate (input/output contract fields).
2. Correctness gate (known-output comparisons for fixed seeds).
3. Trace gate (hash chain + decision envelope consistency).

Advisory:

1. Performance gate.
2. Verification policy where applicable.

## KPI Candidates

1. Fallback rate under canonical workloads.
2. Atlas miss rate trend.
3. p50/p95 encode timing trend for eligible scenes.
4. Quality-fallback frequency by adapter profile.

## Promotion Preconditions

1. Contract fields promoted to schema with migration notes.
2. Required quality guards are explicit and configurable.
3. Fallback behavior is measurable and surfaced in reports.
4. CI includes deterministic seed workload checks.
