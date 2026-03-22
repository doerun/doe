const builtin = @import("builtin");
const std = @import("std");
const common_timing = @import("../common/timing.zig");
const common_errors = @import("../common/errors.zig");
const path_utils = @import("../common/path_utils.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const model = @import("../../model.zig");
const doe_wgsl = @import("../../doe_wgsl/mod.zig");
const hlsl_dispatch_contract = @import("../../doe_wgsl/hlsl_dispatch_contract.zig");

const d3d12_texture = @import("resources/d3d12_texture.zig");
const d3d12_sampler = @import("resources/d3d12_sampler.zig");
const d3d12_depth_stencil = @import("resources/d3d12_depth_stencil.zig");
const d3d12_texture_view = @import("resources/d3d12_texture_view.zig");
const d3d12_streaming_copy = @import("commands/d3d12_streaming_copy.zig");
const d3d12_dispatch = @import("commands/d3d12_dispatch.zig");
const d3d12_render = @import("commands/d3d12_render.zig");
const d3d12_surface = @import("surface/d3d12_surface.zig");
const d3d12_async = @import("commands/d3d12_async_diagnostics.zig");
const d3d12_timestamps = @import("commands/d3d12_gpu_timestamps.zig");
const d3d12_map = @import("commands/d3d12_map_async.zig");
const d3d12_query_set = @import("d3d12_query_set.zig");
const d3d12_descriptors = @import("d3d12_descriptors.zig");
const d3d12_device_caps = @import("d3d12_device_caps.zig");
const dc = @import("d3d12_constants.zig");
const render_bundle = @import("../../render_bundle.zig");

pub const MAX_UPLOAD_BYTES: u64 = 64 * 1024 * 1024;
pub const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;
pub const DEFAULT_KERNEL_ROOT: []const u8 = "bench/kernels";
pub const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;
pub const GENERATED_SHADER_DIR: []const u8 = "bench/out/shader-artifacts/generated";
pub const MAX_DXC_OUTPUT_BYTES: usize = 64 * 1024;
pub const DXC_PROFILE: []const u8 = "cs_6_0";
pub const DXC_ENTRYPOINT: []const u8 = "main";
pub const HEAP_TYPE_DEFAULT: c_int = 1;

extern fn d3d12_bridge_create_device() callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_device_create_command_queue(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_fence(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_copy_buffer(cmd_list: ?*anyopaque, dst: ?*anyopaque, src: ?*anyopaque, size: usize) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_device_create_compute_pipeline(device: ?*anyopaque, root_sig: ?*anyopaque, bytecode: [*]const u8, bytecode_size: usize) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_set_compute_root_signature(cmd_list: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_pipeline_state(cmd_list: ?*anyopaque, pipeline: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_dispatch(cmd_list: ?*anyopaque, x: u32, y: u32, z: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_descriptor_heaps(cmd_list: ?*anyopaque, cbv_srv_uav_heap: ?*anyopaque, sampler_heap: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_compute_root_descriptor_table(cmd_list: ?*anyopaque, root_parameter_index: u32, heap: ?*anyopaque, base_descriptor_index: u32) callconv(.c) void;
extern fn d3d12_bridge_resource_map(resource: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_unmap(resource: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_device_create_root_signature_with_tables(device: ?*anyopaque, ranges: [*]const d3d12_descriptors.DescriptorRangeDesc, range_count: u32, flags: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_allocator_reset(allocator_h: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_command_list_reset(cmd_list: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) c_int;

const D3D12_DESCRIPTOR_RANGE_TYPE_CBV: u32 = 2;

const DispatchInfoWords = extern struct {
    x: u32,
    y: u32,
    z: u32,
    _pad: u32,
};

pub const PendingUpload = struct {
    cmd_allocator: ?*anyopaque,
    cmd_list: ?*anyopaque,
    src_buffer: ?*anyopaque,
    dst_buffer: ?*anyopaque,
    byte_count: usize,
};

pub const PoolEntry = struct {
    buffer: ?*anyopaque,
};

pub const DispatchMetrics = struct {
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    dispatch_count: u32 = 0,
};

pub const NativeD3D12Runtime = struct {
    allocator: std.mem.Allocator,
    kernel_root: ?[]const u8 = null,
    device: ?*anyopaque = null,
    queue: ?*anyopaque = null,
    fence: ?*anyopaque = null,
    fence_value: u64 = 0,

    has_device: bool = false,
    pending_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},
    has_deferred_submissions: bool = false,

    upload_pool: std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(PoolEntry)) = .{},
    default_pool: std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(PoolEntry)) = .{},

    root_signature: ?*anyopaque = null,
    compute_pipeline: ?*anyopaque = null,
    compute_allocator: ?*anyopaque = null,
    compute_cmd_list: ?*anyopaque = null,
    dispatch_info_buffer: ?*anyopaque = null,
    dispatch_info_cbv_index: u32 = 0,
    has_dispatch_info_cbv: bool = false,
    current_shader_hash: u64 = 0,
    has_root_signature: bool = false,
    has_compute_pipeline: bool = false,
    has_compute_cmd: bool = false,

    device_caps: d3d12_device_caps.D3D12DeviceCaps = .{},

    texture_map: d3d12_texture.TextureMap = .{},
    sampler_state: d3d12_sampler.SamplerState = .{},
    depth_stencil_state: d3d12_depth_stencil.DepthStencilState = .{},
    texture_view_state: d3d12_texture_view.TextureViewState = .{},
    streaming_copy_state: d3d12_streaming_copy.StreamingCopyState = .{},
    dispatch_state: d3d12_dispatch.DispatchState = .{},
    render_state: d3d12_render.RenderState = .{},
    surface_state: d3d12_surface.SurfaceState = .{},
    timestamp_state: d3d12_timestamps.TimestampState = .{},
    query_set_state: d3d12_query_set.QuerySetState = .{},
    descriptor_state: d3d12_descriptors.DescriptorHeapState = .{},

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeD3D12Runtime {
        var self = NativeD3D12Runtime{ .allocator = allocator, .kernel_root = kernel_root };
        errdefer self.deinit();
        try self.bootstrap();
        return self;
    }

    pub fn deinit(self: *NativeD3D12Runtime) void {
        _ = self.flush_queue() catch {};
        self.release_pending_uploads();
        self.pending_uploads.deinit(self.allocator);
        d3d12_release_pool(&self.upload_pool, self.allocator);
        d3d12_release_pool(&self.default_pool, self.allocator);
        self.streaming_copy_state.deinit();
        self.destroy_compute_objects();
        self.timestamp_state.deinit();
        self.query_set_state.deinit(self.allocator);
        self.render_state.deinit();
        self.dispatch_state.deinit();
        self.surface_state.deinit(self.allocator);
        self.sampler_state.deinit(self.allocator);
        self.depth_stencil_state.deinit();
        self.texture_view_state.deinit(self.allocator);
        self.descriptor_state.deinit();
        if (self.dispatch_info_buffer) |buffer| {
            d3d12_bridge_release(buffer);
            self.dispatch_info_buffer = null;
            self.has_dispatch_info_cbv = false;
        }
        d3d12_texture.release_all(&self.texture_map);
        if (self.fence) |f| {
            d3d12_bridge_release(f);
            self.fence = null;
        }
        if (self.queue) |q| {
            d3d12_bridge_release(q);
            self.queue = null;
        }
        if (self.device) |d| {
            d3d12_bridge_release(d);
            self.device = null;
            self.has_device = false;
        }
    }

    pub fn upload_bytes(self: *NativeD3D12Runtime, bytes: u64, _mode: webgpu.UploadBufferUsageMode) !void {
        _ = _mode;
        if (bytes == 0) return error.InvalidArgument;
        if (bytes > MAX_UPLOAD_BYTES) return error.UnsupportedFeature;
        const len: usize = @intCast(bytes);

        const cmd_alloc = d3d12_bridge_device_create_command_allocator(self.device) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(cmd_alloc);

        const cmd_list = d3d12_bridge_device_create_command_list(self.device, cmd_alloc) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(cmd_list);

        const src_buf = d3d12_pool_pop(&self.upload_pool, len) orelse
            (d3d12_bridge_device_create_buffer(self.device, len, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState);
        errdefer d3d12_pool_push_or_release(&self.upload_pool, self.allocator, len, src_buf);

        const dst_buf = d3d12_pool_pop(&self.default_pool, len) orelse
            (d3d12_bridge_device_create_buffer(self.device, len, HEAP_TYPE_DEFAULT) orelse return error.InvalidState);
        errdefer d3d12_pool_push_or_release(&self.default_pool, self.allocator, len, dst_buf);

        d3d12_bridge_command_list_copy_buffer(cmd_list, dst_buf, src_buf, len);
        d3d12_bridge_command_list_close(cmd_list);

        try self.pending_uploads.append(self.allocator, .{
            .cmd_allocator = cmd_alloc,
            .cmd_list = cmd_list,
            .src_buffer = src_buf,
            .dst_buffer = dst_buf,
            .byte_count = len,
        });
        self.has_deferred_submissions = true;
    }

    pub fn flush_queue(self: *NativeD3D12Runtime) !u64 {
        if (!self.has_device) return 0;
        const start_ns = common_timing.now_ns();

        // Flush any streaming copy commands first so they execute before the fence.
        if (self.streaming_copy_state.has_pending()) {
            _ = try self.streaming_copy_state.flush(self.queue, self.fence, &self.fence_value);
        }

        for (self.pending_uploads.items) |item| {
            d3d12_bridge_queue_execute_command_list(self.queue, item.cmd_list);
        }

        if (self.pending_uploads.items.len > 0 or self.has_deferred_submissions) {
            self.fence_value +|= 1;
            d3d12_bridge_queue_signal(self.queue, self.fence, self.fence_value);
            d3d12_bridge_fence_wait(self.fence, self.fence_value);
            self.has_deferred_submissions = false;
        }

        self.release_pending_uploads();
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn barrier(self: *NativeD3D12Runtime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        _ = queue_wait_mode;
        const start_ns = common_timing.now_ns();
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn prewarm_upload_path(self: *NativeD3D12Runtime, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        if (max_upload_bytes == 0) return;
        try self.upload_bytes(@min(max_upload_bytes, MAX_UPLOAD_BYTES), mode);
        _ = try self.flush_queue();
    }

    pub fn load_kernel_cso(self: *const NativeD3D12Runtime, alloc: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        if (kernel_name.len == 0) return error.InvalidArgument;
        const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;

        const dxil_path = try std.fmt.allocPrint(alloc, "{s}/{s}.dxil", .{ root, strip_extension(kernel_name) });
        defer alloc.free(dxil_path);
        if (path_utils.file_exists(dxil_path)) {
            return std.fs.cwd().readFileAlloc(alloc, dxil_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        }

        const cso_path = try std.fmt.allocPrint(alloc, "{s}/{s}.cso", .{ root, strip_extension(kernel_name) });
        defer alloc.free(cso_path);
        if (path_utils.file_exists(cso_path)) {
            return std.fs.cwd().readFileAlloc(alloc, cso_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        }

        const dxbc_path = try std.fmt.allocPrint(alloc, "{s}/{s}.dxbc", .{ root, strip_extension(kernel_name) });
        defer alloc.free(dxbc_path);
        if (path_utils.file_exists(dxbc_path)) {
            return std.fs.cwd().readFileAlloc(alloc, dxbc_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        }

        const source_path = self.resolve_kernel_source_path(alloc, kernel_name) catch return error.ShaderCompileFailed;
        defer alloc.free(source_path);

        const source = std.fs.cwd().readFileAlloc(alloc, source_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
        defer alloc.free(source);

        if (std.mem.endsWith(u8, source_path, ".dxil") or
            std.mem.endsWith(u8, source_path, ".cso") or
            std.mem.endsWith(u8, source_path, ".dxbc"))
        {
            return try alloc.dupe(u8, source);
        }

        if (std.mem.endsWith(u8, source_path, ".wgsl")) {
            return try self.compile_wgsl_source(alloc, source);
        }

        if (std.mem.endsWith(u8, source_path, ".hlsl")) {
            return try self.compile_hlsl_source(alloc, source);
        }

        return error.ShaderCompileFailed;
    }

    pub fn set_compute_shader(self: *NativeD3D12Runtime, bytecode: []const u8) !void {
        if (bytecode.len == 0) return error.ShaderCompileFailed;
        const hash = std.hash.Wyhash.hash(0, bytecode);
        if (self.has_compute_pipeline and hash == self.current_shader_hash) return;
        try self.build_compute_pipeline(bytecode, hash);
    }

    pub fn run_dispatch(self: *NativeD3D12Runtime, x: u32, y: u32, z: u32, repeat: u32) !DispatchMetrics {
        if (x == 0 or y == 0 or z == 0) return error.InvalidArgument;
        if (!self.has_compute_pipeline) return error.Unsupported;

        if (self.has_deferred_submissions) _ = try self.flush_queue();

        const run_count: u32 = if (repeat == 0) 1 else repeat;
        const encode_start = common_timing.now_ns();

        if (d3d12_bridge_command_allocator_reset(self.compute_allocator) != 0) return error.InvalidState;
        if (d3d12_bridge_command_list_reset(self.compute_cmd_list, self.compute_allocator) != 0) return error.InvalidState;

        d3d12_bridge_command_list_set_compute_root_signature(self.compute_cmd_list, self.root_signature);
        d3d12_bridge_command_list_set_pipeline_state(self.compute_cmd_list, self.compute_pipeline);
        try self.bind_dispatch_info(x, y, z);

        var i: u32 = 0;
        while (i < run_count) : (i += 1) {
            d3d12_bridge_command_list_dispatch(self.compute_cmd_list, x, y, z);
        }
        d3d12_bridge_command_list_close(self.compute_cmd_list);
        const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

        d3d12_bridge_queue_execute_command_list(self.queue, self.compute_cmd_list);
        self.fence_value +|= 1;
        d3d12_bridge_queue_signal(self.queue, self.fence, self.fence_value);
        const submit_start = common_timing.now_ns();
        d3d12_bridge_fence_wait(self.fence, self.fence_value);
        const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start);

        return .{ .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns, .dispatch_count = run_count };
    }

    // --- Forwarding to sub-modules ---

    pub fn texture_write(self: *NativeD3D12Runtime, cmd: model.TextureWriteCommand) !u64 {
        return d3d12_texture.texture_write(self.device, self.queue, &self.texture_map, self.allocator, cmd);
    }

    pub fn texture_query(self: *const NativeD3D12Runtime, cmd: model.TextureQueryCommand) !u64 {
        return d3d12_texture.texture_query(&self.texture_map, cmd);
    }

    pub fn texture_destroy(self: *NativeD3D12Runtime, cmd: model.TextureDestroyCommand) !u64 {
        return d3d12_texture.texture_destroy(&self.texture_map, cmd);
    }

    pub fn sampler_create(self: *NativeD3D12Runtime, cmd: model.SamplerCreateCommand) !u64 {
        return self.sampler_state.sampler_create(self.device, self.allocator, cmd);
    }

    pub fn sampler_destroy(self: *NativeD3D12Runtime, cmd: model.SamplerDestroyCommand) !u64 {
        return self.sampler_state.sampler_destroy(cmd);
    }

    pub fn execute_compute_dispatch(self: *NativeD3D12Runtime, cmd: model.DispatchCommand) !d3d12_dispatch.DispatchMetrics {
        return self.dispatch_state.execute_dispatch(self.device, self.queue, self.fence, &self.fence_value, cmd);
    }

    pub fn execute_dispatch_indirect(self: *NativeD3D12Runtime, cmd: model.DispatchIndirectCommand) !d3d12_dispatch.DispatchMetrics {
        return self.dispatch_state.execute_dispatch_indirect(self.device, self.queue, self.fence, &self.fence_value, cmd);
    }

    pub fn execute_copy(self: *NativeD3D12Runtime, cmd: model.CopyCommand, queue_sync_mode: webgpu.QueueSyncMode) !d3d12_streaming_copy.CopyMetrics {
        var metrics = try self.streaming_copy_state.record_copy(self.device, &self.texture_map, self.allocator, cmd);
        self.has_deferred_submissions = true;
        if (queue_sync_mode == .per_command) {
            metrics.submit_wait_ns = try self.streaming_copy_state.flush(self.queue, self.fence, &self.fence_value);
            self.has_deferred_submissions = false;
        }
        return metrics;
    }

    pub fn execute_render_draw(self: *NativeD3D12Runtime, cmd: model.RenderDrawCommand, is_indirect: bool, is_indexed_indirect: bool) !d3d12_render.RenderMetrics {
        return self.render_state.execute_render_draw(self.device, self.queue, self.fence, &self.fence_value, cmd, is_indirect, is_indexed_indirect, &self.descriptor_state);
    }

    pub fn execute_render_bundles(
        self: *NativeD3D12Runtime,
        bundles: []const *const render_bundle.DoeRenderBundle,
        target_width: u32,
        target_height: u32,
        color_format: u32,
        sample_count: u32,
    ) !d3d12_render.RenderMetrics {
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0)
            _ = try self.flush_queue();
        return self.render_state.execute_render_bundles(self.device, self.queue, self.fence, &self.fence_value, bundles, target_width, target_height, color_format, sample_count);
    }

    pub fn surface_create(self: *NativeD3D12Runtime, cmd: model.SurfaceCreateCommand) !u64 {
        return self.surface_state.create_surface(self.allocator, cmd);
    }

    pub fn surface_capabilities(self: *NativeD3D12Runtime, cmd: model.SurfaceCapabilitiesCommand) !u64 {
        return self.surface_state.surface_capabilities(self.allocator, cmd);
    }

    pub fn surface_configure(self: *NativeD3D12Runtime, cmd: model.SurfaceConfigureCommand) !u64 {
        return self.surface_state.configure_surface(self.device, self.queue, self.allocator, cmd);
    }

    pub fn surface_acquire(self: *NativeD3D12Runtime, cmd: model.SurfaceAcquireCommand) !u64 {
        return self.surface_state.acquire_surface(self.allocator, cmd);
    }

    pub fn surface_present(self: *NativeD3D12Runtime, cmd: model.SurfacePresentCommand) !u64 {
        return self.surface_state.present_surface(cmd);
    }

    pub fn surface_unconfigure(self: *NativeD3D12Runtime, cmd: model.SurfaceUnconfigureCommand) !u64 {
        return self.surface_state.unconfigure_surface(self.allocator, cmd);
    }

    pub fn surface_release(self: *NativeD3D12Runtime, cmd: model.SurfaceReleaseCommand) !u64 {
        return self.surface_state.release_surface(cmd);
    }

    pub fn execute_async_diagnostics(self: *NativeD3D12Runtime, cmd: model.AsyncDiagnosticsCommand) !d3d12_async.AsyncDiagnosticsMetrics {
        return d3d12_async.execute_async_diagnostics(self.device, cmd);
    }

    pub fn execute_map_async(self: *NativeD3D12Runtime, cmd: model.MapAsyncCommand) !u64 {
        return d3d12_map.execute_map_async(self.device, cmd);
    }

    pub fn init_timestamps(self: *NativeD3D12Runtime) !void {
        try self.timestamp_state.init_resources(self.device, self.queue);
    }

    // Doe is synchronous — onSubmittedWorkDone completes immediately.
    pub fn on_submitted_work_done(self: *NativeD3D12Runtime) !u64 {
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            return try self.flush_queue();
        }
        return 0;
    }

    pub fn has_feature(self: *const NativeD3D12Runtime, feature: u32) bool {
        if (self.has_device) {
            return d3d12_device_caps.d3d12_device_has_feature_with_caps(feature, self.device_caps);
        }
        return d3d12_device_caps.d3d12_device_has_feature(feature);
    }

    pub fn get_limits(self: *const NativeD3D12Runtime, limits: *@import("../../core/abi/wgpu_types.zig").WGPULimits) void {
        _ = self;
        d3d12_device_caps.d3d12_device_get_limits(limits);
    }

    pub fn create_query_set(self: *NativeD3D12Runtime, handle: u64, query_type: d3d12_query_set.QueryType, count: u32) !u64 {
        return self.query_set_state.create(self.allocator, self.device, self.queue, handle, query_type, count);
    }

    pub fn destroy_query_set(self: *NativeD3D12Runtime, handle: u64) void {
        self.query_set_state.destroy(handle);
    }

    pub fn ensure_descriptor_heaps(self: *NativeD3D12Runtime) !void {
        try self.descriptor_state.ensure_heaps(self.device);
    }

    pub fn create_depth_stencil(self: *NativeD3D12Runtime, width: u32, height: u32, format: u32) !void {
        try self.depth_stencil_state.ensure_depth_texture(self.device, width, height, format);
    }

    // --- Private ---

    fn bootstrap(self: *NativeD3D12Runtime) !void {
        self.device = d3d12_bridge_create_device() orelse return error.UnsupportedFeature;
        self.queue = d3d12_bridge_device_create_command_queue(self.device) orelse return error.InvalidState;
        self.fence = d3d12_bridge_device_create_fence(self.device) orelse return error.InvalidState;
        self.has_device = true;
        self.device_caps = d3d12_device_caps.query_device_caps(self.device);
    }

    fn resolve_kernel_source_path(self: *const NativeD3D12Runtime, alloc: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
        const direct = try alloc.dupe(u8, kernel_name);
        if (path_utils.file_exists(direct)) return direct;
        alloc.free(direct);

        const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
        const rooted = try std.fmt.allocPrint(alloc, "{s}/{s}", .{ root, kernel_name });
        if (path_utils.file_exists(rooted)) return rooted;
        alloc.free(rooted);

        if (!std.mem.endsWith(u8, kernel_name, ".wgsl")) {
            const wgsl_path = try std.fmt.allocPrint(alloc, "{s}/{s}.wgsl", .{ root, kernel_name });
            if (path_utils.file_exists(wgsl_path)) return wgsl_path;
            alloc.free(wgsl_path);
        }

        if (!std.mem.endsWith(u8, kernel_name, ".hlsl")) {
            const hlsl_path = try std.fmt.allocPrint(alloc, "{s}/{s}.hlsl", .{ root, kernel_name });
            if (path_utils.file_exists(hlsl_path)) return hlsl_path;
            alloc.free(hlsl_path);
        }

        return error.ShaderCompileFailed;
    }

    fn compile_hlsl_source(self: *const NativeD3D12Runtime, alloc: std.mem.Allocator, hlsl_source: []const u8) ![]u8 {
        _ = self;
        return try compile_hlsl_to_bytecode(alloc, hlsl_source);
    }

    fn compile_wgsl_source(self: *const NativeD3D12Runtime, alloc: std.mem.Allocator, wgsl_source: []const u8) ![]u8 {
        var hlsl_buf = try alloc.alloc(u8, doe_wgsl.MAX_HLSL_OUTPUT);
        defer alloc.free(hlsl_buf);
        const hlsl_len = doe_wgsl.translateToHlsl(alloc, wgsl_source, hlsl_buf) catch return error.ShaderCompileFailed;
        return try self.compile_hlsl_source(alloc, hlsl_buf[0..hlsl_len]);
    }

    fn build_compute_pipeline(self: *NativeD3D12Runtime, bytecode: []const u8, shader_hash: u64) !void {
        if (!self.has_root_signature) {
            const range = d3d12_descriptors.DescriptorRangeDesc{
                .range_type = D3D12_DESCRIPTOR_RANGE_TYPE_CBV,
                .num_descriptors = 1,
                .base_shader_register = hlsl_dispatch_contract.DISPATCH_INFO_REGISTER_SLOT,
                .register_space = hlsl_dispatch_contract.DISPATCH_INFO_REGISTER_SPACE,
            };
            self.root_signature = d3d12_bridge_device_create_root_signature_with_tables(self.device, @ptrCast(&range), 1, 0) orelse return error.InvalidState;
            self.has_root_signature = true;
        }

        if (self.has_compute_pipeline) {
            d3d12_bridge_release(self.compute_pipeline);
            self.compute_pipeline = null;
            self.has_compute_pipeline = false;
        }

        self.compute_pipeline = d3d12_bridge_device_create_compute_pipeline(
            self.device,
            self.root_signature,
            bytecode.ptr,
            bytecode.len,
        ) orelse return error.ShaderCompileFailed;
        self.has_compute_pipeline = true;
        self.current_shader_hash = shader_hash;

        if (!self.has_compute_cmd) {
            self.compute_allocator = d3d12_bridge_device_create_command_allocator(self.device) orelse return error.InvalidState;
            self.compute_cmd_list = d3d12_bridge_device_create_command_list(self.device, self.compute_allocator) orelse return error.InvalidState;
            d3d12_bridge_command_list_close(self.compute_cmd_list);
            self.has_compute_cmd = true;
        }
    }

    fn bind_dispatch_info(self: *NativeD3D12Runtime, x: u32, y: u32, z: u32) !void {
        try self.ensure_dispatch_info_cbv();
        const mapped = d3d12_bridge_resource_map(self.dispatch_info_buffer) orelse return error.InvalidState;
        const words: *DispatchInfoWords = @ptrCast(@alignCast(mapped));
        words.* = .{ .x = x, .y = y, .z = z, ._pad = 0 };
        d3d12_bridge_resource_unmap(self.dispatch_info_buffer);

        d3d12_bridge_command_list_set_descriptor_heaps(
            self.compute_cmd_list,
            self.descriptor_state.cbv_srv_uav_heap,
            self.descriptor_state.sampler_heap,
        );
        d3d12_bridge_command_list_set_compute_root_descriptor_table(
            self.compute_cmd_list,
            hlsl_dispatch_contract.DISPATCH_INFO_ROOT_PARAMETER_INDEX,
            self.descriptor_state.cbv_srv_uav_heap,
            self.dispatch_info_cbv_index,
        );
    }

    fn ensure_dispatch_info_cbv(self: *NativeD3D12Runtime) !void {
        if (self.dispatch_info_buffer == null) {
            self.dispatch_info_buffer = d3d12_bridge_device_create_buffer(
                self.device,
                @intCast(hlsl_dispatch_contract.DISPATCH_INFO_BUFFER_BYTES),
                dc.HEAP_TYPE_UPLOAD,
            ) orelse return error.InvalidState;
        }
        if (!self.has_dispatch_info_cbv) {
            self.dispatch_info_cbv_index = try self.descriptor_state.allocate_cbv(
                self.device,
                self.dispatch_info_buffer,
                hlsl_dispatch_contract.DISPATCH_INFO_BUFFER_BYTES,
            );
            self.has_dispatch_info_cbv = true;
        }
    }

    fn destroy_compute_objects(self: *NativeD3D12Runtime) void {
        if (self.has_compute_cmd) {
            d3d12_bridge_release(self.compute_cmd_list);
            d3d12_bridge_release(self.compute_allocator);
            self.compute_cmd_list = null;
            self.compute_allocator = null;
            self.has_compute_cmd = false;
        }
        if (self.has_compute_pipeline) {
            d3d12_bridge_release(self.compute_pipeline);
            self.compute_pipeline = null;
            self.has_compute_pipeline = false;
        }
        if (self.has_root_signature) {
            d3d12_bridge_release(self.root_signature);
            self.root_signature = null;
            self.has_root_signature = false;
        }
    }

    fn release_pending_uploads(self: *NativeD3D12Runtime) void {
        for (self.pending_uploads.items) |item| {
            d3d12_bridge_release(item.cmd_list);
            d3d12_bridge_release(item.cmd_allocator);
            d3d12_pool_push_or_release(&self.upload_pool, self.allocator, item.byte_count, item.src_buffer);
            d3d12_pool_push_or_release(&self.default_pool, self.allocator, item.byte_count, item.dst_buffer);
        }
        self.pending_uploads.clearRetainingCapacity();
    }
};

pub fn strip_extension(name: []const u8) []const u8 {
    const suffixes = [_][]const u8{ ".wgsl", ".hlsl", ".dxil", ".cso", ".dxbc" };
    for (suffixes) |sfx| {
        if (std.mem.endsWith(u8, name, sfx)) return name[0 .. name.len - sfx.len];
    }
    return name;
}

fn compile_hlsl_to_bytecode(alloc: std.mem.Allocator, hlsl_source: []const u8) ![]u8 {
    std.fs.cwd().makePath(GENERATED_SHADER_DIR) catch return error.ShaderCompileFailed;

    const source_hash = std.hash.Wyhash.hash(0, hlsl_source);
    const stem = try std.fmt.allocPrint(alloc, "{s}/d3d12_{x}", .{ GENERATED_SHADER_DIR, source_hash });
    defer alloc.free(stem);
    const hlsl_path = try std.fmt.allocPrint(alloc, "{s}.generated.hlsl", .{stem});
    defer alloc.free(hlsl_path);
    const cso_path = try std.fmt.allocPrint(alloc, "{s}.generated.cso", .{stem});
    defer alloc.free(cso_path);

    if (!path_utils.file_exists(cso_path)) {
        const file = std.fs.cwd().createFile(hlsl_path, .{ .truncate = true }) catch return error.ShaderCompileFailed;
        defer file.close();
        file.writeAll(hlsl_source) catch return error.ShaderCompileFailed;
        try run_dxc(alloc, hlsl_path, cso_path, DXC_ENTRYPOINT);
    }

    return std.fs.cwd().readFileAlloc(alloc, cso_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
}

fn run_dxc(alloc: std.mem.Allocator, input_path: []const u8, output_path: []const u8, entrypoint: []const u8) !void {
    const exe = if (builtin.os.tag == .windows) "dxc.exe" else "dxc";
    const argv = [_][]const u8{
        exe,
        "-T",
        DXC_PROFILE,
        "-E",
        entrypoint,
        "-Fo",
        output_path,
        input_path,
    };
    const result = std.process.Child.run(.{
        .allocator = alloc,
        .argv = &argv,
        .max_output_bytes = MAX_DXC_OUTPUT_BYTES,
    }) catch |err| return switch (err) {
        error.FileNotFound => error.ShaderToolchainUnavailable,
        else => error.ShaderCompileFailed,
    };
    defer alloc.free(result.stdout);
    defer alloc.free(result.stderr);

    switch (result.term) {
        .Exited => |code| if (code != 0) return error.ShaderCompileFailed,
        else => return error.ShaderCompileFailed,
    }
}

pub const D3D12Pool = std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(PoolEntry));

pub fn d3d12_pool_pop(pool: *D3D12Pool, size: usize) ?*anyopaque {
    if (pool.getPtr(size)) |list| {
        if (list.items.len > 0) {
            const entry = list.pop() orelse return null;
            return entry.buffer;
        }
    }
    return null;
}

fn d3d12_pool_push_or_release(pool: *D3D12Pool, allocator: std.mem.Allocator, size: usize, buf: ?*anyopaque) void {
    const gop = pool.getOrPut(allocator, size) catch {
        d3d12_bridge_release(buf);
        return;
    };
    if (!gop.found_existing) gop.value_ptr.* = .{};
    if (gop.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        d3d12_bridge_release(buf);
        return;
    }
    gop.value_ptr.append(allocator, .{ .buffer = buf }) catch {
        d3d12_bridge_release(buf);
    };
}

fn d3d12_release_pool(pool: *D3D12Pool, allocator: std.mem.Allocator) void {
    var it = pool.valueIterator();
    while (it.next()) |list| {
        for (list.items) |entry| d3d12_bridge_release(entry.buffer);
        var m = list.*;
        m.deinit(allocator);
    }
    pool.deinit(allocator);
}
