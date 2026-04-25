# 14 — Why ONNX-shaped pipelines hit a wall

## Goals

Make the comparison explicit. Show side-by-side that operator-graph
IRs need per-op codegen for every backend, while TSIR's emitter shape
factors that surface into one emitter per backend. The "wall" for
spatial compute is concrete: there is no Cerebras backend emitter for
ONNX that you can drop in and have working kernels.

## What it shows

Two side-by-side stacks at the same scale:

- **Left (ONNX-shaped):** model graph → ONNX protobuf → backend
  runtime → per-backend kernel codegen for every op. Each backend
  box has N kernel sub-boxes (one per op). Multiplier badge:
  "N ops × M backends = N×M codegen surface."
- **Right (TSIR):** model graph → TSIR semantic functions → per-
  backend emitter (1 emitter handling all body ops) → backend output.
  Each backend box has 1 emitter, not N kernels. Multiplier badge:
  "M emitters."

Caption: "The codegen surface is a structural property of the IR, not
a tooling choice. Operator graphs grow surface area combinatorially;
TSIR's surface is per-backend, not per-op-per-backend."

## What it might look like

Two columns of equal width with matching horizontal bands so the
contrast is at the same vertical positions. Both columns use the
operator-graph stack icon from slide 02 at the top, then diverge
below. Multiplier badges sit at the bottom of each column. Reuse the
operator-graph black-box icon for the ONNX side and the TSIR 4-slot
box for the right side.

### Visual spec (per design tokens)

- **Layout pattern:** `side-by-side-stacks`. Identical structure to
  slide 02 but expanded with explicit codegen surface visualization.
- **Left column — ONNX-shaped stack:**
  - Top: model-graph icon (small, `red.opaque` outline, with 5-6
    op-nodes connected by edges).
  - Middle: ONNX protobuf icon (rectangle with `.onnx` filename,
    `red.opaque` stroke).
  - Lower-middle: backend-runtime box (`red.opaque` stroke).
  - Bottom: **fork into N kernel sub-boxes** (e.g., 6 small rectangles
    in a row, all `red.dim` filled) — one per op. This is the visual
    "wall" that the slide title references.
  - Multiplier badge below: `red.opaque` rounded pill, label
    *"N ops × M backends"*.
- **Right column — TSIR stack:**
  - Top: model-graph icon (same shape as left, but `blue.preserve`
    outline) — same model, different IR target.
  - Middle: TSIR semantic-function row (4-slot box, `blue.preserve`)
    repeated for each op (3-4 visible boxes stacked vertically with
    16 px gap). Each box has the same 4-slot shape, different body
    op tags inside the diamonds.
  - Lower-middle: per-backend emitter box (`blue.preserve` stroke,
    1 box not N) labeled *"emitter (consumes any semantic
    function)"*.
  - Bottom: backend output (`purple.spatial` stroke, single box).
  - Multiplier badge below: `blue.preserve` rounded pill, label
    *"M emitters"*.
- **Caption strip below both columns:** italic, `neutral.body`,
  *"The codegen surface is a structural property of the IR, not a
  tooling choice."*
- **Persistent elements reused:** TSIR 4-slot semantic-function box
  (slide 05), reused N times in the right column. Operator-graph
  black-box icon from slide 02 reused in the left column.

## What it doesn't claim

- Not asserting ONNX runtimes are bad or unmaintained. ONNX is widely
  used and works well on its target SIMD/SIMT hardware.
- Not asserting Doe is unique in factoring codegen. Halide, Triton,
  TVM with TIR, and others factor differently. The narrow claim is
  that *for spatial compute*, exposed-axis IRs compose where opaque-
  body IRs require per-op work.
- The N×M counting is illustrative. Real codegen surfaces are sized
  by op-family count and backend count; the slide is making the
  shape argument, not a measured count claim.

## Source artifacts to cite

- `runtime/zig/src/tsir/emit_kernel_body.zig` — the single emitter per
  backend that backs the right-column claim.
- `runtime/zig/src/doe_wgsl/emit_csl_*.zig` — the CSL emitter family
  showing the per-pattern dispatch within one backend.
- External: ONNX Runtime backend kernel directories (cited as
  comparison shape, not reproduced in the deck).
