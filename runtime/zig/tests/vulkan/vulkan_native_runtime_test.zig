const std = @import("std");
const backend_policy = @import("../../src/backend/backend_policy.zig");
const webgpu = @import("../../src/compat/webgpu_ffi.zig");
const native_runtime = @import("../../src/backend/vulkan/native_runtime.zig");
const compute_program = @import("../../src/backend/vulkan/vk_compute_program.zig");
const resources = @import("../../src/backend/vulkan/vk_resources.zig");
const shared = @import("../../src/backend/vulkan/vk_shared_pipeline.zig");
const compiler = @import("../../src/compiler/wgsl/mod.zig");
const compute = @import("../../src/contracts/model/model_compute_types.zig");
const binding_types = @import("../../src/contracts/model/model_binding_value_types.zig");
const vk = @import("../../src/backend/vulkan/vk_constants.zig");
const adapter_probe = @import("../../src/backend/vulkan/vk_adapter_probe.zig");

fn probe_with_allocator(allocator: std.mem.Allocator) !void {
    var probe = try adapter_probe.probe_selected_adapter(allocator, .prefer_graphics_compute);
    defer probe.deinit(allocator);
}

test "Vulkan adapter selection preserves allocation failures" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, probe_with_allocator, .{});
}

const REUSE_SHADER =
    \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
    \\@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    \\    if (id.x < arrayLength(&data)) { data[id.x] = data[id.x] + id.x + 7u; }
    \\}
;
const REUSE_BUFFER_BYTES = 4 * @sizeOf(u32);
const DEVICE_LOCAL_FAILURE_BYTES = 64 * 1024;
const ALIGNED_STORAGE_BINDING_OFFSET: u64 = 256;

test "Vulkan inline index allocations survive submission and preserve rendered pixels" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    try expectIndexedRenderPixels(&rt);
}

fn expectIndexedRenderPixels(rt: *native_runtime.NativeVulkanRuntime) !void {
    const texture_types = @import("../../src/contracts/model/model_texture_value_types.zig");
    const render_types = @import("../../src/contracts/model/model_render_types.zig");
    const texture_commands = @import("../../src/backend/vulkan/vk_texture_commands.zig");
    const vertex_source =
        \\@vertex fn main(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
        \\    var p = vec2f(-1.0, -1.0);
        \\    if (i == 1u) { p = vec2f(3.0, -1.0); }
        \\    if (i == 2u) { p = vec2f(-1.0, 3.0); }
        \\    return vec4f(p, 0.0, 1.0);
        \\}
    ;
    const fragment_source = "@fragment fn main() -> @location(0) vec4f { return vec4f(1.0, 0.0, 0.0, 1.0); }";
    const target_handle = 980;
    const readback_handle = 981;
    const extent = 4;
    const row_bytes = 256;
    var vertex: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    var fragment: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const vertex_length = try compiler.translateToSpirv(std.testing.allocator, vertex_source, &vertex);
    const fragment_length = try compiler.translateToSpirv(std.testing.allocator, fragment_source, &fragment);
    const target = try resources.ensure_texture_resource(rt, .{
        .handle = target_handle,
        .width = extent,
        .height = extent,
        .format = texture_types.WGPUTextureFormat_RGBA8Unorm,
        .usage = texture_types.WGPUTextureUsage_RenderAttachment | texture_types.WGPUTextureUsage_CopySrc,
    });
    const readback = try resources.ensure_compute_buffer(rt, readback_handle, row_bytes * extent, true);
    for ([_]render_types.RenderIndexData{ .{ .uint16 = &.{ 0, 1, 2 } }, .{ .uint32 = &.{ 0, 1, 2 } } }) |indices| {
        _ = try rt.run_render_draw(.{
            .draw_count = 1,
            .target_handle = target_handle,
            .target_width = extent,
            .target_height = extent,
            .index_data = indices,
            .vertex_spirv = std.mem.bytesAsSlice(u32, vertex[0..vertex_length]),
            .fragment_spirv = std.mem.bytesAsSlice(u32, fragment[0..fragment_length]),
        });
        rt.recorded_submit_replay_active = true;
        _ = try texture_commands.record_texture_to_buffer(rt, target, readback, .{
            .offset = 0,
            .bytes_per_row = row_bytes,
            .rows_per_image = extent,
            .mip = 0,
            .width = extent,
            .height = extent,
            .depth_or_layers = 1,
        });
        _ = try rt.flush_queue();
        const pixels: [*]const u8 = @ptrCast(readback.mapped.?);
        for (0..extent) |y| for (0..extent) |x| {
            try std.testing.expectEqualSlices(u8, &.{ 255, 0, 0, 255 }, pixels[y * row_bytes + x * 4 ..][0..4]);
        };
    }
}

test "Vulkan SPIR-V cache invalidation preserves stores pointer writes branches and loops" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    const source =
        \\@group(0) @binding(0) var<storage, read_write> out: array<u32>;
        \\fn change(p: ptr<function, u32>) { *p += 5u; }
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    var x = id.x + 1u;
        \\    out[id.x * 5u] = x + x;
        \\    x += 3u;
        \\    out[id.x * 5u + 1u] = x;
        \\    change(&x);
        \\    out[id.x * 5u + 2u] = x;
        \\    if ((id.x % 2u) == 0u) { x += 10u; } else { x += 20u; }
        \\    out[id.x * 5u + 3u] = x;
        \\    for (var j = 0u; j < 3u; j++) { x += j; }
        \\    out[id.x * 5u + 4u] = x;
        \\}
    ;
    const lanes = 4;
    const values_per_lane = 5;
    const result_bytes = lanes * values_per_lane * @sizeOf(u32);
    const result_handle = 982;
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, source, &output);
    const binding = compute.KernelBinding{ .binding = 0, .resource_kind = .buffer, .resource_handle = result_handle, .buffer_size = result_bytes, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
    _ = try resources.ensure_compute_buffer_for_binding(&rt, binding, true);
    try rt.set_compute_shader_spirv(std.mem.bytesAsSlice(u32, output[0..length]), "main", &.{binding}, true);
    _ = try rt.run_dispatch(lanes, 1, 1, .deferred, .wait_any, .off);
    _ = try rt.flush_queue();
    const bytes = try resources.capture_compute_buffer(&rt, std.testing.allocator, rt.compute_buffers.get(result_handle).?, 0, result_bytes);
    defer std.testing.allocator.free(bytes);
    var expected: [lanes * values_per_lane]u32 = undefined;
    for (0..lanes) |lane| {
        const i: u32 = @intCast(lane);
        const branch_result = i + 9 + @as(u32, if (i % 2 == 0) 10 else 20);
        @memcpy(expected[lane * values_per_lane ..][0..values_per_lane], &[_]u32{ (i + 1) * 2, i + 4, i + 9, branch_result, branch_result + 3 });
    }
    try std.testing.expectEqualSlices(u8, std.mem.sliceAsBytes(&expected), bytes);
}

test "Vulkan deferred fence and timeline submissions preserve dependent results" {
    for ([_]@import("../../src/contracts/backend.zig").DeferredSubmissionSyncPolicy{ .require_fence_pool, .prefer_timeline_semaphore }) |policy| {
        var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
            error.UnsupportedFeature => return error.SkipZigTest,
            else => return err,
        };
        defer rt.deinit();
        rt.deferred_submission_sync_policy = policy;
        rt.recorded_submit_replay_active = false;
        var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
        const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
        const binding = compute.KernelBinding{ .binding = 0, .resource_kind = .buffer, .resource_handle = 221, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
        _ = try resources.ensure_compute_buffer_for_binding(&rt, binding, true);
        try rt.set_compute_shader_spirv(std.mem.bytesAsSlice(u32, output[0..length]), "main", &.{binding}, true);
        for (0..2) |_| {
            const metrics = try rt.run_dispatch(4, 1, 1, .deferred, .wait_any, .off);
            try std.testing.expectEqual(@as(u32, 1), metrics.submit_count);
        }
        try std.testing.expect(rt.has_deferred_submissions);
        switch (policy) {
            .require_fence_pool => {
                try std.testing.expect(rt.has_fence_pool);
                try std.testing.expect(!rt.has_timeline_semaphore);
                try std.testing.expectEqual(@as(u32, 2), rt.fence_pool_state.in_flight_count);
            },
            .prefer_timeline_semaphore => {
                if (!rt.has_timeline_semaphore) return error.SkipZigTest;
                try std.testing.expectEqual(@as(u64, 2), rt.timeline_semaphore.current_value);
            },
        }
        try expect_reuse_output(&rt, 221, &.{ 14, 16, 18, 20 });
        try std.testing.expect(!rt.has_deferred_submissions);
        _ = try rt.run_dispatch(4, 1, 1, .deferred, .wait_any, .off);
        try expect_reuse_output(&rt, 221, &.{ 21, 24, 27, 30 });
    }
}

test "Vulkan calibrated timestamps preserve single and dependent batch results" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    try @import("../../src/backend/vulkan/vk_device.zig").ensure_timestamp_query_pool(&rt);
    if (!rt.timestamp_query_supported_value) return error.SkipZigTest;
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const binding = compute.KernelBinding{ .binding = 0, .resource_kind = .buffer, .resource_handle = 222, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
    _ = try resources.ensure_compute_buffer_for_binding(&rt, binding, true);
    try rt.set_compute_shader_spirv(std.mem.bytesAsSlice(u32, output[0..length]), "main", &.{binding}, true);
    const single = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .require);
    try std.testing.expect(single.gpu_timestamp_attempted and single.gpu_timestamp_valid);
    try std.testing.expect(single.gpu_timestamp_ns > 0);
    try expect_reuse_output(&rt, 222, &.{ 7, 8, 9, 10 });
    const batch = try rt.run_dispatch_repeat(4, 1, 1, 3, .dependent, .wait_any, .require);
    try std.testing.expect(batch.gpu_timestamp_attempted and batch.gpu_timestamp_valid);
    try std.testing.expect(batch.gpu_timestamp_ns > 0);
    try expect_reuse_output(&rt, 222, &.{ 28, 32, 36, 40 });
}

test "Vulkan descriptor collisions preserve distinct recorded resources" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    const bindings = [_]compute.KernelBinding{
        .{ .binding = 0, .resource_kind = .buffer, .resource_handle = 601, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage },
        .{ .binding = 0, .resource_kind = .buffer, .resource_handle = 602, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage },
    };
    for (bindings) |binding| _ = try resources.ensure_compute_buffer_for_binding(&rt, binding, true);
    var program = compute_program.ComputeProgram{};
    defer program.deinit(&rt);
    try program.begin(&rt);
    for ([_]usize{ 0, 1, 0 }) |index| {
        try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 0, "main", bindings[index..][0..1], false);
        try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    }
    try program.finish(&rt);
    try program.submit(&rt);
    try expect_reuse_output(&rt, 601, &.{ 14, 16, 18, 20 });
    try expect_reuse_output(&rt, 602, &.{ 7, 8, 9, 10 });
    try program.submit(&rt);
    try expect_reuse_output(&rt, 601, &.{ 28, 32, 36, 40 });
    try expect_reuse_output(&rt, 602, &.{ 14, 16, 18, 20 });
}

test "Vulkan descriptor identity survives collision spill and allocation failure without changing recorded bindings" {
    const descriptor_cache = @import("../../src/backend/vulkan/vk_pipeline_cache.zig");
    const descriptors = @import("../../src/backend/vulkan/vk_descriptors.zig");
    const variant_count = descriptor_cache.HOT_DESCRIPTOR_STATE_CACHE_CAPACITY + 2;
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    var bindings: [variant_count]compute.KernelBinding = undefined;
    for (&bindings, 0..) |*binding, index| {
        binding.* = .{ .binding = 0, .resource_kind = .buffer, .resource_handle = 701 + index, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
        _ = try resources.ensure_compute_buffer_for_binding(&rt, binding.*, true);
    }
    var program = compute_program.ComputeProgram{};
    defer program.deinit(&rt);
    try program.begin(&rt);
    for (0..variant_count - 1) |index| {
        try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, std.math.maxInt(u64), "main", bindings[index..][0..1], false);
        try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    }
    const previous_pool = rt.descriptor_pool;
    // Each scratch allocation and the first overflow-map allocation must roll back.
    const prepare_allocation_count = 7;
    for (0..prepare_allocation_count) |failure| {
        var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = failure });
        rt.allocator = failing.allocator();
        const result = descriptors.prepare(&rt, bindings[variant_count - 1 ..], false, std.math.maxInt(u64));
        rt.allocator = std.testing.allocator;
        try std.testing.expectError(error.OutOfMemory, result);
        try std.testing.expectEqual(previous_pool, rt.descriptor_pool);
        try std.testing.expectEqual(failing.allocated_bytes, failing.freed_bytes);
    }
    try descriptors.prepare(&rt, bindings[variant_count - 1 ..], false, std.math.maxInt(u64));
    try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    try std.testing.expect(rt.current_descriptor_state_cache.count() > 0);
    var no_allocations = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    rt.allocator = no_allocations.allocator();
    const hit = descriptors.prepare(&rt, bindings[variant_count - 1 ..], false, std.math.maxInt(u64));
    rt.allocator = std.testing.allocator;
    try hit;
    for ([_]usize{ 0, variant_count - 2, variant_count - 1 }) |index| {
        try descriptors.prepare(&rt, bindings[index..][0..1], false, std.math.maxInt(u64));
        try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    }
    try program.finish(&rt);
    try program.submit(&rt);
    for (bindings, 0..) |binding, index| {
        if (index == 0 or index >= variant_count - 2) {
            try expect_reuse_output(&rt, binding.resource_handle, &.{ 14, 16, 18, 20 });
        } else {
            try expect_reuse_output(&rt, binding.resource_handle, &.{ 7, 8, 9, 10 });
        }
    }
}

test "Vulkan descriptor identity rejects replaced buffers and rebuilds ordinary bindings" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    const bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 801, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage }};
    var program = try prepare_reuse_program(&rt, words, &bindings, 4);
    defer program.deinit(&rt);
    try program.submit(&rt);
    try expect_reuse_output(&rt, 801, &.{ 7, 8, 9, 10 });
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    const previous_pool = rt.descriptor_pool;
    const previous_generation = rt.compute_buffers.get(801).?.generation;
    _ = try resources.ensure_compute_buffer(&rt, 801, REUSE_BUFFER_BYTES * 2, true);
    try std.testing.expect(rt.compute_buffers.get(801).?.generation != previous_generation);
    try std.testing.expectError(error.InvalidState, program.submit(&rt));
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    try std.testing.expect(previous_pool != rt.descriptor_pool);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, 801, &.{ 7, 8, 9, 10 });
    const removed = rt.compute_buffers.fetchRemove(801).?;
    resources.release_compute_buffer(&rt, removed.value);
    try std.testing.expectError(error.InvalidState, program.submit(&rt));
    _ = try resources.ensure_compute_buffer_for_binding(&rt, bindings[0], true);
    try std.testing.expect(rt.compute_buffers.get(801).?.generation != previous_generation);
    try std.testing.expectError(error.InvalidState, program.submit(&rt));
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, 801, &.{ 7, 8, 9, 10 });
}

test "Vulkan descriptor aliases retain final buffer extent and offset" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    var bindings = [_]compute.KernelBinding{
        .{ .binding = 0, .resource_kind = .buffer, .resource_handle = 851, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage },
        .{ .binding = 1, .resource_kind = .buffer, .resource_handle = 851, .buffer_size = REUSE_BUFFER_BYTES * 2, .buffer_type = binding_types.WGPUBufferBindingType_Storage },
    };
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, true);
    try std.testing.expectEqual(rt.current_descriptor_identity[0].handle, rt.current_descriptor_identity[1].handle);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, 851, &.{ 7, 8, 9, 10 });
    // Use a device-supported storage offset; the hash remains deliberately unchanged.
    const offset = ALIGNED_STORAGE_BINDING_OFFSET;
    _ = try resources.ensure_compute_buffer(&rt, 851, offset + REUSE_BUFFER_BYTES, true);
    bindings[0].buffer_offset = offset;
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, 851, &.{ 0, 0, 0, 0 });
    const bytes = try resources.capture_compute_buffer(&rt, std.testing.allocator, rt.compute_buffers.get(851).?, offset, REUSE_BUFFER_BYTES);
    defer std.testing.allocator.free(bytes);
    try std.testing.expectEqualSlices(u8, std.mem.sliceAsBytes(&[_]u32{ 7, 8, 9, 10 }), bytes);
}

test "Vulkan descriptor identity rejects replaced images samplers and orphaned native views" {
    const texture_types = @import("../../src/contracts/model/model_texture_value_types.zig");
    const resource_types = @import("../../src/contracts/model/model_resource_types.zig");
    const descriptor_identity = @import("../../src/backend/vulkan/vk_descriptor_identity.zig");
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    var texture_description = resource_types.CopyTextureResource{
        .handle = 901,
        .kind = .texture,
        .width = 4,
        .height = 4,
        .format = texture_types.WGPUTextureFormat_RGBA8Unorm,
        .usage = texture_types.WGPUTextureUsage_TextureBinding,
    };
    _ = try resources.ensure_texture_resource(&rt, texture_description);
    _ = try resources.create_sampler(&rt, .{ .handle = 902 });
    var bindings = [_]compute.KernelBinding{
        .{ .binding = 0, .resource_kind = .buffer, .resource_handle = 903, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage },
        .{ .binding = 1, .resource_kind = .texture, .resource_handle = 901, .texture_format = texture_types.WGPUTextureFormat_RGBA8Unorm },
        .{ .binding = 2, .resource_kind = .sampler, .resource_handle = 902 },
    };
    _ = try resources.ensure_compute_buffer_for_binding(&rt, bindings[0], true);
    var program = compute_program.ComputeProgram{};
    defer program.deinit(&rt);
    try program.begin(&rt);
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    try program.finish(&rt);
    try program.submit(&rt);
    try expect_reuse_output(&rt, 903, &.{ 7, 8, 9, 10 });
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    var previous_pool = rt.descriptor_pool;
    _ = try resources.create_sampler(&rt, .{ .handle = 902, .mag_filter = 2 });
    try std.testing.expectError(error.InvalidState, program.submit(&rt));
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    try std.testing.expect(previous_pool != rt.descriptor_pool);
    previous_pool = rt.descriptor_pool;
    texture_description.width = 8;
    _ = try resources.ensure_texture_resource(&rt, texture_description);
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    try std.testing.expect(previous_pool != rt.descriptor_pool);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, 903, &.{ 14, 16, 18, 20 });

    const parent = rt.textures.get(901).?;
    const view = try resources.create_texture_view(&rt, parent, parent.format, parent.view_dimension, 0, 1, 0, 1, parent.aspect, 0, 0, 0, 0);
    var borrowed = parent;
    borrowed.generation = try rt.next_resource_generation();
    borrowed.parent_handle = 901;
    borrowed.parent_generation = parent.generation;
    borrowed.view = view;
    borrowed.memory = 0;
    borrowed.owns_image = false;
    borrowed.owns_memory = false;
    try rt.textures.put(std.testing.allocator, 904, borrowed);
    bindings[1].resource_handle = 904;
    const retained_view = try descriptor_identity.snapshot(&rt, bindings[1]);
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false);
    texture_description.width = 16;
    _ = try resources.ensure_texture_resource(&rt, texture_description);
    try std.testing.expectError(error.InvalidState, descriptor_identity.validate(&rt, &.{retained_view}));
    try std.testing.expectError(error.InvalidState, rt.set_compute_shader_spirv_with_hashes(words, 1, 1, 1, "main", &bindings, false));
}

test "Vulkan pipeline hash collisions preserve every recorded shader and reject invalid entry points" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const first_words = std.mem.bytesAsSlice(u32, output[0..length]);
    const changed_source = try std.mem.replaceOwned(u8, std.testing.allocator, REUSE_SHADER, "7u", "11u");
    defer std.testing.allocator.free(changed_source);
    var changed_output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const changed_length = try compiler.translateToSpirv(std.testing.allocator, changed_source, &changed_output);
    const second_words = std.mem.bytesAsSlice(u32, changed_output[0..changed_length]);

    for ([_]u64{ 0, std.math.maxInt(u64) }, 0..) |hash, index| {
        const bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 401 + index, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage }};
        _ = try resources.ensure_compute_buffer_for_binding(&rt, bindings[0], true);
        var program = compute_program.ComputeProgram{};
        defer program.deinit(&rt);
        try program.begin(&rt);
        for ([_][]const u32{ first_words, second_words, first_words }) |words| {
            try rt.set_compute_shader_spirv_with_hashes(words, hash, hash, null, "main", &bindings, false);
            try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
        }
        try program.finish(&rt);
        try program.submit(&rt);
        try expect_reuse_output(&rt, bindings[0].resource_handle, &.{ 25, 28, 31, 34 });
        try program.submit(&rt);
        try expect_reuse_output(&rt, bindings[0].resource_handle, &.{ 50, 56, 62, 68 });

        // Finished recordings own private caches; prepare ordinary selection separately.
        for ([_][]const u32{ first_words, second_words, first_words }) |words| {
            try rt.set_compute_shader_spirv_with_hashes(words, hash, hash, null, "main", &bindings, false);
        }
        {
            var no_allocations = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
            rt.allocator = no_allocations.allocator();
            defer rt.allocator = std.testing.allocator;
            for ([_][]const u32{ first_words, second_words, first_words }) |words| {
                try rt.set_compute_shader_spirv_with_hashes(words, hash, hash, null, "main", &bindings, false);
                const owner = rt.pending_spirv_pipeline.?;
                try std.testing.expectEqual(rt.shared_pipeline.?, owner);
                try std.testing.expect(owner.words.ptr != words.ptr);
                try std.testing.expectEqualSlices(u32, words, owner.words);
            }
            try std.testing.expectEqual(@as(usize, 0), no_allocations.allocations);
            try std.testing.expectEqual(@as(usize, 0), no_allocations.allocated_bytes);
            try std.testing.expect(!no_allocations.has_induced_failure);
        }

        try rt.set_compute_shader_spirv_with_hashes(first_words, hash, hash, null, "main", &bindings, false);
        const original_pipeline = rt.pipeline;
        try std.testing.expectError(error.InvalidArgument, rt.set_compute_shader_spirv_with_hashes(first_words, hash, hash, null, "missing_entry", &bindings, false));
        try std.testing.expectEqual(original_pipeline, rt.pipeline);
        try std.testing.expectError(error.InvalidArgument, rt.set_compute_shader_spirv_with_hashes(first_words, hash, hash, null, "main", &.{}, false));
        try std.testing.expectEqual(original_pipeline, rt.pipeline);
    }
}

test "Vulkan pipeline layout collisions rebuild descriptor layouts" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    const bindings = [_]compute.KernelBinding{
        .{ .binding = 0, .resource_kind = .buffer, .resource_handle = 411, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage },
        .{ .group = 1, .binding = 0, .resource_kind = .buffer, .resource_handle = 412, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Uniform },
    };
    try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, null, "main", bindings[0..1], true);
    const pipeline = @import("../../src/backend/vulkan/vk_pipeline.zig");
    try pipeline.build_pipeline_for_words(&rt, words, 2, 1, "main", &bindings);
    try std.testing.expectEqual(@as(u32, 2), rt.descriptor_set_count);
    try rt.set_compute_shader_spirv_with_hashes(words, 2, 1, null, "main", &bindings, false);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, bindings[0].resource_handle, &.{ 7, 8, 9, 10 });
    try pipeline.build_pipeline_for_words(&rt, words, 1, 1, "main", bindings[0..1]);
    try std.testing.expectEqual(@as(u32, 1), rt.descriptor_set_count);
}

test "Vulkan pipeline identity follows effective subgroup policy on active and cached hits" {
    if (std.posix.getenv("DOE_VULKAN_REQUIRED_SUBGROUP_SIZE") != null) return error.SkipZigTest;
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    if (!rt.has_subgroup_size_control_ext or rt.required_compute_subgroup_size == 0) return error.SkipZigTest;
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    const bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 451, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage }};
    try rt.set_compute_shader_spirv(words, "main", &bindings, true);
    const required = rt.pipeline;
    try std.testing.expectEqual(rt.required_compute_subgroup_size, rt.shared_pipeline.?.required_subgroup_size.?);
    rt.vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation;
    try rt.set_compute_shader_spirv(words, "main", &bindings, false);
    try std.testing.expectEqual(@as(?u32, null), rt.shared_pipeline.?.required_subgroup_size);
    try std.testing.expect(rt.pipeline != required);
    rt.vulkan_subgroup_size_policy = .fixed_32_when_supported;
    try rt.set_compute_shader_spirv(words, "main", &bindings, false);
    try std.testing.expectEqual(required, rt.pipeline);
    _ = try rt.run_dispatch(4, 1, 1, .per_command, .wait_any, .off);
    try expect_reuse_output(&rt, bindings[0].resource_handle, &.{ 7, 8, 9, 10 });
}

test "Vulkan pipeline identity survives collision chains beyond the hot cache" {
    const variant_count = @import("../../src/backend/vulkan/vk_pipeline_cache.zig").HOT_COMPUTE_STATE_CACHE_CAPACITY + 2;
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    const bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 501, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage }};
    _ = try resources.ensure_compute_buffer_for_binding(&rt, bindings[0], true);
    var program = compute_program.ComputeProgram{};
    defer program.deinit(&rt);
    try program.begin(&rt);
    var handles: [variant_count]vk.VkPipeline = undefined;
    for (0..variant_count * 2) |iteration| {
        const index = if (iteration < variant_count) iteration else variant_count * 2 - iteration - 1;
        var literal: [32]u8 = undefined;
        const source = try std.mem.replaceOwned(u8, std.testing.allocator, REUSE_SHADER, "7u", try std.fmt.bufPrint(&literal, "{d}u", .{index + 1}));
        defer std.testing.allocator.free(source);
        var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
        const length = try compiler.translateToSpirv(std.testing.allocator, source, &output);
        const words = std.mem.bytesAsSlice(u32, output[0..length]);
        try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, null, "main", &bindings, false);
        if (iteration < variant_count) {
            handles[index] = rt.pipeline;
        } else try std.testing.expectEqual(handles[index], rt.pipeline);
        try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    }
    try program.finish(&rt);
    try program.submit(&rt);
    var expected: [4]u32 = undefined;
    for (&expected, 0..) |*value, index| value.* = @intCast(variant_count * (variant_count + 1) + variant_count * 2 * index);
    try expect_reuse_output(&rt, bindings[0].resource_handle, &expected);
}

test "Vulkan subgroup metadata follows changed shaders despite a shared hash" {
    if (std.posix.getenv("DOE_VULKAN_REQUIRED_SUBGROUP_SIZE") != null) return error.SkipZigTest;
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    if (!rt.has_subgroup_size_control_ext or rt.required_compute_subgroup_size == 0) return error.SkipZigTest;
    rt.vulkan_subgroup_size_policy = .suppress_for_workgroup_memory_256_or_single_invocation;
    const prefix = "@group(0) @binding(0) var<storage, read_write> output: array<u32>;\n";
    const sources = [_][]const u8{
        prefix ++ "@compute @workgroup_size(1) fn main() { output[0] += 7u; }",
        prefix ++ "@compute @workgroup_size(64) fn main(@builtin(local_invocation_id) id: vec3u) { if (id.x == 0u) { output[0] += 11u; } }",
        prefix ++ "var<workgroup> values: array<u32, 256>;\n@compute @workgroup_size(256) fn main(@builtin(local_invocation_id) id: vec3u) { values[id.x] = id.x; workgroupBarrier(); if (id.x == 0u) { output[0] += values[255]; } }",
    };
    const bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 551, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage }};
    var handles: [sources.len]vk.VkPipeline = undefined;
    var expected: u32 = 0;
    const increments = [_]u32{ 7, 11, 255 };
    for ([_]usize{ 0, 1, 2, 1, 0, 2 }, 0..) |index, iteration| {
        var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
        const length = try compiler.translateToSpirv(std.testing.allocator, sources[index], &output);
        const words = std.mem.bytesAsSlice(u32, output[0..length]);
        try rt.set_compute_shader_spirv_with_hashes(words, 1, 1, null, "main", &bindings, true);
        const entry = rt.shared_pipeline.?;
        try std.testing.expectEqual(if (index == 1) @as(?u32, rt.required_compute_subgroup_size) else null, entry.required_subgroup_size);
        try std.testing.expectEqual(@as(u32, if (index == 0) 1 else if (index == 1) 64 else 256), entry.compute_metadata.local_size.?.x);
        try std.testing.expectEqual(index == 2, entry.compute_metadata.has_workgroup_storage);
        if (iteration < sources.len) {
            handles[index] = rt.pipeline;
        } else try std.testing.expectEqual(handles[index], rt.pipeline);
        _ = try rt.run_dispatch(1, 1, 1, .per_command, .wait_any, .off);
        expected += increments[index];
        try expect_reuse_output(&rt, bindings[0].resource_handle, &.{ expected, 0, 0, 0 });
    }
}

test "Vulkan buffer publication failure cannot leave an unowned initialization command" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    const binding = compute.KernelBinding{
        .binding = 0,
        .resource_kind = .buffer,
        .resource_handle = 301,
        .buffer_size = DEVICE_LOCAL_FAILURE_BYTES,
        .buffer_type = binding_types.WGPUBufferBindingType_Storage,
    };
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    rt.allocator = failing.allocator();
    defer rt.allocator = std.testing.allocator;
    try std.testing.expectError(error.OutOfMemory, resources.ensure_compute_buffer_for_binding(&rt, binding, true));
    try std.testing.expectEqual(@as(usize, 0), rt.compute_buffers.count());
    try std.testing.expect(!rt.streaming_copy_active);

    rt.allocator = std.testing.allocator;
    const created = try resources.ensure_compute_buffer_for_binding(&rt, binding, true);
    try std.testing.expectEqual(resources.ComputeBufferMemoryKind.device_local, created.buffer.memory_kind);
    _ = try rt.flush_queue();
    const initialized = try resources.capture_compute_buffer(&rt, std.testing.allocator, created.buffer, 0, REUSE_BUFFER_BYTES);
    defer std.testing.allocator.free(initialized);
    try std.testing.expectEqualSlices(u8, &([_]u8{0} ** REUSE_BUFFER_BYTES), initialized);
    const replacement = try resources.ensure_compute_buffer(&rt, binding.resource_handle, DEVICE_LOCAL_FAILURE_BYTES * 2, true);
    try std.testing.expect(replacement.buffer != created.buffer.buffer);
    try std.testing.expectEqual(replacement.buffer, rt.compute_buffers.get(binding.resource_handle).?.buffer);
    _ = try rt.flush_queue();
    const resized = try resources.capture_compute_buffer(&rt, std.testing.allocator, replacement, 0, REUSE_BUFFER_BYTES);
    defer std.testing.allocator.free(resized);
    try std.testing.expectEqualSlices(u8, initialized, resized);
}

fn prepare_reuse_program(rt: *native_runtime.NativeVulkanRuntime, words: []const u32, bindings: []const compute.KernelBinding, workgroups: u32) !compute_program.ComputeProgram {
    for (bindings) |binding| _ = try resources.ensure_compute_buffer_for_binding(rt, binding, true);
    var program = compute_program.ComputeProgram{};
    errdefer program.deinit(rt);
    try program.begin(rt);
    try rt.set_compute_shader_spirv(words, "main", bindings, true);
    try rt.record_prepared_dispatch_replay_on(program.command_buffer, workgroups, 1, 1);
    try program.finish(rt);
    return program;
}

fn expect_reuse_output(rt: *native_runtime.NativeVulkanRuntime, id: u64, expected: []const u32) !void {
    _ = try rt.flush_queue();
    const bytes = try resources.capture_compute_buffer(rt, std.testing.allocator, rt.compute_buffers.get(id).?, 0, REUSE_BUFFER_BYTES);
    defer std.testing.allocator.free(bytes);
    try std.testing.expectEqualSlices(u8, std.mem.sliceAsBytes(expected), bytes);
}

fn acquire_with_allocation_failures(allocator: std.mem.Allocator, rt: *native_runtime.NativeVulkanRuntime, layouts: []const vk.VkDescriptorSetLayout, request: shared.Request) !void {
    var registry = shared.Registry{};
    defer registry.deinit(allocator);
    const entry = try registry.acquire(allocator, rt.device, 0, layouts, request, false);
    registry.release(allocator, rt.device, entry);
    try std.testing.expectEqual(@as(usize, 0), registry.entries.items.len);
}

test "Vulkan prepared programs share live pipelines and keep private descriptors after creator teardown" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    var bindings = [_]compute.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 101, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage }};
    var first = try prepare_reuse_program(&rt, words, &bindings, 2);
    defer first.deinit(&rt);
    bindings[0].resource_handle = 102;
    var second = try prepare_reuse_program(&rt, words, &bindings, 4);
    defer second.deinit(&rt);
    const first_pipeline = first.owned.active.shared_pipeline.?;
    const second_pipeline = second.owned.active.shared_pipeline.?;
    const share = @import("build_options").vulkan_share_live_compute_pipelines;
    try std.testing.expectEqual(share, first_pipeline == second_pipeline);
    try std.testing.expectEqual(share, first_pipeline.handle == second_pipeline.handle);
    try std.testing.expect(first.owned.active.descriptor_pool != second.owned.active.descriptor_pool);
    try std.testing.expect(first.owned.active.pipeline_layout != second.owned.active.pipeline_layout);
    try std.testing.expect(first.owned.active.pipeline_layout != second_pipeline.creation_layout);

    var request = shared.Request{ .words = words, .entry_point = "main", .bindings = &bindings, .required_subgroup_size = second_pipeline.required_subgroup_size };
    try std.testing.expect(try second_pipeline.matches(request));
    request.entry_point = "another_entry";
    try std.testing.expect(!try second_pipeline.matches(request));
    request.entry_point = "main";
    request.required_subgroup_size = if (request.required_subgroup_size == null) 32 else null;
    try std.testing.expect(!try second_pipeline.matches(request));
    request.required_subgroup_size = second_pipeline.required_subgroup_size;
    bindings[0].buffer_type = binding_types.WGPUBufferBindingType_Uniform;
    try std.testing.expect(!try second_pipeline.matches(request));
    bindings[0].buffer_type = binding_types.WGPUBufferBindingType_Storage;
    try std.testing.checkAllAllocationFailures(std.testing.allocator, acquire_with_allocation_failures, .{ &rt, second.owned.active.descriptor_set_layouts[0..second.owned.active.descriptor_set_count], request });

    try first.submit(&rt);
    try expect_reuse_output(&rt, 101, &.{ 7, 8, 0, 0 });
    first.deinit(&rt);
    try std.testing.expectEqual(@as(usize, 2), second_pipeline.references);
    try std.testing.expectEqual(@as(?*shared.Pipeline, second_pipeline), rt.pending_spirv_pipeline);
    try second.submit(&rt);
    try expect_reuse_output(&rt, 102, &.{ 7, 8, 9, 10 });

    var failed = compute_program.ComputeProgram{};
    try failed.begin(&rt);
    try std.testing.expectError(error.InvalidArgument, rt.set_compute_shader_spirv(words, "missing_entry", &bindings, false));
    failed.deinit(&rt);
    try std.testing.expectEqual(@as(usize, 2), second_pipeline.references);
    try second.submit(&rt);
    try expect_reuse_output(&rt, 102, &.{ 14, 16, 18, 20 });

    var extended_bindings = [_]compute.KernelBinding{
        bindings[0],
        .{ .binding = 1, .resource_kind = .buffer, .resource_handle = 103, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Uniform },
    };
    var extended = try prepare_reuse_program(&rt, words, &extended_bindings, 4);
    defer extended.deinit(&rt);
    try std.testing.expect(extended.owned.active.shared_pipeline.? != second_pipeline);
    extended.deinit(&rt);

    var changed_output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const changed_source = try std.mem.replaceOwned(u8, std.testing.allocator, REUSE_SHADER, "7u", "11u");
    defer std.testing.allocator.free(changed_source);
    const changed_length = try compiler.translateToSpirv(std.testing.allocator, changed_source, &changed_output);
    const changed_words = std.mem.bytesAsSlice(u32, changed_output[0..changed_length]);
    var changed = try prepare_reuse_program(&rt, changed_words, &bindings, 4);
    defer changed.deinit(&rt);
    try std.testing.expect(changed.owned.active.shared_pipeline.? != second_pipeline);
    try changed.submit(&rt);
    try expect_reuse_output(&rt, 102, &.{ 25, 28, 31, 34 });
    changed.deinit(&rt);
    try second.submit(&rt);
    try expect_reuse_output(&rt, 102, &.{ 32, 36, 40, 44 });

    var other_device = try native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null);
    defer other_device.deinit();
    var foreign = try prepare_reuse_program(&other_device, words, &bindings, 4);
    defer foreign.deinit(&other_device);
    try std.testing.expect(foreign.owned.active.shared_pipeline.? != second_pipeline);
    try foreign.submit(&other_device);
    try expect_reuse_output(&other_device, 102, &.{ 7, 8, 9, 10 });

    second.deinit(&rt);
    try std.testing.expectEqual(@as(usize, 1), rt.shared_pipelines.entries.items.len);
    try std.testing.expectEqual(@as(usize, 1), rt.pending_spirv_pipeline.?.references);
    try std.testing.expectEqualSlices(u32, changed_words, rt.pending_spirv_pipeline.?.words);
    @import("../../src/backend/vulkan/vk_pipeline.zig").discardPendingSpirv(&rt);
    try std.testing.expectEqual(@as(usize, 0), rt.shared_pipelines.entries.items.len);
}

test "vulkan mapped fast upload path stays bounded when shortcuts are allowed" {
    try std.testing.expect(native_runtime.upload_uses_fast_path(.allow_mapped_shortcuts, .copy_dst, 1024));
    try std.testing.expect(native_runtime.upload_uses_fast_path(.allow_mapped_shortcuts, .copy_dst, 1024 * 1024));
    try std.testing.expect(!native_runtime.upload_uses_fast_path(.allow_mapped_shortcuts, .copy_dst, 1024 * 1024 + 1));
    try std.testing.expect(!native_runtime.upload_uses_fast_path(.allow_mapped_shortcuts, .copy_dst_copy_src, 1024));
    try std.testing.expect(!native_runtime.upload_uses_fast_path(.allow_mapped_shortcuts, webgpu.UploadBufferUsageMode.copy_dst_copy_src, 1024 * 1024));
}

test "vulkan large copy-dst uploads use direct mapped path when shortcuts are allowed" {
    try std.testing.expect(native_runtime.upload_uses_direct_path(.allow_mapped_shortcuts, .copy_dst, 1024 * 1024 + 1));
    try std.testing.expect(native_runtime.upload_uses_direct_path(.allow_mapped_shortcuts, .copy_dst, 1024 * 1024 * 1024));
    try std.testing.expect(native_runtime.upload_uses_direct_path(.allow_mapped_shortcuts, .copy_dst, 4 * 1024 * 1024 * 1024));
    try std.testing.expect(!native_runtime.upload_uses_direct_path(.allow_mapped_shortcuts, .copy_dst, 1024 * 1024));
    try std.testing.expect(!native_runtime.upload_uses_direct_path(.allow_mapped_shortcuts, .copy_dst_copy_src, 4 * 1024 * 1024));
}

test "strict Vulkan upload policy allows fast_mapped for small, forces staged for large" {
    const strict_policy = backend_policy.UploadPathPolicy.staged_copy_only;
    // Small host-visible buffers use fast_mapped (direct memcpy) to match
    // Dawn's WriteBuffer behavior (CLAUDE.md rules 7/10/11).
    try std.testing.expect(native_runtime.upload_uses_fast_path(strict_policy, .copy_dst, 1024));
    // Large buffers still use staged copy under strict policy.
    try std.testing.expect(!native_runtime.upload_uses_direct_path(strict_policy, .copy_dst, 1024 * 1024 + 1));
    try std.testing.expect(!native_runtime.upload_uses_direct_path(strict_policy, .copy_dst, 4 * 1024 * 1024 * 1024));
    try std.testing.expect(!native_runtime.upload_uses_direct_path(strict_policy, .copy_dst_copy_src, 4 * 1024 * 1024));
}

test "Vulkan recorded compute writes become visible to uniform consumers" {
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    const source_binding = compute.KernelBinding{ .binding = 0, .resource_kind = .buffer, .resource_handle = 211, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
    const result_binding = compute.KernelBinding{ .binding = 1, .resource_kind = .buffer, .resource_handle = 212, .buffer_size = REUSE_BUFFER_BYTES, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
    _ = try resources.ensure_compute_buffer_for_binding(&rt, source_binding, true);
    _ = try resources.ensure_compute_buffer_for_binding(&rt, result_binding, true);
    var uniform_binding = source_binding;
    uniform_binding.buffer_type = binding_types.WGPUBufferBindingType_Uniform;
    const consumer =
        \\@group(0) @binding(0) var<uniform> input: vec4u;
        \\@group(0) @binding(1) var<storage, read_write> output: array<u32>;
        \\@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    output[id.x] = input[id.x];
        \\}
    ;
    var producer_spirv: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const producer_length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &producer_spirv);
    var consumer_spirv: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const consumer_length = try compiler.translateToSpirv(std.testing.allocator, consumer, &consumer_spirv);
    var program = compute_program.ComputeProgram{};
    defer program.deinit(&rt);
    try program.begin(&rt);
    try rt.set_compute_shader_spirv(std.mem.bytesAsSlice(u32, producer_spirv[0..producer_length]), "main", &.{source_binding}, false);
    try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    try rt.set_compute_shader_spirv(std.mem.bytesAsSlice(u32, consumer_spirv[0..consumer_length]), "main", &.{ uniform_binding, result_binding }, false);
    try rt.record_prepared_dispatch_replay_on(program.command_buffer, 4, 1, 1);
    try program.finish(&rt);
    try program.submit(&rt);
    try expect_reuse_output(&rt, 212, &.{ 7, 8, 9, 10 });
    try program.submit(&rt);
    try expect_reuse_output(&rt, 212, &.{ 14, 16, 18, 20 });
}

test "Vulkan staged upload reuses compatible native buffers without new allocation" {
    const upload = @import("../../src/backend/vulkan/vk_upload.zig");
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();
    const bytes = REUSE_BUFFER_BYTES;
    const narrow = vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    const broad = narrow | vk.VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
    try upload.prewarm_staged_upload_pool(&rt, bytes, narrow);
    const original = rt.hot_dst_pool_entry.?;
    try upload.prewarm_staged_upload_pool(&rt, bytes, broad);
    try std.testing.expectEqual(original.buffer, rt.hot_dst_pool_entry.?.buffer);
    const compatible = rt.dst_pool.get(bytes).?.items[0];
    try std.testing.expect(original.buffer != compatible.buffer);
    try std.testing.expectEqual(broad, compatible.usage);
    var no_allocations = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    rt.allocator = no_allocations.allocator();
    const reused = upload.prewarm_staged_upload_pool(&rt, bytes, broad);
    rt.allocator = std.testing.allocator;
    try reused;
    try std.testing.expect(!no_allocations.has_induced_failure);
    try std.testing.expectEqual(compatible.buffer, rt.dst_pool.get(bytes).?.items[0].buffer);

    const pending = try upload.record_upload_copy(&rt, bytes, broad);
    try std.testing.expectEqual(compatible.buffer, pending.dst_buffer);
    const expected = [_]u32{ 17, 29, 43, 71 };
    @memcpy(@as([*]u8, @ptrCast(pending.src_mapped.?))[0..bytes], std.mem.sliceAsBytes(&expected));
    rt.hot_pending_upload = pending;
    _ = try rt.flush_queue();
    const readback = try resources.create_host_visible_buffer(&rt, bytes, vk.VK_BUFFER_USAGE_TRANSFER_DST_BIT);
    defer resources.destroy_host_visible_buffer(&rt, readback);
    try upload.copy_buffer_region_and_wait(&rt, pending.dst_buffer, 0, readback.buffer, 0, bytes);
    try std.testing.expectEqualSlices(u8, std.mem.sliceAsBytes(&expected), @as([*]u8, @ptrCast(readback.mapped.?))[0..bytes]);
}

test "Vulkan completed buffer owner preserves mapping dispatch readback and replacement generations" {
    var rt = try native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null);
    defer rt.deinit();
    const bytes = 32 * 1024;
    const handle = 901;
    const original = try resources.ensure_compute_buffer(&rt, handle, bytes, true);
    const required = vk.VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT | vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT;
    if ((original.memory_property_flags & required) != required) return error.SkipZigTest;
    var output: [compiler.MAX_SPIRV_OUTPUT]u8 align(@alignOf(u32)) = undefined;
    const length = try compiler.translateToSpirv(std.testing.allocator, REUSE_SHADER, &output);
    const words = std.mem.bytesAsSlice(u32, output[0..length]);
    const binding = compute.KernelBinding{ .binding = 0, .resource_kind = .buffer, .resource_handle = handle, .buffer_size = bytes, .buffer_type = binding_types.WGPUBufferBindingType_Storage };
    const input = [_]u32{ 1, 2, 3, 4 };
    @memcpy(@as([*]u8, @ptrCast(original.mapped.?))[0..@sizeOf(@TypeOf(input))], std.mem.asBytes(&input));
    try rt.set_compute_shader_spirv(words, "main", &.{binding}, true);
    _ = try rt.run_dispatch(4, 1, 1, .deferred, .wait_any, .off);
    try expect_reuse_output(&rt, handle, &.{ 8, 10, 12, 14 });
    resources.destroy_compute_buffer(&rt, handle);
    try std.testing.expectEqual(original.allocation_size, rt.compute_buffer_cache.retained_bytes);
    const replacement = try resources.ensure_compute_buffer(&rt, handle, bytes, true);
    try std.testing.expectEqual(original.buffer, replacement.buffer);
    try std.testing.expectEqual(original.mapped, replacement.mapped);
    try std.testing.expect(replacement.generation > original.generation);
    try expect_reuse_output(&rt, handle, &.{ 0, 0, 0, 0 });
    try rt.set_compute_shader_spirv(words, "main", &.{binding}, true);
    _ = try rt.run_dispatch(4, 1, 1, .deferred, .wait_any, .off);
    try expect_reuse_output(&rt, handle, &.{ 7, 8, 9, 10 });
    resources.destroy_compute_buffer(&rt, handle);
    rt.deinit();
    try std.testing.expectEqual(@as(u64, 0), rt.compute_buffer_cache.retained_bytes);
    rt.deinit();
}

test "Vulkan bundle rejection preserves typed errors and allows subsequent rendering" {
    const render = @import("../../src/backend/vulkan/vk_render.zig");
    const bundle = @import("../../src/runtime/render/render_bundle.zig");
    const texture_types = @import("../../src/contracts/model/model_texture_value_types.zig");
    var rt = native_runtime.NativeVulkanRuntime.init(std.testing.allocator, null) catch |err| switch (err) {
        error.UnsupportedFeature => return error.SkipZigTest,
        else => return err,
    };
    defer rt.deinit();

    const vertex = try resources.create_host_visible_buffer(&rt, 16, vk.VK_BUFFER_USAGE_VERTEX_BUFFER_BIT);
    defer {
        if (vertex.mapped != null) vk.vkUnmapMemory(rt.device, vertex.memory);
        vk.vkDestroyBuffer(rt.device, vertex.buffer, null);
        vk.vkFreeMemory(rt.device, vertex.memory, null);
    }
    var commands = [_]bundle.BundleCmd{.{ .set_vertex_buffer = .{
        .slot = 0,
        .buffer_handle = @ptrFromInt(vertex.buffer),
        .offset = 0,
        .size = 16,
    } }};
    const valid = bundle.DoeRenderBundle{
        .allocator = std.testing.allocator,
        .backend = .vulkan,
        .color_format = texture_types.WGPUTextureFormat_RGBA8Unorm,
        .depth_stencil_format = texture_types.WGPUTextureFormat_Undefined,
        .sample_count = 1,
        .cmds = &commands,
    };
    for ([_]bundle.ReplayError{ error.InvalidBundle, error.FormatMismatch, error.SampleCountMismatch }) |expected| {
        var invalid = valid;
        switch (expected) {
            error.InvalidBundle => invalid.error_object = true,
            error.FormatMismatch => invalid.color_format = texture_types.WGPUTextureFormat_BGRA8Unorm,
            error.SampleCountMismatch => invalid.sample_count = 4,
        }
        for ([_][]const *const bundle.DoeRenderBundle{ &.{&invalid}, &.{ &valid, &invalid } }) |sequence| {
            try std.testing.expectError(expected, render.execute_render_bundles(&rt, sequence, 4, 4, valid.color_format, 1));
            _ = try render.execute_render_bundles(&rt, &.{&valid}, 4, 4, valid.color_format, 1);
            try expectIndexedRenderPixels(&rt);
        }
    }
}
