const std = @import("std");
const timing = @import("../../src/backend/metal/metal_timing.zig");

test "metal timing reports unsupported until explicit implementation" {
    try std.testing.expectError(error.Unsupported, timing.operation_timing_ns());
}
