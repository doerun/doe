const std = @import("std");
const copy_encode = @import("../../src/backend/metal/commands/copy_encode.zig");

test "metal copy encode succeeds" {
    try copy_encode.encode_copy();
}
