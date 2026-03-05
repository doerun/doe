const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");

pub const DispatchMetrics = struct {
    encode_ns: u64,
    submit_wait_ns: u64,
    dispatch_count: u32,
};

pub const RenderMetrics = struct {
    encode_ns: u64,
    submit_wait_ns: u64,
    draw_count: u32,
};

pub const NativeMetalRuntime = struct {
    allocator: std.mem.Allocator,

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeMetalRuntime {
        _ = allocator;
        _ = kernel_root;
        return error.UnsupportedFeature;
    }

    pub fn deinit(self: *NativeMetalRuntime) void { _ = self; }

    pub fn upload_bytes(self: *NativeMetalRuntime, bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = self; _ = bytes; _ = mode;
        return error.UnsupportedFeature;
    }

    pub fn flush_queue(self: *NativeMetalRuntime) !u64 { _ = self; return error.UnsupportedFeature; }

    pub fn barrier(self: *NativeMetalRuntime, mode: webgpu.QueueWaitMode) !u64 {
        _ = self; _ = mode;
        return error.UnsupportedFeature;
    }

    pub fn prewarm_upload_path(self: *NativeMetalRuntime, max: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = self; _ = max; _ = mode;
        return error.UnsupportedFeature;
    }

    pub fn run_kernel_dispatch(self: *NativeMetalRuntime, kernel: []const u8, x: u32, y: u32, z: u32, repeat: u32, warmup: u32, bindings: ?[]const model.KernelBinding) !DispatchMetrics {
        _ = self; _ = kernel; _ = x; _ = y; _ = z; _ = repeat; _ = warmup; _ = bindings;
        return error.UnsupportedFeature;
    }

    pub fn sampler_create(self: *NativeMetalRuntime, cmd: model.SamplerCreateCommand) !void {
        _ = self; _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn sampler_destroy(self: *NativeMetalRuntime, cmd: model.SamplerDestroyCommand) !void {
        _ = self; _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn texture_write(self: *NativeMetalRuntime, cmd: model.TextureWriteCommand) !void {
        _ = self; _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn texture_query(self: *NativeMetalRuntime, cmd: model.TextureQueryCommand) !void {
        _ = self; _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn texture_destroy(self: *NativeMetalRuntime, cmd: model.TextureDestroyCommand) !void {
        _ = self; _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn render_draw(self: *NativeMetalRuntime, cmd: model.RenderDrawCommand) !RenderMetrics {
        _ = self; _ = cmd;
        return error.UnsupportedFeature;
    }
};
