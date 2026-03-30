# Doe Zig Module

Purpose:
- produce specialization outputs from validated quirk sets
- provide standalone or embedded/adjacent integration paths

Decision rubric (when to use Zig):
1. Use Zig for hot-path runtime logic that executes per command/dispatch/frame.
2. Use Zig for compile-time specialization from static quirk/profile data.
3. Use Zig when allocator control or bounded-memory behavior is part of the requirement.
4. Keep logic out of Zig when it is policy-only, proof-only, or infrequent orchestration.
5. Move logic into Zig only after benchmark traces show it is in the latency-critical path.
6. For incumbent-replacement/runtime paths, implement in Zig first, then remove branches only when Lean proofs let us hoist them out safely.

Interop note:
- initial integration target is Doe's standalone runtime path
- adapter/ABI paths are used only for side-by-side incumbent comparisons

Terminology note:
- Doe's real execution path is its own direct backend implementation path.
- In benchmark docs, that is the path contrasted with the Dawn delegate path.
- "native" in flags such as `--backend native` means Doe is executing the
  workload through its own backend implementation, not that Doe has some
  separate non-runtime identity.

Style guide:
- follow `STYLE.md` for all Zig implementations in this module.

## Source modules (runtime + backend lanes)

Core:
- `src/model.zig` — typed contract for API, scope, safety, proof mode, match spec, actions, command kinds, device profile.
- `src/quirk/mod.zig` — quirk module entry: `QuirkMode` enum (`off`/`trace`/`active`), `dispatchWithMode()`, re-exports sub-modules.
- `src/quirk/runtime.zig` — deterministic matcher, selector, and action application with profile-indexed command buckets.
- `src/quirk/quirk_json.zig` — deterministic JSON parser for quirk records with strict schema checks.
- `src/quirk/toggle_registry.zig` — toggle behavioral classification (`behavioral`/`informational`/`unhandled`) for known Dawn toggles.
- `src/runtime.zig` — re-export shim for `quirk/runtime.zig` (backwards compatibility).
- `src/main.zig` — CLI, arg parsing, dispatch loop, `--trace`/`--replay`/`--trace-meta` orchestration.
- `src/execution.zig` — execution mode switching (`trace` and `native`) and run result envelope.
- `src/command_stream.zig` — command stream parser that preserves optional
  semantic operator metadata and targeted capture requests alongside
  `model.Command` values.
- `src/semantic_trace.zig` — shared semantic operator context and capture-request types.
- `src/operator_artifacts.zig` — per-op manifest writer, targeted capture
  emission, and structural repro bundle generation.

Parsing:
- `src/command_json.zig` — JSON command stream parser for replay-style inputs.

Trace and replay:
- `src/trace.zig` — TraceState, hash functions, name helpers, trace row and meta output.
- `src/replay.zig` — replay expectation parsing and hash-chain validation.

WebGPU backend:
- `src/webgpu_ffi.zig` — WebGPUBackend struct, lifecycle (init/deinit), adapter/device request, queue sync, timestamp readback.
- `src/core/abi/wgpu_types.zig` — all WebGPU C API types, constants, function pointer types, Procs table, record types.
- `src/core/abi/wgpu_loader.zig` — dynamic library loading, C callbacks, helper functions.
- `src/wgpu_commands.zig` — command execution orchestration for upload/copy/barrier/dispatch/kernel dispatch plus render command delegation.
- `src/wgpu_render_commands.zig` — native `render_draw` lowering via render pass, async pipeline diagnostics, and render-bundle execution.
- `src/wgpu_render_draw_loops.zig` — specialized render-pass/render-bundle draw-loop encoders for explicit pipeline/bind-group mode combinations.
- `src/wgpu_render_resources.zig` — render uniform/texture/sampler bind-group resource setup and cached texture-view helpers.
- `src/wgpu_render_api.zig` — render-pass and render-bundle proc table for state/draw/execute APIs.
- `src/wgpu_render_types.zig` — render bundle/pass/pipeline extern descriptor/value types.
- `src/wgpu_texture_procs.zig` — sampler/queueWriteTexture/texture query+destroy proc surface.
- `src/wgpu_surface_procs.zig` — surface creation/configure/present proc surface and structs.
- `src/wgpu_async_procs.zig` — async render-pipeline/error-scope/compilation-info proc surface and wait helpers.
- `src/core/resource/wgpu_resources.zig` — buffer/texture management, bind group building, shader module and pipeline creation.

Public surface (core/full split):
- `src/core/surface.zig` — core-only public API surface: validate, accept, coverage ledger for compute/copy/resource/queue commands.
- `src/full/surface_api.zig` — full public API surface: classify (core vs full-only), accept, combined coverage ledger for all commands.
- `src/core/command_partition.zig` — core command kind enum, `CoreCommand` union, and partition membership.
- `src/full/command_partition.zig` — full-only command kind enum, `FullCommand` union, and partition membership.

Build:
- `build.zig` — compile and run hooks, links libC and libdl.
- `zig build dropin` — full drop-in shared library (`libwebgpu_doe.so`).
- `zig build dropin-core` — core-only drop-in shared library (`libwebgpu_doe_core.so`).
- `zig build module-core-runner` — explicit service runner for promoted Zig
  module contracts, including the v1 numeric-stability service.
- `zig build csl-sim-runner` — explicit CSL simulator contract runner (`doe-csl-sim-runner`).
- `zig build coverage-gate` — validate split coverage ledgers against Zig command partitions.
- `zig build import-fence` — validate core/full one-way import boundaries.
- benchmark/claim runs should use `zig build -Doptimize=ReleaseFast` so `zig-out/bin/doe-zig-runtime` is built with optimized codegen before compare lanes are executed.

## How to run (toolchain must be available)

```bash
cd zig
zig build run -- --vendor intel --api vulkan --family gen12 --driver 31.0.101
zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --trace
zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --replay path/to/trace.jsonl
zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --backend native --execute --trace --trace-jsonl run.jsonl --trace-meta run.meta.json
zig build run -- --commands ../examples/kernel_dispatch_commands.json --backend native --execute --kernel-root ../bench/kernels
zig build run -- --commands ../examples/draw_call_proxy_commands.json --backend native --execute --trace --trace-meta run.meta.json
zig build run -- --commands ../examples/draw_call_proxy_commands.json --backend native --execute --trace --queue-sync-mode deferred --trace-meta run.deferred.meta.json
zig build run -- --commands ../../examples/kernel_dispatch_commands.json --trace
zig build run -- --commands ../../examples/kernel_dispatch_commands.json --emit-normalized
zig build test
zig build dropin
zig build csl-sim-runner
zig build app
```

### Explicit numeric-stability service

`module-core-runner` now exposes the first live Doe numeric-stability service
as an explicit Zig-owned contract:

- module: `doe_numeric_stability`
- service: `matmul_logits_slice`
- policy source: `config/numeric-stability-policy.json`

The v1 path is intentionally explicit:

- it evaluates a bounded LM-head / `matmul.logits` slice
- it runs fast, stable, and bounded CPU-reference policies
- it emits a per-event numeric-stability receipt plus an optional trace-meta
  summary block
- it supports explicit route-policy selection, including:
  - `numeric-stability/prefer-stable-on-selected-token-disagreement-v1`
  - `numeric-stability/abstain-on-selected-token-disagreement-v1`
- it remains the current public/package-facing numeric-stability helper

### In-path ordinary-execution numeric stability

`doe-zig-runtime` now supports native ordinary-execution numeric-stability
evaluation from config-backed auto-detect profiles during real
`kernel_dispatch` execution.

- the current auto-detect registry lives in:
  - `config/numeric-stability-policy.json`
  - `config/numeric-stability-policy.schema.json`
- the current native ordinary-execution operator families are:
  - `matmul.logits`
  - `rmsnorm.output`
  - `attention.output`
- ordinary execution now resolves a named execution profile from the shared
  registry:
  - `numeric-stability/default-ordinary-execution-v1`
  - `numeric-stability/cautious-ordinary-execution-v1`
  - `numeric-stability/observe-only-ordinary-execution-v1`
- matching uses semantic fields plus executed kernel identity
- explicit command-local `numericStability` annotations remain supported as an
  override path, but they are no longer required for the primary in-path lane
- when a supported native command stream runs with `--trace-meta`, the runtime:
  - captures the live operator operands and fast output from the executed
    dispatch
  - computes stable and exact-reference comparisons locally in Zig
  - can rewrite the committed result for `prefer-stable`
  - can stop the downstream command suffix for `abstain`
  - emits decode-boundary receipts for the shipped `sample.wgsl` path when it
    follows an auto-detected `decode.final_logits` producer
  - emits `<trace-meta>.numeric-stability.jsonl`
  - populates the `numericStability` trace-meta summary block
  - records the selected `executionProfileId` in trace meta
  - binds receipt identity to kernel path/basename, layout fingerprint,
    adapter/driver profile, and compiled plan hash
- the current live decode-boundary surface is intentionally narrow but no
  longer greedy-only:
  - `decode.sample_token` receipts report a real full-vocabulary decode
    boundary
  - the legacy 16-byte sample uniform remains backward-compatible and reports
    `decodeMode = greedy-argmax`
  - when the expanded sample ABI is present, the runtime now:
    - parses `temperature`, `topK`, `topP`, `rngSeed`, and `rngDraw`
    - replays `fast`, `stable`, and `reference` under the same draw
    - writes the committed sampled token back into the real output buffer
    - records `cdfDistanceToDraw` plus the sampled selected-token triple
  - `decodeBoundary.upstreamLinks` still point back to the governing
    `decode.final_logits` receipt

This in-path ordinary-execution support is still strongest in the native
runtime lane, but `doe-gpu` now also exposes the same ordinary command-stream
contract via `gpu.ordinaryExecution(...)`, with
`gpu.numericStability.ordinaryExecution(...)` retained as a compatibility
alias.

Use this path when promoting bench numeric-fragility evidence into a real Doe
runtime contract.

### CSL simulator contract runner

`doe-csl-sim-runner` is the explicit bridge between Doe-emitted
`csl_simulator_plan` artifacts and a real Cerebras simulator executable.

- It validates the simulator plan artifact before launch.
- It resolves the simulator driver from:
  1. `--driver-executable`
  2. `$DOE_CSL_SIM_EXECUTABLE`
- The external driver may also consume:
  - `$DOE_CSLC_EXECUTABLE` for `cslc`
  - `$DOE_CSL_RUNTIME_EXECUTABLE` for a real simulator/runtime command
- It writes stdout/stderr to the plan-declared output paths.
- It emits a result artifact at `<tracePath>.result.json` by default, or the path
  provided via `--result-json`.
- It does not synthesize trace output or fake execution if the driver is absent.

Example:

```bash
zig-out/bin/doe-csl-sim-runner --plan path/to/simulator-plan.json
DOE_CSL_SIM_EXECUTABLE=/opt/cerebras/bin/csl-sim zig-out/bin/doe-csl-sim-runner --plan path/to/simulator-plan.json
```

When `--quirks` is provided, JSON file values are loaded directly and validated before transform.
Quirk records now use schemaVersion `2` with strict action payloads:
- `use_temporary_buffer` requires `params.bufferAlignmentBytes`
- `toggle` requires `params.toggle`
- `no_op` does not accept params

### DXIL toolchain contract

WGSL-to-DXIL now uses native Zig DXIL bytecode generation as the primary path.
The native emitter translates Doe IR directly to LLVM 3.7 bitcode, serializes
it, and wraps it in a DXBC container -- no external DXC dependency required.
DXC remains available as a fallback path for validation against the reference
compiler.

Native DXIL modules (2,303 LOC total):
- `runtime/zig/src/doe_wgsl/dxil_spec.zig` -- DXIL opcodes, types, and constants
- `runtime/zig/src/doe_wgsl/dxil_bitcode.zig` -- LLVM 3.7 bitcode encoding
- `runtime/zig/src/doe_wgsl/dxil_builder.zig` -- IR-to-DXIL instruction builder
- `runtime/zig/src/doe_wgsl/dxil_serialize.zig` -- bitcode serialization
- `runtime/zig/src/doe_wgsl/dxil_container.zig` -- DXBC container wrapping
- `runtime/zig/src/doe_wgsl/emit_dxil_native.zig` -- top-level native emitter

`runtime/zig/src/doe_wgsl/emit_dxil.zig` routes the primary `emit()` call
through `emit_dxil_native`, with `emitWithToolchainConfig()` as the DXC
fallback path.

DXC fallback configuration (for validation or legacy use):
- `runtime/zig/src/doe_wgsl/mod.zig` exports `translateToDxilWithToolchainConfig(...)`
  plus `DxilToolchainConfig` for explicit callers.
- Set `DOE_WGSL_DXC=/absolute/or/workspace-relative/path/to/dxc(.exe)` to pin
  the exact compiler binary for the fallback path.
- Set `DOE_WGSL_DXC=PATH` to opt into PATH lookup explicitly.
- If `DOE_WGSL_DXC` is unset, the native path is used; no external tool needed.

### Quirk pipeline (automated)

Generate quirk records from Dawn source (no manual authoring required):

```bash
cd ..
python3 pipeline/agent/mine_upstream_quirks.py \
  --source-root bench/vendor/dawn/src/dawn/native \
  --source-repo dawn/main \
  --source-commit $(git -C bench/vendor/dawn rev-parse --short HEAD) \
  --vendor apple --api metal \
  --output bench/out/mined-apple-metal-quirks.json \
  --manifest-output bench/out/mined-apple-metal-quirks.manifest.json
```

Then run with active quirks:

```bash
zig build run -- \
  --quirks ../bench/out/mined-apple-metal-quirks.json \
  --commands path/to/commands.json \
  --vendor apple --api metal \
  --quirk-mode active \
  --backend native --execute --trace
```

The miner auto-promotes known behavioral toggles (e.g. `UseTemporaryBufferInCompressedTextureToTextureCopy`)
from `action: toggle` to `action: use_temporary_buffer` via its `TOGGLE_PROMOTIONS` table.
With `--quirk-mode active`, promoted records change backend execution (staging buffer insertion).
With `--quirk-mode trace` (default), records match and trace but do not modify commands.

Drop-in shared library artifact:
- `zig build` installs `runtime/zig/zig-out/lib/libwebgpu_doe.so` alongside `runtime/zig/zig-out/bin/doe-zig-runtime`
- `zig build dropin` installs the same drop-in shared library bundle without requiring the default runtime step
- when Dawn sidecars are present at `bench/vendor/dawn/out/Release/libwebgpu_dawn.so`,
  both `zig build` and `zig build dropin` co-install:
  - `runtime/zig/zig-out/lib/libwebgpu_dawn.so`
  - `runtime/zig/zig-out/lib/libwebgpu.so`
  - `runtime/zig/zig-out/lib/libwgpu_native.so`
- exported core WebGPU symbols are forwarded through deterministic resolver logic
- `wgpuGetProcAddress` returns local exported wrappers first, then resolves from the native backend
- resolver error state can be queried with:
  - `doeWgpuDropinLastErrorCode()`
  - `doeWgpuDropinClearLastError()`

macOS app bundle artifact:
- `zig build app` installs `runtime/zig/zig-out/app/Doe Runtime.app`
- the build deterministically generates `Contents/Resources/DoeRuntime.icns`
  during bundle assembly (host target must be macOS)

Timestamp debug mode (for zero/empty GPU timestamp investigation):

```bash
DOE_WGPU_TIMESTAMP_DEBUG=1 zig build run -- --commands path/to/commands.json --backend native --execute --trace --trace-meta run.meta.json
```

This emits timestamp-path diagnostics to stderr, including adapter/device feature state, query artifact creation, write mode, map status, and begin/end readback values.

- `--trace` now emits trace rows conforming to `config/trace.schema.json`.
- trace rows include `traceVersion`, `module`, `opCode`, deterministic `hash` and `previousHash`,
  and the full decision envelope used by Lean parity checks.
- when command JSON includes semantic fields (`semanticOpId`, `semanticStage`,
  `semanticPhase`, `semanticTokenIndex`, `semanticLayerIndex`,
  `semanticExecutionPlanHash`), trace rows preserve those fields and fold them
  into the hash chain.
- execution rows now include both human and machine status fields:
  `executionStatusMessage` (raw detail) and `executionStatusCode` (normalized stable token).
- execution-backed semantic rows now also include runtime provenance required for
  operator-level debugging: backend lane, selection policy hash, shader-artifact
  manifest references, adapter ordinal, queue family index, and present-capable
  state when available.
- `--trace-meta` execution timing now includes split fields:
  `executionSetupTotalNs`, `executionEncodeTotalNs`, `executionSubmitWaitTotalNs`, `executionDispatchCount`.
  Native execution metadata also records `queueSyncMode` when `--execute` is enabled.
- the shared trace-meta schema now also reserves an optional `determinism`
  block for explicit post-logit policy boundaries (`stable-token`,
  `stable-choice`, `reviewed-choice`). The Zig trace summary carries that
  field as an opt-in contract stub so native/runtime lanes can emit the same
  policy IDs and proof-linked boundary metadata as the package helpers.
- when a trace anchor is present (`--trace-meta` or `--trace-jsonl`), Doe-native
  runs also emit operator artifacts adjacent to that anchor:
  - `.operators.json` manifest
  - optional `.capture.bin` files for commands with capture requests
  - `.repro.commands.json` + `.repro.meta.json` structural rerun bundles
- command JSON accepts optional semantic/capture fields without changing command
  semantics:
  - `semanticOpId`, `semanticStage`, `semanticPhase`
  - `semanticTokenIndex`, `semanticLayerIndex`, `semanticExecutionPlanHash`
  - `captureBufferHandle`, `captureOffset`, `captureSize`
- GPU timestamp reliability fields are emitted when execution is enabled:
  per-row `executionGpuTimestampAttempted` / `executionGpuTimestampValid`,
  and trace-meta counters `executionGpuTimestampAttemptedCount` / `executionGpuTimestampValidCount`.
- `--replay` mode validates per-row `seq`, `command`, optional `kernel`, `module`, `opCode`, and hash-chain fields.

## Runtime behavior contract (minimal clone slice)

- `--quirk-mode off|trace|active` controls quirk system behavior:
  - `off` — skip quirk loading and matching entirely
  - `trace` (default) — match and trace quirk decisions but do not modify execution commands
  - `active` — full backend consumption: quirk-modified commands reach backends (e.g. `use_temporary_buffer` inserts staging copies)
- trace-meta output includes `quirkMode` field when set.
- fixed precedence rules in `runtime.zig`
- runtime dispatch now pre-filters quirks once per process profile and buckets by command kind before tracing starts.
- profile matching:
  - vendor + api hard match
  - optional device family match
  - optional driver range match (`>=`, `>`, `<=`, `<`)
- deterministic action selection by score
- action application returns a transformed command, never silent fallthrough.
- lean obligation fields in dispatch decisions:
  - `requiresLean` (derived from `verificationMode`)
  - `blocking` (required proof not met)
  - `verificationMode` and `proofLevel` of selected quirk
- `--trace` emits JSON rows including the Lean gate fields for replay and gate auditing.
- trace rows now also include:
- `scope`
- `safetyClass`
- `toggle` (toggle action payload when present)
- command parsing accepts `command`, `kind`, or `command_kind` with extra kernel alias (`kernel_name`).

## Lean-out workflow for Zig runtime

1. Implement runtime behavior deterministically in Zig (no placeholder execution branches).
2. Capture benchmark + trace evidence for the current path.
3. Prove removable conditions in Lean and emit bind/build artifacts that encode the decision.
4. Delete the corresponding Zig runtime branch once proof+artifact path is in place.
5. If proof is not available, keep the explicit Zig path and continue measuring.

### Active eliminations (`-Dlean-verified=true`)

Six theorems gate runtime branch elimination. All are `tautological` or `comptime_verified` — none require Lean. See `pipeline/lean/README.md` for the four-tier classification.

- Init time: `scopeCommandTableComplete` (tautological — table built from function) replaces `supportsCommand` switch. `requiredProof_forbidden_reject_from_rank` and `strongerSafetyRaisesProofDemand` (comptime_verified — finite enums) narrow `is_blocking` in `finalizeBucket`.
- Per command: `identityActionComplete` (comptime_verified — 4 variants) + `identityActionPreservesCommand` (tautological — follows from above) skip `applyAction` for identity actions.

Build without `-Dlean-verified=true` produces identical logic (the non-lean code paths are equivalent). The payoff is simpler runtime code (657 lines, down from 796) with less duplication.

## Native execution status

Native Zig+WebGPU/FFI execution is implemented across backend modules in `runtime/zig/src`:
- `webgpu_ffi.zig` — backend struct, adapter/device/queue lifecycle, timestamp readback.
- `core/abi/wgpu_types.zig` — C API type definitions and function pointer table.
- `core/abi/wgpu_loader.zig` — dynamic library loading, C callbacks, helpers.
- `wgpu_commands.zig` — command execution with compute pipeline lowering and GPU timestamp queries.
- `wgpu_resources.zig` — buffer/texture/bind-group/pipeline resource management.

Execution capabilities:
- `--backend native --execute` emits `executionBackend` fields in trace rows.
- `upload`, `copy`, `barrier`, `dispatch`, `kernel_dispatch`, and `render_draw` all submit through real command buffers.
- native queue waiting is configurable via `--queue-wait-mode process-events|wait-any` (default: `process-events`; `wait-any` fails explicitly when unsupported).
- queue synchronization timing is configurable via `--queue-sync-mode per-command|deferred` (default: `per-command`);
  deferred mode skips per-submit waits and performs one final queue flush after the command loop.
- kernel-dispatch GPU timestamp querying is configurable via `--gpu-timestamp-mode auto|off|require` (default: `auto`).
  `auto` falls back to non-timestamp timing when timestamp capture is unavailable/invalid, `off` disables timestamp attempts, and `require` fails execution when timestamp capture is unavailable/invalid.
- `kernel_dispatch` runs through full compute pipeline lowering with bind groups and optional GPU timestamp queries.
- render core APIs (`DeviceCreateRenderPipeline`, `CommandEncoderBeginRenderPass`, and `RenderPassEncoder*` state/draw/end/release calls) are wired through the shared `core/abi/wgpu_types.zig` proc table and loaded in `core/abi/wgpu_loader.zig`.
- render-pass state coverage includes bind-group, viewport, scissor, blend-constant, stencil-reference, and render-pipeline bind-group-layout query calls.
- `render_draw` now uses async pipeline creation (`DeviceCreateRenderPipelineAsync`) with explicit shader compilation-info and error-scope checks before cache insert.
- `render_draw` now uses a textured bind-group contract (uniform + texture + sampler) with deterministic `QueueWriteTexture` upload and runtime sampler creation.
- `render_draw` draws through render-bundle encoding and `RenderPassEncoderExecuteBundles` submission.
- surface presentation wrappers are available through backend methods for create/capabilities/configure/current-texture/present/unconfigure/release.
- kernel lookup supports `--kernel-root` and built-in marker fallback kernels.
- wall-time, setup, encode, and submit-wait timing split into trace rows and `--trace-meta`.

Known gaps:
- adapter/driver timestamp reliability still varies by host; use `--gpu-timestamp-mode require` for fail-fast strict timestamp lanes and `auto`/`off` for directional fallback lanes.
- render path is currently minimal (`render_draw`) but now applies command-driven pass-state controls (viewport/scissor/blend/stencil, encode mode, dynamic bind-group offsets); broader multi-pass scene orchestration remains open.

Reference commands:
- `zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --backend native --execute`
- `zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --backend native --execute --trace --trace-jsonl run.jsonl --trace-meta run.meta.json`
- `zig build run -- --commands path/to/commands.json --replay path/to/run.jsonl --backend native`

### Parser behavior guarantees

- API, vendor, and command names are matched case-insensitively where practical.
- malformed payload fields fail fast rather than injecting placeholder strings.

## Backend lane selection

Native execution now supports explicit backend selection lanes:

```bash
zig build run -- --backend native --execute --backend-lane vulkan_dawn_release
zig build run -- --backend native --execute --backend-lane d3d12_doe_app
zig build run -- --backend native --execute --backend-lane metal_doe_comparable
zig build run -- --backend native --execute --backend-lane metal_doe_release
zig build run -- --backend native --execute --backend-lane metal_dawn_release
zig build run -- --backend native --execute --backend-lane d3d12_doe_release
```

Lane policy is contractized in `config/backend-runtime-policy.json`. Trace metadata records:

- `backendId`
- `backendSelectionReason`
- `fallbackUsed`
- `selectionPolicyHash`
- `backendLane`

### Command replay examples for AI workload command derivatives

- `kernel_dispatch` with `kernel` label and dispatch dimensions: `examples/kernel_dispatch_commands.json`
- `kernel_dispatch` accepts optional `repeat` (aliases: `dispatch_count`, `dispatchCount`), default `1`.
- `kernel_dispatch` accepts optional `warmup_dispatch_count` (`warmupDispatchCount`) to run untimed warmup dispatches before timed dispatch execution, default `0`.
- `kernel_dispatch` accepts optional `initialize_buffers_on_create` (`initializeBuffersOnCreate`) to zero-fill newly created bound buffers before first use, default `false`.
- `render_draw` supports repeated draw-call submission via `draw_count`/`drawCount`,
  optional `first_vertex`/`firstVertex` and `first_instance`/`firstInstance`,
  indexed mode via `draw_indexed` with required `index_data`/`indexData`/`indices`,
  optional `index_format`/`indexFormat` (`uint16`|`uint32`), and optional indexed-draw fields
  `index_count`/`indexCount`, `first_index`/`firstIndex`, and `base_vertex`/`baseVertex`,
  optional target size/format overrides, and explicit state-set variants:
  `pipelineMode` (`static` | `redundant`) and `bindGroupMode` (`no-change` | `redundant`).
- `render_draw` also accepts:
  `encodeMode` (`render-pass` | `render-bundle`),
  viewport fields (`viewportX`, `viewportY`, `viewportWidth`, `viewportHeight`, `viewportMinDepth`, `viewportMaxDepth`),
  scissor fields (`scissorX`, `scissorY`, `scissorWidth`, `scissorHeight`),
  blend constants (`blendR`, `blendG`, `blendB`, `blendA`),
  `stencilReference`, and `bindGroupDynamicOffsets` (single dynamic-uniform offset).
- `texture_query` can optionally include expected values (`width`, `height`, `depthOrArrayLayers`, `format`,
  `dimension`, `viewDimension`, `sampleCount`, `usage`) to assert runtime `wgpuTextureGet*` results.
- runtime command families now include:
  `sampler_create`/`sampler_destroy`,
  `texture_write`/`texture_query`/`texture_destroy`,
  `surface_create`/`surface_capabilities`/`surface_configure`/`surface_acquire`/`surface_present`/`surface_unconfigure`/`surface_release`,
  and `async_diagnostics`.
- alias names accepted in command inputs:
  - `upload` | `buffer_upload`
  - `copy_buffer_to_texture` | `texture_copy` | `copy_texture` | `copy_buffer_to_buffer` | `copy_texture_to_buffer`
  - `dispatch` | `dispatch_workgroups` | `dispatch_invocations`
  - `dispatch_indirect`
  - `kernel_dispatch`
  - `render_draw` | `draw` | `draw_call` | `draw_indexed`
  - `draw_indirect` | `draw_indexed_indirect` | `render_pass`
  - `sampler_create` | `create_sampler`, `sampler_destroy` | `destroy_sampler`
  - `texture_write` | `write_texture` | `queue_write_texture`, `texture_query` | `query_texture`, `texture_destroy` | `destroy_texture`
  - `surface_create` | `create_surface`, `surface_capabilities` | `get_surface_capabilities`, `surface_configure` | `configure_surface`,
    `surface_acquire` | `acquire_surface_texture`, `surface_present` | `present_surface`,
    `surface_unconfigure` | `unconfigure_surface`, `surface_release` | `release_surface`
  - `async_diagnostics` | `pipeline_async_diagnostics`
- async diagnostics mode values:
  `pipeline_async`, `capability_introspection`, `resource_table_immediates`, `lifecycle_refcount`, `pixel_local_storage`, `full`.
- either `kind` or `command` may carry the command name in command JSON.

## CSL smoke bundle and simulator prep

Build the WGSL-to-CSL smoke bundle emitter:

```bash
zig build csl-bundle-emitter
```

Emit a split `layout.csl` + `pe_program.csl` bundle from the checked-in smoke WGSL fixture:

```bash
zig-out/bin/doe-csl-bundle-emitter \
  --wgsl runtime/zig/examples/wgsl/csl-gelu-smoke.wgsl \
  --out-dir /tmp/csl-gelu-smoke
```

The generated bundle is intended for the governed CSL smoke lane and the simulator
contract runner. It does not claim full model-runtime execution.
