const std = @import("std");
const upload_path = @import("../../src/backend/metal/upload/upload_path.zig");

test "metal upload path runs" {
    try upload_path.upload_once();
}
