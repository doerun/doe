const std = @import("std");
const backend_policy = @import("../../src/backend/backend_policy.zig");

test "backend runtime policy loads local metal lane from config" {
    const loaded = try backend_policy.load_policy_for_lane(
        std.testing.allocator,
        "config/backend-runtime-policy.json",
        .local_metal_comparable,
    );
    defer std.testing.allocator.free(loaded.owned_policy_hash);

    try std.testing.expect(loaded.policy.default_backend == .zig_metal);
    try std.testing.expect(!loaded.policy.allow_fallback);
    try std.testing.expect(loaded.policy.strict_no_fallback);
    try std.testing.expectEqualStrings("backend-runtime-policy-v1", loaded.policy.policy_hash);
}

test "backend lane parser handles metal_app and local metal lanes" {
    try std.testing.expect(
        backend_policy.parse_lane("metal_app") == .macos_app,
    );
    try std.testing.expect(
        backend_policy.parse_lane("metal_local_directional") == .local_metal_directional,
    );
    try std.testing.expect(
        backend_policy.parse_lane("metal_oracle") == .metal_oracle,
    );
}
