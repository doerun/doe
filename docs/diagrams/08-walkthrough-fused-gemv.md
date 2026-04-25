# 08 — Walkthrough: fused_gemv

## Goals

Second per-kernel walkthrough. Same four-pane layout as slide 07, but
with a kernel whose multi-axis structure makes the PE-grid mapping
non-trivial. Establishes that axis-to-PE assignment is the planning
move spatial compute requires.

## What it shows

Four panes derived from the fused_gemv TSIR fixture:

1. **WGSL source** — `fused_gemv.wgsl`, the matrix-vector multiply
   with output scaling.
2. **TSIR semantic function** — two axes (`row` ∈ `[0, M)`, `col` ∈
   `[0, K)`), three bindings (matrix `A` read, vector `x` read,
   output `y` write), reduction along `col`, body op `fused_gemv`.
3. **CSL emission** — actual `tsir.emit_csl` output. Per-PE local
   GEMM via DSD + collectives along the row axis for fabric reduce.
4. **PE grid mapping** — `row` axis maps to PE rows, `col` axis
   distributed across PE columns. Fabric reduce drawn as horizontal
   arrows along the PE grid.

## What it might look like

Same four-pane layout as slide 07. The PE grid pane this time carries
an annotation: "row axis → PE row coordinate; col axis → PE column
coordinate; reduction → fabric collective along col." A small inset in
the corner of the grid pane shows the same kernel's GPU lowering as
contrast: a single dispatch, no fabric, threads cover the iteration
space.

### Visual spec (per design tokens)

- **Layout pattern:** `four-pane-walkthrough`, identical structure to
  slide 07.
- **Panes 1-3 (WGSL / TSIR / CSL):** same code-window styling as
  slide 07; content sourced from
  `runtime/zig/tests/tsir/real/fused_gemv/`.
- **Bottom-right pane — PE grid mapping:**
  - PE-grid icon (8×8 hexagons) center.
  - Top edge labeled `row ∈ [0, M)` with a `blue.preserve` arrow
    pointing right — row axis maps to PE row index.
  - Left edge labeled `col ∈ [0, K)` with a `blue.preserve` arrow
    pointing down — col axis maps to PE column index.
  - Horizontal `purple.spatial` dashed arrows across each row
    labeled `fabric reduce: sum`, indicating the per-row collective.
  - **GPU contrast inset (top-right corner, 160×100):** browser-tab
    + workgroup-grid icon (small) labeled *"GPU lowering: single
    dispatch, no fabric"*. Inset has 1 px `neutral.line` border to
    visually separate from the CSL grid. Inset is `blue.preserve`
    while the main grid is `purple.spatial` — the color contrast
    reinforces the lowering-target distinction.
- **Footer:** *"Two axes, two PE coordinates, one fabric reduce
  per output row."*
- **Persistent elements reused:** PE grid (slide 04), browser-tab +
  workgroup grid (slide 04, used at small-icon size for the GPU
  contrast inset).

## What it doesn't claim

- Not a SUMMA-tiling demonstration. fused_gemv is the simpler GEMV;
  the SUMMA tiled matmul is a separate kernel (`tiled` in the host
  plan) with its own scaling-pathology story (R2-1 in north-star).
- The "GPU contrast inset" is illustrative; the deck does not measure
  GPU vs CSL performance for this kernel.
- The mapping shown is the live wrapper's choice. TSIR-only callers
  could pick a different PE assignment; this pane shows what the live
  emitter currently does.

## Source artifacts to cite

- `runtime/zig/tests/tsir/real/fused_gemv/` — fixture directory.
- `runtime/zig/src/tsir/emit_kernel_body.zig:emitCslFusedGemv` — the
  emitter producing the CSL pane.
- `runtime/zig/src/doe_wgsl/emit_csl_matmul.zig` — for context on the
  SUMMA path the GEMV does *not* take (kept separate from this slide
  to avoid scope creep).
