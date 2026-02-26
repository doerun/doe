const std = @import("std");
const compute_encode = @import("../../src/backend/metal/commands/compute_encode.zig");

test "metal compute encode succeeds" {
    try compute_encode.encode_compute();
}
