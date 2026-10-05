# Fawn hosted demonstrations

The canonical demo is [CanvasContext](https://canvascontext.com/). Doe owns the
HTML/WGSL under `browser/chromium/resources/`; the sibling D4DA repository owns
packaging and publication through `firebase.fawn.json`. Legacy D4DA Doe routes
redirect to CanvasContext with their demo filenames intact.
The [live release manifest](https://canvascontext.com/release.json) identifies
the published demo source and hosting package.

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

The hosted main page and benchmark pages have a compact Demos disclosure.
It marks the current page and switches between the particle
cycle, Particle Trails, Magnetic Fluids, and Prismatic Fluids. Image Lab is
excluded from the menu and retained as a repository-only benchmark. The
main page continues cycling its own particle fields; choosing another simulator
navigates to that separate implementation. Escape restores focus and outside
interaction closes the disclosure.

The benchmark pages align Particle Trails, Magnetic
Fluids, Prismatic Fluids, and Image Lab with the main page's fullscreen canvas,
Fawn branding, Settings panel, GitHub link, and compact footer. It has no address
field. The packaged simulators are published on CanvasContext; Image Lab remains
repository-only. Simulation
shaders, default workloads, and image-processing resolution remain unchanged.
Pause freezes simulation and shader time; reset and resize can redraw while
paused. Image Lab renders on demand and reports completed-update latency.

[Alignment application evidence](../../reports/maintenance/20261005-fawn-demo-pages/README.md)
binds the preceding alignment source to matched GPU state and pixels, allocation/upload counts,
desktop/mobile controls, pause/reset/resize, image upload recovery, and device
lifecycle checks. [The standalone-page check](../../browser/chromium/scripts/test-fawn-demo-pages.mjs)
runs with `FAWN_PLAYWRIGHT_MODULE` pointing to an installed Playwright ESM module;
artifacts go under `bench/out/fawn-demo-pages/` by default. The
[prismatic-specific UI check](../../browser/chromium/scripts/test-fawn-prismatic-controls.mjs)
remains available for narrower validation.

[Switcher and clock evidence](../../reports/maintenance/20261005-fawn-demo-switcher/README.md)
binds the switcher-introduction source to navigation, desktop/mobile layout, keyboard dismissal,
and a real particle cycle. RAF timestamps earlier than initialization now produce
zero elapsed time instead of negative simulation steps or a negative field phase.
These demos have no established Doe-versus-Dawn application speed comparison;
local diagnostics use Chrome's existing WebGPU provider. The current menu is
checked by the switcher script and references the existing packaged simulators.

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
