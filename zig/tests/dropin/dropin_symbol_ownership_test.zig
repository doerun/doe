const std = @import("std");
const ownership = @import("../../src/dropin/dropin_symbol_ownership.zig");

test "symbol ownership parser accepts zig_metal" {
    try std.testing.expect(ownership.parse_symbol_owner("zig_metal") != null);
    try std.testing.expect(ownership.parse_symbol_owner("zig_vulkan") != null);
}
