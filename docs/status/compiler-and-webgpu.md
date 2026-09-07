# Doe status: compiler and WebGPU

This is the live status front door for the non-TSIR WGSL compiler and WebGPU
runtime path. Artifacts and executable tests own pass/fail state.

## Immediate-data admission

Native immediate-data calls now reject unsupported shader-visible payloads
through device validation scopes and invalidate their command or bundle
recording. Non-zero immediate-data layouts fail before allocation or binding
retention. Zero-byte calls at the empty layout's origin remain harmless.
Payload execution is unsupported; former proc-surface diagnostics did not
establish shader-visible behavior. The capability inventory, spec index, and
generated reports reflect that distinction.

Acceptance: `bench/out/compute-program/20260906-immediate-admission/README.md`.
No backend gains immediate-data execution through this correction.

## Active pass ownership

The encoder's recording state now identifies its active pass. End unlocks the
encoder; nested passes, encoder copy/query commands inside a pass, finish with
an open pass, repeated end, and calls through an earlier ended pass invalidate
recording. Releasing the caller's pass reference does not imply end. Draw state,
bundles, pass queries, immediate-data entrypoints, and debug-marker entrypoints
check the same owner before accessing retained pass state.

Canonical regressions, the failing pre-fix C-boundary reproduction, corrected
physical execution, and exact-package qualification are indexed at
`bench/out/compute-program/20260906-pass-lifecycle/README.md`.
This is pass-lifecycle acceptance, not complete WebGPU validation: debug-group
nesting, query semantics, descriptor validation, and capability coverage still
need their respective tests and implementation.

## Recording failures and submission ordering

Ordinary recording preserves allocation failures and owned dependencies. Buffer
copies validate device, usage, aligned ranges and aliasing before allocation;
empty and whole-size requests share that admission. Native fused constructors
retain their disjoint-alias and omitted-copy contract. Queue submission checks
all retained resources before executing any buffer in the batch, including bind
groups and bundles. Query commands share the typed lease list. Texture destruction
invalidates execution/writes while retained owners preserve backing allocation;
caller release and unmapping before submission preserve valid work. Acceptance:
`bench/out/compute-program/20260907-submit-availability/README.md`.
Earlier copy admission: `bench/out/compute-program/20260907-buffer-copy-admission/README.md`.

Vulkan buffer/image copies execute at their recorded queue position without CPU
staging. Both directions share mip-relative extent, block, layer, stride, and
last-accessed-byte validation. Texture copies can feed resident storage and a
dependent dispatch; mapped readback receives explicit transfer visibility.
Abandoned recordings do not execute, and padding remains untouched. Copy-only
textures and their WebGPU views allocate no Vulkan image views; the physical
fixture also runs with synchronization validation enabled.
The WebGPU C bridge preserves origins and aspects; shared admission rejects
invalid descriptors before retention. Array, volume, and depth/stencil evidence:
`bench/out/compute-program/20260907-texture-copy-regions/README.md`.
This does not establish full conformance, concurrent queue safety, physical
Metal/D3D12 behavior, or a performance advantage.

## Transactional fused command construction

The native fused compute entrypoints now use a typed recording builder that
reserves storage before taking resource references. Failed construction releases
all earlier commands and dependencies; only a completed command buffer is
published. Its allocator remains attached through final cleanup. The C boundary
reports the original failure through the device's existing error scopes.

Allocation-fault tests exercise object allocation, command/reference list growth,
aliased copy buffers, ownership transfer, and abandoned construction. Native
scope tests check failed-copy diagnostics and cleanup. A direct C regression
executes the single and batched native constructors after rejected construction,
releases caller state before submission, and checks independent integer outputs.
It uses the same library bytes as retained-package qualification; the addon's
similarly named helper uses ordinary encoding and is separate evidence.
Fused-constructor acceptance: `bench/out/compute-program/20260906-recorded-allocation/README.md`.
Ordinary recording is covered by the checkpoint above.

## Depth attachment ownership

Native Vulkan execution binds the application's retained depth texture and view
instead of allocating an unrelated target for each draw. Internal commands
carry attachment identity, load operations, and clear values. Draws, later
passes, and read-only depth use preserve the existing state; an empty clear
pass resets it explicitly. Borrowed attachments remain owned by the native
command-buffer leases, and temporary backend targets retain separate cleanup.

Descriptor snapshots and render attachments use the same texture-parent
allocation identity rule. Recycled generations, changed images, and another
parent cannot satisfy a retained view's binding. The regression checks depth
occlusion across draws/passes, read-only depth, empty clears, caller release,
and readback from the application's depth texture.
Source, native traces, tests, and retained packages are indexed at
`bench/out/compute-program/20260906-depth-ownership/README.md`.
The physical image regression covers depth; stencil operations, depth-only
passes, store/discard initialization, multisampling/resolve, broad view-range
validation, and other backends still require their own acceptance evidence.

## Color attachment preservation

Native Vulkan recording now distinguishes the first recorded attachment use
from API draw-count accounting. The initial draw honors the declared color load;
later direct and bundled draws preserve previous color writes. Empty passes
also preserve existing color when `load` is requested. Render-pass dependencies
derive their source scope from the existing texture-layout owner.

The native-addon regression draws adjacent regions, loads them through an empty
pass, releases caller references, and checks the submitted pixels. The failing
reproduction, source correction, native checks, and exact-package qualification
are indexed at `bench/out/compute-program/20260906-render-load/README.md`.
This checkpoint concerns existing color attachments. Broader depth/stencil
behavior, store/discard initialization, resolve behavior, render queries, and
broader render-pass conformance remain separate correctness work.

## Deferred rendering and native ownership

Vulkan draws are recorded as owned command snapshots and executed during queue
submission. Render passes and bundles retain pipelines, bindings, attachments,
vertex/index/indirect buffers, and their encoder/device dependencies. Caller
reference release is distinct from explicit destruction. The native-addon
regression writes vertex data after recording, releases caller references, and
checks the submitted image for direct and bundled draws.

Vertex-format ABI interpretation has one typed owner checked against the pinned
header. Vulkan buffers include native vertex/index usage, and rendering receives
physical synchronization validation. Qualification rejects native validation
errors even on successful process exit. The failing and corrected runs are at
`bench/out/compute-program/20260907-render-validation/README.md`.
Render shader copies publish transactionally. Metal preserves its retained layout
and prepared vertex layouts. Atomic reference leases do not establish concurrent
queue safety.

Earlier ownership evidence: `bench/out/shader-ownership/20260906-owned-diagnostics/README.md`
and `bench/out/compute-program/20260906-render-ownership-qualified/summary.json`.
This targeted image test does not establish full render-pass conformance,
attachment load/store and resolve behavior across multiple draws, render query
coverage, or physical Metal/D3D12 execution.

## Explicit shader failures and owned diagnostics

Reflection, required WGSL retention, and compiler diagnostics are repaired
through their native and compiler owners. Focused regressions exercise valid
empty interfaces, allocation failures, extraction capacity, source-context
retention, and concurrent compiler requests. The migration contract lives in
[shader compiler architecture](../shader-compiler-architecture.md).

Declared module initializers now evaluate or report a typed failure; unsupported
expressions cannot silently become zero. Scalar/vector constant bit counts and
partial-fold cleanup are covered by
`bench/out/compute-program/20260907-constant-initializers/README.md`.

Metal libraries have device owners and independent shader leases. CPU reference
accounting and Vulkan qualification do not establish physical Metal behavior:
`bench/out/shader-ownership/20260906-owned-diagnostics/README.md`.

## Scalar compute fusion and allocation failures

The SPIR-V compute pipeline has a versioned arithmetic policy and a typed IR
transform preserving operand order and ownership. Its physical continuous
simulation correction, unchanged oracle, and remaining cross-backend boundary
are recorded in [reusable compute programs](reusable-compute-programs.md).

Allocation-failure regressions repair name publication in semantic analysis and
IR building, ownership transfer for entry points, and robustness builtin names.
Allocation errors now retain their original typed cause. Correction evidence is
under `bench/out/compute-program/20260905-resident-fusion-correction/`; this does
not establish general shader conformance or remove unrelated downstream gaps.

## Current boundary

- Doe has source-preserving WGSL lowering and backend emit paths for Metal,
  Vulkan, and D3D12/DXIL.
- Browser-corpus and CTS-subset evidence exists, but it does not establish full
  WebGPU conformance or a general Doe-over-Tint claim.
- The shared-contract WebGPU lane has transcript and parity plumbing but is not
  green end to end for the promoted model path.
- TSIR status lives in [`tsir.md`](tsir.md).

## Active blockers

- Close remaining WGSL semantic-analysis and backend-emission failures on real
  downstream shaders.
- Produce non-zero, oracle-validated state for the WebGPU model transcript
  path.
- Publish broader CTS evidence before using conformance or replacement
  language.
- Make compiler and runtime failure diagnostics preserve the original typed
  cause throughout package and native boundaries.

## Ground truth

- Compiler tests: `zig build test-wgsl` from `runtime/zig`
- CTS ledger: `config/webgpu-cts-evidence.json`
- Compiler evidence: schema-registered artifacts under `examples/` and
  `bench/out/`
- Historical entries:
  [`archive/2026-04-to-2026-07-compiler-and-webgpu.md`](archive/2026-04-to-2026-07-compiler-and-webgpu.md)
