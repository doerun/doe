const std = @import("std");
const timing = @import("../../src/backend/metal/metal_timing.zig");

test "metal timing returns immediate timing sample" {
    const ns = try timing.operation_timing_ns();
    try std.testing.expectEqual(@as(u64, 0), ns);
}
