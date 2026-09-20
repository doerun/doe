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

test "Metal repair proof: checked indirect arguments execute exact dimensions and preserve guards" {
    try requireMetal();
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32, 8>;
        \\@compute @workgroup_size(3) fn main(@builtin(global_invocation_id) id: vec3<u32>) {
        \\    data[id.x] = id.x + 10u;
        \\}
    ;
    var directory = std.testing.tmpDir(.{});
    defer directory.cleanup();
    try directory.dir.writeFile(.{ .sub_path = "indirect.wgsl", .data = source });
    try directory.dir.writeFile(.{ .sub_path = "dispatch_noop.wgsl", .data = "@compute @workgroup_size(1) fn main() {}" });
    const root = try directory.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    var runtime = try metal.NativeMetalRuntime.init(std.testing.allocator, root, "", false);
    defer runtime.deinit();
    const sentinel: u32 = 123456;
    const initial = [_]u32{sentinel} ** 8;
    const arguments = [_]u32{ sentinel, 2, 1, 1 };
    try runtime.write_buffer_bytes(1, 0, @sizeOf(@TypeOf(initial)), std.mem.asBytes(&initial));
    try runtime.write_buffer_bytes(2, 0, @sizeOf(@TypeOf(arguments)), std.mem.asBytes(&arguments));
    const program = try runtime.ensure_kernel_pipeline_info("indirect", "main");
    try runtime.completion.reserve(runtime.allocator);
    const command = bridge.metal_bridge_create_command_buffer(runtime.queue) orelse return error.MetalEncodingFailed;
    var submitted = false;
    defer if (!submitted) bridge.metal_bridge_release(command);
    const encoder = bridge.metal_bridge_cmd_buf_compute_encoder(command) orelse return error.MetalEncodingFailed;
    var encoding = true;
    defer if (encoding) bridge.metal_bridge_end_compute_encoding(encoder);
    // Zero dispatches prepares the validated fixed-size buffer binding only.
    try std.testing.expectEqual(@as(c_int, 1), bridge.metal_bridge_compute_encoder_dispatch_checked(encoder, program.pipeline, &.{runtime.compute_buffers.get(1).?}, &.{0}, &.{@sizeOf(@TypeOf(initial))}, 1, std.math.maxInt(u32), &.{ 1, 1, 1 }, &program.workgroup_size, 0));
    const indirect = runtime.compute_buffers.get(2).?;
    try std.testing.expectEqual(@as(c_int, 0), bridge.metal_bridge_compute_encoder_dispatch_indirect_checked(encoder, program.pipeline, indirect, 1, &program.workgroup_size));
    try std.testing.expectEqual(@as(c_int, 0), bridge.metal_bridge_compute_encoder_dispatch_indirect_checked(encoder, program.pipeline, indirect, 8, &program.workgroup_size));
    try std.testing.expectEqual(@as(c_int, 0), bridge.metal_bridge_compute_encoder_dispatch_indirect_checked(encoder, program.pipeline, indirect, 4, &.{ 0, 1, 1 }));
    try std.testing.expectEqual(@as(c_int, 1), bridge.metal_bridge_compute_encoder_dispatch_indirect_checked(encoder, program.pipeline, indirect, 4, &program.workgroup_size));
    bridge.metal_bridge_end_compute_encoding(encoder);
    encoding = false;
    bridge.metal_bridge_command_buffer_commit(command);
    runtime.completion.retainSubmitted(command);
    submitted = true;
    try runtime.completion.retire();
    try runtime.completion.check();
    const bytes = bridge.metal_bridge_buffer_contents(runtime.compute_buffers.get(1).?).?;
    for (0..initial.len) |i| {
        const expected: u32 = if (i < 6) @as(u32, @intCast(i)) + 10 else sentinel;
        try std.testing.expectEqual(expected, std.mem.readInt(u32, bytes[i * 4 ..][0..4], .little));
    }
    const direct = try runtime.run_dispatch(2, 1, 1, .per_command);
    const deferred = try runtime.run_dispatch_indirect(2, 1, 1, .deferred);
    _ = try runtime.flush_queue();
    try std.testing.expectEqual(@as(u32, 1), direct.submit_count);
    try std.testing.expectEqual(@as(u32, 1), deferred.submit_count);
}

test "Metal repair proof: selected WGSL entrypoint bindings and source replacement preserve guards" {
    try requireMetal();
    const source =
        \\@group(1) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(1) fn main() { data[0] = 999u; }
        \\@compute @workgroup_size(7) fn selected(@builtin(local_invocation_id) id: vec3<u32>) {
        \\    data[id.x] = arrayLength(&data);
        \\}
    ;
    var directory = std.testing.tmpDir(.{});
    defer directory.cleanup();
    try directory.dir.writeFile(.{ .sub_path = "selected.wgsl", .data = source });
    try directory.dir.writeFile(.{ .sub_path = "selected.metal", .data = "invalid sibling must never be selected" });
    const root = try directory.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    var runtime = try metal.NativeMetalRuntime.init(std.testing.allocator, root, "", false);
    defer runtime.deinit();
    const prefix = 256;
    const words = 7;
    const guard = [_]u8{211} ** (prefix + words * @sizeOf(u32) + 16);
    try runtime.write_buffer_bytes(1, 0, guard.len, &guard);
    var bindings = [_]compute.KernelBinding{.{ .group = 1, .binding = 0, .resource_kind = .buffer, .resource_handle = 1, .buffer_offset = prefix, .buffer_size = words * @sizeOf(u32) }};
    _ = try runtime.run_kernel_dispatch("selected.wgsl", "selected", 1, 1, 1, 1, 1, false, &bindings);
    const buffer = runtime.compute_buffers.get(1).?;
    const bytes = bridge.metal_bridge_buffer_contents(buffer).?[0..guard.len];
    try std.testing.expectEqualSlices(u8, guard[0..prefix], bytes[0..prefix]);
    try std.testing.expectEqualSlices(u8, guard[prefix + words * 4 ..], bytes[prefix + words * 4 ..]);
    for (0..words) |i| try std.testing.expectEqual(@as(u32, words), std.mem.readInt(u32, bytes[prefix + i * 4 ..][0..4], .little));
    bindings[0].buffer_size = 2;
    try std.testing.expectError(error.InvalidBindingRange, runtime.run_kernel_dispatch("selected", "selected", 1, 1, 1, 1, 0, false, &bindings));
    bindings[0].buffer_size = words * 4;
    const replacement =
        \\@group(1) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(7) fn selected(@builtin(local_invocation_id) id: vec3<u32>) {
        \\    data[id.x] = 42u;
        \\}
    ;
    try directory.dir.writeFile(.{ .sub_path = "selected.wgsl", .data = replacement });
    _ = try runtime.run_kernel_dispatch("selected", "selected", 1, 1, 1, 1, 0, false, &bindings);
    for (0..words) |i| try std.testing.expectEqual(@as(u32, 42), std.mem.readInt(u32, bytes[prefix + i * 4 ..][0..4], .little));
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
            try runtime.transition_streaming_submission_deferred();
            @memset(source, 83);
            try runtime.stage_buffer_write_bytes(source_handle, 0, size, source);
            try runtime.transition_streaming_submission_deferred();
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
    const source_code =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(1) fn main() { data[0] += 1u; }
    ;
    try temporary.dir.writeFile(.{ .sub_path = "increment.wgsl", .data = source_code });
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
