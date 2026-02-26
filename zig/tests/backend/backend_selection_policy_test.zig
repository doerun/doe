const std = @import("std");
const model = @import("../../src/model.zig");
const backend_policy = @import("../../src/backend/backend_policy.zig");
const backend_selection = @import("../../src/backend/backend_selection.zig");

test "metal lane selects zig_metal" {
    const profile = model.DeviceProfile{
        .vendor = .intel,
        .api = .metal,
        .device_family = null,
        .driver = "0.0.0",
    };
    const policy = backend_policy.default_policy_for_lane(.local_metal_comparable);
    const selected = backend_selection.select_backend(profile, policy);
    try std.testing.expectEqualStrings("policy_lane_prefers_zig_metal", selected.reason);
}

test "vulkan lane selects zig_vulkan" {
    const profile = model.DeviceProfile{
        .vendor = .intel,
        .api = .vulkan,
        .device_family = null,
        .driver_version = "0.0.0",
    };
    const policy = backend_policy.default_policy_for_lane(.local_vulkan_comparable);
    const selected = backend_selection.select_backend(profile, policy);
    try std.testing.expect(selected.backend_id == .zig_vulkan);
    try std.testing.expectEqualStrings("policy_lane_prefers_zig_vulkan", selected.reason);
}
