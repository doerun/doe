const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn pipeline_cache_lookup() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.pipeline_cache_lookup();
}
