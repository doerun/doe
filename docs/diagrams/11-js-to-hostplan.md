# 11 — JS orchestration → HostPlan

## Goals

Pivot from per-kernel mechanics to macro orchestration. Show that
declarative JS model programs lower statically into a HostPlan,
contrasted with PyTorch-style traced graphs that depend on eager
execution and don't carry stable identity.

## What it shows

- Left pane: a Doppler model program in JS, declarative form. A short
  excerpt showing the model's call sequence: embed → layer-block ×N →
  lm_head → sample. Pure declarative; no imperative tensors.
- Right pane: the HostPlan's launch list, mirroring the JS structure
  but expanded into the per-kernel sequence (rmsnorm, rope, gemv, …).
  Reuses the HostPlan icon from slide 06.
- Connecting label: "Static lowering — no eager execution, no
  Python-runtime dependency, no graph capture step."
- Footer comparison row: PyTorch (traced graph, eager-dependent),
  ONNX (signature graph, body opaque), Doppler (declarative model
  program, body-and-identity preserving).

## What it might look like

Two-column slide. Left column: code window with ~15 lines of the
Doppler model program. Right column: vertical list of launches (the
HostPlan icon). Arrow between columns labeled "static lowering."
Footer comparison row is a thin horizontal table at the bottom with
three columns (one per framework) and a single row checking
identity-preservation property.

### Visual spec (per design tokens)

- **Layout pattern:** `two-pane-with-arrow`.
- **Left pane (large-block, ~640×500):** code-window frame
  (`blue.preserve` stroke, title bar `model.js`). ~15 lines of
  Doppler model program in monospace 13 px, syntax-highlighted.
  Caption beneath: *"Declarative model program — no eager tensors."*
- **Center arrow:** thick (6 px) `blue.preserve` band labeled in
  italic *"static lowering — no eager execution, no Python-runtime
  dependency, no graph capture step"*. Arrow head points right.
- **Right pane (large-block, ~640×500):** HostPlan vertical strip
  (reuse from slide 06), 8 visible launches with bind-by-symbol
  arrows. Strip aligned to the same vertical center as the code
  window.
- **Footer comparison row:** thin horizontal table, 3 equal columns,
  no border. Single row labeled "identity-preserving":
  - PyTorch (eager-traced) — `red.opaque` ✗
  - ONNX (signature graph) — `red.opaque` ✗
  - Doppler (declarative) — `blue.preserve` ✓
  Each column has the framework name in sans-serif 600 above the
  check/cross. Cross/check are simple geometric (not emoji).
- **Persistent elements reused:** HostPlan vertical strip (slide 06).

## What it doesn't claim

- Not asserting JS is intrinsically better than Python for ML.
  The claim is that *declarative-with-static-lowering* is the property
  that gives content-addressable identity, regardless of host language.
- Not asserting Doppler covers every model PyTorch covers. The claim
  is structural (the orchestration model is amenable to static
  lowering), not feature-coverage.
- The JS code excerpt is illustrative; the deck does not propose this
  is the only way to write a Doppler model program.

## Source artifacts to cite

- `/home/x/deco/doppler/` — for actual Doppler model program shape
  and runtime inference path (referenced by directory; deck doesn't
  inline Doppler internals).
- `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/host-plan.json`
  — the real HostPlan the right pane should be rendered from.
- `docs/cerebras-evidence-bundle.md` claim #1 — the L1 layer-block
  parity claim that backs the lowering chain at the smallest scale.
