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
