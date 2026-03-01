const std = @import("std");
const model = @import("../../src/model.zig");
const webgpu = @import("../../src/webgpu_ffi.zig");
const vulkan_mod = @import("../../src/backend/vulkan/mod.zig");
const vulkan_timing = @import("../../src/backend/vulkan/vulkan_timing.zig");

test "vulkan timing source query succeeds" {
    const timing_ns = try vulkan_timing.operation_timing_ns();
    try std.testing.expect(timing_ns > 0);
}

test "vulkan dispatch timing separates encode and submit-wait buckets" {
    const result = try vulkan_mod.run_contract_path_for_test(
        model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } },
        webgpu.QueueSyncMode.per_command,
    );
    try std.testing.expectEqual(@as(u64, 13_700), result.encode_ns);
    try std.testing.expectEqual(@as(u64, 16_000), result.submit_wait_ns);
}

test "vulkan deferred sync records submit cost but not per-command wait cost" {
    const result = try vulkan_mod.run_contract_path_for_test(
        model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } },
        webgpu.QueueSyncMode.deferred,
    );
    try std.testing.expectEqual(@as(u64, 13_700), result.encode_ns);
    try std.testing.expectEqual(@as(u64, 7_000), result.submit_wait_ns);
}
