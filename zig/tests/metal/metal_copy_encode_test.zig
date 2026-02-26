const std = @import("std");
const copy_encode = @import("../../src/backend/metal/commands/copy_encode.zig");

test "metal copy encode reports unsupported" {
    try std.testing.expectError(error.Unsupported, copy_encode.encode_copy());
}
