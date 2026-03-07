const std = @import("std");
const backend_policy = @import("../backend_policy.zig");
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

    pub fn upload_bytes(
        self: *NativeVulkanRuntime,
        bytes: u64,
        mode: webgpu.UploadBufferUsageMode,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !void {
        _ = self;
        _ = bytes;
        _ = mode;
        _ = upload_path_policy;
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

    pub fn adapter_ordinal(self: *NativeVulkanRuntime) ?u32 {
        _ = self;
        return null;
    }

    pub fn queue_family_index_value(self: *NativeVulkanRuntime) ?u32 {
        _ = self;
        return null;
    }

    pub fn present_capable(self: *NativeVulkanRuntime) ?bool {
        _ = self;
        return null;
    }

    pub fn lifecycle_probe(self: *NativeVulkanRuntime, iterations: u32) !u64 {
        _ = self;
        _ = iterations;
        return error.UnsupportedFeature;
    }

    pub fn pipeline_async_probe(self: *NativeVulkanRuntime, allocator: std.mem.Allocator, path: []const u8, iterations: u32) !u64 {
        _ = self;
        _ = allocator;
        _ = path;
        _ = iterations;
        return error.UnsupportedFeature;
    }

    pub fn resource_table_immediates_emulation_probe(
        self: *NativeVulkanRuntime,
        iterations: u32,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !u64 {
        _ = self;
        _ = iterations;
        _ = upload_path_policy;
        return error.UnsupportedFeature;
    }

    pub fn pixel_local_storage_emulation_probe(
        self: *NativeVulkanRuntime,
        iterations: u32,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !u64 {
        _ = self;
        _ = iterations;
        _ = upload_path_policy;
        return error.UnsupportedFeature;
    }

    pub fn create_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self;
        _ = handle;
        return error.UnsupportedFeature;
    }

    pub fn get_surface_capabilities(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self;
        _ = handle;
        return error.UnsupportedFeature;
    }

    pub fn configure_surface(self: *NativeVulkanRuntime, cmd: anytype) !void {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn acquire_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self;
        _ = handle;
        return error.UnsupportedFeature;
    }

    pub fn present_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self;
        _ = handle;
        return error.UnsupportedFeature;
    }

    pub fn unconfigure_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self;
        _ = handle;
        return error.UnsupportedFeature;
    }

    pub fn release_surface(self: *NativeVulkanRuntime, handle: u64) !void {
        _ = self;
        _ = handle;
        return error.UnsupportedFeature;
    }

    pub fn flush_queue(self: *NativeVulkanRuntime) !u64 {
        _ = self;
        return error.UnsupportedFeature;
    }

    pub fn prewarm_upload_path(
        self: *NativeVulkanRuntime,
        max_upload_bytes: u64,
        mode: webgpu.UploadBufferUsageMode,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !void {
        _ = self;
        _ = max_upload_bytes;
        _ = mode;
        _ = upload_path_policy;
        return error.UnsupportedFeature;
    }
};
