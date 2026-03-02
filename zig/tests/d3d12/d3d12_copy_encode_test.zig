const d3d12_copy_encode = @import("../../src/backend/d3d12/commands/copy_encode.zig");

test "d3d12 copy encode succeeds" {
    try d3d12_copy_encode.encode_copy();
}
