const std = @import("std");
const model = @import("../../src/model.zig");
const execution = @import("../../src/execution.zig");
const backend_ids = @import("../../src/backend/backend_ids.zig");
const backend_policy = @import("../../src/backend/backend_policy.zig");

test "execution backend lane parser accepts vulkan_app" {
    try std.testing.expect(execution.parseBackendLane("vulkan_app") == .amd_vulkan_app);
    try std.testing.expect(execution.parseBackendLane("amd-vulkan-app") == .amd_vulkan_app);
}

test "execution backend lane parser accepts metal_oracle" {
    try std.testing.expect(execution.parseBackendLane("metal_oracle") == .metal_oracle);
    try std.testing.expect(execution.parseBackendLane("metal-oracle") == .metal_oracle);
}

test "default backend lane routes vulkan and metal profiles to app lanes" {
    const vulkan_profile = model.DeviceProfile{
        .vendor = "amd",
        .api = .vulkan,
        .device_family = "gfx11",
        .driver_version = .{ .major = 24, .minor = 0, .patch = 0 },
    };
    const metal_profile = model.DeviceProfile{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };

    try std.testing.expect(execution.defaultBackendLane(vulkan_profile) == .amd_vulkan_app);
    try std.testing.expect(execution.defaultBackendLane(metal_profile) == .macos_app);
}

test "backend runtime policy exposes vulkan_app as strict zig_vulkan lane" {
    const allocator = std.testing.allocator;
    const loaded = try backend_policy.load_policy_for_lane(
        allocator,
        backend_policy.DEFAULT_RUNTIME_POLICY_PATH,
        .amd_vulkan_app,
    );
    defer allocator.free(loaded.owned_policy_hash);

    try std.testing.expect(loaded.policy.default_backend == backend_ids.BackendId.zig_vulkan);
    try std.testing.expect(loaded.policy.allow_fallback == false);
    try std.testing.expect(loaded.policy.strict_no_fallback == true);
}
