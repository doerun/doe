# Track A Seam Edit Plan (Draft)

## Status

`draft`

## Goal

Start Chromium-side integration with minimal, reversible edits:

1. add selector control (`dawn|doe|auto`),
2. keep Dawn default,
3. add explicit fallback reason plumbing,
4. keep all logic scoped to WebGPU seam.

## Edit Set 0: Flag and Preference Plumbing

## Candidate Files

1. `src/gpu/config/gpu_switches.h`
2. `src/gpu/config/gpu_switches.cc`
3. `src/gpu/ipc/common/gpu_preferences.mojom`
4. `src/gpu/ipc/common/gpu_preferences_mojom_traits.h`

## Patch Intention

1. Add runtime selector switch string constant (default `auto`, but behavior defaults to Dawn unless all Fawn gates pass).
2. Add kill-switch boolean preference.
3. Phase 0 focuses only on selector and kill-switch plumbing; fallback reason and selected-runtime telemetry fields are deferred to Edit Set 1/3.

### Status (2026-02-24)

Implemented in local Chromium checkout:

1. Added WebGPU runtime selector switches:
   - `--use-webgpu-runtime=auto|dawn|doe`
   - `--disable-webgpu-doe`
2. Added GPU preference fields:
   - `webgpu_runtime_selection` (`kAuto|kDawn|kDoe`)
   - `disable_webgpu_doe` (`bool`)
3. Wired fields through GPU preference parsing and mojo serialization:
   - `service_utils.cc`
   - `gpu_preferences.mojom`
   - `gpu_preferences_mojom_traits.h`
   - `gpu_preferences_unittest.cc`
4. Verified compile and test:
   - `autoninja -C out/fawn_debug chrome`
   - `autoninja -C out/fawn_debug gpu_unittests`
   - `./out/fawn_debug/gpu_unittests --gtest_filter=GpuPreferencesTest.EncodeDecode`

## Guardrails

1. No behavior change when switch unset.
2. Unknown selector values fail closed to Dawn and emit typed reason.

## Edit Set 1: Runtime Selection Bridge

## Candidate Files

1. `src/gpu/ipc/service/gpu_init.cc`
2. `src/gpu/ipc/service/webgpu_command_buffer_stub.cc`
3. `src/gpu/ipc/service/webgpu_command_buffer_stub.h`

## Patch Intention

1. Introduce a narrow selector bridge function:
   - input: preferences + adapter/profile + runtime availability
   - output: selected runtime + fallback reason
2. Keep existing Dawn proc path untouched as baseline branch.
3. Add Doe branch behind selector contract with immediate Dawn fallback on any precondition failure.

### Status (2026-02-24)

Implemented in local Chromium checkout:

1. Added a runtime-selection bridge in:
   - `src/gpu/ipc/service/webgpu_command_buffer_stub.cc`
2. Added typed selection/fallback decision model:
   - selected runtime: `dawn|doe`
   - fallback reasons:
     - `none`
     - `global_disable_active`
     - `profile_denylisted`
     - `runtime_artifact_missing`
     - `runtime_artifact_load_failed`
     - `symbol_surface_incomplete`
3. Added selection telemetry emission:
   - trace event `WebGPU.RuntimeSelection` with mode, selected runtime, and fallback reason.
4. Enforced forced-runtime fail-fast behavior:
   - `--use-webgpu-runtime=doe` now returns fatal failure if Doe is unavailable or globally disabled.
5. Preserved Dawn-default behavior:
   - `auto` and `dawn` continue to run on Dawn path.
6. Verified compile after bridge edits:
   - `autoninja -C out/fawn_debug chrome`
7. Added selector policy helper extraction for testability:
   - `src/gpu/ipc/service/webgpu_runtime_selection.{h,cc}`
8. Added selector policy unit tests:
   - `src/gpu/ipc/service/webgpu_runtime_selection_unittest.cc`
   - verifies decision outcomes for `dawn|auto|doe` and fallback precedence

## Guardrails

1. No process model changes.
2. No compositor/Skia Graphite coupling.
3. Forced `doe` mode must fail fast when branch/runtime preconditions are unmet; no silent Dawn substitution.

## Edit Set 2: Blocklist and Denylist Hook

## Candidate Files

1. `src/gpu/config/webgpu_blocklist_impl.cc`
2. `src/gpu/config/software_rendering_list.json` (only if strictly needed)

## Patch Intention

1. Map denylist result into selector precondition check.
2. Emit typed fallback reason on denylist hit.

### Status (2026-02-24, partial)

Implemented as a precondition inside the Set 1 runtime selector bridge:

1. Selector now checks `gpu_feature_info.status_values[GPU_FEATURE_TYPE_ACCELERATED_WEBGPU]`.
2. `kGpuFeatureStatusSoftware` is treated as denylisted profile for Doe selection preconditions.
3. Typed fallback reason emitted as:
   - `profile_denylisted`
4. Selector now probes configured/default runtime artifact and symbol availability:
   - `--doe-webgpu-library-path`
   - `runtime_artifact_missing`
   - `runtime_artifact_load_failed`
   - `symbol_surface_incomplete`

Deferred for full Set 2:

1. Dedicated `webgpu_blocklist_impl` integration for adapter-level reason detail.
2. Denylist reason propagation beyond stub-level selection telemetry.

## Guardrails

1. Do not create hidden per-adapter behavior.
2. All denylist-triggered fallbacks must be typed and observable.

## Edit Set 3: Telemetry and Test Skeleton

## Candidate Files

1. GPU/WebGPU unit tests under `src/gpu/*`
2. Browser tests that exercise selector and fallback paths.

## Required Negative Cases

1. Missing artifact -> `runtime_artifact_missing`
2. Symbol mismatch -> `symbol_surface_incomplete`
3. Denylist hit -> `profile_denylisted`
4. Global disable -> `global_disable_active`
5. Forced `doe` init failure -> hard error (no silent Dawn fallback)

### Status (2026-02-24, partial)

1. Decision-policy unit tests now cover denylist/global-disable/unavailable/available cases.
2. Selector-precedence test added:
   - denylist reason wins over kill-switch and artifact-unavailable reasons.
3. End-to-end browser tests for forced-doe init failure are still pending.

## Edit Set 4: Decoder Runtime Execution Wiring

## Candidate Files

1. `src/gpu/command_buffer/service/webgpu_decoder.h`
2. `src/gpu/command_buffer/service/webgpu_decoder.cc`
3. `src/gpu/command_buffer/service/webgpu_decoder_impl.h`
4. `src/gpu/command_buffer/service/webgpu_decoder_impl.cc`
5. `src/gpu/command_buffer/service/webgpu_proc_table_entries.inc` (new)
6. `src/gpu/ipc/service/gpu_init.cc`
7. `src/gpu/ipc/service/webgpu_command_buffer_stub.cc`

## Patch Intention

1. Remove implicit Dawn-only assumptions in decoder startup path.
2. Thread an explicit runtime enum into decoder creation.
3. Enable concrete Doe runtime execution path while preserving Dawn fallback behavior.
4. Keep proc dispatch thread-scoped and deterministic.

### Status (2026-02-24, landed with follow-ups)

1. Decoder creation now receives explicit runtime enum (`kDawn|kDoe`).
2. `WebGPUDecoderImpl` has Doe branch that:
   - loads `libdoe_webgpu.so`,
   - populates proc table from `wgpuGetProcAddress`,
   - creates `WGPUInstance`,
   - injects instance into wire server,
   - scopes thread procs during command execution/polling,
   - releases instance/library during teardown.
3. Doe availability/surface probing moved to generated proc-table validation (`webgpu_proc_table_entries.inc`).
4. GPU process proc bootstrap switched to thread-dispatch mode with Dawn-native default thread procs.
5. Crash fix added in `WebGPUCommandBufferStub` destructor:
   - guard `decoder_context()` before `Destroy(false)`.
6. Revalidated:
   - `autoninja -C out/fawn_debug gpu_unittests`
   - `autoninja -C out/fawn_debug chrome`
   - `out/fawn_debug/gpu_unittests --gtest_filter=WebGPURuntimeSelectionTest.*:GpuPreferencesTest.EncodeDecode`
7. Remaining:
   - direct unit/integration tests for decoder Doe init/teardown failure branches,
   - validation under non-denylisted GPU profile.

## Bring-Up Sequence for Edits

1. Edit one set at a time.
2. `gn gen out/fawn_debug --args='is_debug=true'`
3. `autoninja -C out/fawn_debug chrome`
4. Run narrow target tests for touched module first.
5. Record selector/fallback artifact evidence per run.

## Exit Criteria for First Integration PR Slice

1. Flag/pref plumbing merged locally and compiles.
2. Dawn default behavior unchanged.
3. Selector decision and fallback reason observable in artifacts/logging.
4. At least one negative test path validated.

## Edit Set 5: Browser API surface completion (`GPUCanvasContext`, `GPUExternalTexture`)

## Candidate Files (apply in lane/src when mounted)

### Canvas path

1. `src/third_party/blink/renderer/modules/webgpu/gpu_canvas_context.idl`
2. `src/third_party/blink/renderer/modules/webgpu/gpu_canvas_context.h`
3. `src/third_party/blink/renderer/modules/webgpu/gpu_canvas_context.cc`
4. `src/third_party/blink/renderer/modules/webgpu/html_canvas_element.cc` (if needed for canvas binding assertions)

### Device/queue path

1. `src/third_party/blink/renderer/modules/webgpu/gpu_device.idl`
2. `src/third_party/blink/renderer/modules/webgpu/gpu_device.h`
3. `src/third_party/blink/renderer/modules/webgpu/gpu_device.cc`
4. `src/third_party/blink/renderer/modules/webgpu/gpu_queue.idl`
5. `src/third_party/blink/renderer/modules/webgpu/gpu_queue.h`
6. `src/third_party/blink/renderer/modules/webgpu/gpu_queue.cc`

### External texture path

1. `src/third_party/blink/renderer/modules/webgpu/gpu_external_texture.idl`
2. `src/third_party/blink/renderer/modules/webgpu/gpu_external_texture.h`
3. `src/third_party/blink/renderer/modules/webgpu/gpu_external_texture.cc`
4. `src/third_party/blink/renderer/modules/webgpu/gpu_texture.h`
5. `src/third_party/blink/renderer/modules/webgpu/gpu_texture.cc`

## Candidate Areas

1. Blink WebGPU API surface and canvas binding ownership.
2. WebGPU device binding points that expose browser-facing device methods and queue methods.
3. External-image transport path from browser resource objects to platform-native shared textures.
4. Swapchain and context-lifecycle integration for presentation paths.

## Patch Intention

1. Make browser `navigator.gpu` canvas APIs deterministic under Fawn mode:
   - preferred canvas format
   - `getContext("webgpu")` flow
   - queue/texture readback behavior used by presentation scenarios
2. Make `GPUDevice.importExternalTexture` and `GPUDevice.copyExternalImageToTexture` explicit in browser mode:
   - fully wired with platform image sources, or
   - explicit unsupported behavior with the same typed reason path used by other seam failures.
3. Keep all edits in browser Track A files only; do not change headless runtime package semantics.

### Merge-ready behavior

#### BrowserCanvasContext requirements for Fawn mode

1. `navigator.gpu.getPreferredCanvasFormat()` returns a concrete format via the WebGPU runtime seam.
2. `canvas.getContext("webgpu")` returns a non-null `GPUCanvasContext`.
3. `GPUCanvasContext.configure` and `getCurrentTexture` are present and internally call into the active runtime proc-table.
4. `GPUCanvasContext.unconfigure` and descriptor validation paths remain deterministic under both Dawn and Doe runtime selections.

#### Device queue requirements for Fawn mode

1. `GPUDevice.importExternalTexture`:
   - either implemented for platform-supported image sources, or
   - returns `OperationError` with typed unsupported reason consistent with fallback taxonomy.
2. `GPUQueue.copyExternalImageToTexture` follows same determinism contract and telemetry format.
3. `webgpu_playwright` smoke probes for both methods are required to run in both dawn/doe modes before merge.

#### Test and gate requirements

1. Add/extend Blink unit tests in `third_party/blink/renderer/modules/webgpu/*_test.cc` for both APIs.
2. Update browser smoke/layered probes to assert:
   - `webgpuCanvasApi.webgpuContextAvailable === true`
   - `webgpuDeviceApi.hasImportExternalTexture === true` or explicit typed unsupported
3. Add browser gate rule requiring no required-L1 regression for the two APIs before Track A claiming.

### Readiness criteria

1. Browser smoke/layered probes report:
   - `offscreenCanvasAvailable === true`
   - `webgpuContextAvailable === true`
2. `importExternalTexture`/`copyExternalImageToTexture` either both behave deterministically or emit typed unsupported with traceable telemetry.
3. Regression checks confirm no hidden runtime switching introduced by this API layer.

### Status (2026-03-17, merge-ready queue)

1. Runtime probes were instrumented at browser harness level.
2. Chromium checkout touchpoint edits are still pending until lane source is mounted.
3. This edit set now has explicit implementation targets and gate requirements in Blink API surface files.
