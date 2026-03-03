const std = @import("std");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const vulkan_mod = @import("../../src/backend/vulkan/mod.zig");
const vulkan_runtime_state = @import("../../src/backend/vulkan/vulkan_runtime_state.zig");

fn test_profile() model.DeviceProfile {
    return .{
        .vendor = "amd",
        .api = .vulkan,
        .device_family = "gfx11",
        .driver_version = .{ .major = 24, .minor = 0, .patch = 0 },
    };
}

test "vulkan backend upload behavior applies mode and submit cadence" {
    const backend = try vulkan_mod.ZigVulkanBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_behavior", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    vulkan_runtime_state.reset_state();

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);
    try std.testing.expectEqual(@as(u64, 1), vulkan_runtime_state.upload_copy_dst_calls());
    try std.testing.expectEqual(@as(u64, 0), vulkan_runtime_state.upload_copy_dst_copy_src_calls());

    const second = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, second.status);
    try std.testing.expectEqual(@as(u64, 2), vulkan_runtime_state.upload_copy_dst_calls());
}

test "vulkan backend flush_queue submits upload cadence tail in per-command mode" {
    const backend = try vulkan_mod.ZigVulkanBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_tail_flush", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    iface.set_queue_sync_mode(.per_command);
    vulkan_runtime_state.reset_state();

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);

    _ = try iface.flush_queue();
    try std.testing.expectEqual(@as(u64, 1), vulkan_runtime_state.upload_copy_dst_calls());
}

test "vulkan kernel_dispatch emits one manifest per command" {
    const result = try vulkan_mod.run_contract_path_for_test(
        model.Command{ .kernel_dispatch = .{
            .kernel = "vector_add",
            .x = 1,
            .y = 1,
            .z = 1,
        } },
        webgpu.QueueSyncMode.per_command,
    );
    try std.testing.expect(result.status == .ok);
    try std.testing.expectEqual(@as(u64, 1), vulkan_runtime_state.manifest_emit_count());
    if (vulkan_runtime_state.current_manifest_path()) |path| {
        try std.testing.expect(std.mem.endsWith(u8, path, "vulkan-manifest-1.json"));
    } else {
        return error.MissingManifestPath;
    }
}
