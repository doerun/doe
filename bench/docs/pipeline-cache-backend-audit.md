# Pipeline-cache backend audit: Metal, Vulkan, D3D12

Audience: engineers scoping "Doe faster than Dawn across all boards" work.

## Why this audit exists

The 2026-04-16 Metal pipeline-cache-asymmetry push established a fair-cold lane for Apple Metal and set up the integration plan (`bench/docs/dawn-delegate-cache-integration.md`) for a fair-warm Dawn-cache shim. That framing assumed the asymmetry was "Doe has a cache, Dawn doesn't" and generalized to every board.

A source-level audit of the three native backends on 2026-04-16 shows the generalization is wrong. Vulkan and D3D12 have the *opposite* asymmetry: Dawn caches, Doe does not.

## Findings

### Apple Metal

- Doe opens `MTLBinaryArchive` at `runtime/zig/src/backend/metal/metal_native_runtime.zig:380-402` when `HAS_PIPELINE_CACHE` (macOS 11+) and `--no-pipeline-cache` is not passed. The archive is pre-warmed from `bench/kernels/doe_pipeline_archive.manifest`, which enumerates benchmark-specific kernels.
- Dawn's delegate path in Doe's vendored build does not open an `MTLBinaryArchive` because the Dawn instance is created through the standard `wgpuCreateInstance` path with no platform-caching interface installed.
- Default Doe-vs-Dawn native compare lanes now pass `--no-pipeline-cache` on both sides (G18 push) and record `trace_meta.pipelineCache.state="disabled" reason="cli-flag"` so the comparability gate auto-suppresses `pathAsymmetry: true` for cache-membership reasons.

**Direction: Doe ahead on cache; asymmetry handled for apples-to-apples by disabling Doe's cache.** Fair-warm requires wiring Dawn a persistent cache equivalent.

### AMD Vulkan

- Doe's Vulkan backend passes `VK_NULL_U64` (Vulkan's `VK_NULL_HANDLE`) as the `pipelineCache` argument to every pipeline creation call:
  - `runtime/zig/src/backend/vulkan/vk_pipeline.zig:385` — `vkCreateComputePipelines(self.device, VK_NULL_U64, 1, ...)`
  - `runtime/zig/src/backend/vulkan/vk_render_pipeline.zig:457` — `vkCreateGraphicsPipelines(...)` with the same `VK_NULL_U64` argument
- `runtime/zig/src/backend/vulkan/vk_pipeline_cache.zig` is a misleading filename: it holds `CachedDescriptorState` / `CachedComputeState` structs that represent *in-memory per-dispatch state* (descriptor set bindings, active pipeline handles). It is not a persistent pipeline cache.
- Dawn's Vulkan backend implements `PipelineCacheVk` (`bench/vendor/dawn/src/dawn/native/vulkan/PipelineCacheVk.{h,cpp}`) and uses it during pipeline creation in `ComputePipelineVk.cpp` and `RenderPipelineVk.cpp`. Dawn's VkPipelineCache is active by default on the delegate path.

**Direction: Dawn ahead on cache.** Every current AMD Vulkan Doe-vs-Dawn compute-pipeline compare is already strictly disadvantaged on the Doe side at the cache layer. Existing Doe wins on compute-pipeline-heavy workloads are therefore genuine runtime-engineering wins *despite* Dawn having a cache advantage — a stronger claim than was previously framed. But Doe is leaving performance on the table by not caching.

### Local D3D12

- Doe's D3D12 compute pipeline creation is in `runtime/zig/src/backend/d3d12/d3d12_bridge.c:174-192` and does not populate `desc.CachedPSO.pCachedBlob` / `.CachedBlobSizeInBytes` — the descriptor is `memset(&desc, 0, sizeof(desc))` and no cached-blob assignment follows before `CreateComputePipelineState(device, &desc, ...)`.
- The graphics pipeline paths at `d3d12_bridge.c:820` and `:930` follow the same shape.
- Dawn's D3D12 backend populates `d3dDesc.CachedPSO.pCachedBlob` / `.CachedBlobSizeInBytes` in `bench/vendor/dawn/src/dawn/native/d3d12/ComputePipelineD3D12.cpp:103-104` and the equivalent lines in `RenderPipelineD3D12.cpp:449` when a cached blob is available.

**Direction: Dawn ahead on cache when blob is available.** The D3D12 asymmetry mirrors Vulkan.

## Strategic implications

"Doe faster than Dawn across all boards" is two distinct engineering programs at the cache layer, not one:

1. **Metal program — Dawn catches up.** Wire Dawn a persistent cache equivalent through the shim designed in `bench/docs/dawn-delegate-cache-integration.md`. Moves Doe's existing cache wins from diagnostic to claim-grade. The build machinery is already proven buildable on Linux (see the 2026-04-16 component-build push).

2. **Vulkan + D3D12 program — Doe catches up.** Implement persistent pipeline caching on both Doe Vulkan and Doe D3D12 so Doe stops losing performance at the cache layer. This is independent of the Metal shim and independent of Dawn changes.

The two programs have very different implications:

| Program | Effect on Metal claims | Effect on Vulkan/D3D12 claims |
| --- | --- | --- |
| Metal Dawn-cache shim | promotes diagnostic → claim-grade | none |
| Doe Vulkan/D3D12 cache impl | none | removes a Dawn-side cache advantage currently hidden in the evidence |

Without the Vulkan/D3D12 cache work, any future claim that "Doe is faster than Dawn across all boards" is fundamentally weaker on Vulkan and D3D12 because Doe is running with the cache layer disabled. The existing AMD Vulkan claimable evidence survives this audit — it has always been fair-cold on Doe's side and fair-warm on Dawn's, so if Doe wins today, Doe wins more once both sides cache. But that "wins more" is not yet in the artifacts.

## Scope of the Vulkan + D3D12 cache implementation

Both implementations follow the same rough shape, adapted from `runtime/zig/src/backend/metal/metal_pipeline_cache.zig`:

### Vulkan

- create a process-level `VkPipelineCache` with `vkCreatePipelineCache` during device init
- thread its handle through the `vkCreateComputePipelines` / `vkCreateGraphicsPipelines` calls instead of `VK_NULL_U64`
- serialize via `vkGetPipelineCacheData` at shutdown and persist to a keyed disk location
- reload on startup via `VkPipelineCacheCreateInfo.pInitialData` when a matching key exists
- CLI knob parallel to Metal's `--no-pipeline-cache` and schema slot parallel to `trace_meta.pipelineCache.{state, reason, warmupCount, warmupNs}`

### D3D12

- implement a process-level PSO blob cache keyed by a hash over `(root-signature-blob, shader-bytecode, desc.Flags, NodeMask)`
- on hit, set `desc.CachedPSO.pCachedBlob` / `.CachedBlobSizeInBytes` before `CreateComputePipelineState`
- on miss, create uncached and call `ID3D12PipelineState::GetCachedBlob` to extract the blob post-creation for future caching
- persist to the same on-disk location contract as Vulkan (shared cache-dir policy with per-backend subdirectories)
- same CLI knob + schema slot treatment

The two implementations can share a cross-backend shape for the on-disk format, the `--no-pipeline-cache` / `--dawn-cache-dir` equivalent CLI flags, and the `trace_meta.pipelineCache.*` schema fields. The per-backend work is the API-specific serialization.

## What this audit does not decide

- Whether either Vulkan or D3D12 cache implementation lands before or after the Metal Dawn-cache shim. All three are independent; ordering is a bandwidth question.
- Whether to reuse Metal's benchmark-manifest (`doe_pipeline_archive.manifest`) shape for Vulkan / D3D12. The manifest shape was Metal-specific (benchmark-tuned pre-warm list); Vulkan's native `VkPipelineCache` is opaque and key-value, which is a cleaner default starting point.
- Whether the Vulkan cache should be a general runtime feature or a benchmark-fixture (the Metal archive is currently documented as a benchmark fixture, not a product runtime contract). This needs a product decision before landing.

## Follow-up queue

1. Implement Doe Vulkan persistent `VkPipelineCache`. Linux-executable with immediate AMD Vulkan evidence value.
2. Implement Doe D3D12 `CachedPSO` persistence. Windows-host testable only, but Linux-executable for the Zig + bridge-C side.
3. Complete the Metal Dawn-cache shim per `bench/docs/dawn-delegate-cache-integration.md`.
4. Re-run the affected AMD Vulkan and D3D12 compare lanes under the new caches to confirm Doe's wins remain or grow.
