const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn create_bind_group() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.create_bind_group();
}

pub fn destroy_bind_group() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.destroy_bind_group();
}
