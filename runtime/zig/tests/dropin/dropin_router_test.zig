const std = @import("std");
const router = @import("../../src/dropin/dropin_router.zig");
const ownership = @import("../../src/dropin/dropin_symbol_ownership.zig");
const policy = @import("../../src/dropin/dropin_behavior_policy.zig");

test "strict route does not mark fallback" {
    const decision = router.decide_symbol_route(.doe_metal, policy.BehaviorMode.dawn_ownership, true);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.doe_metal);
    try std.testing.expect(!decision.fallback_used);
}

test "mixed mode routes to dawn without fallback marker" {
    const decision = router.decide_symbol_route(.doe_vulkan, policy.BehaviorMode.mixed_ownership, false);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.dawn_delegate);
    try std.testing.expect(!decision.fallback_used);
}

test "strict-mode ignores fallback preference" {
    const decision = router.decide_symbol_route(.doe_vulkan, policy.BehaviorMode.doe_vulkan_ownership, true);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.doe_vulkan);
    try std.testing.expect(!decision.fallback_used);
}

test "strict d3d12 route does not mark fallback" {
    const decision = router.decide_symbol_route(.doe_d3d12, policy.BehaviorMode.doe_d3d12_ownership, true);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.doe_d3d12);
    try std.testing.expect(!decision.fallback_used);
}

test "non-strict doe ownership does not set fallback marker" {
    const decision = router.decide_symbol_route(.doe_vulkan, policy.BehaviorMode.doe_vulkan_ownership, false);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.doe_vulkan);
    try std.testing.expect(!decision.fallback_used);
}
