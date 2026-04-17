// Process-level persistent VkPipelineCache for the Doe Vulkan backend.
//
// Parallels runtime/zig/src/backend/metal/metal_pipeline_cache.zig in shape.
// The first tracked landing keeps the cache in-memory only: we create a real
// VkPipelineCache via vkCreatePipelineCache at device bring-up and pass its
// handle to vkCreateComputePipelines / vkCreateGraphicsPipelines instead of
// VK_NULL_U64. Disk-backed persistence (vkGetPipelineCacheData read/write
// against a keyed blob on shutdown) is a follow-up; the module exposes the
// serializer seam here so that landing does not require touching callsites.

const std = @import("std");
const c = @import("vk_constants.zig");

pub const VulkanPipelineCacheState = enum { disabled, enabled, enabled_reloaded };

pub const WarmupTelemetry = struct {
    count: u64 = 0,
    ns: u64 = 0,
};

// Process-level handle mirroring the Metal backend's process_active_cache
// pattern. Only one Vulkan device is active per process in current benchmark
// usage; the module deliberately stays single-handle until a multi-device
// consumer needs it.
var process_cache_handle: c.VkPipelineCache = c.VK_NULL_U64;
var process_cache_state: VulkanPipelineCacheState = .disabled;
var process_cache_disabled: bool = false;
var process_cache_device: c.VkDevice = null;
var process_warmup: WarmupTelemetry = .{};

pub fn set_process_pipeline_cache_disabled(disabled: bool) void {
    process_cache_disabled = disabled;
}

pub fn is_process_pipeline_cache_disabled() bool {
    return process_cache_disabled;
}

/// Create the process-level VkPipelineCache after vkCreateDevice. The cache is
/// empty on first creation; disk-backed preload is a follow-up. Safe to call
/// multiple times: if the cache is already live, the call is a no-op.
pub fn create_process_pipeline_cache(device: c.VkDevice) !void {
    if (process_cache_disabled) {
        process_cache_state = .disabled;
        return;
    }
    if (process_cache_handle != c.VK_NULL_U64) {
        // Already live; treat as idempotent.
        return;
    }
    if (device == null) return error.InvalidArgument;

    const start_ns = std.time.nanoTimestamp();
    var create_info = c.VkPipelineCacheCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .initialDataSize = 0,
        .pInitialData = null,
    };
    var handle: c.VkPipelineCache = c.VK_NULL_U64;
    const result = c.vkCreatePipelineCache(device, &create_info, null, &handle);
    if (result != c.VK_SUCCESS) {
        process_cache_state = .disabled;
        return error.PipelineCacheCreateFailed;
    }
    process_cache_handle = handle;
    process_cache_device = device;
    process_cache_state = .enabled;
    const end_ns = std.time.nanoTimestamp();
    process_warmup.count = 1;
    process_warmup.ns = @intCast(end_ns - start_ns);
}

/// Destroy the process-level cache. Safe to call multiple times. Must be
/// called before vkDestroyDevice on the same device the cache was created on.
pub fn destroy_process_pipeline_cache(device: c.VkDevice) void {
    if (process_cache_handle == c.VK_NULL_U64) return;
    if (device == null) return;
    if (process_cache_device != device) {
        // Device mismatch; refuse to destroy against a foreign device rather
        // than crash inside the driver. This should be impossible in current
        // single-device usage, but keeps the invariant explicit.
        return;
    }
    c.vkDestroyPipelineCache(device, process_cache_handle, null);
    process_cache_handle = c.VK_NULL_U64;
    process_cache_device = null;
    process_cache_state = .disabled;
    process_warmup = .{};
}

/// Returns the handle to pass to vkCreateComputePipelines /
/// vkCreateGraphicsPipelines. Returns VK_NULL_U64 when the cache is disabled
/// (either by --no-pipeline-cache or by a failed create); that preserves
/// existing behavior as the fallback.
pub fn handle_for_pipeline_creation() c.VkPipelineCache {
    if (process_cache_disabled) return c.VK_NULL_U64;
    return process_cache_handle;
}

pub fn process_active_cache_present() bool {
    return process_cache_handle != c.VK_NULL_U64 and process_cache_state != .disabled;
}

pub fn process_active_cache_warmup_telemetry() WarmupTelemetry {
    return process_warmup;
}

/// Reset module-level state. Test-only entrypoint.
pub fn reset_for_testing() void {
    process_cache_handle = c.VK_NULL_U64;
    process_cache_state = .disabled;
    process_cache_disabled = false;
    process_cache_device = null;
    process_warmup = .{};
}

test "disabled flag suppresses cache creation" {
    reset_for_testing();
    set_process_pipeline_cache_disabled(true);
    try std.testing.expect(is_process_pipeline_cache_disabled());
    try std.testing.expectEqual(@as(c.VkPipelineCache, c.VK_NULL_U64), handle_for_pipeline_creation());
    try std.testing.expect(!process_active_cache_present());
}

test "default state is disabled handle" {
    reset_for_testing();
    try std.testing.expect(!is_process_pipeline_cache_disabled());
    try std.testing.expectEqual(@as(c.VkPipelineCache, c.VK_NULL_U64), handle_for_pipeline_creation());
    try std.testing.expect(!process_active_cache_present());
}
