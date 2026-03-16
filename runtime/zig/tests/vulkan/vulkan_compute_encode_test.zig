const vulkan_compute_encode = @import("../../src/backend/vulkan/commands/compute_encode.zig");

test "vulkan compute encode succeeds" {
    try vulkan_compute_encode.encode_compute();
}
