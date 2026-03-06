const std = @import("std");
const webgpu = @import("../../src/webgpu_ffi.zig");
const native_runtime = @import("../../src/backend/vulkan/native_runtime.zig");

test "vulkan fast upload path stays bounded to small copy-dst uploads" {
    try std.testing.expect(native_runtime.upload_uses_fast_path(.copy_dst, 1024));
    try std.testing.expect(native_runtime.upload_uses_fast_path(.copy_dst, 1024 * 1024));
    try std.testing.expect(!native_runtime.upload_uses_fast_path(.copy_dst, 1024 * 1024 + 1));
    try std.testing.expect(!native_runtime.upload_uses_fast_path(.copy_dst_copy_src, 1024));
    try std.testing.expect(!native_runtime.upload_uses_fast_path(webgpu.UploadBufferUsageMode.copy_dst_copy_src, 1024 * 1024));
}
