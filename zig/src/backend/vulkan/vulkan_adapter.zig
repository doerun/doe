const vulkan_errors = @import("vulkan_errors.zig");
const vulkan_runtime_state = @import("vulkan_runtime_state.zig");

pub fn select_adapter() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.select_adapter();
}
