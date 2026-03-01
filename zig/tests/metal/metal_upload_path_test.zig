const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const staging_ring = @import("../../src/backend/metal/upload/staging_ring.zig");
const upload_path = @import("../../src/backend/metal/upload/upload_path.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal upload path runs" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try staging_ring.reserve(1024);
    try upload_path.upload_once(.copy_dst_copy_src, 1024);
}
