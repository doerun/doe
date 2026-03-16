const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");

pub fn emit() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.emit_shader_artifact_manifest();
}
