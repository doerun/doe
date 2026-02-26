const std = @import("std");
const compute_encode = @import("../../src/backend/metal/commands/compute_encode.zig");

test "metal compute encode reports unsupported" {
    try std.testing.expectError(error.Unsupported, compute_encode.encode_compute());
}
