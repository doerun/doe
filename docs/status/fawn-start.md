# Fawn hosted demonstrations

The canonical demo is [CanvasContext](https://canvascontext.com/). Doe owns the
HTML/WGSL under `browser/chromium/resources/`; the sibling D4DA repository owns
packaging and publication through `firebase.fawn.json`. Legacy D4DA Doe routes
redirect to CanvasContext with their demo filenames intact.

The hosted main page previews the local HTML start page selected by Fawn's
launcher. Packaging copies that source into the app bundle; an existing
installation can retain an older copy. The preview visibly links to Fawn's
Chromium integration on GitHub and identifies the visitor's browser WebGPU
backend in Settings. The preview has no search/address field.

The main page is the public demo entry point. Settings and the README no longer
send visitors to standalone demos. Particle Trails, Magnetic Fluids, Prismatic
Fluids, and Image Lab remain in `browser/chromium/resources/` for benchmarks and
diagnostics. Existing hosted fixture URLs remain available; Image Lab remains
repository-only. Lifecycle probes navigate directly to the fluid fixture rather
than requiring a public navigation link.

The prismatic fluid page shares the landing page's fullscreen canvas, Fawn
branding, typography, Settings panel, and compact metrics. Pause freezes
simulation and shader time; reset and resize can redraw while paused. Reduced
motion starts paused. The fluid shaders and default workload remain unchanged.
[The prismatic UI check](../../browser/chromium/scripts/test-fawn-prismatic-controls.mjs)
exercises desktop/mobile layout, controls, GPU submission suspension, search,
and unsupported-WebGPU errors. Run it with `FAWN_PLAYWRIGHT_MODULE` pointing to
an installed Playwright ESM module; artifacts go under
`bench/out/fawn-prismatic-ui/` by default.

The landing page retains particle settings, continuous field transitions,
pointer and keyboard interaction, pause, reset, and reduced-motion
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
