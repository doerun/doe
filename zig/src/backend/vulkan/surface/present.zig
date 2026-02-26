const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn acquire_surface() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.acquire_surface();
}

pub fn present_surface() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.present_surface();
}

pub fn release_surface() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.release_surface();
}
