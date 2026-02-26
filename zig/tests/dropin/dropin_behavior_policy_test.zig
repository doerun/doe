const std = @import("std");
const policy = @import("../../src/dropin/dropin_behavior_policy.zig");

test "behavior mode parser accepts strict mode" {
    try std.testing.expect(policy.parse_behavior_mode("zig_metal_ownership") != null);
}
