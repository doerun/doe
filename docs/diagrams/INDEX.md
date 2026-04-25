# Index — Doppler → Doe → CSL slide deck

This document is the design-system source-of-truth for the deck under
`docs/diagrams/`. Per-slide files reference design tokens by name; this
file defines them.

## Table of contents

| # | Title | File | Persistent example |
|---|---|---|---|
| 01 | Cover — Two preservation properties, one author identity | [`01-cover.md`](01-cover.md) | — |
| 02 | The problem — Spatial compute needs exposed axes | [`02-problem.md`](02-problem.md) | — |
| 03 | The stack at a glance — Doppler → Doe → CSL | [`03-stack-overview.md`](03-stack-overview.md) | — |
| 04 | Hardware primer — three execution models, one author | [`04-hardware-primer.md`](04-hardware-primer.md) | — |
| 05 | TSIR semantic function — the body-preserving IR | [`05-tsir-semantic-function.md`](05-tsir-semantic-function.md) | rms_norm |
| 06 | HostPlan — the identity-preserving orchestration | [`06-hostplan-identity.md`](06-hostplan-identity.md) | Gemma 3 1B |
| 07 | Walkthrough: rms_norm | [`07-walkthrough-rmsnorm.md`](07-walkthrough-rmsnorm.md) | rms_norm |
| 08 | Walkthrough: fused_gemv | [`08-walkthrough-fused-gemv.md`](08-walkthrough-fused-gemv.md) | fused_gemv |
| 09 | Walkthrough: kv_write — the stateful case | [`09-walkthrough-kv-write.md`](09-walkthrough-kv-write.md) | kv_write |
| 10 | Walkthrough: attention_decode — multi-axis reduction | [`10-walkthrough-attention-decode.md`](10-walkthrough-attention-decode.md) | attention_head256_f16kv |
| 11 | JS orchestration → HostPlan | [`11-js-to-hostplan.md`](11-js-to-hostplan.md) | Gemma 3 1B |
| 12 | HostPlan → per-PE programs | [`12-hostplan-to-per-pe.md`](12-hostplan-to-per-pe.md) | Gemma 3 1B |
| 13 | The bundle — one artifact, three execution surfaces | [`13-bundle-distribution.md`](13-bundle-distribution.md) | Gemma 4 31B |
| 14 | Why ONNX-shaped pipelines hit a wall | [`14-onnx-comparison.md`](14-onnx-comparison.md) | — |
| 15 | Where the analogy breaks down — honesty | [`15-honesty-limits.md`](15-honesty-limits.md) | — |
| 16 | Evidence ledger — receipt-backed claims today | [`16-evidence-ledger.md`](16-evidence-ledger.md) | — |
| 17 | Forward path — hardware verification | [`17-forward-path.md`](17-forward-path.md) | — |

## Design theme

### Color palette

Three named hues plus neutral. Hex values are reference; designers may
substitute palette-equivalent shades but the *semantic* assignment of
each hue to its meaning is fixed.

| Token | Hex (reference) | Semantic assignment |
|---|---|---|
| `red.opaque` | `#C73E3E` | The path we're contrasting against. Opaque-body operators, ONNX-shaped IRs, hidden state, "we don't compose with this." |
| `red.dim` | `#E89090` | Faded variant for de-emphasized red elements (e.g., per-op kernel boxes in slide 14's left column). |
| `blue.preserve` | `#2B6CB0` | The Doe preservation chain. WGSL authoring, TSIR semantic functions, per-backend emitters, HostPlan identity. |
| `blue.dim` | `#90B8DC` | Faded variant for supporting blue elements. |
| `purple.spatial` | `#6B46C1` | Spatial compute. Cerebras WSE, PE grid, fabric routes, wafer ROI, hardware execution. |
| `purple.dim` | `#B8A0E0` | Faded variant for supporting purple elements. |
| `neutral.body` | `#4A5568` | Body text, most labels, neutral infrastructure. |
| `neutral.bg` | `#F7FAFC` | Slide background. |
| `neutral.line` | `#CBD5E0` | Light separators, grid guides. |
| `accent.gold` | `#D69E2E` | Identity / hash badges. Used sparingly — only on content-addressable identity elements. |

**Rule of thumb:** if an element is part of the preservation chain
(WGSL → TSIR → CSL emitter), it's `blue.preserve`. If it executes on
a PE grid or wafer, it's `purple.spatial`. If it's the operator-graph
contrast, it's `red.opaque`. Identity hashes and bundle pointers get
`accent.gold`. Everything else is `neutral.body`.

### Shape vocabulary

| Shape | Represents | First defined |
|---|---|---|
| Square / rectangle (sharp corners) | Component, kernel, file, code panel, IR slot | Slide 02 |
| Rounded rectangle (corner radius 8px) | Bundle artifact, packaged unit | Slide 13 |
| Circle | Identity token, axis value, flow node, scalar | Slide 06 |
| Diamond | Body op tag (rms_norm, kv_write, fused_gemv) | Slide 05 |
| Hexagon | PE cell on the grid | Slide 04 |
| Wafer-shape (large rounded rectangle, 16px corner) | Cerebras WSE wafer outline | Slide 04 |
| Browser-tab outline (rectangle with small tabs at top) | WebGPU execution context | Slide 04 |
| Tarball cylinder | Bundle on disk | Slide 13 |
| Hash-badge pill (rounded rectangle, accent.gold fill) | Content-addressable identity | Slide 06 |

### Connection vocabulary

| Stroke | Represents |
|---|---|
| Solid arrow with label | Data flow or transformation. Color matches the source element. |
| Dotted line | Conceptual relationship without flow ("this is the same thing in a different form"). |
| Thick band (4-6px) under stack arrow | Preservation property — labels what is preserved across a transformation. |
| Dashed line | Boundary or scope marker (e.g., sliding-window mask in slide 10). |

### Typography

| Use | Family | Weight |
|---|---|---|
| Code, file paths, hashes | Monospace (system stack: SF Mono, Menlo, Consolas, Liberation Mono, monospace) | 400-500 |
| Labels, captions | Sans-serif (system stack: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif) | 500-600 |
| Body / non-claim text | Same sans-serif | 400, italic |
| Slide titles | Same sans-serif | 700 |

### Sizing

| Class | Pixel size (reference) | Use |
|---|---|---|
| Small icon | 32 × 32 | Visual-key row, inline references |
| Medium block | 200 × 120 | Component boxes inside a stack |
| Large block | 320 × 200 | Hero element on a comparison slide |
| Slide canvas | 1600 × 900 (16:9) | Full slide |
| Slide margin | 80 px on each side | Reserved white space |
| Pane gap | 24 px between adjacent panes | Walkthrough four-pane layout |

### Layout patterns

Every slide's `What it might look like` section maps to one of these
named patterns. Designers should match the pattern's structural
proportions; specific element placement is then per-slide.

| Pattern | Used by | Description |
|---|---|---|
| `cover-card` | 01 | Centered title + subtitle stack; thin icon-key row at bottom. |
| `side-by-side-stacks` | 02, 14 | Two equal-width columns, matched horizontal bands so contrast is at the same vertical position. |
| `three-columns-flow` | 03 | Three vertical columns with cross-column arrows labeled with preservation property. |
| `icon-row-with-captions` | 04 | Three icons across the top, each with a one-line caption beneath; reference bar at slide bottom. |
| `hero-box-with-inset` | 05, 06 | One dominant central element + small inset code panel for ground-truth anchoring. |
| `four-pane-walkthrough` | 07, 08, 09, 10 | 2×2 grid: WGSL (top-left), TSIR (top-right), CSL emission (bottom-left), PE-grid (bottom-right). Equal panes, 24px gaps. |
| `two-pane-with-arrow` | 11 | Left pane (source view), right pane (lowered view), labeled arrow between. |
| `expansion-flow` | 12 | Vertical HostPlan strip on left, horizontal expansion of one launch into h2d→dispatch→d2h→next-input. |
| `radial-distribution` | 13 | Center-top hero (bundle), three radiating arrows down to three execution-surface columns. |
| `text-list-discipline` | 15, 16 | Single column of structured text rows with explicit visual hierarchy. No diagrams. |
| `bottom-up-dag` | 17 | Three or more nodes in a DAG, oriented bottom-up, with labeled arrows. |

### Persistent visual elements (referenced across slides)

The following icons appear on multiple slides and must look identical
each time. Designed once, reused everywhere.

| Element | Color | Shape | Source slide |
|---|---|---|---|
| Browser tab + workgroup grid | `blue.preserve` outline, `neutral.bg` fill, blue grid cells | Browser-tab outline + 4×4 inner grid of small squares | 04 |
| PE grid + fabric routes | `purple.spatial` outline + `purple.dim` fill, `neutral.line` route lines | 8×8 hexagons (PEs) connected by thin lines | 04 |
| Wafer outline + ROI | `purple.spatial` outline (corner radius 16), `purple.dim` ROI rectangle | Large rounded rectangle with smaller inner rectangle | 04 |
| TSIR semantic-function box | `blue.preserve` border, four horizontal slot bands separated by `neutral.line` | Sharp-corner rectangle with internal divisions | 05 |
| HostPlan vertical strip | `blue.preserve` boxes connected by `blue.preserve` arrows | 5-8 stacked rectangles with downward arrows | 06 |
| Bundle tarball | `accent.gold` cylinder shape with `neutral.body` band labels | Cylinder with hash strings as labels | 13 |
| Identity hash badge | `accent.gold` fill, `neutral.body` text (monospace) | Rounded-rectangle pill | 06 |
| Body-op diamond | `blue.preserve` fill, `neutral.bg` text | Diamond, 80×80 px | 05 |

### Per-slide visual spec checklist

Each slide's `What it might look like` section must specify:

1. **Layout pattern** (one from the named list above).
2. **Color assignments** for the slide's main elements (using token names, not raw hex).
3. **Shape assignments** for any new shape not listed in the persistent-elements table.
4. **Specific labels** that appear in the slide (titles, captions, axis names).
5. **Spatial relationships** ("PE grid pane shows X axis as horizontal, Y axis as vertical, with collective arrows along Y").
6. **Reference to persistent elements** by name ("reuse the HostPlan vertical strip from slide 06").

If a slide's spec doesn't include all six, it's not yet
graphic-generatable; flag with a `<!-- TODO: visual spec -->` comment
inline in the markdown.

## Snapshot assumption (deck-level)

The deck is written as if every component of the simfabric + WebGPU
evidence chain is in hand: TSIR coverage complete, WebGPU references
frozen, 31B program bundle in tree, decode mechanism exercised
including kv_write / kv_read, smoke ladder L1-L61 receipts landed,
bundle ready to circulate. **The single outstanding gate is execution
on Cerebras hardware (R2-10).** Slides 13, 15, 16, and 17 carry this
distinction explicitly; everything else is structural and unaffected
by the hardware leg.

## Generation pipeline (implied)

The markdown source-of-truth + this design system is intended to feed
two downstream artifacts:

1. **Static SVGs** under `docs/diagrams/svg/` (one per slide, named
   `<slide-id>.svg`) — auto-generatable from the spec sections plus
   design tokens.
2. **Interactive HTML** following the existing
   `docs/onboarding-view.{html,css,js}` pattern, embedding the SVGs
   as side-by-side panels with the markdown text as narrative.

Neither is committed yet. The markdown discipline is what gates both.
