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

pub const SymbolOwnership = struct {
    symbol: []const u8,
    owner: SymbolOwner,
    required_in_strict: bool,
};

const SymbolOwnershipConfig = struct {
    schemaVersion: u32,
    symbols: []const struct {
        symbol: []const u8,
        owner: []const u8,
        requiredInStrict: bool,
    },
};

pub const ParseError = error{
    InvalidSchemaVersion,
    InvalidSymbolOwner,
};

pub fn parse_symbol_ownership_config(
    allocator: std.mem.Allocator,
    raw_json: []const u8,
) ![]const SymbolOwnership {
    const parsed = try std.json.parseFromSlice(SymbolOwnershipConfig, allocator, raw_json, .{
        .ignore_unknown_fields = false,
    });
    defer parsed.deinit();

    if (parsed.value.schemaVersion != 1) return ParseError.InvalidSchemaVersion;

    var entries = try allocator.alloc(SymbolOwnership, parsed.value.symbols.len);
    for (entries) |*entry| {
        entry.* = .{
            .symbol = "",
            .owner = .shared,
            .required_in_strict = false,
        };
    }
    var should_cleanup = true;
    errdefer if (should_cleanup) {
        for (entries) |entry| {
            if (entry.symbol.len != 0) allocator.free(entry.symbol);
        }
        allocator.free(entries);
    }
    for (parsed.value.symbols, 0..) |entry, index| {
        const owner = parse_symbol_owner(entry.owner) orelse return ParseError.InvalidSymbolOwner;
        const symbol = try allocator.dupe(u8, entry.symbol);
        entries[index] = .{
            .symbol = symbol,
            .owner = owner,
            .required_in_strict = entry.requiredInStrict,
        };
    }
    should_cleanup = false;
    return entries;
}

pub fn find_symbol_ownership(
    ownerships: []const SymbolOwnership,
    symbol: []const u8,
) ?SymbolOwnership {
    for (ownerships) |entry| {
        if (std.mem.eql(u8, entry.symbol, symbol)) {
            return entry;
        }
    }
    return null;
}

pub fn symbol_owner_name(owner: SymbolOwner) []const u8 {
    return switch (owner) {
        .dawn_oracle => "dawn_oracle",
        .zig_metal => "zig_metal",
        .zig_vulkan => "zig_vulkan",
        .shared => "shared",
    };
}
