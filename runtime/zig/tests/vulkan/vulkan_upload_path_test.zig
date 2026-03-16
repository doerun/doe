const std = @import("std");
const vulkan_upload_path = @import("../../src/backend/vulkan/upload/upload_path.zig");
const vulkan_staging_ring = @import("../../src/backend/vulkan/upload/staging_ring.zig");
const vulkan_runtime_state = @import("../../src/backend/vulkan/vulkan_runtime_state.zig");

test "vulkan upload path honors byte budget and upload usage mode" {
    vulkan_runtime_state.reset_state();
    try vulkan_upload_path.prewarm_upload_path(1024);
    try std.testing.expectEqual(@as(u64, 1024), vulkan_runtime_state.staging_reserved_bytes());
    try vulkan_staging_ring.reserve(2048);
    try std.testing.expectEqual(@as(u64, 3072), vulkan_runtime_state.staging_reserved_bytes());
    try vulkan_upload_path.upload_once(.copy_dst, 512);
    try std.testing.expectEqual(@as(u64, 3584), vulkan_runtime_state.staging_reserved_bytes());
    try std.testing.expectEqual(@as(u64, 1), vulkan_runtime_state.upload_copy_dst_calls());
    try std.testing.expectEqual(@as(u64, 0), vulkan_runtime_state.upload_copy_dst_copy_src_calls());
}

test "vulkan upload path rejects zero-byte reserves" {
    vulkan_runtime_state.reset_state();
    try std.testing.expectError(error.InvalidArgument, vulkan_staging_ring.reserve(0));
    try std.testing.expectError(error.InvalidArgument, vulkan_upload_path.upload_once(.copy_dst_copy_src, 0));
}
