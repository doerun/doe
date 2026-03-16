const std = @import("std");
const common_timing = @import("../../src/backend/common/timing.zig");

test "now_ns returns nonzero on supported platforms" {
    const ts = common_timing.now_ns();
    try std.testing.expect(ts > 0);
}

test "operation_timing_ns returns nonzero" {
    const ts = try common_timing.operation_timing_ns();
    try std.testing.expect(ts > 0);
}

test "ns_delta computes positive difference" {
    try std.testing.expectEqual(@as(u64, 500), common_timing.ns_delta(1500, 1000));
}

test "ns_delta returns zero when after <= before" {
    try std.testing.expectEqual(@as(u64, 0), common_timing.ns_delta(1000, 1500));
    try std.testing.expectEqual(@as(u64, 0), common_timing.ns_delta(1000, 1000));
}

test "per-backend timing aliases resolve to common" {
    const vulkan_timing = @import("../../src/backend/vulkan/vulkan_timing.zig");
    const metal_timing = @import("../../src/backend/metal/metal_timing.zig");
    const d3d12_timing = @import("../../src/backend/d3d12/d3d12_timing.zig");

    const vk_ts = try vulkan_timing.operation_timing_ns();
    const mtl_ts = try metal_timing.operation_timing_ns();
    const dx_ts = try d3d12_timing.operation_timing_ns();

    try std.testing.expect(vk_ts > 0);
    try std.testing.expect(mtl_ts > 0);
    try std.testing.expect(dx_ts > 0);
    try std.testing.expect(dx_ts >= vk_ts);
}
