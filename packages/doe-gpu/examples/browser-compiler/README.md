# Doe-assisted WebGPU

An ordinary-browser particle experiment with an explicitly injected shader
adapter. The browser owns the device, shader compilation and GPU submission.
Doe's Worker owns semantic admission and a bounded WGSL source rewrite.

From the installed package directory:

```sh
npm run demo:browser-compiler
```

Open the printed localhost URL in a WebGPU browser. The packaged compiler does
not require Zig on the user's machine. HTTPS is required when hosting remotely.
Serve the example, source modules, and compiler asset together or bundle module
URLs explicitly. The asset digest is pinned by trusted application metadata;
OPFS stores verified bytes and never supplies authority.

Choose a preview mode or compare fixed work. Switching pauses, drains, captures
the application snapshot, recreates provider-owned buffers, verifies their
contents, then resumes. Reduced-motion settings pause automatic animation.

The [workload contract](contract.json) owns the seed, timestep, steps, geometry,
tolerances and capacity budget. Every fixed-work row starts from identical
particles and draws the same frame with the same shader and camera. An
independent scalar CPU implementation verifies every position and velocity;
adapter modes also compare with the baseline. Dispatches, draw count, output
shape and copied bytes remain observable.

Repeated cohorts rotate sequential mode order. Pipeline and resource creation
repeat per sample; the browser device, driver caches and compiler Worker are
shared. The browser exposes no cache-reset promise. One-time compiler delivery
and initialization are separate from warm application latency. Complete operation
includes recording, submission, completion and readback. Application latency
also includes preparation, allocation/upload and verification admission. Teardown
follows result availability. GPU compute timestamps overlap host work and are
never added to host intervals; unavailable timing stays explicit. Rounded host
intervals below clock resolution are not zero-cost claims.

The particle ceiling is a separate, capped experiment after fixed work succeeds.
It verifies every sampled result and reports the complete-operation budget.
Reaching the configured cap does not establish the hardware's maximum.
No shader-execution or native-runtime advantage follows from attractive pixels.

## Build-time use

The same compiler core emits WGSL offline for static shaders:

```sh
# From runtime/zig:
zig build emit-wgsl -Doptimize=ReleaseFast
zig-out/bin/doe-emit-wgsl source.wgsl optimized.wgsl
```

Use the output directly with browser WebGPU; a static application need not ship
the compiler. From the repository root, rebuild the bounded WASM and pinned
metadata with `npm --prefix packages/doe-gpu run build:browser-compiler`.

## Acceptance

The repository-only browser harness needs Playwright and an explicitly selected
browser. Set `DOE_PLAYWRIGHT_MODULE` to its module path when installed elsewhere:

```sh
node packages/doe-gpu/scripts/test-browser-compiler.js
```

`DOE_BROWSER`, `DOE_BROWSER_ARGS`, `DOE_BROWSER_HEADFUL`,
`DOE_BROWSER_PACKAGE_ROOT` and `DOE_BROWSER_REPORT` select the observed browser,
launch configuration, extracted package and evidence destination. The retained
Linux Vulkan configuration enables browser WebGPU explicitly; it does not prove
default-browser availability. A desktop compositor is required for the retained
rendered screenshot. See the [report](../../../../reports/browser-compiler/20261004/README.md)
for exact commands, raw outcomes and earlier failures.
