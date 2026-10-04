# Doe-assisted WebGPU prototype

## Disposition

Retain the bounded compiler/adapter prototype and reject a performance promotion
for its first pass. The browser owns GPU execution. Doe supplies semantic
admission and a WGSL source rewrite shared by the native emitter and Worker
WASM. This proves a delivery and execution mechanism, without establishing
material application advantage or native-runtime replacement.

The final [timestamped cohort](timestamped.json) and
[uninstrumented confirmation](uninstrumented.json) lose on application latency.
Both remain diagnostic. GPU compute, preparation,
CPU recording/submission, completion/readback and warm application latency have
separate scopes. Cold compiler delivery/initialization is reported separately
and would add cost to first use; local transfer does not estimate Internet
delivery. Browser driver caches are shared and not reset. No interval is moved
to another boundary to manufacture improvement.

The [separate ceiling experiment](capacity.json) reaches the configured cap in
all modes. This does not establish a capacity advantage or actual hardware
maximum. Do not compare its variable work with fixed-work timings.

## Implementation and acceptance

- Compiler-owned source emission admits scalar unsigned power-of-two
  division/remainder for exact identifier/member spans. Parenthesized ambiguous
  spans, calls, indexed operands, vectors, signed values and overrides decline
  transformation. Floating-point arithmetic is unchanged. Original compiler
  diagnostics retain UTF-8 offsets; browser diagnostics name emitted WGSL.
- [Offline WGSL](particles.optimized.wgsl) runs directly through the same browser
  and matches the baseline and independent CPU oracle. The
  [timestamped](offline.json) and [uninstrumented](offline-uninstrumented.json)
  direct-shader comparisons rotate original, disabled round-trip and transformed
  text through fresh resources. No Worker request runs inside those samples.
  Identical original/disabled text has substantial timing variation. An apparent
  transformed advantage cannot yet be attributed to the rewrite; no repeatable
  shader or application benefit is established.
- The [archive identity](package.json) identifies one extracted npm package
  used by the physical browser test. The [acceptance record](acceptance.json)
  retains exact Chrome version/arguments, adapter identity, original-source
  diagnostics, pending Worker cancellation, shader edge oracles and state
  restoration. No package was published or website deployed.
- Final-archive source limits use UTF-8 bytes. Physical Worker tests admit ASCII
  immediately below and at the limit, non-ASCII at the limit, reject both forms
  above it, then successfully compile another shader. Unit instrumentation proves
  oversized requests are rejected before transmission and structured cloning.
- Every fixed-work row starts from identical seeded particles, timestep,
  geometry, precision and camera. Every position and velocity is checked against
  an independent scalar CPU reference. The separate integer fixture checks
  unsigned boundary values against ordinary arithmetic in all modes.
- Browser GPU identity remains unchanged. Switching pauses/drains, snapshots,
  recreates resources, verifies exact restored values, then resumes. Worker
  ownership is bounded by source/memory/deadline limits and idempotent close.
- OPFS cache hits reverify bytes; corruption and loss cause verified reacquisition.
  Wrong network digests fail. The package tests inject quota exhaustion, caller
  metadata mutation and buffer-allocation failure while preserving verified
  bytes, pinned identity, owned cleanup and the original failure.
- [Compiler tests](zig-tests.log), [package contracts](package-contracts.log),
  [architecture](architecture.log), [charters](catscan.json) and
  [tool surface](tool-surfaces.json) retain scoped validation. Native Vulkan
  performance, Metal, WebGL, model inference and general compatibility receive
  no credit from these tests.

The [desktop](desktop.png) and [mobile](mobile.png) captures are actual browser
renders. The ordinary installed Chrome requires explicit Linux Vulkan launch
arguments in this environment; default-browser availability is unqualified.
This does not require Fawn or a native bridge.

## Retained failures and interim cohorts

[Archive](archive/) preserves launch/admission failures, the initial missing
favicon failure, earlier passing/slower diagnostic rows and the intermediate
compiler bytes. The first Vulkan/ANGLE launch configuration crashed Chrome's GPU
process. A second configuration lacked a compatible shared-image path. The
retained final launch arguments resolve device admission; headless execution
still lacked a presented canvas, so render evidence uses the desktop compositor.

The earlier initialization changed from a uniform disc to a seeded spiral
before final qualification. Those snapshots are not cross-comparable. One
intermediate run overlapped compiler checks and is explicitly unqualified for
performance interpretation. The installed-archive cohort ran after build/test
completion; unfavorable results remain retained. The final byte-boundary archive
replaces earlier source-guard archives for acceptance; their records remain in
the archive with stage prefixes.

## Reproduce

```sh
ZIG=/path/to/zig node packages/doe-gpu/scripts/build-browser-compiler.js
cd runtime/zig
zig build test-browser-wgsl test-wgsl -Doptimize=ReleaseFast --summary all
```

From the repository root, run package contracts, then pack/extract into an
owned scratch directory. Select the extracted directory explicitly:

```sh
node packages/doe-gpu/test/run-contracts.js
DOE_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
DOE_BROWSER=/usr/bin/google-chrome DOE_BROWSER_HEADFUL=1 \
DOE_BROWSER_PACKAGE_ROOT=/path/to/extracted/package \
DOE_BROWSER_REPORT=/path/to/evidence \
node packages/doe-gpu/scripts/test-browser-compiler.js
```

The desktop environment supplies its display authorization; do not copy another
machine's authorization path. The acceptance record owns exact launch arguments.
Use [the example](../../../packages/doe-gpu/examples/browser-compiler/README.md)
for ordinary local serving and build-time WGSL use. The [manifest](manifest.json)
binds source and retained artifacts. [Package identity](package.json) records the
archive digest; the archive itself remains a reproducible scratch build.

## Next bounded work

Select a profitable general WGSL transformation from recoverable cost in an
independent application, prove emitted WGSL offline, then re-evaluate runtime
delivery. The current pass is a mechanism fixture and has no established
acceleration value. Do not make Worker packaging, Zig or shader minification a
novelty or superiority claim.

Component: compiler WGSL, public package adapter and application evidence.
Intent: changed by adding compiler-owned WGSL output and explicit browser shader
adaptation. Acceptance evidence: linked above. Boundary effects: the browser
retains device, native compilation, submission and policy ownership.
