# 02 — The problem: "Spatial compute needs exposed axes"

## Goals

Frame the structural gap that the rest of the deck answers. SIMD/SIMT
backends tolerate opaque kernel bodies because parallelism lives inside
each op. Spatial compute (Cerebras WSE) cannot — PE grid assignment
requires exposing the iteration axes the kernel runs over.

## What it shows

- Two side-by-side stacks at the same vertical scale.
- Left stack: an operator-graph IR (ONNX-shaped) with each op drawn as
  an opaque black box. Backends hang off the bottom; each backend has
  its own kernel codegen.
- Right stack: a TSIR semantic function with axes, binding roles,
  reduction structure, and body op visibly labeled. Backends share a
  single emitter.
- Caption: "Operator graphs preserve signatures. TSIR preserves bodies.
  Spatial compute needs the latter."

## What it might look like

Two columns of equal width. Each column is a vertical stack of three
boxes (author → IR → execution). On the left column the middle box
("op") is a solid filled rectangle with no internal labels. On the
right column the middle box is divided into four slots labeled `axes`,
`bindings`, `reduction`, `body op`. Below each column is a fork into
two backend boxes; on the left the fork carries a multiplier badge
("× N ops"), on the right it carries a single-emitter badge.

### Visual spec (per design tokens)

- **Layout pattern:** `side-by-side-stacks`. Two equal-width columns
  with matched horizontal bands so the IR row sits at the same y on
  both sides.
- **Left column ("operator graph"):** all elements `red.opaque`. Author
  box (top) → IR box (middle, solid filled, no slots) → execution
  fork (bottom, two `red.dim` backend boxes). Multiplier badge:
  `red.opaque` rounded-rectangle pill, label "× N ops × M backends".
- **Right column ("TSIR"):** all elements `blue.preserve`. Author box
  → 4-slot TSIR semantic-function box (slots labeled `axes`,
  `bindings`, `reduction`, `body op`, separated by `neutral.line`)
  → execution fork (two `blue.dim` backend boxes). Single-emitter
  badge: `blue.preserve` pill, label "× M emitters".
- **Caption strip below:** sans-serif 500, `neutral.body`, ~28 px:
  *"Operator graphs preserve signatures. TSIR preserves bodies.
  Spatial compute needs the latter."*
- **Persistent elements reused:** TSIR semantic-function box from
  slide 05, at medium-block size.

## What it doesn't claim

- This is not a claim that ONNX is unusable. ONNX-shaped pipelines work
  fine on SIMD/SIMT. The claim is narrower: they don't compose with
  spatial compute without per-op codegen.
- This is not a claim that TSIR is the only IR with this property.
  Halide, Triton, and others expose axes. The claim is that TSIR's
  axis system is what Doe's CSL emitter consumes.
- No quantitative codegen-surface claim. The "× N ops" badge is
  illustrative, not measured.

## Source artifacts to cite

- `runtime/zig/src/tsir/schema.zig` — where TSIR's axes / bindings /
  body-op fields are defined.
- `runtime/zig/src/tsir/emit_kernel_body.zig` — the single emitter
  shared across CSL, MSL, DXIL, SPIR-V, WebGPU.
- `docs/cerebras-evidence-bundle.md` claim #11 (CSL WebGPU emulator
  vs simfabric speed) — backs the "one source, multiple correct
  executions" framing without leaking into a perf claim.
