const std = @import("std");
const webgpu = @import("../../webgpu_ffi.zig");

pub const DispatchMetrics = struct {
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    dispatch_count: u32 = 0,
};

pub const NativeD3D12Runtime = struct {
    allocator: std.mem.Allocator,

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeD3D12Runtime {
        _ = allocator;
        _ = kernel_root;
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

    pub fn load_kernel_cso(self: *const NativeD3D12Runtime, alloc: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        _ = self;
        _ = alloc;
        _ = kernel_name;
        return error.UnsupportedFeature;
    }

    pub fn set_compute_shader(self: *NativeD3D12Runtime, bytecode: []const u8) !void {
        _ = self;
        _ = bytecode;
        return error.UnsupportedFeature;
    }

    pub fn run_dispatch(self: *NativeD3D12Runtime, x: u32, y: u32, z: u32, repeat: u32) !DispatchMetrics {
        _ = self;
        _ = x;
        _ = y;
        _ = z;
        _ = repeat;
        return error.UnsupportedFeature;
    }
};
