//! Physical checks for deferred writes, dispatch ordering and surface retirement.
//! Unsupported hosts skip explicitly; a failed native acquisition is a failure.
const std = @import("std");
const builtin = @import("builtin");
const metal = @import("../../src/backend/metal/metal_native_runtime.zig");
const bridge = @import("../../src/backend/metal/metal_bridge_decls.zig");
const compute = @import("../../src/contracts/model/model_compute_types.zig");

fn requireMetal() !void {
    if (builtin.os.tag != .macos) return error.SkipZigTest;
}

fn expectBytes(runtime: *metal.NativeMetalRuntime, handle: u64, length: usize, expected: u8) !void {
    const buffer = runtime.compute_buffers.get(handle) orelse return error.MissingBuffer;
    const raw = bridge.metal_bridge_buffer_contents(buffer) orelse return error.UnmappedBuffer;
    const bytes = @as([*]const u8, @ptrCast(raw))[0..length];
    for (bytes) |byte| try std.testing.expectEqual(expected, byte);
}

test "Metal repair proof: staged writes preserve interleaved snapshots across size boundaries" {
    try requireMetal();
    var runtime = try metal.NativeMetalRuntime.init(std.testing.allocator, null, "", false);
    defer runtime.deinit();
    const sizes = [_]usize{ 4, 252, 256, 260, 4096, metal.SMALL_UPLOAD_CAPACITY - 4, metal.SMALL_UPLOAD_CAPACITY, metal.SMALL_UPLOAD_CAPACITY + 4 };
    for (sizes, 0..) |size, index| {
        const source_handle: u64 = index * 2 + 1;
        const destination_handle = source_handle + 1;
        for (0..2) |_| {
            const source = try std.testing.allocator.alloc(u8, size);
            defer std.testing.allocator.free(source);
            @memset(source, 17);
            try runtime.stage_buffer_write_bytes(source_handle, 0, size, source);
            _ = try runtime.copy_command(.{
                .direction = .buffer_to_buffer,
                .src = .{ .handle = source_handle },
                .dst = .{ .handle = destination_handle },
                .bytes = size,
            }, .deferred);
            @memset(source, 83);
            try runtime.stage_buffer_write_bytes(source_handle, 0, size, source);
            // Poison the borrowed input before any submission reads its snapshot.
            @memset(source, 255);
            _ = try runtime.flush_queue();
            try expectBytes(&runtime, source_handle, size, 83);
            try expectBytes(&runtime, destination_handle, size, 17);
        }
    }
}

test "Metal repair proof: caller allocation dies before write and dispatch completion" {
    try requireMetal();
    var temporary = std.testing.tmpDir(.{});
    defer temporary.cleanup();
    try temporary.dir.writeFile(.{ .sub_path = "increment.metal", .data = 
        \\#include <metal_stdlib>
        \\using namespace metal;
        \\[[max_total_threads_per_threadgroup(1)]]
        \\kernel void main_kernel(device uint* data [[buffer(0)]]) { data[0] += 1; }
    });
    const root = try temporary.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    var runtime = try metal.NativeMetalRuntime.init(std.testing.allocator, root, "", false);
    defer runtime.deinit();
    {
        const source = try std.testing.allocator.alloc(u8, @sizeOf(u32));
        defer std.testing.allocator.free(source);
        std.mem.writeInt(u32, source[0..4], 42, .little);
        try runtime.stage_buffer_write_bytes(1, 0, source.len, source);
    }
    const bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 1, .buffer_size = @sizeOf(u32) }};
    _ = try runtime.run_kernel_dispatch("increment", "main", 1, 1, 1, 1, 0, false, &bindings);
    _ = try runtime.flush_queue();
    const buffer = runtime.compute_buffers.get(1) orelse return error.MissingBuffer;
    const raw = bridge.metal_bridge_buffer_contents(buffer) orelse return error.UnmappedBuffer;
    const bytes = @as([*]const u8, @ptrCast(raw))[0..4];
    try std.testing.expectEqual(@as(u32, 43), std.mem.readInt(u32, bytes, .little));
}

test "Metal repair proof: acquired offscreen surface survives explicit release and teardown" {
    try requireMetal();
    var runtime = try metal.NativeMetalRuntime.init(std.testing.allocator, null, "", false);
    defer runtime.deinit();
    for ([_]u64{ 1, 2 }) |handle| {
        try runtime.surface_create(.{ .handle = handle });
        try runtime.surface_configure(.{ .handle = handle, .width = 4, .height = 4 });
        try runtime.surface_acquire(.{ .handle = handle });
    }
    try runtime.surface_release(.{ .handle = 1 });
    // The remaining acquired surface exercises runtime-owned teardown.
}

test "Metal repair proof: padded texture layers and temporary copies preserve bytes and guards" {
    try requireMetal();
    const values = @import("../../src/contracts/model/model_texture_value_types.zig");
    var runtime = try metal.NativeMetalRuntime.init(std.testing.allocator, null, "", false);
    defer runtime.deinit();
    var source = [_]u8{255} ** 60;
    @memset(source[4..12], 17);
    @memset(source[16..24], 18);
    @memset(source[40..48], 83);
    @memset(source[52..60], 84);
    const descriptor = @import("../../src/contracts/model/model_resource_types.zig").CopyTextureResource{
        .handle = 21,
        .kind = .texture,
        .width = 4,
        .height = 4,
        .depth_or_array_layers = 2,
        .mip_level = 1,
        .format = values.WGPUTextureFormat_RGBA8Unorm,
        .usage = values.WGPUTextureUsage_CopySrc | values.WGPUTextureUsage_CopyDst,
        .offset = 4,
        .bytes_per_row = 12,
        .rows_per_image = 3,
    };
    try std.testing.expectError(error.TextureCopyRange, runtime.texture_write(.{ .texture = descriptor, .data = source[0..59] }));
    try std.testing.expectEqual(@as(u32, 0), runtime.textures.count());
    try runtime.texture_write(.{ .texture = descriptor, .data = &source });
    try std.testing.expectError(error.InvalidState, runtime.texture_query(.{ .handle = descriptor.handle, .expected_depth_or_array_layers = 1 }));
    var destination = descriptor;
    destination.handle = 22;
    // Exercise both native texture copies and the selected temporary-buffer path.
    for ([_]bool{ false, true }, 0..) |temporary, index| {
        _ = try runtime.copy_command(.{ .direction = .texture_to_texture, .src = descriptor, .dst = destination, .bytes = 32, .uses_temporary_buffer = temporary, .temporary_buffer_alignment = 256 }, .deferred);
        const readback_handle: u64 = 30 + index;
        const guard = [_]u8{211} ** 60;
        try runtime.write_buffer_bytes(readback_handle, 0, guard.len, &guard);
        _ = try runtime.copy_command(.{ .direction = .texture_to_buffer, .src = destination, .dst = .{ .handle = readback_handle, .offset = 4, .bytes_per_row = 12, .rows_per_image = 3 }, .bytes = 56 }, .deferred);
        _ = try runtime.flush_queue();
        const buffer = runtime.compute_buffers.get(readback_handle) orelse return error.MissingBuffer;
        const raw = bridge.metal_bridge_buffer_contents(buffer) orelse return error.UnmappedBuffer;
        var expected = guard;
        @memset(expected[4..12], 17);
        @memset(expected[16..24], 18);
        @memset(expected[40..48], 83);
        @memset(expected[52..60], 84);
        try std.testing.expectEqualSlices(u8, &expected, @as([*]const u8, @ptrCast(raw))[0..expected.len]);
    }
}
