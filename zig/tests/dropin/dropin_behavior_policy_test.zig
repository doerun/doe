const std = @import("std");
const policy = @import("../../src/dropin/dropin_behavior_policy.zig");

test "behavior mode parser accepts strict mode" {
    try std.testing.expect(policy.parse_behavior_mode("doe_metal_ownership") != null);
}

test "behavior mode parser accepts strict vulkan mode" {
    try std.testing.expect(policy.parse_behavior_mode("doe_vulkan_ownership") != null);
}

test "behavior mode parser accepts strict d3d12 mode" {
    try std.testing.expect(policy.parse_behavior_mode("doe_d3d12_ownership") != null);
}

test "behavior mode parser rejects unknown mode" {
    try std.testing.expect(policy.parse_behavior_mode("no_such_mode") == null);
}
