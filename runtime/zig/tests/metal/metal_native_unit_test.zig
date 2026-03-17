const std = @import("std");
const builtin = @import("builtin");
const metal_runtime = @import("../../src/backend/metal/metal_native_runtime.zig");

// ============================================================
// DispatchMetrics — struct layout and field values
// ============================================================

test "metal: DispatchMetrics stores all timing phases and dispatch count" {
    const m = metal_runtime.DispatchMetrics{
        .setup_ns = 100,
        .encode_ns = 200,
        .submit_wait_ns = 300,
        .dispatch_count = 4,
    };
    try std.testing.expectEqual(@as(u64, 100), m.setup_ns);
    try std.testing.expectEqual(@as(u64, 200), m.encode_ns);
    try std.testing.expectEqual(@as(u64, 300), m.submit_wait_ns);
    try std.testing.expectEqual(@as(u32, 4), m.dispatch_count);
}

test "metal: DispatchMetrics zero values are valid" {
    const m = metal_runtime.DispatchMetrics{
        .setup_ns = 0,
        .encode_ns = 0,
        .submit_wait_ns = 0,
        .dispatch_count = 0,
    };
    try std.testing.expectEqual(@as(u64, 0), m.setup_ns);
    try std.testing.expectEqual(@as(u32, 0), m.dispatch_count);
}

test "metal: DispatchMetrics accepts u64 max for timing fields" {
    const m = metal_runtime.DispatchMetrics{
        .setup_ns = std.math.maxInt(u64),
        .encode_ns = std.math.maxInt(u64),
        .submit_wait_ns = std.math.maxInt(u64),
        .dispatch_count = std.math.maxInt(u32),
    };
    try std.testing.expectEqual(std.math.maxInt(u64), m.setup_ns);
    try std.testing.expectEqual(std.math.maxInt(u32), m.dispatch_count);
}

// ============================================================
// RenderMetrics — struct layout and field values
// ============================================================

test "metal: RenderMetrics stores all timing phases and draw count" {
    const m = metal_runtime.RenderMetrics{
        .setup_ns = 10,
        .encode_ns = 20,
        .submit_wait_ns = 30,
        .draw_count = 5,
    };
    try std.testing.expectEqual(@as(u64, 10), m.setup_ns);
    try std.testing.expectEqual(@as(u64, 20), m.encode_ns);
    try std.testing.expectEqual(@as(u64, 30), m.submit_wait_ns);
    try std.testing.expectEqual(@as(u32, 5), m.draw_count);
}

test "metal: RenderMetrics zero values are valid" {
    const m = metal_runtime.RenderMetrics{
        .setup_ns = 0,
        .encode_ns = 0,
        .submit_wait_ns = 0,
        .draw_count = 0,
    };
    try std.testing.expectEqual(@as(u64, 0), m.setup_ns);
    try std.testing.expectEqual(@as(u32, 0), m.draw_count);
}

// ============================================================
// NativeMetalRuntime — default state initialization
// ============================================================

test "metal: NativeMetalRuntime default state has null device and queue" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.device);
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.queue);
    try std.testing.expect(!rt.has_device);
}

test "metal: NativeMetalRuntime default state has no deferred submissions" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expect(!rt.has_deferred_submissions);
}

test "metal: NativeMetalRuntime default streaming state is idle" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.streaming_cmd_buf);
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.streaming_blit_encoder);
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.streaming_render_encoder);
    try std.testing.expect(!rt.streaming_has_render);
    try std.testing.expect(!rt.streaming_has_copy);
    try std.testing.expectEqual(@as(usize, 0), rt.streaming_max_upload_bytes);
}

test "metal: NativeMetalRuntime default staging buffers are null" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.staging_src);
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.staging_dst);
    try std.testing.expectEqual(@as(?[*]u8, null), rt.staging_src_ptr);
    try std.testing.expect(!rt.staging_src_zeroed);
}

test "metal: NativeMetalRuntime default fence value is zero" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u64, 0), rt.fence_value);
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.shared_event);
}

test "metal: NativeMetalRuntime default render state is uninitialized" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.render_pipeline);
    try std.testing.expectEqual(@as(u32, 0), rt.render_pipeline_format);
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.render_target);
    try std.testing.expectEqual(@as(u32, 0), rt.render_target_width);
    try std.testing.expectEqual(@as(u32, 0), rt.render_target_height);
    try std.testing.expectEqual(@as(u32, 0), rt.render_target_format);
}

test "metal: NativeMetalRuntime default ICB cache is null" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.cached_icb);
}

test "metal: NativeMetalRuntime default pipeline binary cache is null" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.pipeline_binary_cache);
}

test "metal: NativeMetalRuntime default outstanding_cmd_buf is null" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?*anyopaque, null), rt.outstanding_cmd_buf);
}

test "metal: NativeMetalRuntime kernel_root default is null" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(?[]const u8, null), rt.kernel_root);
}

test "metal: NativeMetalRuntime kernel_root can be set at construction" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
        .kernel_root = "bench/kernels",
    };
    try std.testing.expectEqualStrings("bench/kernels", rt.kernel_root.?);
}

// ============================================================
// NativeMetalRuntime — streaming uploads list default
// ============================================================

test "metal: NativeMetalRuntime default streaming uploads list is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(usize, 0), rt.streaming_uploads.items.len);
}

// ============================================================
// NativeMetalRuntime — deferred releases default
// ============================================================

test "metal: NativeMetalRuntime default deferred releases list is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(usize, 0), rt.deferred_releases.items.len);
}

// ============================================================
// NativeMetalRuntime — hash map defaults are empty
// ============================================================

test "metal: NativeMetalRuntime default compute buffers map is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.compute_buffers.count());
}

test "metal: NativeMetalRuntime default textures map is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.textures.count());
}

test "metal: NativeMetalRuntime default samplers map is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.samplers.count());
}

test "metal: NativeMetalRuntime default surfaces map is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.surfaces.count());
}

test "metal: NativeMetalRuntime default kernel_pipelines map is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.kernel_pipelines.count());
}

// ============================================================
// NativeMetalRuntime — buffer pool defaults are empty
// ============================================================

test "metal: NativeMetalRuntime default shared_pool is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.shared_pool.count());
}

test "metal: NativeMetalRuntime default private_pool is empty" {
    const rt = metal_runtime.NativeMetalRuntime{
        .allocator = std.testing.allocator,
    };
    try std.testing.expectEqual(@as(u32, 0), rt.private_pool.count());
}
