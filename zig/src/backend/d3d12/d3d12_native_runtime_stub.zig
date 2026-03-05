const std = @import("std");
const webgpu = @import("../../webgpu_ffi.zig");

pub const NativeD3D12Runtime = struct {
    allocator: std.mem.Allocator,

    pub fn init(allocator: std.mem.Allocator) !NativeD3D12Runtime {
        _ = allocator;
        return error.UnsupportedFeature;
    }

    pub fn deinit(self: *NativeD3D12Runtime) void {
        _ = self;
    }

    pub fn upload_bytes(self: *NativeD3D12Runtime, bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = self;
        _ = bytes;
        _ = mode;
        return error.UnsupportedFeature;
    }

    pub fn flush_queue(self: *NativeD3D12Runtime) !u64 {
        _ = self;
        return error.UnsupportedFeature;
    }

    pub fn barrier(self: *NativeD3D12Runtime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        _ = self;
        _ = queue_wait_mode;
        return error.UnsupportedFeature;
    }

    pub fn prewarm_upload_path(self: *NativeD3D12Runtime, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = self;
        _ = max_upload_bytes;
        _ = mode;
        return error.UnsupportedFeature;
    }
};
