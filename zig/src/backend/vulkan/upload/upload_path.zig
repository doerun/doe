const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");
const staging_ring = @import("staging_ring.zig");

pub fn prewarm_upload_path(max_upload_bytes: u64) vulkan_errors.VulkanError!void {
    _ = max_upload_bytes;
    try staging_ring.reserve(max_upload_bytes);
}

pub fn upload_once() vulkan_errors.VulkanError!void {
    return try vulkan_runtime_state.upload_once();
}
