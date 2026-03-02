const d3d12_render_encode = @import("../../src/backend/d3d12/commands/render_encode.zig");

test "d3d12 render encode succeeds" {
    try d3d12_render_encode.encode_render();
}
