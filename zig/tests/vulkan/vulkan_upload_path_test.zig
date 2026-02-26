const vulkan_upload_path = @import("../../src/backend/vulkan/upload/upload_path.zig");
const vulkan_staging_ring = @import("../../src/backend/vulkan/upload/staging_ring.zig");

test "vulkan upload path and staging ring operations succeed" {
    try vulkan_upload_path.prewarm_upload_path(1024);
    try vulkan_staging_ring.reserve(2048);
    try vulkan_upload_path.upload_once();
}
