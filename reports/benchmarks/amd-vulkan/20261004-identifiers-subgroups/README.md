# WGSL identifier admission and Vulkan subgroup normalization

This checkpoint repairs declaration admission and rejects a subgroup-width
performance hypothesis. Vulkan remains the active backend. The accepted
submission implementation and private-zero repair are preserved; rejected loop
hoisting is not restored. No generated-execution or whole-application advantage
is established. [evidence.json](evidence.json) binds source, commands, providers,
workloads and the retained observations. [artifact-index.json](artifact-index.json)
binds the adjacent evidence bytes.

Final source gates: [final-validation.json](final-validation.json).

## Compiler repair

The predecessor emits SPIR-V for `let alias = 1u`. Its declaration parsers advance
over names without checking eligibility. The first incorrect boundary is syntax
admission, before semantic analysis or target emission. WGSL's
[identifier rules](https://www.w3.org/TR/2026/CRD-WGSL-20260921/#identifiers)
distinguish keywords and reserved words from legal contextual names.

The token owner now supplies lexical eligibility, including the pinned reserved
spelling set. One parser helper checks eligibility, records the original token
span and advances only on success. Structs, members, functions, parameters,
globals, overrides, constants, aliases and local declarations share it. AST name
indices, allocation ownership and the existing parser error category are intact.
No target emitter, sampler, backend policy or public descriptor changes.

Focused checks cover every language keyword across declaration forms, selected
reserved names, punctuation, forbidden underscores, contextual/type spellings,
exact spans, owned diagnostics and failure during partial AST allocation. The
physical package regression rejects invalid names and executes valid aliases,
contextual members, pointer mutation, branches, modular arithmetic, uniform
updates, computation and rendering against independent expected values.
Doe and pinned Dawn pass the same checks. Previously invalid pointer, atomic
and barrier fixtures now use legal names; their semantic assertions remain.
Original failing suite and compiler observations are retained alongside passing
[combined suites](combined-final.log.gz) and the subsequent
[complete WGSL suite](wgsl-final.log.gz).

## Normalize before optimizing

Fresh final-program captures identify width 32 for Doe and width 64 for Dawn.
Requiring width 64 through the existing diagnostic override makes Doe's reported
VGPR allocation match Dawn's. Both have zero spills and scratch. Driver counts
are per selected program/width; the earlier difference does not establish excess
live values in Doe lowering. [driver-statistics.json](driver-statistics.json)
and compressed captures preserve both widths and the incumbent.

The unchanged UMAP application, numerical oracle, geometry, upload, completion
and readback are preserved. Pass timestamp probes reuse the existing bounded
wrapper; ordinary cohorts run without it or driver capture. The original
exploratory series overlapped a compiler-tool build and is retained separately.
The confirmation series runs after builds; no exploratory timings authorize a
production change. [gpu-widths.json](gpu-widths.json) retains every measured
operation and [application-comparison.json](application-comparison.json) retains
all ordinary cohorts, process latency and process-tree memory.

Width 64 does not meet the predeclared shader-gain requirement or establish a
repeatable complete-operation gain. **Reject changing the production width from
this evidence.** Compiler translation time and backing allocations are measured
separately in [compiler-costs.json](compiler-costs.json); static driver estimates
are not GPU durations. The apply-forces compiler samples are slower after the admission repair; the SGD
pair varies. Allocation counts and emitted bytes match. These compiler observations
are retained without a compilation-speed or non-regression claim.
Neither fewer reported registers nor a favorable cohort
promotes performance. No production pipeline or SPIR-V optimization is retained.

## Reproduction and remaining work

From `runtime/zig/`:

```sh
zig build test test-full test-wgsl -Doptimize=ReleaseFast --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /path/to/retained-runtime
```

From the repository root, select that exact library through `DOE_WEBGPU_LIB`:

```sh
node packages/doe-gpu/test/integration/test-integration-shader-semantics.js
node bench/external-projects/umap-gpu/run-sgd-benchmark.mjs \
  --clean-process-runs 10 --run-id unique-id --require-all-pass
node bench/external-projects/doppler/run-matmul-f16w-f32a-tiled-parity.mjs \
  --run-id unique-kernel-id
```

The width investigation additionally records `DOE_VULKAN_REQUIRED_SUBGROUP_SIZE`
as 32 or 64, and `RADV_DEBUG=nocache,shaders,shaderstats` only for driver capture.
Use the retained invocation metadata and original timestamp wrapper for diagnostic
replay. Explicit override treatments do not qualify arbitrary subgroup sizes or
change the declared production policy. Compiled libraries remain in local ignored
custody with hashes; this is source/workspace qualification, not installed-package
release or portable artifact availability.

The Doppler transfer checks qualify the retained edge and production-QKV shapes,
not complete inference. Process RSS is not physical GPU residency; populated disk
caches and one physical host do not establish cold-cache or cross-device results.
The next compiler transformation still requires a demonstrated recoverable cost
with application contribution. Metal follows; D3D12 remains deferred.

Component: `doe.compiler.wgsl`, `doe.runtime`, `doe.packages.doe-gpu`, `doe.reports`.
Intent: preserved. Boundary effects: stricter syntax admission through existing
compiler diagnostics; no Vulkan execution-policy change.
