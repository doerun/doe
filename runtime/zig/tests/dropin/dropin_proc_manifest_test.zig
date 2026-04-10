const std = @import("std");
const manifest = @import("../../src/dropin/dropin_proc_manifest.zig");
const ownership = @import("../../src/dropin/dropin_symbol_ownership.zig");

test "manifest ownership covers exported shared queue submit symbol" {
    try std.testing.expectEqual(ownership.SymbolOwner.shared, manifest.manifestOwnerForSymbol("wgpuQueueSubmit").?);
}

test "symbol ownership config agrees with manifest-covered symbols" {
    const owned = try ownership.parse_symbol_ownership_config(std.testing.allocator, @embedFile("../../../config/dropin-symbol-ownership.json"));
    defer {
        for (owned) |entry| {
            std.testing.allocator.free(entry.symbol);
        }
        std.testing.allocator.free(owned);
    }

    for (owned) |entry| {
        if (manifest.manifestOwnerForSymbol(entry.symbol)) |owner| {
            try std.testing.expectEqual(owner, entry.owner);
        }
    }
}
