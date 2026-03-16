const vulkan_copy_encode = @import("../../src/backend/vulkan/commands/copy_encode.zig");

test "vulkan copy encode succeeds" {
    try vulkan_copy_encode.encode_copy();
}
