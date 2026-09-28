# SPIR-V instruction-cache ownership

`InstructionCache` owns access-chain keys, local-load entries, result operands,
and their allocations for a function. The function emitter requests lookups and
insertions without coordinating collection cleanup. Stores invalidate the named
local; calls invalidate local loads; block transitions invalidate all cached
instruction IDs. Opcode eligibility, scalar construction, ID allocation and
SPIR-V loop controls remain emission decisions. No generic cache or pass framework
was introduced. Cache insertion remains fallible and frees unpublished keys.

Reference-root and parameter-write queries now live in `ir_query.zig`. Their
traversal still follows members, indices, and loads. It does not follow
constructors or constant initializers as `resolveValueAlias()` does. The direct
IR regression preserves that distinction.

The actual consumer is `emit_spirv.zig`'s function emission: translation lowers
validated IR, constructs function state, emits its body and destroys the state
on success or failure. Native shader creation and public pipeline construction
consume the resulting SPIR-V. The separately retained
[ordinary query regression](../20260928-production-query/README.md) still passes
against the library containing this compiler change.

## Executed evidence

[Identity](identity.json) records source and library identities, test outcomes,
and binary sizes. [Artifact parity](parity.json) compares complete emitted bytes
and error outcomes from isolated predecessor/candidate tools. Successful SPIR-V
also passes `spirv-val`. The selection includes the existing compilation corpus
and a store/pointer-write/branch/loop fixture. The latter executes physically on
AMD Vulkan against an independent integer oracle in the permanent runtime suite.

Cache tests cover copied-key ownership, distinct key identities, selective load
invalidation, block reset, reuse and exhaustive allocation-failure unwinding.
IR tests cover reference chains and their distinction from value aliases.
The complete compiler and runtime suites pass with their retained platform skips.
[Raw evidence](raw-evidence.tar.gz) retains logs, scripts, fixtures, emitted output,
timing process records and the source diff.

[Compiler observations](compiler-observations.json) preserve independent,
interleaved predecessor/candidate processes using the existing compilation bench,
with explicit warmup and sample counts. These observations are diagnostic, not
application latency measurements or a compiler speed claim. The initial cohort
contains a higher median for a small vertex fixture amid bimodal process results.
A [fixed-CPU follow-up](compiler-followup.json), including unchanged controls,
does not reproduce that slowdown. Both cohorts remain retained separately;
this does not establish performance equivalence across workloads.
[Build measurements](build-measurements.json) runs the existing complete stock
profile in its isolated snapshot/cache. Its clean, no-change, edit and restore
measurements are candidate workflow observations, not a paired build-speed claim.
The build recipe itself is unchanged. Process RSS has the scope recorded in the
receipt and does not represent simultaneous whole-build memory.

## Reproduction

From `runtime/zig`:

```bash
zig build test-wgsl test --summary all
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json \
  zig build test -Dtest-filter='SPIR-V cache invalidation' --summary all
zig build bench-compilation emit-ir-digest emit-spirv emit-msl emit-hlsl dropin \
  -Doptimize=ReleaseFast --prefix /absolute/candidate-prefix
```

Use the baseline identity and exact commands in the raw comparison scripts to
repeat emitted-byte and timing observations. From the repository root:

```bash
python3 runtime/zig/tools/capture_build_measurements.py --output /absolute/build.json
python3 runtime/zig/tools/review_log.py --check --base-ref 628f8dd39
```

## Remaining limits

A named function-pointer alias fixture returns the same `InvalidIr` SPIR-V
failure in both builds; direct pointer arguments work. That pre-existing lowering
limitation is retained as a failure, not counted as successful shader parity or
new alias support. No general WGSL conformance, Dawn comparison, application
performance, browser, physical Metal/D3D12 or release qualification is claimed.
Khronos validation layers are unavailable. Generated architecture catalogs were
not refreshed or recertified; current source-layout and import gates passed.

This completes the bounded ownership correction, not a whole compiler audit.
Further Vulkan interface work must identify the real consumer, complete path,
and observable consequence before changing its owner. Surface synchronization and
attachment admission retain separate findings. Completed bundle/build-recipe
repairs remain closed.

Component: WGSL SPIR-V function emission and IR queries
Intent: preserved
Acceptance evidence: identity.json, parity.json, compiler-observations.json, build-measurements.json, raw-evidence.tar.gz
Boundary effects: target-independent reference queries move to IR; cache storage and cleanup move to the emitter-owned typed cache; public ABI unchanged
