const std = @import("std");
const d3d12_upload_path = @import("../../src/backend/d3d12/upload/upload_path.zig");
const d3d12_staging_ring = @import("../../src/backend/d3d12/upload/staging_ring.zig");
const d3d12_runtime_state = @import("../../src/backend/d3d12/d3d12_runtime_state.zig");

test "d3d12 upload path honors byte budget and upload usage mode" {
    d3d12_runtime_state.reset_state();
    try d3d12_upload_path.prewarm_upload_path(1024);
    try std.testing.expectEqual(@as(u64, 1024), d3d12_runtime_state.staging_reserved_bytes());
    try d3d12_staging_ring.reserve(2048);
    try std.testing.expectEqual(@as(u64, 3072), d3d12_runtime_state.staging_reserved_bytes());
    try d3d12_upload_path.upload_once(.copy_dst, 512);
    try std.testing.expectEqual(@as(u64, 3584), d3d12_runtime_state.staging_reserved_bytes());
    try std.testing.expectEqual(@as(u64, 1), d3d12_runtime_state.upload_copy_dst_calls());
    try std.testing.expectEqual(@as(u64, 0), d3d12_runtime_state.upload_copy_dst_copy_src_calls());
}

test "d3d12 upload path rejects zero-byte reserves" {
    d3d12_runtime_state.reset_state();
    try std.testing.expectError(error.InvalidArgument, d3d12_staging_ring.reserve(0));
    try std.testing.expectError(error.InvalidArgument, d3d12_upload_path.upload_once(.copy_dst_copy_src, 0));
}
