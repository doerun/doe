# 03 — The stack at a glance: "Doppler → Doe → CSL"

## Goals

Show the macro architecture before any per-component detail. Establish
what each box does, what flows between them, and what is preserved at
each boundary.

## What it shows

- Three vertical columns left-to-right:
  1. **Doppler** — JS orchestration + WGSL kernels, running in a
     browser context.
  2. **Doe** — TSIR semantic functions + per-backend emitters +
     HostPlan generator.
  3. **CSL execution** — PE grid layout + per-PE program + runtime
     executor + receipt.
- Two cross-column arrows, each annotated with what is preserved:
  - JS → HostPlan: **identity preserved** (manifest sha + graph sha +
    compile-target hashes).
  - WGSL → TSIR → CSL: **body preserved** (axes + binding roles +
    reduction + body op tag).

## What it might look like

Three columns, each a vertical stack of two-to-three boxes labeled by
component. Arrows between columns are thick and labeled with the
preservation property (italic text, not the column components). A thin
horizontal label band below the diagram reads "browser-runnable →
backend-agnostic IR → spatial-compute target." No icon legend; that's
slide 04.

### Visual spec (per design tokens)

- **Layout pattern:** `three-columns-flow`.
- **Left column ("Doppler"):** `blue.preserve` boxes — top: "JS model
  program" (medium-block), bottom: "WGSL kernels" (medium-block).
- **Middle column ("Doe"):** `blue.preserve` boxes — top: "TSIR
  semantic functions" (medium-block, reuse 4-slot icon from slide
  05), middle: "per-backend emitters" (medium-block), bottom:
  "HostPlan generator" (medium-block, reuse vertical-strip icon
  from slide 06 at medium scale).
- **Right column ("CSL execution"):** `purple.spatial` boxes — top:
  "PE grid layout" (medium-block, reuse PE-grid icon from slide
  04), middle: "per-PE program" (medium-block), bottom: "runtime
  executor + receipt" (medium-block).
- **Cross-column arrows:** thick (4-6 px) bands. Left → middle band
  is `blue.preserve`, label *"identity preserved (manifest sha +
  graph sha + compile-target hashes)"*. Middle → right band is
  `blue.preserve` fading into `purple.spatial`, label *"body
  preserved (axes + binding roles + reduction + body op tag)"*.
- **Footer label band:** sans-serif 500, `neutral.body`,
  *"browser-runnable → backend-agnostic IR → spatial-compute
  target"*.
- **Persistent elements reused:** TSIR semantic-function box (05),
  HostPlan vertical strip (06), PE grid (04).

## What it doesn't claim

- The diagram is not a build-system flow chart. Compile-time vs
  runtime distinctions are deferred to slides 11–12.
- Not a performance pipeline. Latency / throughput annotations are
  out of scope.
- Not implying every backend is equally mature. The deck keeps
  claim-discipline by deferring evidence to slide 16.

## Source artifacts to cite

- `runtime/zig/src/doe_wgsl/emit_csl_*.zig` — the CSL emitter family.
- `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py` —
  the runtime executor that walks the HostPlan.
- `docs/architecture.md` — the parent architecture doc this slide
  visualizes one layer of.
- `docs/cerebras-north-star.md` NS-0 — the proof-chain framing whose
  "portability via TSIR" rung this slide depicts.
