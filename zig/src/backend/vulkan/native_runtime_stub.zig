const std = @import("std");
const webgpu = @import("../../webgpu_ffi.zig");

pub const DispatchMetrics = struct {
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    gpu_timestamp_ns: u64 = 0,
    gpu_timestamp_attempted: bool = false,
    gpu_timestamp_valid: bool = false,
};

pub const NativeVulkanRuntime = struct {
    allocator: std.mem.Allocator,
    kernel_root: ?[]const u8,

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeVulkanRuntime {
        _ = allocator;
        _ = kernel_root;
        return error.UnsupportedFeature;
    }

    pub fn deinit(self: *NativeVulkanRuntime) void {
        _ = self;
    }

    pub fn load_kernel_spirv(self: *const NativeVulkanRuntime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
        _ = self;
        _ = allocator;
        _ = kernel_name;
        return error.UnsupportedFeature;
    }

    pub fn set_compute_shader_spirv(self: *NativeVulkanRuntime, words: []const u32) !void {
        _ = self;
        _ = words;
        return error.UnsupportedFeature;
    }

    pub fn upload_bytes(self: *NativeVulkanRuntime, bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = self;
        _ = bytes;
        _ = mode;
        return error.UnsupportedFeature;
    }

    pub fn barrier(self: *NativeVulkanRuntime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        _ = self;
        _ = queue_wait_mode;
        return error.UnsupportedFeature;
    }

    pub fn run_dispatch(
        self: *NativeVulkanRuntime,
        x: u32,
        y: u32,
        z: u32,
        queue_sync_mode: webgpu.QueueSyncMode,
        queue_wait_mode: webgpu.QueueWaitMode,
        gpu_timestamp_mode: webgpu.GpuTimestampMode,
    ) !DispatchMetrics {
        _ = self;
        _ = x;
        _ = y;
        _ = z;
        _ = queue_sync_mode;
        _ = queue_wait_mode;
        _ = gpu_timestamp_mode;
        return error.UnsupportedFeature;
    }

    pub fn flush_queue(self: *NativeVulkanRuntime) !u64 {
        _ = self;
        return error.UnsupportedFeature;
    }

    pub fn prewarm_upload_path(self: *NativeVulkanRuntime, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = self;
        _ = max_upload_bytes;
        _ = mode;
        return error.UnsupportedFeature;
    }
};
