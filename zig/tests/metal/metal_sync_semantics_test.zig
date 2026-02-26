const std = @import("std");
const sync = @import("../../src/backend/metal/metal_sync.zig");

test "metal sync waits successfully" {
    try sync.wait_for_completion();
}
