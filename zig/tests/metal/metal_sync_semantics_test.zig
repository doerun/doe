const std = @import("std");
const sync = @import("../../src/backend/metal/metal_sync.zig");

test "metal sync reports unsupported until explicit implementation" {
    try std.testing.expectError(error.Unsupported, sync.wait_for_completion());
}
