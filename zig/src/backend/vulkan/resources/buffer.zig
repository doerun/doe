const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn create_buffer() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.create_buffer();
}

pub fn destroy_buffer() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.destroy_buffer();
}
