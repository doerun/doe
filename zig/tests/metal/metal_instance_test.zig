const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");

test "metal instance reports explicit unsupported" {
    try std.testing.expectError(error.Unsupported, metal_instance.create_instance());
}
