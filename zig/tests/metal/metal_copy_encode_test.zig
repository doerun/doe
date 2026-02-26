const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const copy_encode = @import("../../src/backend/metal/commands/copy_encode.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal copy encode succeeds" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try copy_encode.encode_copy();
}
