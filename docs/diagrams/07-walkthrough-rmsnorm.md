# 07 — Walkthrough: rms_norm

## Goals

First per-kernel walkthrough. Pick the simplest kernel in the live set
so the four-pane format is readable on its own merits before more
complex kernels (gemv, kv_write, attention_decode) reuse it. Show that
one TSIR semantic function emits to multiple backends with shared body
semantics and divergent memory access.

## What it shows

Four panes side-by-side, all derived from the same TSIR fixture:

1. **WGSL source** — real `rmsnorm.wgsl` from the Doppler kernel set.
   Reduction over `hidden_size`, per-element scaling by `weight`.
2. **TSIR semantic function** — the JSON form of the rmsnorm semantic
   function: one axis (`d` ∈ `[0, hidden_size)`), three bindings
   (`input` read, `scale`/`weight` read, `output` write), reduction
   along `d`, body op `rms_norm`.
3. **CSL emission** — the actual output of `tsir.emit_csl` for this
   semantic function. Chunked sum-of-squares + sqrt + per-element
   scale + Gemma `(1 + w)` offset.
4. **PE grid mapping** — diagram showing each PE owns a chunk of the
   `hidden_size` axis. The reduction (`sum_sq`) is fabric-reduced;
   the per-element output is local.

## What it might look like

Slide split horizontally into two rows. Top row: panes 1 and 2
(WGSL + TSIR JSON), each in a code-window frame. Bottom row: panes 3
and 4 (CSL emission code + PE grid icon with axis-to-PE mapping
overlay). Reuse the four-pane layout for slides 08, 09, 10. A small
caption beneath each pane labels the artifact source.

### Visual spec (per design tokens)

- **Layout pattern:** `four-pane-walkthrough`. 2×2 grid, equal panes
  ~700×360 each, 24 px gaps.
- **Top-left pane — WGSL source:** code-window frame (`blue.preserve`
  stroke 1 px, `neutral.bg` fill, with a small title bar reading
  `rmsnorm.wgsl` in monospace 11 px). Code in monospace 13 px,
  syntax-highlighted with `blue.preserve` for keywords,
  `neutral.body` for identifiers, `neutral.line` for comments.
  Caption beneath: italic 11 px, `neutral.body`,
  *"`runtime/zig/tests/tsir/real/rmsnorm/wgsl.wgsl`"*.
- **Top-right pane — TSIR semantic function:** code-window frame
  same as left, title bar `semantic.json`. JSON shown
  pretty-printed; key tokens (`axes`, `bindings`, `reduction`,
  `op`) bold in `blue.preserve`. Caption: *"`tests/tsir/real/rmsnorm/semantic.json`"*.
- **Bottom-left pane — CSL emission:** code-window frame, title
  bar `pe_program.csl` (auto-generated). Code in monospace 13 px,
  CSL syntax with `purple.spatial` for `@fmacs`/`@fmovs` builtins,
  `neutral.body` for identifiers. Caption: *"output of
  `tsir.emit_csl.emitCslRmsNorm`"*.
- **Bottom-right pane — PE grid mapping:** PE-grid icon (8×8
  hexagons, persistent from slide 04) at center. An overlay axis
  label `d ∈ [0, hidden_size)` (`blue.preserve` arrow) running
  horizontally across the top edge of the grid, indicating the
  axis is distributed across PE columns. Each hexagon shows a
  small inner label `chunk[i]` in 9 px monospace. Below the grid,
  a fabric-reduce arc (`purple.spatial`, dashed) labeled
  `fabric reduce: sum_sq`.
- **Footer:** thin band, *"Same arithmetic across all four panes;
  different memory access."*
- **Persistent elements reused:** PE grid + fabric routes (slide 04).

## What it doesn't claim

- Numeric parity across the four panes is enforced by the emitter
  contract, not asserted on this slide. The runtime parity check is
  a separate artifact.
- The PE grid pane is conceptual; actual PE counts and chunking depend
  on layout parameters (`width`, `chunk_size`) that this kernel
  inherits from the host plan, not from the TSIR fixture.
- Doesn't claim rms_norm is novel. It claims the lowering chain is
  honest: the fixture, the emission, and the grid mapping all live in
  the repo and can be re-derived.

## Source artifacts to cite

- `runtime/zig/tests/tsir/real/rmsnorm/` — fixture directory.
- `runtime/zig/src/tsir/emit_kernel_body.zig:emitCslRmsNorm` — the
  emitter function this pane shows the output of.
- `runtime/zig/src/doe_wgsl/emit_csl_layout.zig` — for the layout side
  that consumes the emitted PE program.
- The corresponding `pe_program.csl` fragment in
  `bench/out/.../compile/<target>/` for a recently-compiled rmsnorm
  target.
