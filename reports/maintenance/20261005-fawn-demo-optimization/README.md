# Hosted Fawn application optimization

This work changes the standalone WebGPU experiments served at CanvasContext.
It preserves workload settings, resolution, simulation steps, and visual effects.
It does not change Doe's native runtime or qualify a forced-Doe browser release.

The landing shader evaluates only the active fields and the required transition.
Particle quads use triangle strips. Fade and particle draws share a trail render
pass. Ordered simulation dispatches share a compute pass. Prismatic pressure uses
scalar storage with unchanged precision. Uniform staging arrays are reused.
Submission loops bound pending frames, stop while hidden, dispose devices on
exit, and report completed-frame intervals independently of simulation-time caps.

[Application results](results.json) retain source identities, physical adapter
identity, fixed-frame simulation comparisons, screenshot hashes, controls,
visibility/reduced-motion checks, and alternating before/after completion samples.
[Particle fields](particle-fields.json) cover the scene fields, blend boundaries,
pointer forces, and dispatch indexing against the frozen deployed shader.
[Custody](custody.json) binds retained reports and test sources.

The observed application throughput improves at high landing-page particle
counts. Default scenes remain limited by display scheduling. Tail variation and
an adverse tail observation remain in the report; this is a local diagnostic,
not a portable latency guarantee. Requested buffer bytes are not measured GPU
residency. Completion intervals include browser scheduling and queue waits.

## Reproduction

Run from the Doe repository root with installed Chrome, WebGPU-capable hardware,
and Playwright available through module resolution or `FAWN_PLAYWRIGHT_MODULE`.
The sibling D4DA workspace's installed Playwright can provide that module:

```sh
export FAWN_PLAYWRIGHT_MODULE="$PWD/../d4da/node_modules/playwright/index.mjs"
node browser/chromium/scripts/test-fawn-start-cycle.mjs
node browser/chromium/scripts/test-fawn-particle-fields.mjs
node browser/chromium/scripts/test-fawn-demo-performance.mjs
```

Generated results and screenshots are written under
`bench/out/fawn-demo-optimization/`. `FAWN_REPORT_DIR` selects another output
directory; `FAWN_BASELINE_REF` selects an explicit frozen comparison commit.
The default baseline is the deployed source before this optimization.
The physical-browser checks reject GPU validation errors, changed fixed-frame
images, non-finite state, numerical mismatch, and an unbounded submission queue.

D4DA packages these same HTML files using `npm run build:fawn`. Its
`npm run test:fawn:hosting` checks rendering and migration storage preservation;
`FAWN_HOSTING_ORIGIN=<preview-origin> node tests/fawn-hosting-smoke.mjs` checks
the isolated preview before `npm run deploy:fawn`. Production HTML is compared
with the packaged source after deployment.
