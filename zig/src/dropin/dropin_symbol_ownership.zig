const std = @import("std");

pub const SymbolOwner = enum {
    dawn_oracle,
    zig_metal,
    zig_vulkan,
    shared,
};

pub fn parse_symbol_owner(raw: []const u8) ?SymbolOwner {
    if (std.ascii.eqlIgnoreCase(raw, "dawn_oracle")) return .dawn_oracle;
    if (std.ascii.eqlIgnoreCase(raw, "zig_metal")) return .zig_metal;
    if (std.ascii.eqlIgnoreCase(raw, "zig_vulkan")) return .zig_vulkan;
    if (std.ascii.eqlIgnoreCase(raw, "shared")) return .shared;
    return null;
}
