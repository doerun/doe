const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn create_texture() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.create_texture();
}

pub fn write_texture() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.write_texture();
}

pub fn query_texture() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.query_texture();
}

pub fn destroy_texture() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.destroy_texture();
}
