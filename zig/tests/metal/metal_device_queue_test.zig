const std = @import("std");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const metal_queue = @import("../../src/backend/metal/metal_queue.zig");

test "metal device and queue operations succeed" {
    try metal_device.create_device();
    try metal_queue.submit();
}
