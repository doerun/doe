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
    try std.testing.expectEqual(@as(u64, 1024), metal_runtime_state.staging_reserved_bytes());
    try staging_ring.reserve(2048);
    try std.testing.expectEqual(@as(u64, 3072), metal_runtime_state.staging_reserved_bytes());
    try upload_path.upload_once(.copy_dst, 512);
    try std.testing.expectEqual(@as(u64, 1), metal_runtime_state.upload_copy_dst_calls());
    try std.testing.expectEqual(@as(u64, 0), metal_runtime_state.upload_copy_dst_copy_src_calls());
}
