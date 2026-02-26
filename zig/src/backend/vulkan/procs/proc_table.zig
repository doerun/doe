const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn build_proc_table() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.build_proc_table();
}
