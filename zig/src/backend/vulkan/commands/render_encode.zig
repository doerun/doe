const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn encode_render() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.encode_render();
}
