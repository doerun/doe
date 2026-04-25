# 12 — HostPlan → per-PE programs

## Goals

Show what the runtime executor actually does with a HostPlan. Each
launch becomes a per-PE program invocation with explicit h2d/d2h
plumbing. This is where the declarative orchestration meets the
imperative execution surface.

## What it shows

- A HostPlan vertical strip on the left (reusing the slide-06 icon).
- For one selected launch, a horizontal expansion to the right showing:
  - h2d: input buffers being staged from host to PE memory.
  - dispatch: the per-PE program running on the PE grid.
  - d2h: output buffers captured back to host.
  - bind-by-symbol: the output-symbol → next-launch-input plumbing
    via the runtime's `buffer_files[symbol] -> Path` dict.
- A small annotation showing where checkpoints are persisted (after
  each `hostplan_launch_complete status=succeeded` event), tying back
  to the R2-5a checkpoint/resume mechanism.

## What it might look like

Top half: HostPlan strip on the left, expansion arrow pointing right
to a horizontal flow diagram of (h2d → dispatch → d2h → next-launch
input). Bottom half: a small annotation showing the
`buffer_files[symbol] = Path(...)` dict updating after the d2h step
and how a checkpoint write captures that state. Reuse the PE grid icon
from slide 04 inside the dispatch box.

### Visual spec (per design tokens)

- **Layout pattern:** `expansion-flow`.
- **Top half:**
  - **Left:** HostPlan vertical strip (reuse from slide 06), 240 px
    wide. One launch box (e.g., `tiled` at index 2) highlighted with
    a `purple.spatial` outline 3 px to indicate it's the one being
    expanded.
  - **Expansion arrow:** thick (6 px) `purple.spatial` arrow from
    the highlighted launch box pointing right.
  - **Horizontal flow on the right:** four boxes in sequence with
    24 px gaps between, each medium-block:
    1. **h2d box:** `blue.preserve` stroke, label *"h2d"* (sans-serif
       600), small staging-buffer icon inside (rectangle with arrow
       in).
    2. **dispatch box:** `purple.spatial` stroke, label *"dispatch"*,
       PE-grid icon inside (small variant from slide 04).
    3. **d2h box:** `blue.preserve` stroke, label *"d2h"*, small
       output-buffer icon (rectangle with arrow out).
    4. **next-launch input box:** `blue.preserve` stroke, label
       *"buffer_files[symbol] → next launch"*. Small dict/kv icon.
- **Bottom half — checkpoint annotation:**
  - A small `accent.gold` rounded-rectangle box labeled *"checkpoint
    persisted: launches/0002_tiled/buffers/c.bin"*. Connected by a
    thin `accent.gold` dashed line from the d2h box above to the
    checkpoint box below — depicting that checkpoints are written
    after the d2h step on success.
  - Caption beneath: italic 12 px, `neutral.body`, *"R2-5a
    checkpoint/resume v1: per-launch persistence, atomic manifest
    write, identity-validated resume."*
- **Persistent elements reused:** HostPlan vertical strip (slide 06),
  PE-grid icon (slide 04), identity hash badge styling (slide 06)
  reused for the checkpoint box's `accent.gold` color.

## What it doesn't claim

- Doesn't claim the per-launch executor is performance-optimized. It
  is the diagnostic-and-evidence runner today; performance lanes
  (R4-1 in north-star) are separate work.
- Doesn't claim every launch in the HostPlan is wallclock-tractable
  on simfabric. Production-grid `tiled` launches at P=54 hit
  superlinear scaling (R2-1) — the smoke-shape variants the deck's
  example shows are the runnable ones.
- The checkpoint annotation refers to the v1 implementation
  (prefill-only, identity-validated). Decode-loop checkpoints are
  v2 scope.

## Source artifacts to cite

- `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`
  — `execute_hostplan_runtime` is the function this slide diagrams.
- `bench/runners/csl-runners/int4ple_checkpoint.py` — the
  checkpoint persistence module the annotation references.
- `bench/runners/csl-runners/int4ple_launch_step_adapter.py` —
  the per-launch SdkRuntime invocation called via `cs_python` inside
  the dispatch step.
