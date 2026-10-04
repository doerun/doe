# Vulkan generated execution and private initialization

This checkpoint retains a rejected compiler optimization and an independently
accepted correctness repair. It does not complete the ordinary material-advantage
milestone. [generated-evidence.json](generated-evidence.json) owns source,
workload, host, executable custody, validation and disposition. The accepted
submission implementation and the user's README update are preserved.

## Measured candidate

The frozen UMAP application still runs its original SGD and apply-forces shaders,
dispatch geometry, synchronization, output readback and numerical oracle. Valid
pass timestamps identify SGD as the larger generated-execution cost. Mesa RADV
captures retain final NIR, ACO instructions, register use, scratch and spill
statistics in [driver-statistics.json](driver-statistics.json) and the adjacent
compressed driver logs. Driver estimates are not measured execution time.

The [candidate patch](rejected-loop-invariants.patch.gz) adds a function-owned scope
for already available immutable values that dominate loop bodies. It moves
modular integer addressing and fixed uniform-member loads into loop preheaders.
Mutable memory, calls, division and floating arithmetic retain their original
evaluation points. Existing straight-line instruction-cache ownership remains
intact. This implementation is retained for review and removed from production.

The generated program contains fewer instructions, but valid
[GPU timestamps](gpu-timings.json) do not meet the declared shader-gain bound.
Every instrumentation-disabled application cohort remains in
[application-comparison.json](application-comparison.json), with its original
raw benchmark and receipt. The candidate repeatedly regresses the complete
operation median beyond the existing evaluation policy. Process latency and
process-tree memory do not rescue that failure. **Reject the optimization.**

The smaller per-pass median and lower static instruction count do not establish
a useful speed improvement. Populated disk caches, provider-specific shader
policies and diagnostic instrumentation remain explicit. Dawn and Doe satisfy
the frozen output oracle with different output bytes; candidate and baseline Doe
outputs match. No application adoption or release credit is granted.

[compiler-costs.json](compiler-costs.json) separates translation time from GPU
time. Allocation counters observe the translation arena's backing allocations,
not each internal allocation request. This initial compiler pair supports no
reliability or compilation-speed claim. Public compiler artifacts and runtime
driver captures use their respective existing robustness policies.

## Correctness repair

The independent zero-iteration regression fails on the accepted baseline:
reading an implicitly initialized private variable leaves a nonzero storage
value instead of writing zero. The [baseline SPIR-V](private-zero-baseline.spvasm)
contains a private variable without an initializer. The frontend retains an
optional initializer; the first broken boundary is target emission.

WGSL requires the zero value when a private declaration omits its initializer.
[The specification](https://www.w3.org/TR/WGSL/#var-declarations) owns that
semantic requirement. The [repair](private-fix.patch.gz) supplies a typed null
constant through the existing SPIR-V builder's constant storage. Explicit
initializers, external buffers and their owners retain their contracts. Existing
compiler-content hashes invalidate incompatible cached translations.

Physical package checks cover nested branches, modular overflow, pointer-call
mutation, storage writes, zero-iteration loops, changed uniforms on a reused
pipeline, private scalar and composite state, invocation isolation, computation
and render readback. [Repaired Doe](shader-semantics-fixed-valid.log.gz) and
[pinned Dawn](shader-semantics-dawn-valid.log.gz) pass the same expected-value
checks. The [baseline negative control](shader-semantics-baseline-valid.log.gz)
retains the actual failure. The [combined suites](test-final.log.gz) include
allocation failure coverage; suite counts overlap. [SPIR-V validation](fixed-validation.json)
passes, and the repaired public UMAP shader binary remains identical to baseline.

The [Doppler transfer check](doppler-result.json) preserves exact kernel output
against pinned Dawn and the existing sampled arithmetic oracle. It qualifies
those kernels and shapes, not complete inference.

## Failed probes and reproduction

All failures remain adjacent to the accepted evidence. The initial timestamp
probe exceeded Dawn's query limit; its zero timestamps are excluded. Corrected
captures use a bounded query set and validation error scopes. A separately
identified larger UMAP input failed the original oracle on both implementations;
none of those timings qualify the candidate. The oracle was not weakened.

An independent Dawn run also rejected the fixture variable named `alias`, which
is a WGSL keyword. The fixture now uses `pointerAlias`; valid fixtures pass on
both providers. Doe's acceptance of a keyword as an identifier remains a
separately recorded frontend validation finding. Initial build invocation and
formatting failures are preserved alongside the passing final build.

Production reproduction uses the original commands:

```sh
cd runtime/zig
zig build test test-full test-wgsl -Doptimize=ReleaseFast --summary all
zig build dropin -Doptimize=ReleaseFast --prefix /path/to/retained-runtime
cd ../..
DOE_WEBGPU_LIB=/path/to/retained-runtime/lib/libwebgpu_doe.so \
  node packages/doe-gpu/test/integration/test-integration-shader-semantics.js
DOE_WEBGPU_LIB=/path/to/retained-runtime/lib/libwebgpu_doe.so \
  node bench/external-projects/umap-gpu/run-sgd-benchmark.mjs \
  --clean-process-runs 10 --run-id unique-run-id --require-all-pass
```

The rejected patch applies to the checkpoint predecessor after removing the
private repair. Compiler diagnostic patches add allocation observation and
SPIR-V export outside the timed translation loop. The retained provider wrapper
adds timestamp resolve, copy and readback; keep it out of ordinary performance
runs. Diagnostic JavaScript snapshots preserve their original temporary-module
imports and require reconstruction at those paths; the production test above
is the canonical physical reproduction. [libraries.json](libraries.json) binds
the retained local executable archives. [artifact-index.json](artifact-index.json)
binds the curated evidence bytes.

The next transformation requires a measured recoverable execution cost with an
application contribution. Vulkan remains active; Metal and D3D12 receive no
optimization or hardware qualification from this checkpoint.

Component: `doe.runtime-zig`, `doe.packages`, `doe.config`, `doe.docs`, `doe.reports`.
Intent: preserved. Acceptance evidence: linked artifacts and physical logs.
Boundary effects: correct SPIR-V private initialization and repository-only
fixtures; no public ABI or serialized-cache format change.
