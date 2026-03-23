# Browser lane

This document covers the **Chromium integration lane** (Track A): embedding the
Doe Zig runtime inside Chromium to replace Dawn at `navigator.gpu`.

This is **not** the browser wrapper in `packages/webgpu/src/browser.js`. That
wrapper is a JS shim inside the `@simulatte/webgpu` package that delegates to
the browser's own WebGPU implementation. It exists today and runs no Doe code.
See `packages/webgpu/architecture.md` and the root `README.md` stack diagram
for the wrapper's role.

```text
┌──────────────────────────────────────────────────────────────┐
│ packages/webgpu/src/browser.js   (exists today)             │
│ JS shim → browser's own navigator.gpu → browser drives GPU  │
│ No Doe runtime code runs. Wrapper for API compatibility.    │
├──────────────────────────────────────────────────────────────┤
│ browser/chromium/            (this document — future)   │
│ Embed Doe Zig runtime inside Chromium to replace Dawn       │
│ at the navigator.gpu seam. Plans/contracts only today.      │
└──────────────────────────────────────────────────────────────┘
```

## Chromium integration layers

The browser family is split into two layers:

- `browser/chromium`
  - docs, contracts, scripts, and diagnostics for Chromium integration
- `browser/chromium_webgpu_lane`
  - the actual Chromium checkout/build workspace when stored in-tree

Keep those layers distinct:

- `chromium` is the control and evidence layer
- `chromium_webgpu_lane` is the heavyweight build workspace

Browser smoke and browser benchmark projection remain separate benchmark
contracts even when they share scripts or projection manifests.

## Track B (modules) — archived

Track B proposed optional Chromium-internal GPU modules (SDF renderer, path
engine, effects pipeline, compute services, resource scheduler). It was
archived 2026-03-19: the infrastructure dominance strategy determined that
building parallel browser subsystem replacements duplicates work that arrives
for free once Track A ships. See `browser/chromium/README.md` and
`docs/status.md` for the full rationale.
