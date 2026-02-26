const std = @import("std");
const backend_policy = @import("../../src/backend/backend_policy.zig");

test "amd vulkan lane keeps dawn default" {
    const policy = backend_policy.default_policy_for_lane(.amd_vulkan_release);
    try std.testing.expect(policy.default_backend == .dawn_oracle);
    try std.testing.expect(policy.allow_fallback);
}

test "local vulkan comparable lane picks zig_vulkan by policy" {
    const policy = backend_policy.default_policy_for_lane(.local_vulkan_comparable);
    try std.testing.expect(policy.default_backend == .zig_vulkan);
    try std.testing.expect(!policy.allow_fallback);
    try std.testing.expect(policy.strict_no_fallback);
}
