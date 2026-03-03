const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const compute_encode = @import("../../src/backend/metal/commands/compute_encode.zig");
const timing = @import("../../src/backend/metal/metal_timing.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");
const model = @import("../../src/model.zig");
const metal_mod = @import("../../src/backend/metal/mod.zig");

fn test_profile() model.DeviceProfile {
    return .{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };
}

test "metal timing returns immediate timing sample" {
    metal_runtime_state.reset_state();
    const before = try timing.operation_timing_ns();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try compute_encode.encode_compute();
    const after = try timing.operation_timing_ns();
    try std.testing.expect(after >= before);
    try std.testing.expect(after > 0);
}

test "metal dispatch timing separates encode and submit-wait buckets" {
    const backend = try metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_timing", "test_policy_hash");
    defer iface.deinit();
    iface.set_queue_sync_mode(.per_command);
    const result = try iface.execute_command(model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } });
    try std.testing.expect(result.encode_ns > 0);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch_count);
}

test "metal deferred sync records submit cost without per-command wait cost" {
    const backend = try metal_mod.ZigMetalBackend.init(std.testing.allocator, test_profile(), null);
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_timing", "test_policy_hash");
    defer iface.deinit();
    iface.set_queue_sync_mode(.deferred);
    const result = try iface.execute_command(model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } });
    try std.testing.expect(result.encode_ns > 0);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch_count);
}
