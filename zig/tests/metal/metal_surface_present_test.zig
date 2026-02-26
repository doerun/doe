const std = @import("std");
const present = @import("../../src/backend/metal/surface/present.zig");

test "metal present reports unsupported until explicit implementation" {
    try std.testing.expectError(error.Unsupported, present.present_surface());
}
