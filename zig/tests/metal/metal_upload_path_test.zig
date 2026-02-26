const std = @import("std");
const upload_path = @import("../../src/backend/metal/upload/upload_path.zig");

test "metal upload path reports unsupported" {
    try std.testing.expectError(error.Unsupported, upload_path.upload_once());
}
