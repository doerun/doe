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

    // strict modes force ownership decisions to be honored without fallback.
    if (strict_no_fallback) {
        return .{ .owner = owner, .fallback_used = false };
    }

    // Mixed mode allows falling back to Dawn delegate when a Zig-owned symbol
    // cannot be resolved.
    if (behavior_mode == .mixed_ownership) {
        return .{ .owner = .dawn_delegate, .fallback_used = true };
    }

    // Strict ownership mode with fallback allowed by behavior policy.
    if (behavior_mode == .dawn_ownership) {
        return .{ .owner = .dawn_delegate, .fallback_used = false };
    }

    return .{ .owner = owner, .fallback_used = true };
}
