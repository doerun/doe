const std = @import("std");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const metal_queue = @import("../../src/backend/metal/metal_queue.zig");

test "metal device and queue report unsupported" {
    try std.testing.expectError(error.Unsupported, metal_device.create_device());
    try std.testing.expectError(error.Unsupported, metal_queue.submit());
}
