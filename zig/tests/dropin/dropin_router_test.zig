const std = @import("std");
const router = @import("../../src/dropin/dropin_router.zig");
const ownership = @import("../../src/dropin/dropin_symbol_ownership.zig");

test "strict route does not mark fallback" {
    const decision = router.decide_symbol_route(.zig_metal, true);
    try std.testing.expect(decision.owner == ownership.SymbolOwner.zig_metal);
    try std.testing.expect(!decision.fallback_used);
}
