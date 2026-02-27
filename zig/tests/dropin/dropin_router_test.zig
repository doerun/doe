const std = @import("std");
const router = @import("../../src/dropin/dropin_router.zig");
const ownership = @import("../../src/dropin/dropin_symbol_ownership.zig");
const policy = @import("../../src/dropin/dropin_behavior_policy.zig");

test "strict route does not mark fallback" {
    const decision = router.decide_symbol_route(.zig_metal, policy.BehaviorMode.dawn_ownership, true);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.zig_metal);
    try std.testing.expect(!decision.fallback_used);
}

test "mixed mode can fallback" {
    const decision = router.decide_symbol_route(.zig_vulkan, policy.BehaviorMode.mixed_ownership, false);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.dawn_oracle);
    try std.testing.expect(decision.fallback_used);
}

test "strict-mode ignores fallback preference" {
    const decision = router.decide_symbol_route(.zig_vulkan, policy.BehaviorMode.zig_vulkan_ownership, true);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.zig_vulkan);
    try std.testing.expect(!decision.fallback_used);
}
