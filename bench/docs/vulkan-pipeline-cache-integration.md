# Doe Vulkan persistent pipeline cache — integration design

Audience: engineers implementing Doe-side persistent `VkPipelineCache` to close the cache asymmetry against Dawn on AMD Vulkan and any future Vulkan board.

## Status

Scoping-only as of 2026-04-17. Doe's Vulkan backend currently passes `VK_NULL_U64` (VK_NULL_HANDLE) as the `pipelineCache` argument to `vkCreateComputePipelines` (`runtime/zig/src/backend/vulkan/vk_pipeline.zig:385`) and `vkCreateGraphicsPipelines` (`vk_render_pipeline.zig:457`). Dawn's Vulkan backend uses `dawn::native::vulkan::PipelineCacheVk` and threads a real `VkPipelineCache` into every pipeline creation call.

This document scopes the Doe-side implementation without introducing placeholder Zig code (CLAUDE.md non-negotiable #2 forbids runtime-behavior placeholders in the execution path).

See also:

- `bench/docs/pipeline-cache-backend-audit.md` -- the three-backend audit that identified this asymmetry
- `bench/docs/dawn-delegate-cache-integration.md` -- the parallel Metal-only Dawn-cache shim work
- `bench/docs/compute-matvec-regression-trace.md` -- the matvec regression that is most likely caused by the missing Vulkan cache

## What Doe has today

- `runtime/zig/src/backend/vulkan/vk_pipeline_cache.zig` is an *in-memory* per-device state cache of descriptor-set / pipeline / layout handles. It is not a persistent `VkPipelineCache` and not disk-backed.
- Pipeline creation calls pass `VK_NULL_U64` as the cache handle. Every `vkCreateComputePipelines` / `vkCreateGraphicsPipelines` call is therefore a cold compile at the driver level.
- The `--no-pipeline-cache` CLI flag (`runtime/zig/src/cli/runtime_cli_args.zig:205-206`) exists and is plumbed to Metal (`backend_runtime_telemetry.set_metal_pipeline_cache_disabled`) but is a no-op on the Vulkan path today.
- `trace_meta.pipelineCache.{state,reason,warmupCount,warmupNs}` fields exist and are populated only on Metal builds.

## Vulkan API surface required

From `bench/vendor/dawn/include/vulkan/vulkan_core.h` (and the equivalents in Doe's vendored Vulkan headers):

```c
VkResult vkCreatePipelineCache(
    VkDevice device,
    const VkPipelineCacheCreateInfo* pCreateInfo,
    const VkAllocationCallbacks* pAllocator,
    VkPipelineCache* pPipelineCache);

void vkDestroyPipelineCache(
    VkDevice device,
    VkPipelineCache pipelineCache,
    const VkAllocationCallbacks* pAllocator);

VkResult vkGetPipelineCacheData(
    VkDevice device,
    VkPipelineCache pipelineCache,
    size_t* pDataSize,
    void* pData);

VkResult vkMergePipelineCaches(
    VkDevice device,
    VkPipelineCache dstCache,
    uint32_t srcCacheCount,
    const VkPipelineCache* pSrcCaches);

typedef struct VkPipelineCacheCreateInfo {
    VkStructureType sType;              // VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO = 17
    const void* pNext;
    VkPipelineCacheCreateFlags flags;
    size_t initialDataSize;
    const void* pInitialData;
} VkPipelineCacheCreateInfo;

typedef struct VkPipelineCacheHeaderVersionOne {
    uint32_t headerSize;                // must be 32
    VkPipelineCacheHeaderVersion headerVersion;
    uint32_t vendorID;
    uint32_t deviceID;
    uint8_t pipelineCacheUUID[VK_UUID_SIZE];
} VkPipelineCacheHeaderVersionOne;
```

`VkMergePipelineCaches` is optional; the first implementation can ignore it.

## Integration plan

### 1. FFI additions -- `runtime/zig/src/backend/vulkan/vk_functions.zig` + `vk_constants.zig`

Add:

- extern declarations for `vkCreatePipelineCache`, `vkDestroyPipelineCache`, `vkGetPipelineCacheData`
- `VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO: i32 = 17` in `vk_constants.zig`
- `VkPipelineCacheCreateInfo` struct in the existing `vulkan_types.zig` or a structs module

Must be used by the new module below; the current Zig convention is that every FFI declaration is referenced somewhere in the backend tree.

### 2. Persistent cache module -- `runtime/zig/src/backend/vulkan/vk_pipeline_cache_persistent.zig` (new)

Mirrors the shape of `runtime/zig/src/backend/metal/metal_pipeline_cache.zig`:

```zig
pub const VulkanPipelineCacheState = enum { disabled, enabled, enabled_reloaded };

// Process-level handle (matches Metal's `process_active_cache` pattern).
var process_cache_handle: c.VkPipelineCache = c.VK_NULL_U64;
var process_cache_state: VulkanPipelineCacheState = .disabled;
var process_cache_path: ?[]u8 = null;
var process_cache_disabled: bool = false;

pub fn set_process_pipeline_cache_disabled(disabled: bool) void;
pub fn is_process_pipeline_cache_disabled() bool;

pub fn create_process_pipeline_cache(
    device: c.VkDevice,
    cache_dir: ?[]const u8,
) !void;

pub fn destroy_process_pipeline_cache(device: c.VkDevice) void;

pub fn handle_for_pipeline_creation() c.VkPipelineCache;

pub fn process_active_cache_telemetry() struct { state: VulkanPipelineCacheState, warmup_count: u64, warmup_ns: u64 };
```

Key behaviors:

- `create_process_pipeline_cache` reads the existing blob at `<cache_dir>/vulkan-pipeline-cache.blob` if present, validates its `VkPipelineCacheHeaderVersionOne` against the current device's vendorID/deviceID/UUID (reject mismatches -- loading a mismatched blob is UB per spec), creates the cache with or without `pInitialData`, and records `process_cache_state`.
- `handle_for_pipeline_creation` returns `process_cache_handle` when not disabled, else `VK_NULL_U64`. This is the replacement for the current bare `VK_NULL_U64` argument.
- `destroy_process_pipeline_cache` serializes via `vkGetPipelineCacheData` and writes atomically (`*.tmp` + `rename`) to the cache path, then destroys the handle.

Telemetry mirrors Metal's shape so the existing reader side (`bench/native_compare_modules/run_artifact.py::_pipeline_cache_telemetry`) works without changes.

### 3. Cross-platform wrapper -- `backend_runtime_telemetry.zig` additions

Parallel to the Metal flag plumbing:

```zig
pub fn set_vulkan_pipeline_cache_disabled(disabled: bool) void;  // no-op on non-Vulkan builds
pub fn vulkan_pipeline_cache_telemetry() ?PipelineCacheTelemetry;
```

Preserves the `cli/ -> backend/` import fence.

### 4. Pipeline-creation callsite changes

In `runtime/zig/src/backend/vulkan/vk_pipeline.zig:385` and `vk_render_pipeline.zig:457`, replace `VK_NULL_U64` with `vk_pipeline_cache_persistent.handle_for_pipeline_creation()`.

This is the one-line runtime change that actually activates the cache. Everything else is infrastructure.

### 5. CLI + options

`--no-pipeline-cache` is already parsed (`cli/runtime_cli_args.zig:205-206`). Extend its effect in `cli/runtime_cli.zig` to call both the Metal and Vulkan wrappers before `ExecutionContext.init`.

Optional new flag: `--pipeline-cache-dir <path>` to override the default cache location. Default location is `${XDG_CACHE_HOME:-~/.cache}/doe/pipeline-cache/vulkan/`.

### 6. Trace schema

The existing `trace_meta.pipelineCache.{state, reason}` fields are Metal-specific today. Two options:

a. **Extend the same field to cover whichever backend is active.** When the active backend is Vulkan, populate `pipelineCache.state` from the Vulkan module. Cleaner schema (single field set) but requires the reader to understand the backend context.

b. **Add a parallel `vulkanPipelineCache` object.** More schema fields but each backend owns its own.

Recommended: option (a), with an added `backend` field inside `pipelineCache` (`"metal" | "vulkan" | "d3d12" | null`) so readers can disambiguate. Keep the same `{state, reason, warmupCount, warmupNs}` payload shape.

### 7. Executor registry updates

Mirror the Metal pattern from the G18 push: introduce `doe_direct_vulkan_no_cache` and `doe_direct_vulkan_cache` executor templates in `bench/native_compare_modules/executor_registry.py`. The default `doe_direct_vulkan` can pick either; recommend making the cache-enabled variant the default (matches user-code behavior) and keeping the no-cache variant as an explicit opt-in for cache-contribution lanes.

### 8. Tests

- `bench/tests/test_vulkan_pipeline_cache_state.py` -- mirrors `test_pipeline_cache_state.py`. Unit tests the reader, resolver, and executor template presence.
- `runtime/zig/src/backend/vulkan/vk_pipeline_cache_persistent_test.zig` -- inline Zig test for the header validation and round-trip serialize/deserialize.

### 9. Documentation

- Update `bench/docs/pipeline-cache-backend-audit.md` "Follow-up queue" item 1 to reference this doc and the landed implementation.
- Extend `bench/docs/pipeline-cache-contribution-lane.md` "Per-backend applicability" table row for AMD Vulkan from "No -- Doe does not yet implement persistent VkPipelineCache" to "Yes, via `doe_direct_vulkan_no_cache` / `doe_direct_vulkan_cache`".
- Add a status shard entry.

## Scoping by platform

| Step | Linux-executable | Other hosts |
| --- | --- | --- |
| 1. FFI additions | yes (compile-green) | same |
| 2. Persistent cache module | yes (compile-green; behavior-inert until wired) | same |
| 3. Cross-platform wrapper | yes | same |
| 4. Pipeline-creation callsite | yes (Linux has Vulkan hardware here) | same |
| 5. CLI + options | yes | same |
| 6. Trace schema | yes | same |
| 7. Executor templates | yes | same |
| 8. Tests | yes (Zig inline + Python unit) | same |
| 9. Docs | yes | same |

Unlike the Metal Dawn shim (which needs Mac hardware for end-to-end validation), the Doe Vulkan cache can be fully implemented and validated on Linux with AMD Vulkan hardware (which this host has).

## Expected outcome for "Doe faster than Dawn across all boards"

Confirming directionally only; actual delta will be measured against current artifacts post-landing:

- **Cold-first-compile workloads** (`pipeline_compile_stress`, workloads that create pipelines in the timed loop): Doe gains parity or slight advantage because both sides now cache. Today Doe is winning on `pipeline_compile_stress` by +48% despite no cache -- that delta should widen.
- **Steady-state compute workloads** (`compute_matvec_*`, `compute_workgroup_*`): Doe's first-iteration per-process cost drops. Whether the steady-state `p50` improves depends on whether the matvec regression is in the shader code itself or in the cold-compile cost. Hypothesis 1 in `compute-matvec-regression-trace.md` predicts matvec improves materially under cache; if it does not, the regression is shader-side and needs the RGP follow-up.
- **Upload workloads**: no effect (they don't create pipelines).

## Risks

- **Cache blob UUID mismatch across driver upgrades.** Vulkan spec requires the header UUID to match exactly; an older cache blob from a previous driver version is invalid. The implementation must reject mismatched blobs silently and recreate the cache from scratch, not fail the device init.
- **Thread safety.** `vkCreatePipelineCache` and pipeline creation calls are externally synchronized. A process-level cache accessed from multiple devices would need a mutex, or the cache must be per-device. Recommended: per-device cache, one per `ZigVulkanBackend.init`. The "process-level" framing in the Metal module should be reviewed before mirroring -- Metal's `MTLBinaryArchive` has different threading semantics.
- **Disk I/O in hot path.** The atomic write at `destroy_process_pipeline_cache` can be deferred to an explicit flush hook so it does not slow benchmark teardown.
- **Cache blob size growth.** Pipeline caches can grow unbounded in a long-running process. The first implementation can ignore this; a cap + LRU eviction is a follow-up.

## Follow-up queue

1. Land Steps 1-4 as a single focused push -- minimal plumbing + the one-line callsite change. Validates that Doe-side Vulkan caching works end-to-end on AMD Vulkan hardware.
2. Land Steps 5-7 in a follow-up push -- CLI flag parity, trace schema, executor templates.
3. Re-run the matvec compare and the `pipeline_compile_stress` compare; document the deltas.
4. Parallel track: implement D3D12 `CachedPSO` persistence with the same design shape (once a Windows host is in rotation).
