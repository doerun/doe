const vulkan_render_encode = @import("../../src/backend/vulkan/commands/render_encode.zig");

test "vulkan render encode succeeds" {
    try vulkan_render_encode.encode_render();
}
