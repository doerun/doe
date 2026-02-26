const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");

test "metal instance create succeeds" {
    try metal_instance.create_instance();
}
