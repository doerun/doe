const dropin_symbol_ownership = @import("dropin_symbol_ownership.zig");
const dropin_behavior_policy = @import("dropin_behavior_policy.zig");

pub const RouteDecision = struct {
    owner: dropin_symbol_ownership.SymbolOwner,
    fallback_used: bool,
};

pub fn decide_symbol_route(
    owner: dropin_symbol_ownership.SymbolOwner,
    behavior_mode: dropin_behavior_policy.BehaviorMode,
    strict_no_fallback: bool,
) RouteDecision {
    switch (owner) {
        .dawn_delegate => return .{ .owner = .dawn_delegate, .fallback_used = false },
        .shared => return .{ .owner = .shared, .fallback_used = false },
        else => {}
    }

    // Strict policy never allows delegate fallback behavior.
    if (strict_no_fallback) {
        return .{ .owner = owner, .fallback_used = false };
    }

    return switch (behavior_mode) {
        .dawn_ownership, .mixed_ownership => .{ .owner = .dawn_delegate, .fallback_used = false },
        .doe_metal_ownership, .doe_vulkan_ownership, .doe_d3d12_ownership => .{ .owner = owner, .fallback_used = false },
    };
}
