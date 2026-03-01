const std = @import("std");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const metal_mod = @import("../../src/backend/metal/mod.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal mod routes supported dispatch command through contract path" {
    const command = model.Command{
        .dispatch = .{
            .x = 1,
            .y = 1,
            .z = 1,
        },
    };
    try metal_mod.run_contract_path_for_test(command, webgpu.QueueSyncMode.per_command);

    try std.testing.expect(metal_runtime_state.current_manifest_path() != null);
    try std.testing.expect(metal_runtime_state.current_manifest_hash() != null);
    if (metal_runtime_state.current_manifest_path()) |path| {
        try std.testing.expect(path.len > 0);
    }
    if (metal_runtime_state.current_manifest_hash()) |hash| {
        try std.testing.expect(hash.len == 64);
    }
}

test "metal mod routes render_draw command through manifest-bearing contract path" {
    const command = model.Command{
        .render_draw = .{
            .draw_count = 1,
            .vertex_count = 3,
            .instance_count = 1,
        },
    };
    try metal_mod.run_contract_path_for_test(command, webgpu.QueueSyncMode.per_command);
    try std.testing.expect(metal_runtime_state.current_manifest_path() != null);
    try std.testing.expect(metal_runtime_state.current_manifest_hash() != null);
    if (metal_runtime_state.current_manifest_path()) |path| {
        try std.testing.expect(path.len > 0);
    }
    if (metal_runtime_state.current_manifest_hash()) |hash| {
        try std.testing.expect(hash.len == 64);
    }
}

test "metal mod routes formerly unsupported command kinds" {
    const legacy_commands = [_]model.Command{
        .{ .barrier = .{ .dependency_count = 1 } },
        .{ .sampler_destroy = .{ .handle = 1 } },
        .{ .texture_write = .{
            .texture = .{ .handle = 1 },
            .data = "",
        } },
        .{ .texture_query = .{ .handle = 1 } },
        .{ .texture_destroy = .{ .handle = 1 } },
        .{ .surface_capabilities = .{ .handle = 1 } },
        .{ .surface_unconfigure = .{ .handle = 1 } },
        .{ .surface_acquire = .{ .handle = 1 } },
        .{ .surface_release = .{ .handle = 1 } },
    };
    for (legacy_commands) |command| {
        try metal_mod.run_contract_path_for_test(command, webgpu.QueueSyncMode.per_command);
    }
}

test "metal backend upload behavior applies mode and submit cadence" {
    const profile = model.DeviceProfile{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };
    const backend = try metal_mod.ZigMetalBackend.init(std.testing.allocator, profile, null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_behavior", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    metal_runtime_state.reset_state();

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);
    try std.testing.expectEqual(@as(u64, 1), metal_runtime_state.upload_copy_dst_calls());
    try std.testing.expectEqual(@as(u64, 0), metal_runtime_state.upload_copy_dst_copy_src_calls());

    const second = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expect(second.submit_wait_ns > 0);
    try std.testing.expectEqual(@as(u64, 2), metal_runtime_state.upload_copy_dst_calls());
}

test "metal backend flush_queue submits upload cadence tail in per-command mode" {
    const profile = model.DeviceProfile{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };
    const backend = try metal_mod.ZigMetalBackend.init(std.testing.allocator, profile, null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_tail_flush", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    iface.set_queue_sync_mode(.per_command);
    metal_runtime_state.reset_state();

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);

    const flush_ns = try iface.flush_queue();
    try std.testing.expect(flush_ns > 0);
    try std.testing.expectEqual(@as(u64, 1), metal_runtime_state.upload_copy_dst_calls());
}

test "metal kernel_dispatch emits one manifest per command" {
    try metal_mod.run_contract_path_for_test(
        model.Command{ .kernel_dispatch = .{
            .kernel = "vector_add",
            .x = 1,
            .y = 1,
            .z = 1,
        } },
        webgpu.QueueSyncMode.per_command,
    );

    try std.testing.expectEqual(@as(u64, 1), metal_runtime_state.manifest_emit_count());
    if (metal_runtime_state.current_manifest_path()) |path| {
        try std.testing.expect(std.mem.endsWith(u8, path, "metal_shader_artifact_1.json"));
    } else {
        return error.MissingManifestPath;
    }
}
