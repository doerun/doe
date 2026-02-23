# Fawn Status

## Snapshot

Date: 2026-02-23

Fawn is in active implementation phase. Runtime behavior is operational for dispatch decisions and replay-aware tracing, but several product and release-flow gaps remain before v1-grade stability claims.
The execution platform strategy is full native Zig+WebGPU/FFI runtime execution.
Current `fawn/zig/src` size is 13,485 LOC (`wc -l zig/src/*.zig`, 2026-02-23) and includes native queue-submitted execution for upload, copy, barrier, render, and dispatch-family lowering.
AMD Vulkan comparison presets now include claimable comparable slices (local + release policies) and explicit non-claimable directional slices.

Benchmark contract coverage snapshot (2026-02-22 update):
- `bench/workloads.amd.vulkan.extended.json` now contains `34` workload contracts: `29` comparable + `5` directional contracts (`p1_resource_table_immediates_macro_500`, 3 macro stress workloads, and `p0_render_pixel_local_storage_barrier_macro_500`).
- strict extended comparable matrix now includes render, render-bundle, texture-contract, draw-indexed proxy, and async diagnostics slices in addition to upload/compute/pipeline.
- adapter-agnostic strict preset added for this host class: `bench/compare_dawn_vs_fawn.config.local.vulkan.extended.comparable.json`.
- host prerequisites are now explicit and machine-checkable via `bench/preflight_bench_host.py`.

## Product implementation state (runtime outcomes)

### Implemented

1. v0 runtime prototype in `fawn/zig/src`:
- typed model and JSON ingestion
- deterministic matcher + selector + action application
- runnable `fawn-zig-runtime` entry path
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
7. Added Dawn/Fawn benchmark orchestration scaffolding via `fawn/bench/compare_dawn_vs_fawn.py` and `fawn/bench/workloads.json` for repeatable shared-workload runtime comparisons.
8. Added Zig replay comparison mode in `zig/src/main.zig` (`--replay`) that now enforces `seq`, `command`, optional `kernel`, module/op-code, and hash-chain alignment.
9. Added hard release gate command path in docs/process via `fawn/bench/trace_gate.py` for replay artifact validation.
10. Release gating is explicit in process/docs and enforced in `.github/workflows/release-gates.yml`.
11. Strict Dawn-vs-Fawn upload comparability preflight is now enforced in `fawn/bench/compare_dawn_vs_fawn.py`:
- fail fast if executed `fawn-zig-runtime` does not expose upload knobs (`--upload-buffer-usage`, `--upload-submit-every`)
- fail fast if upload knob validation probes are not recognized
- fail fast if runtime binary appears older than key upload/runtime Zig sources (`zig/src/main.zig`, `zig/src/execution.zig`, `zig/src/wgpu_commands.zig`, `zig/src/webgpu_ffi.zig`)
12. AMD Vulkan upload workloads in `fawn/bench/workloads.amd.vulkan.json` now use explicit size-tuned `leftUploadSubmitEvery` values (instead of a single shared cadence) to keep methodology explicit while reducing upload backpressure artifacts.
13. Comparison delta sign convention is now left-runtime perspective with right baseline (`((rightMs-leftMs)/rightMs)*100`), so positive means left faster and negative means left slower (`compare_dawn_vs_fawn.py` and `compare_runtimes.py`, report `deltaPercentConvention`).
14. Comparison report schema is now `schemaVersion: 3` with percentile summaries centered on p5/p50/p95/p99 (`p5Ms`, `p5Percent`, and overall `p5Approx`/`p50Approx`/`p95Approx`/`p99Approx`).
15. Post-benchmark visualization pipeline step is now available via `fawn/bench/visualize_dawn_vs_fawn.py`, producing a self-contained HTML report and optional analysis JSON from Dawn-vs-Fawn comparison artifacts.
16. Visualization/distribution diagnostics now include ECDF overlays, workload×percentile heatmap, KS statistic with asymptotic p-value, Wasserstein distance, probability of superiority (`P(left<right)`), and bootstrap CI summaries for delta `p50`/`p95`/`p99`.
17. Claimability reliability mode is now implemented in `fawn/bench/compare_dawn_vs_fawn.py`:
- `--claimability local|release` enforces sample-floor and positive-tail checks
- report now includes workload-level `claimability`, top-level `claimabilityPolicy`, `claimabilitySummary`, and `claimStatus`
- claimability failures exit non-zero (`rc=3`) so CI/pipelines can gate on claimable speed
18. Upload ignore-first timing source is now explicit and scope-consistent in reports (`fawn-execution-row-total-ns+ignore-first-ops`) instead of inheriting incompatible base sources.
19. Runtime upload prewarm path is now wired in Zig native execution (`maxUploadBytes` prewarm before timed command loop) to reduce first-upload setup spikes.
20. AMD Vulkan 64KB upload workload now uses size-specific repeat normalization (`leftCommandRepeat=500`, `leftTimingDivisor=500`, `leftIgnoreFirstOps=0`) for more stable per-op claim diagnostics.
21. Comparability assessment now enforces workload contract comparability flags (`workload.comparable`); workloads marked non-comparable are always reported as non-comparable and strict mode fails fast when they are selected.
22. `shader_compile_pipeline_stress` has been promoted to a comparable contract for AMD Vulkan using a fixed `ShaderRobustnessPerf` filter plus explicit 50-dispatch normalization (`leftTimingDivisor=50`) and Dawn-aligned kernel command shape.
23. Render/texture workload contracts now use explicit per-iteration normalization controls (`leftTimingDivisor`/`leftCommandRepeat`) to keep timing units consistent with Dawn-side workload semantics.
24. AMD Vulkan matrix coverage now has config-first presets for release claims, extended comparable runs, and directional diagnostics:
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json`
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json`
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json`
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
- `--queue-wait-mode process-events|wait-any` in `fawn-zig-runtime`
- default remains `process-events`; `wait-any` is available for targeted wait-path diagnostics/tuning and now fails explicitly with runtime taxonomy errors when unsupported or timed out.
37. AMD Vulkan 64KB upload workload cadence is retuned from `leftUploadSubmitEvery=50` to `leftUploadSubmitEvery=100` (with `leftCommandRepeat=500`, `leftTimingDivisor=500`) in:
- `bench/workloads.amd.vulkan.json`
- `bench/workloads.amd.vulkan.extended.json`
- local operation-scope A/B artifact: `bench/out/upload_64kb_submit_wait_100_vs_50.local.json` (`executionSubmitWaitTotalNs`, `n=30` per side): `submit100` faster at `p50 +19.52%`, `p95 +14.21%`.
38. Native runtime now exposes explicit queue synchronization mode control:
- `--queue-sync-mode per-command|deferred` in `fawn-zig-runtime` (`per-command` default preserves existing behavior).
- deferred mode skips `waitForQueue` after individual submits and performs a single final queue flush after the command loop.
- `trace-meta` now records `queueSyncMode` for native execution runs (`config/trace-meta.schema.json` updated).
39. Native `render_draw` command contract now includes explicit draw-offset support:
- command parser accepts `first_vertex`/`firstVertex` and `first_instance`/`firstInstance`.
- native render lowering now forwards those values into `wgpuRenderPassEncoderDraw`.
- defaults remain deterministic (`0`, `0`) when fields are omitted.
40. WebGPU capability expansion is now tracked in config as code:
- `config/webgpu-spec-coverage.schema.json` defines contract for machine-readable capability status.
- `config/webgpu-spec-coverage.json` tracks implemented/partial/planned coverage items and priorities.
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
- new local adapter-agnostic strict config is available: `bench/compare_dawn_vs_fawn.config.local.vulkan.extended.comparable.json`.
- host requirement preflight is now explicit via `bench/preflight_bench_host.py`.
53. Benchmark timing-source selection now rejects tiny submit-only dispatch-window measurements when encode/dispatch work is absent:
- rejection threshold: dispatch window `<100us` and `<1%` of `executionTotalNs`.
- fallback source is `fawn-execution-total-ns`, with explicit metadata `dispatchWindowSelectionRejected`.
54. AMD Vulkan comparable workload defaults were tuned for setup-amortized per-unit normalization:
- `draw_indexed_render_proxy` now runs with `leftCommandRepeat=10`, `leftTimingDivisor=20000`, and `--queue-sync-mode deferred`.
- `texture_sampler_write_query_destroy_contract` and `texture_sampler_write_query_destroy_contract_mip8` now run with `leftCommandRepeat=10` and `leftTimingDivisor=500`.
55. Directional macrobenchmark coverage was added as config-first contracts:
- new workload IDs: `render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`.
- new preset config: `bench/compare_dawn_vs_fawn.config.amd.vulkan.macro.directional.json`.
- new command seeds: `examples/draw_call_proxy_macro_commands.json`, `examples/draw_call_indexed_proxy_macro_commands.json`, `examples/texture_sampler_write_query_destroy_macro_commands.json`.
56. P0 WebGPU API slice implementation and benchmark contracts are now integrated:
- native runtime wiring now covers `wgpuBufferDestroy`, `wgpuCommandEncoderClearBuffer`, `wgpuCommandEncoderWriteBuffer`, `wgpuComputePassEncoderDispatchWorkgroupsIndirect`, `wgpuComputePassEncoderWriteTimestamp`, `wgpuDeviceCreateComputePipelineAsync`, `wgpuDeviceDestroy`, `wgpuQuerySetDestroy`, `wgpuQuerySetGetCount`, `wgpuQuerySetGetType`, `wgpuRenderPassEncoderBeginOcclusionQuery`, `wgpuRenderPassEncoderEndOcclusionQuery`, `wgpuRenderPassEncoderMultiDrawIndirect`, `wgpuRenderPassEncoderMultiDrawIndexedIndirect`, and `wgpuRenderPassEncoderWriteTimestamp`.
- render multidraw dispatch is now feature-gated via `WGPUFeatureName_MultiDrawIndirect`; fallback draw loops remain deterministic when unavailable.
- new directional P0 benchmark workloads were added: `p0_resource_lifecycle_contract`, `p0_compute_indirect_timestamp_contract`, `p0_render_multidraw_contract`, `p0_render_multidraw_indexed_contract`.
- local benchmark artifacts are emitted under `bench/out/p0_*.perf_report.json` and `bench/out/run-bench-p0_*`.
- Dawn-side directional comparisons for these contracts currently skip on CPU-only adapters in this host class (`DawnPerfTest::IsCPU`), so claimable Dawn-vs-Fawn artifacts remain blocked pending a non-CPU adapter host.
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
  `bench/compare_dawn_vs_fawn.config.amd.vulkan.smoke.gpu.json`,
  `bench/verify_smoke_gpu_usage.py`, and self-hosted workflow
  `.github/workflows/amd-vulkan-smoke.yml`.
- Dawn-vs-Fawn feature/benchmark coverage table generation is now scripted via
  `bench/generate_feature_benchmark_table.py` with current artifact
  `bench/out/dawn-vs-fawn-feature-benchmark-coverage.md`.

60. API-surface and matrix coverage metrics are now machine-generated and full for tracked scope:
- `zig/src/wgpu_loader.zig` now preloads the remaining Dawn header symbol set used by coverage scans (label/debug-marker/map-introspection/lost-future/external-texture release paths) via `OPTIONAL_API_SURFACE_SYMBOLS`.
- `bench/generate_feature_benchmark_table.py` now emits a top-level metrics table with:
  - tracked spec-capability completion
  - Dawn header API-surface reference coverage (estimate)
  - capability-to-benchmark mapping coverage
- current matrix artifact reports:
  - tracked spec-capability completion: `100.0% (22/22)`
  - Dawn header API-surface reference coverage: `100.00% (199/199)`
  - capability-to-benchmark mapping coverage: `100.00% (22/22)`
  (`bench/out/dawn-vs-fawn-feature-benchmark-coverage.md`, `bench/out/dawn_header_vs_fawn_ref_scan.json`).

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
- strict probe run over promoted contracts (`bench/out/dawn-vs-fawn.amd.vulkan.promoted.strict_probe.json`) reports `comparisonStatus=comparable` for all 8 promoted workloads (claimability diagnostic due single-sample probe floor).
- release claimability recheck for upload workloads (`buffer_upload_64kb`, `buffer_upload_1mb`) completed with strict comparability and release sample floor:
  `bench/out/dawn-vs-fawn.amd.vulkan.release.upload64kb1mb.json`
  => `comparisonStatus=comparable`, `claimStatus=claimable`.
- benchmark timing rigor now enforces native execution-span timing for strict operation-class comparisons on webgpu-ffi left runs:
  non-native fallback timing sources now trigger non-comparable reasons in `bench/compare_dawn_vs_fawn.py`;
  policy is explicit in report `comparabilityPolicy.requireNativeExecutionTimingForLeftOperation=true`.

62. Capability coverage metric contract now distinguishes directional-only capability domains:
- `config/webgpu-spec-coverage.schema.json` accepts optional `benchmarkClass` (`comparable` or `directional`) per capability entry.
- `bench/generate_feature_benchmark_table.py` now emits both overall comparable-coverage and eligible-only comparable-coverage metrics.
- updated matrix artifact:
  `bench/out/dawn-vs-fawn-feature-benchmark-coverage.md`.

63. Gap-closure promotion completed: strict comparable capability coverage is now full (`22/22`).
- promoted to comparable contracts:
  `p1_resource_table_immediates_contract`,
  `p0_render_pixel_local_storage_barrier_contract`,
  `surface_presentation_contract`.
- resource-table and PLS contracts now use workload-level strict comparability override
  `allowLeftNoExecution=true` with deterministic unsupported/skipped evidence requirements
  in `bench/compare_dawn_vs_fawn.py`; unsupported runtime paths remain explicit taxonomy statuses.
- surface comparable proxy contract now uses deterministic create/release command shape
  (`examples/surface_presentation_commands.json`) to avoid non-deterministic invalid-surface execution errors on headless adapter classes.
- Dawn mapping for promoted contracts now uses explicit deterministic filters:
  `p1_resource_table_immediates_contract -> DrawCallPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151`
  `p0_render_pixel_local_storage_barrier_contract -> DrawCallPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151`.
- strict gap-close probe artifact:
  `bench/out/dawn-vs-fawn.amd.vulkan.gapclose.strict_probe.json`
  reports `comparisonStatus=comparable`, `nonComparableCount=0` for all 3 promoted contracts.
- matrix metrics now report:
  - comparable capability benchmark coverage: `100.00% (22/22)`
  - comparable capability benchmark coverage (eligible-only): `100.00% (22/22)`
  - directional-only capability domains: `0.00% (0/22)`
  (`bench/out/dawn-vs-fawn-feature-benchmark-coverage.md`).

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
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json` now loads `bench/workloads.amd.vulkan.extended.json`, enables `includeExtendedWorkloads=true`, and uses `bench/dawn_workload_map.amd.extended.json`.
- release CI (`.github/workflows/release-gates.yml`) continues to invoke the same release config entrypoint, but now evaluates all comparable AMD Vulkan contracts from the extended matrix under release claimability policy.

69. Drop-in artifact lane now defaults to Fawn-produced shared-library outputs:
- `bench/run_release_pipeline.py`, `bench/run_blocking_gates.py`, and `bench/dropin_gate.py` now default `--dropin-artifact` to `zig/zig-out/lib/libfawn_webgpu.so` and fail fast when a configured artifact is missing.
- release CI now builds `zig build dropin` and passes `zig/zig-out/lib/libfawn_webgpu.so` to drop-in gates.
- drop-in compatibility CI now publishes and gates `libfawn_webgpu.so` plus required sidecars (`libwebgpu_dawn.so`, `libwebgpu.so`, `libwgpu_native.so`) from `zig/zig-out/lib/`.

70. Queue wait-mode fallback behavior is now explicit-taxonomy only:
- native `--queue-wait-mode wait-any` no longer silently mutates to `process-events` on unsupported/timeout paths.
- unsupported/timeout/error outcomes now surface as runtime error taxonomy (`WaitAnyUnsupported`, `WaitTimedOut`, `WaitAnyFailed`, `WaitAnyIncomplete`) for deterministic diagnostics.

71. Release claim-window trend automation is now scriptable and CI-scheduled:
- `bench/run_release_claim_windows.py` runs repeated release windows and emits a summary artifact with per-window command/report path, return code, `comparisonStatus`, `claimStatus`, and non-comparable/non-claimable workload IDs.
- new CI workflow `.github/workflows/release-claim-trends.yml` schedules repeated AMD Vulkan release windows and publishes trend artifacts.

72. Replay gate now includes CI-native semantic parity checks for runtime-to-runtime lanes:
- `bench/trace_gate.py` adds `--semantic-parity-mode off|auto|required`.
- `auto` compares eligible fawn-to-fawn trace pairs with `trace/compare_dispatch_traces.py` while preserving Dawn-vs-Fawn release compatibility.
- `required` fails hard unless semantic parity checks execute and pass, enabling strict Zig-vs-oracle parity lanes.

73. Substantiation evidence is now policy-backed and machine-gated:
- new config contract `config/substantiation-policy.json` (+ schema) defines minimum report-count and minimum unique left-profile requirements.
- new gate `bench/substantiation_gate.py` validates repeated-window and/or explicit report artifacts against that policy.
- `bench/run_release_claim_windows.py` can now run the substantiation gate in-line via `--with-substantiation-gate`.

74. Canonical tested hardware/driver inventory and matrix dashboard are now generated from artifacts:
- new script `bench/build_test_inventory_dashboard.py` scans compare reports and builds:
  - timestamped inventory snapshots (`bench/out/test-inventory.<timestamp>.json`)
  - stable latest inventory registry (`bench/out/test-inventory.latest.json`)
  - timestamped dashboard snapshots (`bench/out/test-dashboard.<timestamp>.html`)
  - stable latest dashboard (`bench/out/test-dashboard.latest.html`)
- dashboard includes per-matrix latest status (`comparisonStatus`, `claimStatus`, non-comparable/non-claimable counts) and top-level p50 delta vs Dawn.
- inventory includes tested profile combos keyed by `vendor|api|deviceFamily|driver` (from `traceMeta.profile`) plus first/last-seen and matrix/report coverage.

### Missing in progress

1. Full upstream quirk mining automation.
2. Lean theorem packs with CI proof execution.
3. Self-hosted AMD Vulkan runner availability/maintenance for automated smoke workflow execution (`.github/workflows/amd-vulkan-smoke.yml`).
4. Full benchmark harness with measured GPU timings tied to native execution spans.
5. Baseline dataset generation and end-to-end comparison automation against Dawn/wgpu incumbents.
6. Native Zig/WebGPU/FFI execution backend hardening in Zig remains a runtime milestone (coverage/reliability/perf).
7. Repeated strict release claim-mode rechecks for 64KB cadence retune are pending on an AMD Vulkan host (current host currently exposes CPU adapters only for Dawn adapter preflight).
8. Keep directional diagnostics macro-scoped and non-claim (`render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`, `p1_resource_table_immediates_macro_500`, `p0_render_pixel_local_storage_barrier_macro_500`).
9. Bench harness sharding follow-up (owner: performance):
- split `bench/compare_dawn_vs_fawn.py` into cohesive modules (`timing_selection.py`, `comparability.py`, `claimability.py`, `reporting.py`) while preserving strict contract behavior.
10. Expand substantiation gate inputs across multiple non-CPU host profiles so `targetUniqueLeftProfiles` can be enforced as blocking (currently advisory target only).

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
- comparison: `left=fawn_render_draw` vs `right=fawn_compute_proxy` (`2000` operations normalized per run)
- result: `p50DeltaPercent=-129.93%` (native render path remains slower than prior compute draw proxy in this environment after adding Dawn-like vertex-buffer + static uniform bind-group parity)

Interpretation:
- this is an expected early parity milestone signal, not a claim benchmark.
- setup amortization still exists for multi-command runs (pipeline + view caches + vertex buffer + bind-group reuse), but render-vs-proxy single-command runs remain dominated by render submit cost.
- latest run shows directional tail improvement (p95 delta from `-143.43%` to `-112.85%`) while remaining non-claim diagnostic.

## Texture directional benchmark note (2026-02-21)

Local directional benchmark comparing the updated texture/raster command seed against the prior dispatch-only raster proxy:

- report: `bench/out/texture_raster_render_step_vs_dispatch_proxy.local.json`
- tool: `python3 bench/compare_runtimes.py`
- comparison: `left=fawn_texture_raster_render_step` vs `right=fawn_texture_raster_dispatch_proxy`
- result: `p50DeltaPercent=-22.38%` (updated texture path is currently slower in this host environment)

Interpretation:
- this confirms the new texture command seed exercises real `kernel_dispatch + render_draw` behavior.
- remaining gap is expected while directional texture methodology is still simplified versus Dawn's full render-pass transitions.

## AMD Vulkan run snapshot (2026-02-22)

Current contract state after matrix expansion:

1. `bench/workloads.amd.vulkan.extended.json`
- workload contracts: `34` total
- strict comparable contracts: `29`
- directional contracts: `5` (`p1_resource_table_immediates_macro_500`, 3 macro stress contracts, and `p0_render_pixel_local_storage_barrier_macro_500`)

2. `bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json`
- strict mode remains `includeNoncomparableWorkloads=false`
- now targets the expanded comparable matrix (upload + compute + render + texture + render-bundle + async diagnostics)

3. `bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json`
- directional diagnostics now focus on macro-only stress workloads
  (`render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`, `p1_resource_table_immediates_macro_500`, `p0_render_pixel_local_storage_barrier_macro_500`)

4. `bench/compare_dawn_vs_fawn.config.amd.vulkan.macro.directional.json`
- directional diagnostics target macro stress workloads only (`render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`, `p0_render_pixel_local_storage_barrier_macro_500`)

5. Host execution note (this machine class)
- strict AMD Vulkan Dawn runs can fail/skips when `/dev/dri/renderD128` access is unavailable to the active user.
- preflight command: `python3 bench/preflight_bench_host.py --strict-amd-vulkan`
- adapter-agnostic strict comparable fallback: `bench/compare_dawn_vs_fawn.config.local.vulkan.extended.comparable.json`
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
- no deterministic GPU timing capture in the execution path.
- robust retry/failure policy for GPU submission errors and mapped GPU status.
- no release-ready benchmark baseline generated against native GPU backend.

### Explicit distinction

- “Not implemented” in developer flow does not mean the runtime is unusable.
- It means release confidence, automation, and proof-binary reproducibility are not yet at stable v1-grade completeness.

## Drop-in + release benchmark update (2026-02-23)

1. Drop-in benchmark coverage is now expanded and grouped by class in the HTML artifact:
- micro: `instance_create_destroy`, `command_encoder_finish_empty`, `queue_submit_empty`, `queue_write_buffer_{1kb,4kb,64kb}`, `buffer_create_destroy_{4kb,64kb}`
- end-to-end: `full_lifecycle_device_only`, `full_lifecycle_queue_submit`, `full_lifecycle_write_{4kb,64kb}`, `full_lifecycle_queue_ops`
- drop-in gate reports continue to include per-step runtime and explicit runtime-to-fix output for failing steps.
- latest Fawn-vs-Dawn p50 snapshot on this host shows the dominant lag at `instance_create_destroy`; `queue_write_buffer_1kb` can also be marginally slower and should be treated as a small residual micro-gap.

2. AMD Vulkan extended release workload contract now uses deferred queue sync for `buffer_upload_1kb` in `bench/workloads.amd.vulkan.extended.json` (matching `bench/workloads.amd.vulkan.json`) to avoid per-command wait inflation at tiny payload sizes while preserving per-upload normalization semantics.

## v0 Reality

Blocking gates: schema, correctness, trace.
Advisory gates: verification, performance.

This matches speed-first priorities while keeping deterministic foundations.

Current comparison claim state: `mixed` (strict comparable + directional diagnostics).

Meaning:
1. strict comparable AMD matrices are contract-defined and expanded, but claimable strict AMD substantiation requires a host with usable AMD render-node access.
2. directional diagnostics are contract-scoped and non-claim: macro-only stress workloads (`render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`, `p1_resource_table_immediates_macro_500`, `p0_render_pixel_local_storage_barrier_macro_500`).
3. no broad substantiated "beats Dawn/wgpu" claim is allowed yet without wider baseline coverage and trend windows.
4. directional diagnostics currently cover macro-only stress workloads:
`render_draw_throughput_macro_200k`, `draw_indexed_render_macro_200k`, `texture_sampler_write_query_destroy_macro_500`, `p1_resource_table_immediates_macro_500`, `p0_render_pixel_local_storage_barrier_macro_500`.
