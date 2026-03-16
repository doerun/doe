const std = @import("std");
const webgpu = @import("../../webgpu_ffi.zig");
const model = @import("../../model.zig");
const d3d12_copy = @import("commands/d3d12_copy.zig");
const d3d12_dispatch = @import("commands/d3d12_dispatch.zig");
const d3d12_render = @import("commands/d3d12_render.zig");
const d3d12_async = @import("commands/d3d12_async_diagnostics.zig");
const d3d12_texture = @import("resources/d3d12_texture.zig");
const d3d12_sampler = @import("resources/d3d12_sampler.zig");
const d3d12_surface = @import("surface/d3d12_surface.zig");
const d3d12_timestamps = @import("commands/d3d12_gpu_timestamps.zig");

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

    pub fn texture_write(self: *NativeD3D12Runtime, cmd: model.TextureWriteCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn texture_query(self: *const NativeD3D12Runtime, cmd: model.TextureQueryCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn texture_destroy(self: *NativeD3D12Runtime, cmd: model.TextureDestroyCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn sampler_create(self: *NativeD3D12Runtime, cmd: model.SamplerCreateCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn sampler_destroy(self: *NativeD3D12Runtime, cmd: model.SamplerDestroyCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn execute_compute_dispatch(self: *NativeD3D12Runtime, cmd: model.DispatchCommand) !d3d12_dispatch.DispatchMetrics {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn execute_dispatch_indirect(self: *NativeD3D12Runtime, cmd: model.DispatchIndirectCommand) !d3d12_dispatch.DispatchMetrics {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn execute_copy(self: *NativeD3D12Runtime, cmd: model.CopyCommand) !d3d12_copy.CopyMetrics {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn execute_render_draw(self: *NativeD3D12Runtime, cmd: model.RenderDrawCommand, is_indirect: bool, is_indexed_indirect: bool) !d3d12_render.RenderMetrics {
        _ = self;
        _ = cmd;
        _ = is_indirect;
        _ = is_indexed_indirect;
        return error.UnsupportedFeature;
    }

    pub fn surface_create(self: *NativeD3D12Runtime, cmd: model.SurfaceCreateCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn surface_capabilities(self: *NativeD3D12Runtime, cmd: model.SurfaceCapabilitiesCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn surface_configure(self: *NativeD3D12Runtime, cmd: model.SurfaceConfigureCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn surface_acquire(self: *NativeD3D12Runtime, cmd: model.SurfaceAcquireCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn surface_present(self: *NativeD3D12Runtime, cmd: model.SurfacePresentCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn surface_unconfigure(self: *NativeD3D12Runtime, cmd: model.SurfaceUnconfigureCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn surface_release(self: *NativeD3D12Runtime, cmd: model.SurfaceReleaseCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn execute_async_diagnostics(self: *NativeD3D12Runtime, cmd: model.AsyncDiagnosticsCommand) !d3d12_async.AsyncDiagnosticsMetrics {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn execute_map_async(self: *NativeD3D12Runtime, cmd: model.MapAsyncCommand) !u64 {
        _ = self;
        _ = cmd;
        return error.UnsupportedFeature;
    }

    pub fn init_timestamps(self: *NativeD3D12Runtime) !void {
        _ = self;
        return error.UnsupportedFeature;
    }
};
