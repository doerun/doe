const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn configure_surface() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.configure_surface();
}

pub fn unconfigure_surface() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.unconfigure_surface();
}

pub fn get_surface_capabilities() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.get_surface_capabilities();
}
