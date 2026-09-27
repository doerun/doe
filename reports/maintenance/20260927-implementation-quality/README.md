# Compiler interfaces and Vulkan allocation ownership

This is a local implementation-quality checkpoint. Source commits, test totals,
artifact hashes, and limitations are in [identity.json](identity.json).
The [compiler patch](compiler.patch) and [Vulkan patch](vulkan.patch) are separately
reviewable. Neither patch changes the public ABI or a runtime policy setting.

## Implementation

Internal WGSL analysis now accepts a typed request with explicit allocator,
robustness, overrides, and diagnostic storage, and returns an owned module with
phase timings. Translation and reflection callers use that entry point. Existing
signatures remain compatibility adapters. Thread-local compatibility storage
belongs to the diagnostic module. Exhaustive error translation includes numeric
parser failures that the old `anyerror` catch-all concealed.

Bounded local-array independence analysis belongs to the IR layer. Its eligibility
algorithm is unchanged; SPIR-V instruction inspection and loop-control decisions
remain in emission. Direct IR tests accompany the existing emitted-loop tests.
This does not complete the remaining instruction-cache, query, and scalar-helper
cohesion review.

The Vulkan completed-buffer cache now owns retained allocations and byte
accounting. Its typed admission input contains only runtime activity and pending
work. It receives an allocator explicitly and never submits or waits. Failed
admission leaves ownership with its caller. Acquisition still initializes contents
and assigns a fresh generation; descriptor invalidation and completion remain
with their existing owners. Retention limits and memory preferences are unchanged.

The examined path runs from native buffer creation and mapped writes through
binding, deferred submission, readback, destruction, reuse, and device teardown.
Tests cover metadata allocation failures, unsupported properties, pending work,
generation replacement, reinitialization, repeated teardown, and delayed or lost
completion. Texture-copy and mapping lifetime cases run through the existing
native ABI fixture. This is not a complete graphics/backend architecture review.

## Executed evidence

- [Final suites](final-suites.log): WGSL and runtime suites, formatting, source
  layout, ABI, line-limit, and inventory checks. Platform skips remain visible.
- [Artifact parity](compiler-artifact-parity.json): identical IR digests and
  SPIR-V, MSL, and HLSL bytes for retained compute fixtures, including eligible
  independent loops and ineligible recurrence. This is a selected fixture set.
- [Compiler timing](compiler-timing-summary.json): fresh alternating baseline
  and candidate processes using the existing compilation benchmark. Process
  percentiles are retained separately. Most changes are small and mixed; the
  larger MSL scale-fixture decrease is not promoted to a speed claim.
- [Build observations](build-summary.json): isolated clean, no-change, and
  compiler-edit builds using the existing capture tool. The compiler executable
  is smaller; clean and edit times are similar. Each arm has a single capture.
- [Native library identity](native-library-identity.json): unchanged exported
  names/types and a small library-size increase. The unchanged package example
  and native recorded-compute fixture pass against both isolated libraries.
- [Raw evidence](raw-evidence.tar.gz): logs, exact build-input inventories,
  emitted outputs, fixture sources, compiler process rows and commands, package
  receipts, and adapted lifetime injection source/configuration.

The stock build profile failed because its leaf-backend edit no longer matches
the current `vk_formats` alias. That failure is retained. The successful capture
uses a temporary profile containing the existing compiler-stage edit and
`bench-compilation` target; it does not certify the full stock profile.

## Reproduction

Use the source commits in `identity.json`, Zig from the retained toolchain record,
and a Linux Vulkan host for physical cases. Build into separate prefixes:

```bash
cd runtime/zig
zig build test-wgsl test --summary all
zig build bench-compilation emit-ir-digest emit-spirv emit-msl emit-hlsl dropin \
  -Doptimize=ReleaseFast --prefix /absolute/isolated-prefix
```

Run each prefix's `bin/doe-compilation-bench` with the exact arguments and arm
order in the archive's `timing/processes.json`. Extracted `fixtures/` are inputs
to the corresponding emit tools; compare complete bytes, not only output sizes.
From the repository root, run the unchanged package example with
`DOE_WEBGPU_LIB=/absolute/isolated-prefix/lib/libwebgpu_doe.so` and
`node packages/doe-gpu/examples/node-first-kernel.mjs`.

Compile `runtime/zig/tests/native_recorded_compute.c` with the vendored WebGPU
header, link the selected `libwebgpu_doe`, and set its runtime library search
path to that prefix. The archive's lifetime log retains the exact interposer and
probe build commands. Temporarily place its `probe.zig` at
`runtime/zig/.audit_shutdown_probe.zig`, refusing to overwrite an existing file,
then remove that temporary file after execution. Fault injection quiesces actual
GPU work before withholding completion knowledge; it does not reset hardware.

## Remaining examination

Metal already has an explicit command-completion owner and native-reference
semantics. Its buffer-pool module also contains unrelated shader-name parsing;
the next examination should trace upload pool admission and completion together
before choosing a cohesion change. No Metal implementation was changed here.

D3D12 retains submitted COM references with fence-owned batches. Continue from
`trackDropinSubmission` through buffer destruction, mapped access, texture
ownership, and terminal fence cleanup. The inspected excerpts do not certify
that complete lifecycle. No D3D12 implementation was changed here.

Continue Vulkan examination with texture/render resource ownership and command
retention, and the remaining broad `anytype` resource interfaces. Use the existing
review ledger; the cache change does not complete its containing file or directory.
No Dawn, reranker, browser, physical Metal, or physical D3D12 comparison was run.
Package smoke durations are correctness observations, not performance evidence.

Component: doe.runtime.compiler.wgsl; doe.runtime.backend.vulkan
Intent: preserved
Acceptance evidence: final-suites.log; compiler-artifact-parity.json; raw-evidence.tar.gz
Boundary effects: internal IR analysis ownership and completed-buffer cache ownership; public contracts unchanged
