const std = @import("std");
const backend_policy = @import("../../src/backend/backend_policy.zig");

test "amd vulkan lane keeps dawn default" {
    const policy = backend_policy.default_policy_for_lane(.vulkan_dawn_release);
    try std.testing.expect(policy.default_backend == .dawn_delegate);
    try std.testing.expect(!policy.allow_fallback);
    try std.testing.expect(policy.strict_no_fallback);
}

test "local vulkan comparable lane picks doe_vulkan by policy" {
    const policy = backend_policy.default_policy_for_lane(.vulkan_doe_comparable);
    try std.testing.expect(policy.default_backend == .doe_vulkan);
    try std.testing.expect(!policy.allow_fallback);
    try std.testing.expect(policy.strict_no_fallback);
}

test "local d3d12 comparable lane picks doe_d3d12 by policy" {
    const policy = backend_policy.default_policy_for_lane(.d3d12_doe_comparable);
    try std.testing.expect(policy.default_backend == .doe_d3d12);
    try std.testing.expect(!policy.allow_fallback);
    try std.testing.expect(policy.strict_no_fallback);
}
