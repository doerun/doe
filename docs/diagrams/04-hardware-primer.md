# 04 — Hardware primer: "Three execution models, one author"

## Goals

Establish the visual vocabulary that the rest of the deck reuses. Three
side-by-side iconographic depictions of the hardware models Doe targets,
so later slides can refer to them without re-explaining.

## What it shows

- Three icons side-by-side, each labeled and dimensioned consistently:
  1. **WebGPU** — a browser-tab outline containing a workgroup grid
     (small squares arranged 4×4). Inside each cell, a tiny thread icon.
  2. **CSL** — a rectangular PE grid (e.g., 8×8 visible cells) with
     explicit fabric-route lines connecting cells along rows and
     columns. Edge ports labeled `h2d` / `d2h`.
  3. **WSE3** — a wafer outline (large rectangle with rounded corners)
     with a smaller highlighted ROI rectangle inside, fabric color
     codes shown on the ROI's edges, PE coordinates labeled at corners.
- Below each icon, a one-line caption: "SIMT, threadgroup parallelism" /
  "PE grid, fabric-routed collectives" / "Wafer-scale, ROI-bounded".

## What it might look like

Three columns of equal width, each ~1/3 of the slide. The icons sit at
the top; captions sit below. A thin horizontal bar at the bottom of the
slide carries six smaller variants of these icons plus three from
slides 05/06/13 (TSIR semantic-function box, HostPlan list, bundle
tarball). That bar is reused as a header/footer reference on subsequent
slides.

### Visual spec (per design tokens)

- **Layout pattern:** `icon-row-with-captions`.
- **Left column — WebGPU icon (large-block):** browser-tab outline
  (`blue.preserve` stroke 2px, `neutral.bg` fill, with two small
  tab-rectangles at top). Inside the tab body, a 4×4 grid of small
  filled squares (`blue.dim` fill, `blue.preserve` stroke). Inside
  each cell, a tiny circular thread marker (`blue.preserve`, 4 px).
  Caption: *"SIMT, threadgroup parallelism."*
- **Middle column — CSL icon (large-block):** 8×8 hexagon grid
  representing PEs (`purple.dim` fill, `purple.spatial` stroke).
  Fabric-route lines (`neutral.line`, 1px) connecting hexagons along
  rows and columns. Edge labels: `h2d` on the left edge, `d2h` on
  the right edge, both `neutral.body` monospace. Caption: *"PE grid,
  fabric-routed collectives."*
- **Right column — WSE3 icon (large-block):** large rounded
  rectangle (corner radius 16, `purple.spatial` stroke 2px,
  `neutral.bg` fill). Inside, a smaller rectangle (the ROI,
  `purple.dim` fill, `purple.spatial` stroke). Fabric color codes
  on the ROI's edges as small colored ticks. PE coordinates labeled
  at corners (e.g., `(0,0)`, `(53,0)`, `(0,53)`, `(53,53)`) in
  `neutral.body` monospace. Caption: *"Wafer-scale, ROI-bounded."*
- **Reference bar at slide bottom:** thin horizontal strip carrying
  9 small icons (32×32, 24px gap): the three large icons above
  (small variants), TSIR semantic-function box, HostPlan vertical
  strip, bundle tarball, body-op diamond, hash badge, PE-grid mini.
- **Persistent elements defined here:** browser tab + workgroup grid,
  PE grid + fabric routes, wafer outline + ROI. All three are
  referenced by slides 03, 07-13, 17.

## What it doesn't claim

- Icons are conceptual. Real WSE3 has 900K PEs, not 64; the diagram is a
  schematic, not a topology map.
- Not a feature comparison. The deck does not assert any of the three
  surfaces is "better" — they are different execution models with
  different lowering requirements.
- Fabric-route lines on the CSL icon are illustrative; actual collectives
  (e.g., `collectives_2d` row/column broadcasts) are deferred to slide 08.

## Source artifacts to cite

- `runtime/zig/src/doe_wgsl/csl_spec.zig` — for naming conventions on
  the CSL side (memcpy, collectives_2d, fabric colors).
- `runtime/zig/src/doe_wgsl/emit_csl_layout.zig` — for the layout
  rectangle and ROI shape conventions.
- `packages/doe-gpu/STYLE.md` — for the WebGPU surface naming.
- Cerebras SDK 2.10 documentation (external) for the wafer outline
  figure; the deck's icon is original artwork, not a reproduction.
