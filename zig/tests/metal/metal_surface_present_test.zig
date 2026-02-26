const std = @import("std");
const present = @import("../../src/backend/metal/surface/present.zig");

test "metal present succeeds" {
    try present.present_surface();
}
