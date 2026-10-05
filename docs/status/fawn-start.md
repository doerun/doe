# Fawn hosted demonstrations

The canonical demo is [CanvasContext](https://canvascontext.com/). Doe owns the
HTML/WGSL under `browser/chromium/resources/`; the sibling D4DA repository owns
packaging and publication through `firebase.fawn.json`. Legacy D4DA Doe routes
redirect to CanvasContext with their demo filenames intact.

The landing page retains particle settings, continuous field transitions,
search, pointer and keyboard interaction, pause, reset, and reduced-motion
startup. The particle renderer uses triangle strips and draws fading trails and
particles within the same render pass. Simulation dispatches share a compute
pass while preserving their order. The prismatic solver stores scalar pressure.
All hosted demos bound pending frames, stop scheduling while hidden, and sample
completed-frame intervals separately from clamped simulation time.

[Retained application evidence](../../reports/maintenance/20261005-fawn-demo-optimization/README.md)
binds the source HTML to physical Chrome GPU state comparisons, screenshot
identity, field-transition checks, controls, lifecycle checks, and alternating
before/after observations. These are application diagnostics on the visitor's
browser WebGPU backend. They do not qualify a forced-Doe Chromium release or
establish a portable optimality claim. Tail variation remains in the raw report.

History: [the earlier start-page preview](archive/20261005-fawn-start-preview.md).
