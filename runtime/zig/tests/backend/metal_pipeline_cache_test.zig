// Metal pipeline cache tests. All tests are pure-logic (no Metal device required).
//
// MetalPipelineCache relies on ObjC bridge calls for archive operations, so
// GPU-dependent tests are not possible without a Metal device. These tests
// cover struct layout, constants, magic number validation, and the
// cache_from_opaque safety check.

const std = @import("std");
const builtin = @import("builtin");
const metal_pipeline_cache = @import("../../src/backend/metal/metal_pipeline_cache.zig");

// ============================================================
// Constants — stability
// ============================================================

test "metal cache: MetalPipelineCache magic is 0xD0EB10AC" {
    // The magic value identifies valid cache pointers passed through the C ABI.
    // Changing it would break in-flight opaque handles.
    const cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    try std.testing.expectEqual(@as(u32, 0xD0EB_10AC), cache.magic);
}

// ============================================================
// Struct layout — field defaults
// ============================================================

test "metal cache: MetalPipelineCache default archive is null" {
    const cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), cache.archive);
    try std.testing.expectEqual(@as(?[]u8, null), cache.archive_path);
}

test "metal cache: MetalPipelineCache default dirty is false" {
    const cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    try std.testing.expect(!cache.dirty);
}

test "metal cache: MetalPipelineCache stores device pointer" {
    var dummy: u8 = 0;
    const cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = @ptrCast(&dummy),
        .archive = null,
        .archive_path = null,
    };
    try std.testing.expect(cache.device != null);
}

// ============================================================
// Lookup with null archive — returns null without crash
// ============================================================

test "metal cache: lookup_compute_pipeline returns null when archive is null" {
    var cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), cache.lookup_compute_pipeline(null));
}

test "metal cache: lookup_render_pipeline returns null when archive is null" {
    var cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), cache.lookup_render_pipeline(0, 0));
}

// ============================================================
// Cache operations with null archive — no-ops without crash
// ============================================================

test "metal cache: cache_compute_pipeline is no-op when archive is null" {
    var cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    cache.cache_compute_pipeline(null);
    try std.testing.expect(!cache.dirty);
}

test "metal cache: cache_render_pipeline is no-op when archive is null" {
    var cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    cache.cache_render_pipeline(null);
    try std.testing.expect(!cache.dirty);
}

test "metal cache: flush_archive is no-op when archive is null" {
    var cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = null,
        .archive_path = null,
    };
    cache.flush_archive();
    try std.testing.expect(!cache.dirty);
}

test "metal cache: flush_archive is no-op when not dirty" {
    var dummy: u8 = 0;
    var cache = metal_pipeline_cache.MetalPipelineCache{
        .allocator = std.testing.allocator,
        .device = null,
        .archive = @ptrCast(&dummy),
        .archive_path = null,
        .dirty = false,
    };
    cache.flush_archive();
    try std.testing.expect(!cache.dirty);
}

// ============================================================
// C ABI export function — null safety
// ============================================================

test "metal cache: doeNativeMetalPipelineCacheFlush handles null" {
    // The flush C export must handle null gracefully.
    metal_pipeline_cache.doeNativeMetalPipelineCacheFlush(null);
}

test "metal cache: doeNativeMetalPipelineCacheLookupCompute returns null for null cache" {
    const result = metal_pipeline_cache.doeNativeMetalPipelineCacheLookupCompute(null, null);
    try std.testing.expectEqual(@as(?*anyopaque, null), result);
}

test "metal cache: doeNativeMetalPipelineCacheLookupRender returns null for null cache" {
    const result = metal_pipeline_cache.doeNativeMetalPipelineCacheLookupRender(null, 0, 0);
    try std.testing.expectEqual(@as(?*anyopaque, null), result);
}

test "metal cache: doeNativeMetalPipelineCacheAddCompute handles null" {
    metal_pipeline_cache.doeNativeMetalPipelineCacheAddCompute(null, null);
}

test "metal cache: doeNativeMetalPipelineCacheAddRender handles null" {
    metal_pipeline_cache.doeNativeMetalPipelineCacheAddRender(null, null);
}

// ============================================================
// C ABI export — magic number validation rejects zero-initialized pointers
// ============================================================

test "metal cache: C ABI flush rejects zero-initialized pointer via magic check" {
    // A zero-initialized buffer has magic == 0, which should fail the check.
    var zeroed: [256]u8 align(@alignOf(metal_pipeline_cache.MetalPipelineCache)) = [_]u8{0} ** 256;
    metal_pipeline_cache.doeNativeMetalPipelineCacheFlush(@ptrCast(&zeroed));
}

test "metal cache: C ABI lookup rejects zero-initialized pointer via magic check" {
    var zeroed: [256]u8 align(@alignOf(metal_pipeline_cache.MetalPipelineCache)) = [_]u8{0} ** 256;
    const result = metal_pipeline_cache.doeNativeMetalPipelineCacheLookupCompute(@ptrCast(&zeroed), null);
    try std.testing.expectEqual(@as(?*anyopaque, null), result);
}
