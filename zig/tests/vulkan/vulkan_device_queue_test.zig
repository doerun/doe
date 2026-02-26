const vulkan_device = @import("../../src/backend/vulkan/vulkan_device.zig");
const vulkan_queue = @import("../../src/backend/vulkan/vulkan_queue.zig");

test "vulkan device and queue operations succeed" {
    try vulkan_device.create_device();
    try vulkan_queue.submit();
    try vulkan_queue.wait_for_completion();
}
