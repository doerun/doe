const vulkan_queue = @import("../../src/backend/vulkan/vulkan_queue.zig");
const vulkan_sync = @import("../../src/backend/vulkan/vulkan_sync.zig");

test "vulkan sync operations succeed" {
    try vulkan_queue.submit();
    try vulkan_sync.wait_for_completion();
}
