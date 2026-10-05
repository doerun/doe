# Fullscreen Fawn benchmark pages

This unpublished application candidate aligns Particle Trails, Magnetic Fluids,
Prismatic Fluids, and Image Lab with the main CanvasContext fullscreen layout.
Fawn branding, Settings, GitHub attribution, and compact metrics share the main
page's presentation. No address field is shown. The main source page and live
hosting are unchanged.

The candidate removes duplicate particle-buffer allocation, redundant zero
uploads to WebGPU's zero-initialized buffers, duplicate render shader modules,
and temporary uniform arrays. Canvas dimensions are read on resize rather than
in the particle frame loop. The simulation shaders and default workloads are
unchanged. Pause freezes shader time and compute work while permitting reset
and resize redraws. Image Lab reuses uniform staging, coalesces input events,
and waits for GPU completion before scheduling another update; it has no idle
animation loop. Image-upload decoding cannot overwrite a newer reset.

[Results](results.json) retain physical Chrome adapter identity, source hashes,
matched fixed-frame GPU readback, exact canvas screenshot hashes, initialization
resource counts, image-mode checks, mobile layout, controls, hidden scheduling,
reduced motion, and failure handling. [Historical correctness](historical-correctness.json) also checks the existing
optimization harness against its original frozen source at matched baseline
canvas dimensions. [Workloads](workloads.json) record unchanged control defaults
and option order. [Custody](custody.json) binds the reports,
test source, and retained visual previews. These are application diagnostics on
Chrome's existing WebGPU provider; they do not qualify a forced-Doe browser
release or establish portable optimality or a measured latency speedup.

## Reproduction

Run from the Doe repository root with installed Chrome, WebGPU-capable hardware,
and Playwright available through module resolution or `FAWN_PLAYWRIGHT_MODULE`:

```sh
export FAWN_PLAYWRIGHT_MODULE="$PWD/../d4da/node_modules/playwright/index.mjs"
node browser/chromium/scripts/test-fawn-demo-pages.mjs
FAWN_CORRECTNESS_ONLY=1 node browser/chromium/scripts/test-fawn-demo-performance.mjs
node browser/chromium/scripts/test-fawn-prismatic-controls.mjs
node browser/chromium/scripts/test-fawn-start-cycle.mjs
```

`FAWN_REPORT_DIR` selects the standalone check's output directory;
`FAWN_BASELINE_REF` explicitly changes its frozen pre-alignment baseline.
Generated screenshots and reports default to `bench/out/fawn-demo-pages/`.
Readback instrumentation adds `COPY_SRC` to storage buffers on both variants.
The correctness canvas uses matched dimensions and excludes interface chrome;
ordinary layout and interaction checks use the unmodified pages.

`FAWN_CORRECTNESS_ONLY=1` skips timing and lifecycle cohorts in the existing
performance harness while preserving its strict GPU-state and pixel checks.
Its ordinary timing path remains separate from these application diagnostics.
