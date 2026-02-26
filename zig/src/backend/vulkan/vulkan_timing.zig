const vulkan_errors = @import("vulkan_errors.zig");
const vulkan_runtime_state = @import("vulkan_runtime_state.zig");

pub fn operation_timing_ns() vulkan_errors.VulkanError!u64 {
    return try vulkan_runtime_state.operation_timing_ns();
}
