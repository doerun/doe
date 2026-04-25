# Index — Doppler -> Doe -> Cerebras slide deck

This document is the design-system source-of-truth for the deck under
`docs/diagrams/`. Per-slide files reference design tokens by name; this
file defines them.

## Table of contents

| # | Title | File | Persistent example |
|---|---|---|---|
| 01 | Cover - One contract, one lowering path, one receipt | [`01-cover.md`](01-cover.md) | Gemma 4 31B |
| 02 | Problem - Cerebras needs the body | [`02-problem.md`](02-problem.md) | — |
| 03 | Names and boundaries - Doppler, Doe, Cerebras | [`03-stack-overview.md`](03-stack-overview.md) | — |
| 04 | Execution surfaces - browser, simfabric, wafer | [`04-hardware-primer.md`](04-hardware-primer.md) | — |
| 05 | TSIR - body shape where semantic | [`05-tsir-semantic-function.md`](05-tsir-semantic-function.md) | rms_norm |
| 06 | HostPlan - identity through execution | [`06-hostplan-identity.md`](06-hostplan-identity.md) | Gemma 4 31B |
| 07 | Walkthrough: rms_norm | [`07-walkthrough-rmsnorm.md`](07-walkthrough-rmsnorm.md) | rms_norm |
| 08 | Walkthrough: fused_gemv | [`08-walkthrough-fused-gemv.md`](08-walkthrough-fused-gemv.md) | fused_gemv |
| 09 | Walkthrough: kv_write - stateful cache | [`09-walkthrough-kv-write.md`](09-walkthrough-kv-write.md) | kv_write |
| 10 | Walkthrough: attention_decode - multi-axis decode | [`10-walkthrough-attention-decode.md`](10-walkthrough-attention-decode.md) | attention_head256_f16kv |
| 11 | Doppler JS to HostPlan | [`11-js-to-hostplan.md`](11-js-to-hostplan.md) | Gemma 4 31B |
| 12 | HostPlan to per-PE execution | [`12-hostplan-to-per-pe.md`](12-hostplan-to-per-pe.md) | Gemma 4 31B |
| 13 | Bundle - one contract, three receipts | [`13-bundle-distribution.md`](13-bundle-distribution.md) | Gemma 4 31B |
| 14 | Why ONNX-shaped pipelines hit a wall | [`14-onnx-comparison.md`](14-onnx-comparison.md) | — |
| 15 | Limits - what this does not prove | [`15-honesty-limits.md`](15-honesty-limits.md) | — |
| 16 | Evidence ledger - what backs the story | [`16-evidence-ledger.md`](16-evidence-ledger.md) | Gemma 4 31B |
| 17 | Forward path - refreshable evidence | [`17-forward-path.md`](17-forward-path.md) | Gemma 4 31B |

## Design theme

### Color palette

Colors encode ownership. Hex values are references; final design may use
brand-equivalent shades, but the semantic assignment is fixed.

| Token | Hex (reference) | Semantic assignment |
|---|---|---|
| `doppler.red` | `#C73E3E` | Doppler-owned source contract: raw JS, raw WGSL, manifest, tokenizer, weights, reference transcript. |
| `doe.blue` | `#2B6CB0` | Doe compiler/lowering surfaces: WGSL IR, TSIR, emitters, HostPlan identity. |
| `doe.lightBlue` | `#90B8DC` | Faded variant for supporting blue elements. |
| `doe.purple` | `#6B46C1` | Doe runtime/evidence surfaces: simfabric runner, bundle plumbing, parity binding. |
| `doe.lightPurple` | `#B8A0E0` | Faded variant for supporting Doe runtime elements. |
| `cerebras.orange` | `#F05A28` | Cerebras-owned execution concepts: WSE, PE grid, fabric routes, SDK run, hardware receipt. |
| `cerebras.light` | `#FDBA8C` | Faded variant for supporting Cerebras elements. |
| `cerebras.charcoal` | `#252525` | Cerebras labels, wafer outlines, and hardware boundary text where orange would over-dominate. |
| `contrast.gray` | `#64748B` | Opaque-body/operator-graph contrast such as ONNX-shaped IRs. Not Doppler. |
| `contrast.light` | `#CBD5E1` | Faded variant for contrast elements. |
| `neutral.body` | `#4A5568` | Body text, most labels, neutral infrastructure. |
| `neutral.bg` | `#F7FAFC` | Slide background. |
| `neutral.line` | `#CBD5E0` | Light separators, grid guides. |
| `accent.gold` | `#D69E2E` | Identity / hash badges. Used sparingly — only on content-addressable identity elements. |

**Rule of thumb:** Doppler source is `doppler.red`; Doe lowering is
`doe.blue`; Doe runtime/evidence plumbing is `doe.purple`; Cerebras hardware,
PE grids, fabric, SDK, and wafer elements are `cerebras.orange` or
`cerebras.charcoal`; opaque-op contrast is `contrast.gray`; identity hashes and
bundle pointers are `accent.gold`.

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

Every slide's `Visual spec` section maps to one of these
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
| Browser tab + workgroup grid | `doe.blue` outline, `neutral.bg` fill, blue grid cells | Browser-tab outline + 4×4 inner grid of small squares | 04 |
| PE grid + fabric routes | `cerebras.orange` outline + `cerebras.light` fill, `neutral.line` route lines | 8×8 hexagons (PEs) connected by thin lines | 04 |
| Wafer outline + ROI | `cerebras.charcoal` outline, `cerebras.orange` ROI rectangle | Large rounded rectangle with smaller inner rectangle | 04 |
| TSIR semantic-function box | `doe.blue` border, four horizontal slot bands separated by `neutral.line` | Sharp-corner rectangle with internal divisions | 05 |
| HostPlan vertical strip | `doe.blue` boxes connected by `doe.blue` arrows | 5-8 stacked rectangles with downward arrows | 06 |
| Bundle tarball | `accent.gold` cylinder shape with `neutral.body` band labels | Cylinder with hash strings as labels | 13 |
| Identity hash badge | `accent.gold` fill, `neutral.body` text (monospace) | Rounded-rectangle pill | 06 |
| Body-op diamond | `doe.blue` fill, `neutral.bg` text | Diamond, 80×80 px | 05 |

### Per-slide visual spec checklist

Each slide's `Visual spec` section must specify:

1. **Layout pattern** (one from the named list above).
2. **Color assignments** for the slide's main elements (using token names, not raw hex).
3. **Shape assignments** for any new shape not listed in the persistent-elements table.
4. **Specific labels** that appear in the slide (titles, captions, axis names).
5. **Spatial relationships** ("PE grid pane shows X axis as horizontal, Y axis as vertical, with collective arrows along Y").
6. **Reference to persistent elements** by name ("reuse the HostPlan vertical strip from slide 06").

If a slide's spec doesn't include all six, it's not yet
graphic-generatable; flag with a `<!-- TODO: visual spec -->` comment
inline in the markdown.

## Slice boundary

This is not a deck about all of Doe. Doe also has ordinary GPU compiler and
runtime paths for WebGPU/Vulkan/SPIR-V, Metal/MSL, DXIL, and native backends.
This deck carves out the Cerebras path only: Doppler raw JS/WGSL contract ->
Doe TSIR/HostPlan/CSL lowering where applicable -> Cerebras SDK/hardware
receipt.

## Snapshot assumption

The deck may be rendered as a forward-looking Cerebras ask. It may assume Gemma
4 31B evidence exists by presentation time, but slide 16 must name which rows
are already in hand and which rows are expected before sending. The central
claim is still structural: evidence is easy to refresh because a new run needs
only the Doppler contract (raw JS, raw WGSL, manifest, weights, tokenizer, and
prompt), then Doe re-emits HostPlan/CSL/receipts from that identity.

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
