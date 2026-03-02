const d3d12_device = @import("../../src/backend/d3d12/d3d12_device.zig");
const d3d12_queue = @import("../../src/backend/d3d12/d3d12_queue.zig");

test "d3d12 device and queue operations succeed" {
    try d3d12_device.create_device();
    try d3d12_queue.submit();
    try d3d12_queue.wait_for_completion();
}
