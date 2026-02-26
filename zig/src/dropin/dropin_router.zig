const dropin_symbol_ownership = @import("dropin_symbol_ownership.zig");

pub const RouteDecision = struct {
    owner: dropin_symbol_ownership.SymbolOwner,
    fallback_used: bool,
};

pub fn decide_symbol_route(owner: dropin_symbol_ownership.SymbolOwner, strict_no_fallback: bool) RouteDecision {
    if (strict_no_fallback) {
        return .{ .owner = owner, .fallback_used = false };
    }
    return .{ .owner = owner, .fallback_used = false };
}
