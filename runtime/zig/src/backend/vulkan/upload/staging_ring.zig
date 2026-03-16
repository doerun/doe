const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn reserve(bytes: u64) vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.reserve_staging(bytes);
}
