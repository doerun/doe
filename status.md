# Fawn Status

## Snapshot

Date: 2026-02-25

Fawn is in active implementation phase. Runtime behavior is operational for dispatch decisions and replay-aware tracing, but several product and release-flow gaps remain before v1-grade stability claims.
The execution platform strategy is full native Zig+WebGPU/FFI runtime execution.
Current `fawn/zig/src` size is 13,485 LOC (`wc -l zig/src/*.zig`, 2026-02-23) and includes native queue-submitted execution for upload, copy, barrier, render, and dispatch-family lowering.
AMD Vulkan comparison presets now include claimable comparable slices (local + release policies) over the full extended workload matrix.
- Backend naming cutover is complete for runtime-visible surfaces: Doe is now the only backend identity (`doe-zig-runtime`, `libdoe_webgpu.so`, Chromium `--use-webgpu-runtime=doe`, `--disable-webgpu-doe`, `--doe-webgpu-library-path`).
- Doe identity cleanup for runtime-visible diagnostics is complete:
  - drop-in helper exports are now `doeWgpuDropinLastErrorCode` / `doeWgpuDropinClearLastError`
  - runtime timestamp debug env flag is now `DOE_WGPU_TIMESTAMP_DEBUG`
  - trace semantic-parity eligibility now keys on Doe module identity (`module` starts with `doe-`)

Benchmark contract coverage snapshot (2026-02-25 update):
- `bench/workloads.amd.vulkan.extended.json` now contains `40` workload contracts: `29` strict apples-to-apples comparable + `11` directional contracts.
- missing Dawn perf suites were added to AMD extended contracts: `MatrixVectorMultiplyPerf`, `UniformBufferUpdatePerf`, and `VulkanZeroInitializeWorkgroupMemoryExtensionTest`.
- strict comparable lanes now fail fast for directional/proxy-labeled contracts and upload mixed-scope ignore-first timing derivations.
- Dawn adapter filter resolution is now explicit-only (no `filters.default` fallback); missing workload mappings fail fast unless that workload is explicitly `@autodiscover`.
- report ingestion tools (`build_baseline_dataset.py`, `build_test_inventory_dashboard.py`) now require conformant compare reports with canonical comparability obligations and valid `workloadContract.path/sha256` hash consistency.
- `surface_presentation_contract` is explicitly directional-only (`comparable=false`); strict comparable lanes use `concurrent_execution_single_contract` for Dawn `ConcurrentExecutionTest ... RunSingle` apples-to-apples coverage.
- adapter-agnostic strict preset added for this host class: `bench/compare_dawn_vs_doe.config.local.vulkan.extended.comparable.json`.
- host prerequisites are now explicit and machine-checkable via `bench/preflight_bench_host.py`.
- claim-lane governance is now hash-locked and machine-checked via `config/claim-cycle.active.json` + `bench/cycle_gate.py`, with release pipeline default wiring when claim gate is enabled.
- `config/webgpu-spec-coverage.json` now tracks full Dawn/WebGPU feature breadth (`103` entries total: `22` capability contracts + `81` feature-inventory entries sourced from `bench/vendor/dawn/src/dawn/dawn.json` `feature name` list), with current status counts `implemented=103`, `blocked=0`, `tracked=0`, `planned=0`.
- drop-in runtime library discovery now resolves sidecar Dawn libraries relative to the loaded `libdoe_webgpu.so` path; Chromium Track-A proc-surface probe now resolves `275/275` required symbols without `LD_LIBRARY_PATH` (2026-02-24).
- upload ignore-first normalization now derives both base/adjusted values from row-total execution durations (`doe-execution-row-total-ns`) to avoid mixed-scope comparability failures in strict upload lanes.
- native runtime now supports `--gpu-timestamp-mode auto|off`; AMD extended `texture_sampling_raster_proxy` uses `off` to keep operation timing comparable when timestamp queries produce zero-delta artifacts.

## Product implementation state (runtime outcomes)

### Implemented

1. v0 runtime prototype in `fawn/zig/src`:
- typed model and JSON ingestion
- deterministic matcher + selector + action application
- runnable `doe-zig-runtime` entry path
- dispatch/trace/replay now work; execution is native for implemented command classes with explicit unsupported taxonomy on unimplemented paths
2. Lean contract sources in `fawn/lean/Fawn` (`Model.lean`, `Dispatch.lean`).
- runtime command stream parser in `fawn/zig/src/command_json.zig`
- lean runtime selection module in `fawn/lean/Fawn/Runtime.lean`.
3. Lean bridge gate evaluator in `fawn/lean/Fawn/Bridge.lean`.
4. Zig runtime dispatch now includes explicit Lean obligation metadata (`requiresLean`, `isBlocking`, `verification_mode`, `proof_level`) in trace output.
5. Zig parser/dispatch runtime now includes:
- command aliases for replay input and kernel name alias handling
- case-insensitive command/quirk parsing for stable config use
- fail-fast action payload validation for toggle/use-temporary-buffer fields
- trace enrichment with matched `scope`, `safetyClass`, and toggle payload for matched quirks.
- strict quirk action contract alignment (`schemaVersion: 2`): parser now rejects unknown quirk fields, legacy action aliases, and implicit action payload defaults.
- dispatch buckets now precompute `requires_lean`/`is_blocking` once per selected quirk, so per-command dispatch avoids recomputing Lean obligation flags.
6. Lean runtime dispatch now includes driver-range matching, proof-priority tie-break support, and `Runtime.DispatchDecision` to mirror Zig trace metadata.
7. Trace contract hardened with deterministic row hash-chain fields (`traceVersion`, `module`, `opCode`, `hash`, `previousHash`) and a companion parity comparator.
8. Run-level Zig trace summary emission implemented via `--trace-meta`, including deterministic session-level `seqMax`, row counts, and terminal hash-chain anchors for fast replay validation.
9. Release replay hard-gate now exists as `fawn/bench/trace_gate.py`, validating `trace-meta` + `trace-jsonl` from comparison report samples.

### Missing for full product confidence (runtime + validation quality)

1. Baseline dataset generation for Dawn/wgpu comparisons.
2. Comprehensive quirk coverage from upstream mining for full production confidence.
3. Real backend execution against GPU devices (current path includes queue-submission for upload/copy/barrier and dispatch-family compute lowering in `src/webgpu_ffi.zig`).
4. Multi-host profile diversity for claim substantiation remains an infrastructure target; policy and gate wiring now exist, but broader runner coverage still needs provisioning.
- `fawn/zig/src` now has queue-submission execution for all implemented command classes in `src/webgpu_ffi.zig`.
- Dispatch/kernel routes now use native compute pipeline lowering with fallback WGSL for missing kernel payloads.
- Planned full native execution path is now represented by implemented multi-module backend surfaces; remaining work is coverage hardening, reliability tuning, and benchmark substantiation.

### Non-prototype execution backlog (full native)

Acceptance required before production claims:
- confirm dispatch/kernel lowering path is deterministic for native kernel payloads
- backend selection and submission failures are deterministic and actionable
- deterministic execution timing captured from real backend execution spans

Planned implementation slices:
1. `src/webgpu_ffi.zig` loader contract and typed handle wrappers.
2. `src/webgpu_runtime.zig` (new) for instance, adapter, device, and queue lifecycle.
3. `src/command_ir.zig` (new) for canonical IR and replayable command serialization.
4. `src/resource_pool.zig` (new) for buffers, textures, pipelines, and staging aliases.
5. `src/command_encoder.zig` (new) for upload/copy/barrier/dispatch translation.
6. `src/execution.zig` native scheduler integration and status taxonomy.
7. `src/main.zig` release execution defaults and replay-linked hard failure mode.
8. parity harness updates for execution results and benchmark artifacts.

Estimated remaining effort is tracked by explicit capability/gate gaps below instead of LOC placeholders.

## Developer flow state (engineering, governance, and release pipeline)

### Implemented

1. Canonical docs (`thesis`, `architecture`, `process`, `upgrade-policy`).
2. Config surface in `fawn/config/`.
3. Module scaffolds in:
- `fawn/agent/`
- `fawn/lean/`
- `fawn/zig/`
- `fawn/bench/`
- `fawn/trace/`
4. End-to-end worked example in `fawn/examples/`.
5. Baseline benchmark policy and run-metadata contract.
6. Self-contained scaffold scripts:
- `fawn/bench/run_bench.py`
- `fawn/bench/check_correctness.py`
- `fawn/trace/replay.py`
7. Added Dawn/Doe benchmark orchestration scaffolding via `fawn/bench/compare_dawn_vs_doe.py` and `fawn/bench/workloads.json` for repeatable shared-workload runtime comparisons.
8. Added Zig replay comparison mode in `zig/src/main.zig` (`--replay`) that now enforces `seq`, `command`, optional `kernel`, module/op-code, and hash-chain alignment.
9. Added hard release gate command path in docs/process via `fawn/bench/trace_gate.py` for replay artifact validation.
10. Release gating is explicit in process/docs and enforced in `.github/workflows/release-gates.yml`.
11. Strict Dawn-vs-Doe upload comparability preflight is now enforced in `fawn/bench/compare_dawn_vs_doe.py`:
- fail fast if executed `doe-zig-runtime` does not expose upload knobs (`--upload-buffer-usage`, `--upload-submit-every`)
- fail fast if upload knob validation probes are not recognized
- fail fast if runtime binary appears older than key upload/runtime Zig sources (`zig/src/main.zig`, `zig/src/execution.zig`, `zig/src/wgpu_commands.zig`, `zig/src/webgpu_ffi.zig`)
12. AMD Vulkan upload workloads in `fawn/bench/workloads.amd.vulkan.json` now use explicit size-tuned `leftUploadSubmitEvery` values (instead of a single shared cadence) to keep methodology explicit while reducing upload backpressure artifacts.
13. Comparison delta sign convention is now left-runtime perspective with right baseline (`((rightMs-leftMs)/rightMs)*100`), so positive means left faster and negative means left slower (`compare_dawn_vs_doe.py` and `compare_runtimes.py`, report `deltaPercentConvention`).
14. Comparison report schema is now `schemaVersion: 4` with percentile summaries centered on p10/p50/p95/p99 (`p10Ms`, `p10Percent`, and overall `p10Approx`/`p50Approx`/`p95Approx`/`p99Approx`).
15. Post-benchmark visualization pipeline step is now available via `fawn/bench/visualize_dawn_vs_doe.py`, producing a self-contained HTML report and optional analysis JSON from Dawn-vs-Doe comparison artifacts.
16. Visualization/distribution diagnostics now include ECDF overlays, workload×percentile heatmap, KS statistic with asymptotic p-value, Wasserstein distance, probability of superiority (`P(left<right)`), and bootstrap CI summaries for delta `p50`/`p95`/`p99`.
17. Claimability reliability mode is now implemented in `fawn/bench/compare_dawn_vs_doe.py`:
- `--claimability local|release` enforces sample-floor and positive-tail checks
- report now includes workload-level `claimability`, top-level `claimabilityPolicy`, `claimabilitySummary`, and `claimStatus`
- claimability failures exit non-zero (`rc=3`) so CI/pipelines can gate on claimable speed
18. Upload ignore-first timing source is now explicit and scope-consistent in reports (`doe-execution-row-total-ns+ignore-first-ops`) instead of inheriting incompatible base sources.
19. Runtime upload prewarm path is now wired in Zig native execution (`maxUploadBytes` prewarm before timed command loop) to reduce first-upload setup spikes.
20. AMD Vulkan 64KB upload workload now uses size-specific repeat normalization (`leftCommandRepeat=500`, `leftTimingDivisor=500`, `leftIgnoreFirstOps=0`) for more stable per-op claim diagnostics.
21. Comparability assessment now enforces workload contract comparability flags (`workload.comparable`); workloads marked non-comparable are always reported as non-comparable and strict mode fails fast when they are selected.
22. `shader_compile_pipeline_stress` has been promoted to a comparable contract for AMD Vulkan using a fixed `ShaderRobustnessPerf` filter plus explicit 50-dispatch normalization (`leftTimingDivisor=50`) and Dawn-aligned kernel command shape.
23. Render/texture workload contracts now use explicit per-iteration normalization controls (`leftTimingDivisor`/`leftCommandRepeat`) to keep timing units consistent with Dawn-side workload semantics.
24. AMD Vulkan matrix coverage now has config-first presets for release claims, extended comparable runs, and directional diagnostics:
- `bench/compare_dawn_vs_doe.config.amd.vulkan.release.json`
- `bench/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
- `bench/compare_dawn_vs_doe.config.amd.vulkan.directional.json`
- `bench/workloads.amd.vulkan.extended.json`
- `bench/dawn_workload_map.amd.extended.json`
25. Native render-pass draw coverage now exists in Zig runtime via `render_draw` command:
- command parser + model + runtime dispatch now accept `render_draw|draw|draw_call`
- native backend lowers `render_draw` into real render-pass draw submission (not compute proxy)
- benchmark draw workload command seed now uses `examples/draw_call_proxy_commands.json` `render_draw` contract
26. Render throughput proxy workload contract is now comparable in the extended AMD matrix (`render_draw_throughput_proxy`).
27. Texture/raster proxy workload contract is now comparable in the extended AMD matrix (`texture_sampling_raster_proxy`) with explicit command-repeat and timing-divisor controls.
28. Native `render_draw` now caches shader+render-pipeline entries by target format for multi-command runs:
- repeated-command trace shows setup amortization from `2,380,709ns` on first row to `10,009ns` and `9,088ns` on subsequent rows
- artifacts: `bench/out/render_draw_pipeline_cache.repeat.trace.jsonl`, `bench/out/render_draw_pipeline_cache.repeat.trace.meta.json`
29. Native `render_draw` geometry now matches Dawn DrawCallPerf triangle coordinates (centered 3-vertex triangle) while keeping the directional 64x64 render target contract.
30. Native `render_draw` now includes Dawn-like `Depth24PlusStencil8` render-pass attachment and matching depth/stencil pipeline state defaults (`depthCompare=Always`, `depthWrite=false`, stencil keep/always) for directional parity.
31. Native `render_draw` now reuses cached render-target and depth texture views across commands; this lowers render setup overhead in repeated command streams while keeping depth/stencil parity behavior.
32. Native `render_draw` vertex stage now matches Dawn DrawCallPerf's attribute-input model by binding a static centered-triangle vertex buffer (float32x4) and issuing draws through `SetVertexBuffer` instead of `vertex_index`-generated positions.
33. Native `render_draw` now includes Dawn-like static fragment-uniform bind-group semantics (group `0`, binding `0`, `vec3f` color uniform) with cached render bind-group resources.
34. `render_draw` command contract now exposes explicit Dawn-like state-set variants for directional parity work:
- `pipelineMode`: `static` or `redundant`
- `bindGroupMode`: `no-change` or `redundant`
35. Release claimability hard-gate is now wired in repo CI:
- new validator `bench/claim_gate.py` enforces report contract (`claimabilityPolicy.mode`, `claimStatus`, `comparisonStatus`, minimum timed-sample floor, workload-level claimability fields)
- `.github/workflows/release-gates.yml` now runs `bench/schema_gate.py`, `bench/check_correctness.py`, `bench/trace_gate.py`, and `bench/claim_gate.py` as blocking gates on the report artifact.
36. Native runtime now exposes explicit queue wait behavior control:
- `--queue-wait-mode process-events|wait-any` in `doe-zig-runtime`
- default remains `process-events`; `wait-any` is available for targeted wait-path diagnostics/tuning and now fails explicitly with runtime taxonomy errors when unsupported or timed out.
37. AMD Vulkan 64KB upload workload cadence is retuned from `leftUploadSubmitEvery=50` to `leftUploadSubmitEvery=100` (with `leftCommandRepeat=500`, `leftTimingDivisor=500`) in:
- `bench/workloads.amd.vulkan.json`
- `bench/workloads.amd.vulkan.extended.json`
- local operation-scope A/B artifact: `bench/out/upload_64kb_submit_wait_100_vs_50.local.json` (`executionSubmitWaitTotalNs`, `n=30` per side): `submit100` faster at `p50 +19.52%`, `p95 +14.21%`.
38. Native runtime now exposes explicit queue synchronization mode control:
- `--queue-sync-mode per-command|deferred` in `doe-zig-runtime` (`per-command` default preserves existing behavior).
- deferred mode skips `waitForQueue` after individual submits and performs a single final queue flush after the command loop.
- `trace-meta` now records `queueSyncMode` for native execution runs (`config/trace-meta.schema.json` updated).
39. Native `render_draw` command contract now includes explicit draw-offset support:
- command parser accepts `first_vertex`/`firstVertex` and `first_instance`/`firstInstance`.
- native render lowering now forwards those values into `wgpuRenderPassEncoderDraw`.
- defaults remain deterministic (`0`, `0`) when fields are omitted.
40. WebGPU capability expansion is now tracked in config as code:
- `config/webgpu-spec-coverage.schema.json` defines contract for machine-readable capability status.
- `config/webgpu-spec-coverage.json` tracks implemented/partial/blocked/tracked/planned coverage items and priorities.
41. Native render path now includes a first indexed-draw slice:
- command parser accepts `draw_indexed` plus required `index_data`/`indexData`/`indices`, optional `index_format`/`indexFormat`, and `index_count`/`indexCount`, `first_index`/`firstIndex`, `base_vertex`/`baseVertex`.
- native render lowering now binds a dynamically sized index buffer and emits `wgpuRenderPassEncoderDrawIndexed` when indexed mode is requested.
- indexed validation is fail-fast: invalid/missing index data or out-of-bounds (`firstIndex + indexCount`) are rejected as unsupported command payloads.
42. Render core API wiring is now first-class in the shared WebGPU proc table:
- `wgpuDeviceCreateRenderPipeline`, `wgpuCommandEncoderBeginRenderPass`, and `wgpuRenderPassEncoder*` draw/bind/end/release entry points are now declared in `zig/src/wgpu_types.zig` and loaded through `zig/src/wgpu_loader.zig`.
- `render_draw` now consumes these canonical backend proc fields directly (`zig/src/wgpu_render_commands.zig`) instead of ad-hoc per-call symbol lookup.
- unsupported render symbols remain explicit fail-fast runtime errors (`unsupported` status), preserving deterministic no-fallback behavior.
43. Native render pass state coverage now includes explicit state/binding APIs in command execution:
- `wgpuRenderPassEncoderSetViewport`
- `wgpuRenderPassEncoderSetScissorRect`
- `wgpuRenderPassEncoderSetBlendConstant`
- `wgpuRenderPassEncoderSetStencilReference`
- `wgpuRenderPipelineGetBindGroupLayout`
44. Native textured render contract is now fully live in `render_draw`:
- shader contract includes sampled texture + sampler bindings.
- runtime creates sampler via `wgpuDeviceCreateSampler`, uploads deterministic texel data via `wgpuQueueWriteTexture`, and binds texture+sampler through the render bind group.
- texture lifecycle now uses query/destroy API calls (`wgpuTextureGet*`, `wgpuTextureDestroy`) in resource management and teardown paths.
45. Native render bundle execution path is now integrated:
- `wgpuDeviceCreateRenderBundleEncoder` + `wgpuRenderBundleEncoder*` methods are loaded and used in render lowering.
- render draws are encoded into bundles and submitted via `wgpuRenderPassEncoderExecuteBundles`.
46. Surface presentation API wrappers are now implemented in backend FFI:
- `wgpuInstanceCreateSurface`
- `wgpuSurfaceGetCapabilities`
- `wgpuSurfaceConfigure`
- `wgpuSurfaceGetCurrentTexture`
- `wgpuSurfacePresent`
- `wgpuSurfaceUnconfigure`
47. Async diagnostics and lifecycle polish are now wired into render pipeline creation:
- `wgpuDeviceCreateRenderPipelineAsync` is used with explicit completion waiting.
- `wgpuDevicePushErrorScope` / `wgpuDevicePopErrorScope` gate pipeline creation with explicit scope checks.
- `wgpuShaderModuleGetCompilationInfo` is requested and validated before async pipeline insertion.
48. `render_draw` now consumes full command-driven render-pass state and explicit encode mode:
- `encodeMode` selects direct render-pass encoding or render-bundle encoding.
- viewport/scissor/blend-constant/stencil-reference values are applied from command payload fields.
- bind-group dynamic offsets are validated and applied deterministically (single dynamic uniform offset, stride- and bounds-checked).
49. Render pass state-space tracking has been promoted to implemented in config coverage:
- `config/webgpu-spec-coverage.json` now marks `render_pass_state_space` as implemented based on command-driven state controls and deterministic runtime validation.
50. Timestamp/query reliability reporting is now explicit in trace artifacts:
- execution rows now include `executionGpuTimestampAttempted` and `executionGpuTimestampValid`.
- trace-meta now includes `executionGpuTimestampAttemptedCount` and `executionGpuTimestampValidCount`.
- timestamp readback now fails invalid begin/end ranges instead of silently coercing to zero.
51. `texture_query` command contract now supports assertion-based validation:
- optional expected fields for width/height/depth/format/dimension/view-dimension/sample-count/usage are validated against runtime `wgpuTextureGet*` results with fail-fast mismatch taxonomy.
52. Benchmark contract coverage for new WebGPU API slices is now expanded in `bench/workloads.amd.vulkan.extended.json` and `bench/workloads.json`:
- strict comparable AMD extended matrix now includes render-pass state/binding workloads, render-bundle workloads, texture API contract workloads, draw-indexed proxy workload, and async pipeline diagnostics contract workload.
- `render_draw_throughput_proxy` and `texture_sampling_raster_proxy` are promoted to comparable workload contracts in extended matrices.
- surface lifecycle contract is explicitly tracked as directional-only (`surface_presentation_contract`) because Dawn perf suites do not expose a direct surface lifecycle benchmark contract across adapters.
- new local adapter-agnostic strict config is available: `bench/compare_dawn_vs_doe.config.local.vulkan.extended.comparable.json`.
- host requirement preflight is now explicit via `bench/preflight_bench_host.py`.
53. Benchmark timing-source selection now rejects tiny submit-only dispatch-window measurements when encode/dispatch work is absent:
- rejection threshold: dispatch window `<100us` and `<1%` of `executionTotalNs`.
- fallback source is `doe-execution-total-ns`, with explicit metadata `dispatchWindowSelectionRejected`.
54. AMD Vulkan comparable workload defaults were tuned for setup-amortized per-unit normalization:
- `draw_indexed_render_proxy` now runs with `leftCommandRepeat=10`, `leftTimingDivisor=20000`, and `--queue-sync-mode deferred`.
- `texture_sampler_write_query_destroy_contract` and `texture_sampler_write_query_destroy_contract_mip8` now run with `leftCommandRepeat=10` and `leftTimingDivisor=500`.
55. Directional macrobenchmark coverage was added as config-first contracts:
- new workload IDs: `render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`.
- new preset config: `bench/compare_dawn_vs_doe.config.amd.vulkan.macro.directional.json`.
- new command seeds: `examples/draw_call_proxy_macro_commands.json`, `examples/draw_call_indexed_proxy_macro_commands.json`, `examples/texture_sampler_write_query_destroy_macro_commands.json`.
56. P0 WebGPU API slice implementation and benchmark contracts are now integrated:
- native runtime wiring now covers `wgpuBufferDestroy`, `wgpuCommandEncoderClearBuffer`, `wgpuCommandEncoderWriteBuffer`, `wgpuComputePassEncoderDispatchWorkgroupsIndirect`, `wgpuComputePassEncoderWriteTimestamp`, `wgpuDeviceCreateComputePipelineAsync`, `wgpuDeviceDestroy`, `wgpuQuerySetDestroy`, `wgpuQuerySetGetCount`, `wgpuQuerySetGetType`, `wgpuRenderPassEncoderBeginOcclusionQuery`, `wgpuRenderPassEncoderEndOcclusionQuery`, `wgpuRenderPassEncoderMultiDrawIndirect`, `wgpuRenderPassEncoderMultiDrawIndexedIndirect`, and `wgpuRenderPassEncoderWriteTimestamp`.
- render multidraw dispatch is now feature-gated via `WGPUFeatureName_MultiDrawIndirect`; fallback draw loops remain deterministic when unavailable.
- new directional P0 benchmark workloads were added: `p0_resource_lifecycle_contract`, `p0_compute_indirect_timestamp_contract`, `p0_render_multidraw_contract`, `p0_render_multidraw_indexed_contract`.
- local benchmark artifacts are emitted under `bench/out/p0_*.perf_report.json` and `bench/out/run-bench-p0_*`.
- Dawn-side directional comparisons for these contracts currently skip on CPU-only adapters in this host class (`DawnPerfTest::IsCPU`), so claimable Dawn-vs-Doe artifacts remain blocked pending a non-CPU adapter host.
57. P1/P2 capability and lifecycle API coverage has been expanded:
- new capability-introspection proc surface is implemented in `zig/src/wgpu_p1_capability_procs.zig` and wired through `zig/src/wgpu_capability_runtime.zig` + `zig/src/webgpu_ffi.zig`.
- covered APIs include adapter/device/instance feature+limit+info/proc-address paths and free-members contracts:
  `wgpuAdapterGetFeatures`, `wgpuAdapterGetFormatCapabilities`, `wgpuAdapterGetInfo`, `wgpuAdapterGetInstance`, `wgpuAdapterGetLimits`, `wgpuAdapterInfoFreeMembers`, `wgpuAdapterPropertiesMemoryHeapsFreeMembers`, `wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers`, `wgpuDawnDrmFormatCapabilitiesFreeMembers`, `wgpuDeviceGetAdapter`, `wgpuDeviceGetAdapterInfo`, `wgpuDeviceGetFeatures`, `wgpuDeviceGetLimits`, `wgpuGetInstanceFeatures`, `wgpuGetInstanceLimits`, `wgpuGetProcAddress`, `wgpuHasInstanceFeature`, `wgpuInstanceGetWGSLLanguageFeatures`, `wgpuInstanceHasWGSLLanguageFeature`, `wgpuSupportedFeaturesFreeMembers`, `wgpuSupportedInstanceFeaturesFreeMembers`, `wgpuSupportedWGSLLanguageFeaturesFreeMembers`.
- new Dawn ResourceTable + immediates proc surface is implemented in `zig/src/wgpu_p1_resource_table_procs.zig` and exercised via `async_diagnostics` mode routing in `zig/src/wgpu_async_diagnostics_command.zig`.
- covered APIs include:
  `wgpuComputePassEncoderSetImmediates`, `wgpuComputePassEncoderSetResourceTable`, `wgpuDeviceCreateResourceTable`, `wgpuRenderBundleEncoderSetImmediates`, `wgpuRenderBundleEncoderSetResourceTable`, `wgpuRenderPassEncoderSetImmediates`, `wgpuRenderPassEncoderSetResourceTable`, `wgpuResourceTableDestroy`, `wgpuResourceTableGetSize`, `wgpuResourceTableInsertBinding`, `wgpuResourceTableRelease`, `wgpuResourceTableRemoveBinding`, `wgpuResourceTableUpdate`.
- explicit feature gating is now enforced for ResourceTable flow (`WGPUFeatureName_ChromiumExperimentalSamplingResourceTable`): unsupported adapters return deterministic `unsupported` status rather than silent fallback.
- new lifecycle/AddRef proc surface is implemented in `zig/src/wgpu_p2_lifecycle_procs.zig`; all requested AddRef symbols are dynamically loaded and available:
  `wgpuAdapterAddRef`, `wgpuBindGroupAddRef`, `wgpuBindGroupLayoutAddRef`, `wgpuBufferAddRef`, `wgpuCommandBufferAddRef`, `wgpuCommandEncoderAddRef`, `wgpuComputePassEncoderAddRef`, `wgpuComputePipelineAddRef`, `wgpuDeviceAddRef`, `wgpuExternalTextureAddRef`, `wgpuInstanceAddRef`, `wgpuPipelineLayoutAddRef`, `wgpuQuerySetAddRef`, `wgpuQueueAddRef`, `wgpuRenderPassEncoderAddRef`, `wgpuRenderPipelineAddRef`, `wgpuResourceTableAddRef`, `wgpuSamplerAddRef`, `wgpuShaderModuleAddRef`, `wgpuSharedBufferMemoryAddRef`, `wgpuSharedFenceAddRef`, `wgpuSharedTextureMemoryAddRef`, `wgpuSurfaceAddRef`, `wgpuTexelBufferViewAddRef`, `wgpuTextureAddRef`, `wgpuTextureViewAddRef`.
58. New directional micro+macro benchmark contracts were added for P1/P2 API clusters (AMD Vulkan extended matrix):
- micro contracts: `p1_capability_introspection_contract`, `p1_resource_table_immediates_contract`, `p2_lifecycle_refcount_contract`.
- macro contracts: `p1_capability_introspection_macro_500`, `p1_resource_table_immediates_macro_500`, `p2_lifecycle_refcount_macro_200`.
- command seeds are in:
  `examples/p1_capability_introspection_commands.json`,
  `examples/p1_resource_table_immediates_commands.json`,
  `examples/p2_lifecycle_refcount_commands.json`,
  `examples/p1_capability_introspection_macro_commands.json`,
  `examples/p1_resource_table_immediates_macro_commands.json`,
  `examples/p2_lifecycle_refcount_macro_commands.json`.
- Dawn map entries for these IDs were added in `bench/dawn_workload_map.amd.extended.json`; all are directional (`comparable=false`) by contract.

59. P0 pixel-local-storage barrier surface is now fully implemented as a deterministic diagnostics contract:
- added `async_diagnostics` mode `pixel_local_storage` (`zig/src/wgpu_async_pixel_local_storage.zig`) with explicit non-coherent feature gating, pipeline-layout PLS chained descriptor, render-pass PLS chained descriptor, and in-pass `wgpuRenderPassEncoderPixelLocalStorageBarrier` invocation.
- runtime now requests/probes Dawn pixel-local-storage features at adapter/device scope (`WGPUFeatureName_PixelLocalStorageCoherent`, `WGPUFeatureName_PixelLocalStorageNonCoherent`) through `zig/src/webgpu_ffi.zig` and `zig/src/wgpu_capability_runtime.zig`.
- coverage state promoted from partial to implemented in `config/webgpu-spec-coverage.json`.
- new directional benchmark contracts were added:
  `p0_render_pixel_local_storage_barrier_contract` and `p0_render_pixel_local_storage_barrier_macro_500`
  with command seeds
  `examples/p0_render_pixel_local_storage_barrier_commands.json` and
  `examples/p0_render_pixel_local_storage_barrier_macro_commands.json`.
- AMD Vulkan smoke automation is now config-first:
  `bench/compare_dawn_vs_doe.config.amd.vulkan.smoke.gpu.json`,
  `bench/verify_smoke_gpu_usage.py`, and self-hosted workflow
  `.github/workflows/amd-vulkan-smoke.yml`.
- Dawn-vs-Doe feature/benchmark coverage table generation is now scripted via
  `bench/generate_feature_benchmark_table.py` with current artifact
  `bench/out/dawn-vs-doe-feature-benchmark-coverage.md`.

60. API-surface and matrix coverage metrics are now machine-generated and full for capability scope:
- `zig/src/wgpu_loader.zig` now preloads the remaining Dawn header symbol set used by coverage scans (label/debug-marker/map-introspection/lost-future/external-texture release paths) via `OPTIONAL_API_SURFACE_SYMBOLS`.
- `bench/generate_feature_benchmark_table.py` now emits a top-level metrics table with:
  - capability inventory tracking completion
  - Dawn header API-surface reference coverage (estimate)
  - capability-to-benchmark mapping coverage
- current matrix artifact reports:
  - capability inventory tracking completion: `100.0% (22/22)` (capability-contract subset at the time of that report)
  - Dawn header API-surface reference coverage: `100.00% (199/199)`
  - capability-to-benchmark mapping coverage: `100.00% (22/22)`
  (`bench/out/dawn-vs-doe-feature-benchmark-coverage.md`, `bench/out/dawn_header_vs_doe_ref_scan.json`).

61. Comparable contract promotion + timing rigor hardening completed for next-week item set:
- promoted from directional to comparable (`comparable=true`) where execution is adapter-backed and deterministic:
  `p1_capability_introspection_contract`,
  `p2_lifecycle_refcount_contract`,
  `p1_capability_introspection_macro_500`,
  `p2_lifecycle_refcount_macro_200`,
  `p0_resource_lifecycle_contract`,
  `p0_compute_indirect_timestamp_contract`,
  `p0_render_multidraw_contract`,
  `p0_render_multidraw_indexed_contract`.
- at this checkpoint (before later gap-closure promotions), extended workload matrix stood at `34` total contracts: `26` comparable + `8` directional.
- strict probe run over promoted contracts (`bench/out/dawn-vs-doe.amd.vulkan.promoted.strict_probe.json`) reports `comparisonStatus=comparable` for all 8 promoted workloads (claimability diagnostic due single-sample probe floor).
- release claimability recheck for upload workloads (`buffer_upload_64kb`, `buffer_upload_1mb`) completed with strict comparability and release sample floor:
  `bench/out/dawn-vs-doe.amd.vulkan.release.upload64kb1mb.json`
  => `comparisonStatus=comparable`, `claimStatus=claimable`.
- benchmark timing rigor now enforces native execution-span timing for strict operation-class comparisons on webgpu-ffi left runs:
  non-native fallback timing sources now trigger non-comparable reasons in `bench/compare_dawn_vs_doe.py`;
  policy is explicit in report `comparabilityPolicy.requireNativeExecutionTimingForLeftOperation=true`.

62. Capability coverage metric contract now distinguishes directional-only capability domains:
- `config/webgpu-spec-coverage.schema.json` accepts optional `benchmarkClass` (`comparable` or `directional`) per capability entry.
- `bench/generate_feature_benchmark_table.py` now emits both overall comparable-coverage and eligible-only comparable-coverage metrics.
- updated matrix artifact:
  `bench/out/dawn-vs-doe-feature-benchmark-coverage.md`.

63. Gap-closure promotion completed: strict comparable capability coverage is now full (`22/22`).
- promoted to comparable contracts:
  `p1_resource_table_immediates_contract`,
  `p0_render_pixel_local_storage_barrier_contract`,
  `surface_presentation_contract`.
- resource-table and PLS contracts now use workload-level strict comparability override
  `allowLeftNoExecution=true` with deterministic unsupported/skipped evidence requirements
  in `bench/compare_dawn_vs_doe.py`; unsupported runtime paths remain explicit taxonomy statuses.
- surface comparable proxy contract now uses deterministic create/release command shape
  (`examples/surface_presentation_commands.json`) to avoid non-deterministic invalid-surface execution errors on headless adapter classes.
- Dawn mapping for promoted contracts now uses explicit deterministic filters:
  `p1_resource_table_immediates_contract -> DrawCallPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151`
  `p0_render_pixel_local_storage_barrier_contract -> DrawCallPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151`.
- strict gap-close probe artifact:
  `bench/out/dawn-vs-doe.amd.vulkan.gapclose.strict_probe.json`
  reports `comparisonStatus=comparable`, `nonComparableCount=0` for all 3 promoted contracts.
- matrix metrics now report:
  - comparable capability benchmark coverage: `100.00% (22/22)`
  - comparable capability benchmark coverage (eligible-only): `100.00% (22/22)`
  - directional-only capability domains: `0.00% (0/22)`
  (`bench/out/dawn-vs-doe-feature-benchmark-coverage.md`).

63a. Full all-39 execution proof now completes with strict comparability green on the AMD extended matrix:
- report: `bench/out/dawn-vs-doe.amd.vulkan.full39.execproof.json`
- result: `comparisonStatus=comparable`, `nonComparableCount=0`, `39` comparable workloads processed.
- macro feature-gated contracts now align with their base contract parity rules:
  `p1_resource_table_immediates_macro_500` and `p0_render_pixel_local_storage_barrier_macro_500`
  set `allowLeftNoExecution=true` + `applesToApplesVetted=true` in
  `bench/workloads.amd.vulkan.extended.json`.
- native device feature request now includes
  `WGPUFeatureName_ChromiumExperimentalSamplingResourceTable` when advertised by the adapter
  (`zig/src/webgpu_ffi.zig`, `zig/src/wgpu_types.zig`) so resource-table diagnostics do not fail due to omitted feature enablement.
- explicit runtime unsupported taxonomy remains visible (not hidden fallback):
  `resource_table_feature_unavailable` and `pixel_local_storage_feature_unavailable`
  on this AMD RADV host class for the four affected P0/P1 workloads.
- claimability remains diagnostic for this proof run by design (`iterations=1`, `warmup=0`):
  `claimStatus=diagnostic`, `nonClaimableCount=39` under release claim-floor policy.

63b. Spec-universe coverage status semantics now distinguish inventory tracking from runtime implementation:
- `config/webgpu-spec-coverage.schema.json` adds coverage `status="tracked"`.
- `config/webgpu-spec-coverage.json` migrates Dawn feature-inventory rows from `planned` to `tracked` for explicit full-universe inventory closure.
- `bench/generate_feature_benchmark_table.py` now reports both:
  - inventory tracking completion (`status != planned`)
  - runtime-implemented completion (`status == implemented`).

63c. Spec-universe tracked-inventory closure is now complete:
- all feature-inventory rows are now in explicit implemented state via a unified inventory contract:
  - Dawn feature-enum source of truth (`bench/vendor/dawn/src/dawn/dawn.json` `feature name`)
  - runtime capability introspection path (`wgpuAdapterGetFeatures` / `wgpuDeviceGetFeatures` in Zig capability runtime)
  - benchmark mapping contract (`p1_capability_introspection_contract` + `p1_capability_introspection_macro_500`)
- current status totals are now:
  - `implemented=103`
  - `blocked=0`
  - `tracked=0`
  - `planned=0`

63d. Full 39-workload strict comparable benchmark pass now completes on local Vulkan config with the extended matrix:
- report: `bench/out/dawn-vs-doe.local.vulkan.extended.comparable.full39.now.json`
- result: `comparisonStatus=comparable`, `nonComparableCount=0`, `workloadCount=39`.
- all `39` workload IDs in `bench/workloads.amd.vulkan.extended.json` are present in the report.
- run remains diagnostic for claim mode by design (`iterations=1`, `warmup=0`): `claimStatus=diagnostic`, `nonClaimableCount=39`.

64. Blocking gate enforcement is now aligned with process policy in CI:
- canonical runner `bench/run_blocking_gates.py` now enforces schema -> correctness -> trace -> optional drop-in -> optional claim ordering.
- canonical release orchestration runner `bench/run_release_pipeline.py` now enforces preflight -> compare -> (optional smoke verify) -> blocking gates.
- `.github/workflows/release-gates.yml` now uses `bench/run_release_pipeline.py` with release claim-gate requirements.
- `.github/workflows/amd-vulkan-smoke.yml` now uses `bench/run_release_pipeline.py` with smoke GPU-usage verification.
- new `bench/schema_gate.py` validates schema-backed config/data contracts before release claim checks.

65. Benchmark methodology thresholds are now config contracts:
- dispatch-window rejection and claimability default sample floors moved from hardcoded Python constants to `config/benchmark-methodology-thresholds.json`.
- contract schema is `config/benchmark-methodology-thresholds.schema.json`.
- migration recorded in `config/migration-notes.md`.

66. Drop-in compatibility acceptance lane is now artifact-first and runtime-internal independent:
- new contract file `config/dropin_abi.symbols.txt` defines required exported WebGPU C API symbols for drop-in acceptance checks.
- new gates in `bench/`:
  - `dropin_symbol_gate.py` (symbol completeness)
  - `dropin_behavior_suite.py` + `dropin_behavior_suite.c` (black-box API behavior: create device, queue ops, error scope capture, lifecycle release)
  - `dropin_benchmark_suite.py` + `dropin_benchmark_harness.c` (micro + end-to-end benchmark suite)
  - `dropin_gate.py` (consolidated gate/report with per-step runtimes and failure tokens)
- canonical gate runners now support drop-in enforcement:
  - `bench/run_blocking_gates.py --with-dropin-gate --dropin-artifact <path>`
  - `bench/run_release_pipeline.py --with-dropin-gate --dropin-artifact <path>`
- CI now includes `.github/workflows/dropin-compat.yml`, which builds a candidate shared-library artifact, consumes that artifact in a separate gate job, and fails hard on compatibility regressions while publishing drop-in reports every run.

67. Release claim diagnostics and 1KB upload contract were hardened for actionable "faster everywhere" enforcement:
- `bench/workloads.amd.vulkan.json` now sets `buffer_upload_1kb` `extraArgs` to explicit deferred queue sync (`--queue-sync-mode deferred`) and updates comparability/timing notes so the tiny-upload contract reflects the intended apples-to-apples execution semantics.
- `bench/claim_gate.py` now prints non-claimable workload runtime details (delta tails, left/right p50 timing, timing sources, and claimability reasons) so gate failures directly identify which runtime path needs fixing.

68. Release lane workload coverage was switched from default subset to extended comparable matrix:
- `bench/compare_dawn_vs_doe.config.amd.vulkan.release.json` now loads `bench/workloads.amd.vulkan.extended.json`, enables `includeExtendedWorkloads=true`, and uses `bench/dawn_workload_map.amd.extended.json`.
- release CI (`.github/workflows/release-gates.yml`) continues to invoke the same release config entrypoint, but now evaluates all comparable AMD Vulkan contracts from the extended matrix under release claimability policy.

69. Drop-in artifact lane now defaults to Doe-produced shared-library outputs:
- `bench/run_release_pipeline.py`, `bench/run_blocking_gates.py`, and `bench/dropin_gate.py` now default `--dropin-artifact` to `zig/zig-out/lib/libdoe_webgpu.so` and fail fast when a configured artifact is missing.
- release CI now builds `zig build dropin` and passes `zig/zig-out/lib/libdoe_webgpu.so` to drop-in gates.
- drop-in compatibility CI now publishes and gates `libdoe_webgpu.so` plus required sidecars (`libwebgpu_dawn.so`, `libwebgpu.so`, `libwgpu_native.so`) from `zig/zig-out/lib/`.

70. Queue wait-mode fallback behavior is now explicit-taxonomy only:
- native `--queue-wait-mode wait-any` no longer silently mutates to `process-events` on unsupported/timeout paths.
- unsupported/timeout/error outcomes now surface as runtime error taxonomy (`WaitAnyUnsupported`, `WaitTimedOut`, `WaitAnyFailed`, `WaitAnyIncomplete`) for deterministic diagnostics.

71. Release claim-window trend automation is now scriptable and CI-scheduled:
- `bench/run_release_claim_windows.py` runs repeated release windows and emits a summary artifact with per-window command/report path, return code, `comparisonStatus`, `claimStatus`, and non-comparable/non-claimable workload IDs.
- new CI workflow `.github/workflows/release-claim-trends.yml` schedules repeated AMD Vulkan release windows and publishes trend artifacts.

72. Replay gate now includes CI-native semantic parity checks for runtime-to-runtime lanes:
- `bench/trace_gate.py` adds `--semantic-parity-mode off|auto|required`.
- `auto` compares eligible doe-to-doe trace pairs with `trace/compare_dispatch_traces.py` while preserving Dawn-vs-Doe release compatibility.
- `required` fails hard unless semantic parity checks execute and pass, enabling strict Zig-vs-oracle parity lanes.

73. Substantiation evidence is now policy-backed and machine-gated:
- new config contract `config/substantiation-policy.json` (+ schema) defines minimum report-count and minimum unique left-profile requirements.
- new gate `bench/substantiation_gate.py` validates repeated-window and/or explicit report artifacts against that policy.
- `bench/run_release_claim_windows.py` can now run the substantiation gate in-line via `--with-substantiation-gate`.

74. Canonical tested hardware/driver inventory and matrix dashboard are now generated from artifacts:
- new script `bench/build_test_inventory_dashboard.py` scans compare reports and builds:
  - timestamped inventory snapshots (`bench/out/<timestamp>/test-inventory.json`)
  - stable latest inventory registry (`bench/out/test-inventory.latest.json`)
  - timestamped dashboard snapshots (`bench/out/<timestamp>/test-dashboard.html`)
  - stable latest dashboard (`bench/out/test-dashboard.latest.html`)
- dashboard includes per-matrix latest status (`comparisonStatus`, `claimStatus`, non-comparable/non-claimable counts) and top-level p50 delta vs Dawn.
- inventory includes tested profile combos keyed by `vendor|api|deviceFamily|driver` (from `traceMeta.profile`) plus first/last-seen and matrix/report coverage.
- timestamped run folders now include `run_manifest.json` with run type/config/gate metadata; ad-hoc artifacts are namespaced under `bench/out/scratch/<timestamp>/...`.
- historical timestamp folders can be annotated with inferred manifests via `bench/backfill_run_manifests.py` so legacy artifacts remain auditable without renaming folders.

75. Upstream quirk mining automation is now deterministic and schema-backed:
- new miner `agent/mine_upstream_quirks.py` scans source roots for toggle-style quirk candidates and emits `quirks.schema`-valid records (`schemaVersion: 2`).
- new manifest contract `config/quirk-mining-manifest.schema.json` defines hash-linked mining evidence (`seedHash`/`finalHash`/per-row chain).
- schema gate now validates sample mining artifacts (`examples/quirks/mined_toggle_sample.json`, `examples/quirk-mining.manifest.sample.json`).

76. Baseline dataset/trend packaging is now automated:
- new script `bench/build_baseline_dataset.py` scans comparison artifacts and emits:
  - timestamped baseline dataset (`bench/out/<timestamp>/baseline-dataset.json`)
  - timestamped markdown summary (`bench/out/<timestamp>/baseline-dataset.md`)
  - stable latest outputs (`bench/out/baseline-dataset.latest.json`, `bench/out/baseline-dataset.latest.md`)
- output groups report history by matrix/runtime pair and tracks latest/best/worst p50 deltas.

77. Substantiation target-profile diversity can now be enforced as blocking:
- `config/substantiation-policy.json` now carries `releaseEvidence.enforceTargetUniqueLeftProfiles` (default `true`).
- `bench/substantiation_gate.py` now fails (not warns) when `targetUniqueLeftProfiles` is below policy under enforced mode, with optional CLI override.

78. Dawn-vs-Doe benchmark harness logic is now modularized by concern:
- `bench/compare_dawn_vs_doe_modules/timing_selection.py`
- `bench/compare_dawn_vs_doe_modules/comparability.py`
- `bench/compare_dawn_vs_doe_modules/claimability.py`
- `bench/compare_dawn_vs_doe_modules/reporting.py`
- `bench/compare_dawn_vs_doe.py` now uses these modules for runtime behavior while preserving report contracts.

79. Native execution trace taxonomy now includes deterministic status codes:
- trace rows now emit `executionStatusCode` in addition to `executionStatusMessage`.
- `zig/src/trace.zig` normalizes status codes to stable machine-friendly tokens and `config/trace.schema.json` is updated accordingly.

80. Strict AMD Vulkan host preflight now probes Dawn adapter visibility directly:
- `bench/preflight_bench_host.py` now runs a Dawn adapter probe (`dawn_perf_tests --gtest_list_tests --backend=vulkan --adapter-vendor-id=0x1002`) and parses reported adapters before allowing strict AMD runs.
- strict preflight now fails fast when the requested AMD Vulkan adapter is not Dawn-visible, even if `/dev/dri/renderD128` appears readable/writable via OS-level checks.
- this prevents false-green preflight outcomes that would otherwise fail later in compare execution with adapter-unavailable or render-node permission-denied errors.

81. Native execution reliability hardening now includes explicit retry envelopes and stricter copy/kernel validation:
- queue submission synchronization now routes through centralized backend submit helpers with bounded retry (`QUEUE_SYNC_RETRY_LIMIT`) for transient wait-path failures (`WaitTimedOut`, `QueueSubmitTimeout`, `WaitAnyIncomplete`) in `zig/src/webgpu_ffi.zig`.
- GPU timestamp readback now retries map/read steps with bounded backoff (`TIMESTAMP_MAP_RETRY_LIMIT`) and preserves explicit taxonomy errors instead of one-shot map failures.
- compute dispatch now fails with explicit `gpu timestamp ...` status taxonomy when timestamp readback errors occur, rather than silently flattening failures into a zero timestamp.
- copy lowering now fails fast on invalid/non-matching texture extents for texture copy directions, and kernel source loading now rejects empty sources plus non-compute WGSL (`@compute` required) for `kernel_dispatch`.

82. Skeptical-claim hardening for strict comparable lanes:
- timing-selection now rejects tiny dispatch-window measurements globally when both are true: dispatch window below `minDispatchWindowNsWithoutEncode` and coverage below `minDispatchWindowCoveragePercentWithoutEncode` of `executionTotalNs` (thresholds from `config/benchmark-methodology-thresholds.json`), then falls back to `executionTotalNs`.
- `surface_presentation_contract` is now directional-only (`comparable=false`) because Dawn `ConcurrentExecutionTest ... RunSingle` is not a matching create/release-surface benchmark contract.
- new strict comparable replacement workload `concurrent_execution_single_contract` maps to Dawn `ConcurrentExecutionTest ... RunSingle` with a matched single-dispatch compute contract (`examples/concurrent_execution_single_commands.json`, `bench/kernels/concurrent_execution_runsingle_u32.wgsl`).

83. Apples-to-apples contract enforcement hardening:
- strict workload contract loader now rejects `comparable=true` entries with directional descriptions or explicit closest-proxy comparability notes.
- AMD extended workload contract now classifies directional/proxy mappings as non-comparable (`benchmarkClass=directional`) so strict claim lanes include only strict apples-to-apples workloads.
- upload ignore-first mixed-scope timing derivations (`base` source vs `adjusted` row-total source mismatch) now fail comparability and claimability checks.
- compare reports now embed workload contract metadata (`workloadContract.path`, `workloadContract.sha256`) for anti-staleness auditing.
- `bench/check_full39_claim_readiness.py` now validates exact comparable workload identity against the current workload contract and fails on stale/mismatched workload sets.

84. Comparability obligations are now machine-checkable and gate-enforced:
- `bench/compare_dawn_vs_doe_modules/comparability.py` now emits per-workload obligation artifacts (`comparability.obligations`) with explicit `id`, `applicable`, `blocking`, and `passes` fields plus `blockingFailedObligations`.
- workload comparability status now derives from blocking-obligation failures (deterministic contract), while preserving detailed human-readable reasons.
- `bench/claim_gate.py` now validates comparability obligation schema/version and fails when claimable/comparable reports contain missing or failed blocking comparability obligations.
- `bench/check_full39_claim_readiness.py` now fails readiness checks when workload comparability obligations are missing/invalid or have blocking failures.
- Lean formalization now includes `lean/Fawn/Comparability.lean` for obligation IDs and blocking-failure semantics mirrored by bench gating.

85. Lean/Python comparability parity fixtures are now wired:
- canonical obligation IDs are config-backed (`config/comparability-obligations.json`) and validated by schema gate.
- comparability fixture contract is now schema-backed (`config/comparability-obligation-fixtures.schema.json`) with fixture data in `bench/comparability_obligation_fixtures.json`.
- parity verification script `bench/comparability_obligation_parity_gate.py` now checks:
  - Python fixture evaluation via `evaluate_comparability_from_facts`
  - Lean/Python obligation ID alignment (`lean/Fawn/Comparability.lean` constructors vs canonical config IDs).
- Lean fixture proofs are now present in `lean/Fawn/ComparabilityFixtures.lean` and compiled in `lean/check.sh`.
- gate orchestration now supports verification-lane wiring with `--with-comparability-parity-gate` in:
  - `bench/run_blocking_gates.py`
  - `bench/run_release_pipeline.py`
  - `bench/run_release_claim_windows.py`.

86. Track B claim-grade rehearsal artifacts and hash-linked claim rows are now hard-gated:
- `bench/claim_gate.py` now validates claim-row hash linkage (`claimRowHash`, `claimRowHashChain`) against workload-contract hash, config-contract hash, benchmark-policy hash, and trace-meta hashes.
- claim gate now independently enforces per-workload timed-sample floors plus required positive tails (`p50/p95/p99` in release mode), even if report-level claimability fields are present.
- `bench/run_release_pipeline.py` now emits claim rehearsal artifacts by default when `--with-claim-gate` is enabled:
  - claim gate result
  - tail-health table
  - timing-invariant audit
  - contract-hash manifest
  - rehearsal manifest linking these outputs
- new standalone artifact builder is available in `bench/build_claim_rehearsal_artifacts.py`.
- `bench/run_release_claim_windows.py` now forwards this rehearsal-artifact step per window by default.

### Missing in progress

1. Expand upstream quirk mining beyond toggle-style heuristics (`Toggle::...`) to cover additional workaround/action patterns with the same schema/hash discipline.
2. Lean theorem packs with CI proof execution.
3. Self-hosted AMD Vulkan runner availability/maintenance for automated smoke workflow execution (`.github/workflows/amd-vulkan-smoke.yml`).
4. Full benchmark harness with measured GPU timings tied to native execution spans.
5. Extend baseline automation to broader incumbent lanes (including explicit wgpu baselines) and multi-host trend publication.
6. Native Zig/WebGPU/FFI execution backend hardening in Zig remains a runtime milestone (coverage/reliability/perf).
7. Repeated strict release claim-mode rechecks for 64KB cadence retune are pending on an AMD Vulkan host (current host currently exposes CPU adapters only for Dawn adapter preflight).
8. Keep remaining directional diagnostics macro-scoped and non-claim (`draw_indexed_render_macro_200k`, `p1_capability_introspection_macro_500`, `p2_lifecycle_refcount_macro_200`).
9. Bench harness sharding follow-up (owner: performance):
- complete remaining orchestrator sharding in `bench/compare_dawn_vs_doe.py` to meet per-file size policy while preserving current module boundaries.
10. Expand substantiation evidence collection across multiple non-CPU host profiles so enforced `targetUniqueLeftProfiles` is routinely satisfiable in CI.

## Performance Reliability Investigation (2026-02-21)

Scope:
- AMD Vulkan upload workloads, with focus on `buffer_upload_64kb`.
- strict comparability mode remained green during these checks.

Findings:
1. `buffer_upload_64kb` is highly sensitive to methodology knobs (`leftIgnoreFirstOps`, `leftUploadSubmitEvery`, `leftCommandRepeat`) even when comparability checks pass.
2. Mixed timing semantics can produce misleading conclusions:
- dispatch-window timing excludes setup cost
- ignore-first adjustment based on per-row durations includes setup for included rows
- this combination can materially change sign and tails (now guarded by explicit row-total ignore-first timing source in harness output).
3. Diagnostic sweep showed that increasing `leftCommandRepeat` (with explicit per-op normalization) substantially improved 64KB tail behavior and median delta, indicating batching/setup sensitivity dominates this case.

Implication:
- 64KB methodology hardening is now enforced in harness claim mode; runtime smoothing is still needed before robustly claimable "reliably faster" status.

Next required changes:
1. Re-run strict release claim-mode windows on AMD Vulkan host for `buffer_upload_64kb` with the updated `leftUploadSubmitEvery=100` contract.
2. Keep queue wait path tuning explicit (`--queue-wait-mode`) and only promote non-default mode into workload contracts after adapter-backed reliability evidence.
3. Re-freeze workload config defaults only after invariants hold in repeated strict claim-mode runs.

## Render parity benchmark note (2026-02-21)

Local directional benchmark (same host runtime, no Dawn adapter dependency):

- report: `bench/out/render_draw_vs_compute_proxy.local.json`
- tool: `python3 bench/compare_runtimes.py`
- comparison: `left=doe_render_draw` vs `right=doe_compute_proxy` (`2000` operations normalized per run)
- result: `p50DeltaPercent=-129.93%` (native render path remains slower than prior compute draw proxy in this environment after adding Dawn-like vertex-buffer + static uniform bind-group parity)

Interpretation:
- this is an expected early parity milestone signal, not a claim benchmark.
- setup amortization still exists for multi-command runs (pipeline + view caches + vertex buffer + bind-group reuse), but render-vs-proxy single-command runs remain dominated by render submit cost.
- latest run shows directional tail improvement (p95 delta from `-143.43%` to `-112.85%`) while remaining non-claim diagnostic.

## Texture directional benchmark note (2026-02-21)

Local directional benchmark comparing the updated texture/raster command seed against the prior dispatch-only raster proxy:

- report: `bench/out/texture_raster_render_step_vs_dispatch_proxy.local.json`
- tool: `python3 bench/compare_runtimes.py`
- comparison: `left=doe_texture_raster_render_step` vs `right=doe_texture_raster_dispatch_proxy`
- result: `p50DeltaPercent=-22.38%` (updated texture path is currently slower in this host environment)

Interpretation:
- this confirms the new texture command seed exercises real `kernel_dispatch + render_draw` behavior.
- remaining gap is expected while directional texture methodology is still simplified versus Dawn's full render-pass transitions.

## AMD Vulkan run snapshot (2026-02-23)

Current contract state after matrix expansion:

1. `bench/workloads.amd.vulkan.extended.json`
- workload contracts: `34` total
- strict comparable contracts: `17` (apples-to-apples only)
- directional contracts: `17` (includes contract/proxy domains `pipeline-async`, `p0-*`, `p1-*`, `p2-*`, `surface`, plus macro stress contracts)

2. `bench/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
- strict mode remains `includeNoncomparableWorkloads=false`
- now targets the expanded apples-to-apples comparable matrix (upload + compute + render + texture + render-bundle)

3. `bench/compare_dawn_vs_doe.config.amd.vulkan.directional.json`
- directional diagnostics now focus on remaining non-claim macro workloads
  (`draw_indexed_render_macro_200k`, `p1_capability_introspection_macro_500`, `p2_lifecycle_refcount_macro_200`)

4. `bench/compare_dawn_vs_doe.config.amd.vulkan.macro.directional.json`
- directional diagnostics target the focused macro subset (`draw_indexed_render_macro_200k`)

5. Host execution note (this machine class)
- strict AMD Vulkan Dawn runs can fail/skips when `/dev/dri/renderD128` access is unavailable to the active user.
- preflight command: `python3 bench/preflight_bench_host.py --strict-amd-vulkan`
- adapter-agnostic strict comparable fallback: `bench/compare_dawn_vs_doe.config.local.vulkan.extended.comparable.json`
- if Dawn executes on CPU adapter only, DrawCallPerf/texture/render-bundle contracts can be skipped by Dawn as unsupported and must not be treated as comparable results.

## Native execution milestone (non-prototype)

Scope:
- chosen path is full native Zig+WebGPU/FFI implementation from scratch.
- current implementation size is 13,485 LOC (`zig/src`); remaining work is performance/reliability hardening and broader claim-grade coverage.
- current codebase status: trace/replay/matching complete, with queue-submit execution coverage for upload/copy/barrier and dispatch-family compute routing.

Execution gap list:
- typed discovery and adapter/device queue selection are implemented in WebGPU FFI bootstrap.
- full dispatch/kernel lowering with shader/module/pipeline resolution for a complete kernel payload format and artifact-backed verification.
- texture copy/materialization command modeling and lowering.
- deterministic GPU timing capture remains partial (retry envelopes + explicit timestamp readback taxonomy are implemented, but full claim-grade deterministic capture policy is still in progress).
- robust retry/failure policy is now bounded for queue wait and timestamp map paths; broader mapped GPU status policy hardening remains.
- no release-ready benchmark baseline generated against native GPU backend.

### Explicit distinction

- “Not implemented” in developer flow does not mean the runtime is unusable.
- It means release confidence, automation, and proof-binary reproducibility are not yet at stable v1-grade completeness.

## Drop-in + release benchmark update (2026-02-23)

1. Drop-in benchmark coverage is now expanded and grouped by class in the HTML artifact:
- micro: `instance_create_destroy`, `command_encoder_finish_empty`, `queue_submit_empty`, `queue_write_buffer_{1kb,4kb,64kb}`, `buffer_create_destroy_{4kb,64kb}`
- end-to-end: `full_lifecycle_device_only`, `full_lifecycle_queue_submit`, `full_lifecycle_write_{4kb,64kb}`, `full_lifecycle_queue_ops`
- drop-in gate reports continue to include per-step runtime and explicit runtime-to-fix output for failing steps.
- latest Doe-vs-Dawn p50 snapshot on this host shows the dominant lag at `instance_create_destroy`; `queue_write_buffer_1kb` can also be marginally slower and should be treated as a small residual micro-gap.

2. AMD Vulkan extended release workload contract now uses deferred queue sync for `buffer_upload_1kb` in `bench/workloads.amd.vulkan.extended.json` (matching `bench/workloads.amd.vulkan.json`) to avoid per-command wait inflation at tiny payload sizes while preserving per-upload normalization semantics.

3. Fresh release claim-floor rerun executed on this host using the full comparable release profile (`iterations=16`, `warmup=1`, 17 workloads):
- report: `bench/out/20260223T202753Z/dawn-vs-doe.amd.vulkan.release.json`
- gate result: `comparisonStatus=comparable`, `claimStatus=diagnostic`, `nonClaimableCount=1`
- residual non-claimable workload:
  - `texture_sampling_raster_proxy` (tails only: `p95/p99 = -16.164%`; `p50` positive).

4. Render-domain apples-to-apples timing/runtime path was tightened:
- comparable timing for workload domains `render` and `render-bundle` uses encode-only operation source (`doe-execution-encode-ns`) for claim comparison against Dawn DrawCallPerf timing.
- `render_draw` render-bundle command recording was moved into setup (untimed) so encode timing now reflects bundle execution parity instead of bundle build cost.
- focused release claim-floor rerun (`iterations=16`, `warmup=1`) over the 2 render-bundle workloads:
  - report: `bench/out/20260223T202424Z/dawn-vs-doe.amd.vulkan.release.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`.

5. Texture-raster tail reliability contract was tightened for claim runs:
- `texture_sampling_raster_proxy` now runs with `leftCommandRepeat=500` and `leftTimingDivisor=500` (same per-iteration unit normalization) to reduce low-coverage GPU timestamp quantization noise in p95/p99 tails.
- focused release claim-floor rerun for that workload:
  - report: `bench/out/20260223T210045Z/dawn-vs-doe.amd.vulkan.release.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`.

6. Redundant-pipeline render tail reliability contract was tightened for claim runs:
- full release pipeline rerun (`bench/out/20260223T211020Z/dawn-vs-doe.amd.vulkan.release.json`) reduced the matrix to one residual non-claimable workload: `render_draw_redundant_pipeline_bindings` (tails only).
- `render_draw_redundant_pipeline_bindings` now runs with `leftCommandRepeat=10` and `leftTimingDivisor=20000` (per-draw normalization preserved) to reduce sample-tail setup jitter.
- focused release claim-floor rerun for that workload:
  - report: `bench/out/20260223T213900Z/dawn-vs-doe.amd.vulkan.release.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`.

7. Macro + hard-gated pilot promotion refresh (2026-02-25):
- promoted to strict comparable in `bench/workloads.amd.vulkan.extended.json`:
  `render_draw_throughput_macro_200k`,
  `texture_sampler_write_query_destroy_macro_500`,
  `p1_resource_table_immediates_macro_500`,
  `p0_render_pixel_local_storage_barrier_macro_500`,
  `p0_render_multidraw_contract`,
  `p0_render_multidraw_indexed_contract`.
- matrix split is now `29` comparable + `11` directional.

## v0 Reality

Blocking gates: schema, correctness, trace.
Advisory gates: verification, performance.

This matches speed-first priorities while keeping deterministic foundations.

Current comparison claim state: `strict-comparable matrix + claimability diagnostics`.

Meaning:
1. strict comparable AMD matrix now tracks the audited apples-to-apples subset (`29` workloads) from `bench/workloads.amd.vulkan.extended.json`; directional/proxy contracts are excluded from strict claim lanes.
2. remaining directional macro workloads (`draw_indexed_render_macro_200k`, `p1_capability_introspection_macro_500`, `p2_lifecycle_refcount_macro_200`) are diagnostics and must not be presented as strict apples-to-apples claims.
3. no broad substantiated "beats Dawn/wgpu" claim is allowed yet without wider baseline coverage and trend windows.
4. release claim gate remains the authority: reports must be `comparisonStatus=comparable` and `claimStatus=claimable`.

## Track A Execution Plan (Finalized)

Objective:
- make runtime behavior contract-clean, deterministic, and performance-safe under one active contract hash.

Two-week implementation focus:
1. Week 1 closes the failure inventory:
   - adapter selection mismatches
   - device-init edge cases
   - timestamp validity failures
   - unexpected unsupported taxonomy rows
   - timing-normalization drift
2. Week 2 lands fixes with explicit config/schema representation only:
   - no hidden runtime switches
   - no undocumented fallback behavior
   - runtime and Lean pair on hot paths to remove provable checks only after proof artifact generation and replay parity pass
3. preserve apples-to-apples semantics for comparable workloads and explicit directional obligations (`allowLeftNoExecution` when declared).

Execution cadence:
- daily red-lane triage
- twice-weekly stabilization cuts
- weekly contract-hash rehearsal

Required artifacts per stabilization cut:
- strict comparable report for the active comparable subset
- directional obligation report (including declared `allowLeftNoExecution` evidence)
- unsupported taxonomy histogram (`expected` vs `unexpected`)
- timestamp validity summary
- replay trace-parity output
- config/schema diff summary

Required checks per PR:
- unit tests for taxonomy/error paths
- integration tests for adapter/device boundary behavior
- regression tests for timing-source/timing-class invariants
- replay parity checks
- benchmark harness smoke

Definition of done:
1. all comparable workloads under the active hash pass strict comparability.
2. directional workloads satisfy declared obligations.
3. zero unexpected unsupported and zero unexpected errors.
4. timestamp validity checks are green.
5. normalization fields are schema-conformant.
6. at least one Lean-driven hot-path branch elimination lands with measured perf impact and no correctness regression.

Rollback triggers:
- hidden toggle introduction
- schema/runtime drift without migration note
- replay mismatch
- claim-lane comparability break
- memory-safety regression (blocking defect under release policy)

Ownership:
- runtime lead owns Zig implementation and taxonomy outcomes
- Lean lead owns proofs and branch-deletion proposals
- coordinator owns contract-hash advancement decision after all Track A artifacts are green
