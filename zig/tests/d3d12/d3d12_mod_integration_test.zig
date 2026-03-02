const std = @import("std");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const d3d12_mod = @import("../../src/backend/d3d12/mod.zig");
const d3d12_runtime_state = @import("../../src/backend/d3d12/d3d12_runtime_state.zig");

fn test_profile() model.DeviceProfile {
    return .{
        .vendor = "amd",
        .api = .d3d12,
        .device_family = "gfx11",
        .driver_version = .{ .major = 24, .minor = 0, .patch = 0 },
    };
}

test "d3d12 backend upload behavior applies mode and submit cadence" {
    const backend = try d3d12_mod.ZigD3D12Backend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_behavior", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    d3d12_runtime_state.reset_state();

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);
    try std.testing.expectEqual(@as(u64, 1), d3d12_runtime_state.upload_copy_dst_calls());
    try std.testing.expectEqual(@as(u64, 0), d3d12_runtime_state.upload_copy_dst_copy_src_calls());

    const second = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expect(second.submit_wait_ns > 0);
    try std.testing.expectEqual(@as(u64, 2), d3d12_runtime_state.upload_copy_dst_calls());
}

test "d3d12 backend flush_queue submits upload cadence tail in per-command mode" {
    const backend = try d3d12_mod.ZigD3D12Backend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_tail_flush", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    iface.set_queue_sync_mode(.per_command);
    d3d12_runtime_state.reset_state();

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);

    const flush_ns = try iface.flush_queue();
    try std.testing.expect(flush_ns > 0);
    try std.testing.expectEqual(@as(u64, 1), d3d12_runtime_state.upload_copy_dst_calls());
}

test "d3d12 kernel_dispatch emits one manifest per command" {
    const result = try d3d12_mod.run_contract_path_for_test(
        model.Command{ .kernel_dispatch = .{
            .kernel = "vector_add",
            .x = 1,
            .y = 1,
            .z = 1,
        } },
        webgpu.QueueSyncMode.per_command,
    );
    try std.testing.expect(result.status == .ok);
    try std.testing.expectEqual(@as(u64, 1), d3d12_runtime_state.manifest_emit_count());
    if (d3d12_runtime_state.current_manifest_path()) |path| {
        try std.testing.expect(std.mem.endsWith(u8, path, "d3d12-manifest-1.json"));
    } else {
        return error.MissingManifestPath;
    }
}
