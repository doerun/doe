const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal instance create succeeds" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
}
