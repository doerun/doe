# 10 — Walkthrough: attention_decode — "Multi-axis reduction"

## Goals

Fourth per-kernel walkthrough. Pick the kernel whose multi-axis
reduction structure most demands the planning surface TSIR provides.
Demonstrates that compositions of axes and reductions still map
cleanly to PE grid coordinates.

## What it shows

Four panes from the attention_decode kernel:

1. **WGSL source** — `attention_decode.wgsl`, computing per-head
   attention output for one decode step against the cached keys/values.
2. **TSIR semantic function** — multi-axis structure: `h` ∈
   `[0, num_heads)`, `kv_chunk` ∈ `[0, kv_len)`, `d` ∈
   `[0, head_dim)`. Bindings include `key_cache`, `value_cache`
   (read), the current `query` (read), and `output` (write).
   Reduction over `kv_chunk` produces per-head scaled-softmax output.
3. **CSL emission** — fabric-reduce along the kv axis, per-head
   parallelism along PE columns. Sliding-window vs global-window
   variants annotated.
4. **PE grid mapping** — `head` axis → PE columns, `kv_chunk` axis →
   PE rows, `head_dim` axis → per-PE local memory. Fabric reduce
   along PE rows. Sliding window narrows the active kv range.

## What it might look like

Same four-pane layout as slides 07-09. The PE-grid pane is the most
visually rich here: a 2-D grid annotated with three different axis
mappings (column = head, row = kv_chunk, in-cell = head_dim), with
dashed boundary lines showing the sliding-window mask. A small inset
shows the global vs sliding variants as toggle states.

### Visual spec (per design tokens)

- **Layout pattern:** `four-pane-walkthrough`, identical structure to
  slides 07-09.
- **Panes 1-3 (WGSL / TSIR / CSL):** code-window styling per slide
  07; content sourced from
  `runtime/zig/tests/tsir/real/attention_head256_f16kv/`.
- **Bottom-right pane — PE grid mapping:**
  - PE-grid icon (8×8 hexagons) center.
  - Top edge: `head ∈ [0, num_heads)` with `blue.preserve` arrow
    pointing right (head per PE column).
  - Left edge: `kv_chunk ∈ [0, kv_len)` with `blue.preserve` arrow
    pointing down (kv_chunk per PE row).
  - Each hexagon shows a small `head_dim` axis annotation (lives
    in PE-local memory).
  - `purple.spatial` dashed arrows along each PE column labeled
    `fabric reduce: scaled-softmax`.
  - **Sliding-window mask:** a `red.dim` dashed boundary
    rectangle around the active kv range, indicating which kv
    positions are visible to each query. Inactive positions
    visually de-emphasized (lower opacity).
  - **Variant toggle inset (top-right corner, 200×80):** small
    rounded-rectangle pill labeled `sliding ↔ global`. Two states
    shown side-by-side in miniature; only one active at a time.
- **Footer:** *"Multi-axis composition maps cleanly to PE grid
  coordinates."*
- **Persistent elements reused:** PE grid (slide 04).

## What it doesn't claim

- attention_decode runs inside the truncated 31B simfabric receipt
  (1-layer, 8 decode steps). Full-depth simfabric is not the proof
  target — that's slide 13's hardware leg, gated on R2-10.
- The PE-grid mapping shown is the live emitter's current choice.
  Alternative axis-to-PE assignments are valid TSIR lowerings; the
  deck does not claim this one is optimal, only that it is honest.

## Source artifacts to cite

- `runtime/zig/tests/tsir/real/attention_head256_f16kv/` — real fixture
  for the local-window head-dim-256 variant (sliding-window mask).
- `runtime/zig/tests/tsir/real/attention_head512_f16kv/` — real fixture
  for the global-window head-dim-512 variant (no mask).
- `runtime/zig/src/doe_wgsl/emit_csl_attention.zig` — the live
  emitter for the attention family.
- `docs/cerebras-evidence-bundle.md` claim #8 — for the
  manifest-shape attention-core diagnostic this slide references.
- `feedback_spirv_binary_operand_scope.md` (auto-memory) and
  `docs/status/compiler-and-webgpu.md:254-293` — for the open mat-
  mixed-shape SPIR-V gap that affects this kernel on E2B.
