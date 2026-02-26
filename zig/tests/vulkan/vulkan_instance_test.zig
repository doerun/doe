const vulkan_adapter = @import("../../src/backend/vulkan/vulkan_adapter.zig");
const vulkan_device = @import("../../src/backend/vulkan/vulkan_device.zig");
const vulkan_instance = @import("../../src/backend/vulkan/vulkan_instance.zig");

test "vulkan instance bootstrap succeeds" {
    try vulkan_instance.create_instance();
    try vulkan_adapter.select_adapter();
    try vulkan_device.create_device();
}
