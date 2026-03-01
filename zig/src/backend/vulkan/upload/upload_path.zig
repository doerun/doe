const vulkan_errors = @import("../vulkan_errors.zig");
const vulkan_runtime_state = @import("../vulkan_runtime_state.zig");
const staging_ring = @import("staging_ring.zig");

pub const UploadUsageMode = vulkan_runtime_state.UploadUsageMode;

pub fn prewarm_upload_path(max_upload_bytes: u64) vulkan_errors.VulkanError!void {
    if (max_upload_bytes == 0) return;
    try staging_ring.reserve(max_upload_bytes);
}

pub fn upload_once(mode: UploadUsageMode, bytes: u64) vulkan_errors.VulkanError!void {
    if (bytes == 0) return vulkan_errors.VulkanError.InvalidArgument;
    try staging_ring.reserve(bytes);
    return try vulkan_runtime_state.upload_once(mode, bytes);
}
