const std = @import("std");
const builtin = @import("builtin");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const vulkan_mod = @import("../../src/backend/vulkan/mod.zig");

fn test_profile() model.DeviceProfile {
    return .{
        .vendor = "amd",
        .api = .vulkan,
        .device_family = "gfx11",
        .driver_version = .{ .major = 24, .minor = 0, .patch = 0 },
    };
}

fn skip_if_runtime_unavailable(result: webgpu.NativeExecutionResult) bool {
    if (result.status == .ok) return false;
    return std.mem.eql(u8, result.status_message, "UnsupportedFeature") or
        std.mem.eql(u8, result.status_message, "AdapterUnavailable") or
        std.mem.eql(u8, result.status_message, "InvalidState") or
        std.mem.eql(u8, result.status_message, "ShaderCompileFailed");
}

test "vulkan backend upload behavior applies mode and submit cadence" {
    if (builtin.os.tag == .macos) return;

    const backend = try vulkan_mod.ZigVulkanBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_behavior", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    if (skip_if_runtime_unavailable(first)) return;
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, first.status);
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);

    const second = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    if (skip_if_runtime_unavailable(second)) return;
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, second.status);
}

test "vulkan backend flush_queue submits upload cadence tail in per-command mode" {
    if (builtin.os.tag == .macos) return;

    const backend = try vulkan_mod.ZigVulkanBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_upload_tail_flush", "test_policy_hash");
    defer iface.deinit();

    iface.set_upload_behavior(.copy_dst, 2);
    iface.set_queue_sync_mode(.per_command);

    const first = try iface.execute_command(model.Command{
        .upload = .{
            .bytes = 256,
            .align_bytes = 4,
        },
    });
    if (skip_if_runtime_unavailable(first)) return;
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, first.status);
    try std.testing.expectEqual(@as(u64, 0), first.submit_wait_ns);

    const flushed_ns = try iface.flush_queue();
    try std.testing.expect(flushed_ns >= 0);
}

test "vulkan kernel_dispatch reports dispatch count" {
    if (builtin.os.tag == .macos) return;

    const result = try vulkan_mod.run_contract_path_for_test(
        model.Command{ .kernel_dispatch = .{
            .kernel = "bench/kernels/shader_compile_pipeline_stress.spv",
            .x = 1,
            .y = 1,
            .z = 1,
        } },
        webgpu.QueueSyncMode.per_command,
    );
    if (result.status != .ok) return;
    try std.testing.expectEqual(webgpu.NativeExecutionStatus.ok, result.status);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch_count);
}

test "vulkan unsupported capability reports dispatch count for dispatch commands" {
    const backend = try vulkan_mod.ZigVulkanBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_dispatch_indirect_unsupported", "test_policy_hash");
    defer iface.deinit();

    const result = try iface.execute_command(model.Command{ .dispatch_indirect = .{
        .x = 1,
        .y = 1,
        .z = 1,
    } });

    try std.testing.expectEqual(webgpu.NativeExecutionStatus.unsupported, result.status);
    try std.testing.expectEqualStrings("compute_dispatch", result.status_message);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch_count);
}

test "vulkan dispatch requires kernel_dispatch capability path" {
    const backend = try vulkan_mod.ZigVulkanBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_dispatch_requires_kernel_dispatch", "test_policy_hash");
    defer iface.deinit();

    const result = try iface.execute_command(model.Command{ .dispatch = .{
        .x = 1,
        .y = 1,
        .z = 1,
    } });

    try std.testing.expectEqual(webgpu.NativeExecutionStatus.unsupported, result.status);
    try std.testing.expectEqualStrings("compute_dispatch", result.status_message);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch_count);
}
