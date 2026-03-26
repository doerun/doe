const builtin = @import("builtin");
const std = @import("std");
const common_timing = @import("../common/timing.zig");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const async_runtime = @import("metal_async_runtime.zig");
const cleanup = @import("metal_cleanup.zig");
const copy_queue = @import("metal_copy_queue.zig");
const copy_runtime = @import("metal_copy_runtime.zig");
const deferred_release = @import("metal_deferred_release.zig");
const dispatch_runtime = @import("metal_dispatch_runtime.zig");
const metal_buffer_pool = @import("metal_buffer_pool.zig");
const metal_gpu_timestamps = @import("metal_gpu_timestamps.zig");
const metal_pipeline_cache = @import("metal_pipeline_cache.zig");
const metal_upload = @import("metal_upload.zig");
const resource_commands = @import("metal_resource_commands.zig");
const resource_runtime = @import("metal_runtime_resources.zig");
const surface_runtime = @import("metal_surface_runtime.zig");
const kernel_dispatch = @import("metal_kernel_dispatch.zig");
const bridge = @import("metal_bridge_decls.zig");
const HAS_PIPELINE_CACHE = builtin.os.tag == .macos;
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_command_buffer_encode_signal_event = bridge.metal_bridge_command_buffer_encode_signal_event;
const metal_bridge_command_buffer_encode_wait_event = bridge.metal_bridge_command_buffer_encode_wait_event;
const metal_bridge_command_buffer_setup_fast_wait = bridge.metal_bridge_command_buffer_setup_fast_wait;
const metal_bridge_command_buffer_wait_completed = bridge.metal_bridge_command_buffer_wait_completed;
const metal_bridge_command_buffer_wait_fast = bridge.metal_bridge_command_buffer_wait_fast;
const metal_bridge_create_command_buffer = bridge.metal_bridge_create_command_buffer;
const metal_bridge_create_default_device = bridge.metal_bridge_create_default_device;
const metal_bridge_device_new_command_queue = bridge.metal_bridge_device_new_command_queue;
const metal_bridge_device_new_command_queue_with_priority = bridge.metal_bridge_device_new_command_queue_with_priority;
const metal_bridge_device_new_shared_event = bridge.metal_bridge_device_new_shared_event;
const metal_bridge_blit_encoder_copy_texture_to_texture = bridge.metal_bridge_blit_encoder_copy_texture_to_texture;
const metal_bridge_cmd_buf_blit_encoder = bridge.metal_bridge_cmd_buf_blit_encoder;
const metal_bridge_device_new_render_target = bridge.metal_bridge_device_new_render_target;
const metal_bridge_end_blit_encoding = bridge.metal_bridge_end_blit_encoding;
const metal_bridge_release = bridge.metal_bridge_release;
const metal_bridge_render_encoder_draw = bridge.metal_bridge_render_encoder_draw;
const metal_bridge_render_encoder_end = bridge.metal_bridge_render_encoder_end;
const metal_bridge_render_encoder_execute_icb = bridge.metal_bridge_render_encoder_execute_icb;
const metal_bridge_shared_event_wait = bridge.metal_bridge_shared_event_wait;

pub const MAX_UPLOAD_BYTES: u64 = 0; // unused; retained for prewarm clamp only
pub const MAX_BINDING_SLOTS: usize = 32;
pub const SMALL_UPLOAD_CAPACITY: usize = 1024 * 1024;
pub const FAST_WAIT_UPLOAD_THRESHOLD: usize = 256 * 1024;
pub const MAX_POOL_ENTRIES_PER_SIZE: usize = metal_buffer_pool.MAX_POOL_ENTRIES_PER_SIZE;
pub const DispatchMetrics = kernel_dispatch.DispatchMetrics;

pub const RenderMetrics = struct {
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
    draw_count: u32,
    gpu_elapsed_ns: u64 = 0,
    gpu_timestamps_attempted: bool = false,
    gpu_timestamps_valid: bool = false,
};

pub const PendingUpload = struct {
    src_buffer: ?*anyopaque,
    dst_buffer: ?*anyopaque,
    byte_count: usize,
};

pub const KernelPipeline = struct {
    library: ?*anyopaque,
    pipeline: ?*anyopaque,
};

pub const IcbKey = struct {
    draw_count: u32,
    vertex_count: u32,
    instance_count: u32,
    redundant: bool,
};

pub const FlushResult = struct {
    submit_wait_ns: u64 = 0,
    gpu_elapsed_ns: u64 = 0,
    gpu_timestamps_attempted: bool = false,
    gpu_timestamps_valid: bool = false,
};

pub const NativeMetalRuntime = struct {
    allocator: std.mem.Allocator,
    device: ?*anyopaque = null,
    queue: ?*anyopaque = null,
    has_device: bool = false,

    kernel_root: ?[]const u8 = null,

    has_deferred_submissions: bool = false,

    outstanding_cmd_buf: ?*anyopaque = null,
    deferred_releases: std.ArrayListUnmanaged(?*anyopaque) = .{},

    // Batch deferred release pool — collects texture/sampler destroys and
    // drains them in a tight loop at command buffer boundaries, amortizing
    // per-call CFRelease overhead that causes tail-negative timing under
    // aggregate lane pressure.
    deferred_pool: deferred_release.DeferredReleasePool = .{},

    // Sampler descriptor cache — reuses identical MTLSamplerState objects
    // across create/destroy cycles instead of round-tripping through
    // Metal's alloc/dealloc path for every sampler lifecycle command.
    sampler_cache: deferred_release.SamplerCache = deferred_release.SamplerCache.init(),

    shared_event: ?*anyopaque = null,
    fence_value: u64 = 0,

    // Copy queue — dedicated MTLCommandQueue for overlapping upload/copy work.
    // Falls back to single-queue mode when null (creation failure or unsupported).
    copy_queue: ?*anyopaque = null,
    copy_cmd_buf: ?*anyopaque = null,
    copy_blit_encoder: ?*anyopaque = null,
    copy_fence_value: u64 = 0,
    has_pending_copies: bool = false,

    streaming_cmd_buf: ?*anyopaque = null,
    streaming_blit_encoder: ?*anyopaque = null,
    streaming_render_encoder: ?*anyopaque = null,
    streaming_has_render: bool = false,
    streaming_has_copy: bool = false,
    streaming_max_upload_bytes: usize = 0,
    streaming_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},
    streaming_gpu_timestamps_active: bool = false,

    shared_pool: std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque)) = .{},
    private_pool: std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque)) = .{},

    staging_src: ?*anyopaque = null,
    staging_dst: ?*anyopaque = null,
    staging_src_ptr: ?[*]u8 = null, // cached contents pointer
    staging_src_zeroed: bool = false,

    kernel_pipelines: std.StringHashMapUnmanaged(KernelPipeline) = .{},

    compute_buffers: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},
    dispatch_indirect_args_buffer: ?*anyopaque = null,

    textures: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},

    samplers: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},
    surfaces: std.AutoHashMapUnmanaged(u64, surface_runtime.SurfaceState) = .{},

    render_pipeline: ?*anyopaque = null,
    render_pipeline_format: u32 = 0,

    render_target: ?*anyopaque = null,
    render_target_width: u32 = 0,
    render_target_height: u32 = 0,
    render_target_format: u32 = 0,

    cached_icb: ?*anyopaque = null,
    cached_icb_key: IcbKey = .{ .draw_count = 0, .vertex_count = 0, .instance_count = 0, .redundant = false },

    pipeline_binary_cache: ?*anyopaque = null,
    timestamp_state: metal_gpu_timestamps.TimestampState = .{},

    pub fn init(allocator: std.mem.Allocator, kernel_root: ?[]const u8) !NativeMetalRuntime {
        var self = NativeMetalRuntime{ .allocator = allocator, .kernel_root = kernel_root };
        errdefer self.deinit();
        try self.bootstrap();
        return self;
    }

    pub fn deinit(self: *NativeMetalRuntime) void {
        _ = self.flush_queue() catch {};
        self.wait_outstanding();
        // Release any remaining streaming uploads (if flush_queue failed).
        for (self.streaming_uploads.items) |item| {
            metal_bridge_release(item.src_buffer);
            metal_bridge_release(item.dst_buffer);
        }
        self.streaming_uploads.deinit(self.allocator);
        if (self.streaming_render_encoder) |enc| {
            metal_bridge_render_encoder_end(enc);
            metal_bridge_release(enc);
            self.streaming_render_encoder = null;
        }
        if (self.streaming_blit_encoder) |enc| {
            metal_bridge_end_blit_encoding(enc);
            self.streaming_blit_encoder = null;
        }
        if (self.streaming_cmd_buf) |cb| {
            metal_bridge_release(cb);
            self.streaming_cmd_buf = null;
        }
        self.release_deferred_releases();
        self.deferred_releases.deinit(self.allocator);
        // Drain any pending batch releases before tearing down resource maps.
        self.deferred_pool.drain();
        cleanup.release_buffer_pool(self.allocator, &self.shared_pool);
        cleanup.release_buffer_pool(self.allocator, &self.private_pool);
        release_ref(&self.staging_src);
        release_ref(&self.staging_dst);
        self.staging_src_zeroed = false;
        cleanup.release_kernel_pipelines(self);
        cleanup.release_compute_buffers(self);
        release_ref(&self.dispatch_indirect_args_buffer);
        cleanup.release_textures(self);
        // release_samplers coordinates with sampler_cache: cache-managed handles
        // are ref-counted down, non-cached handles are released directly.
        cleanup.release_samplers(self);
        // Deinit sampler cache after map cleanup — releases any cached Metal
        // objects whose ref counts reached zero above.
        self.sampler_cache.deinit();
        cleanup.release_surfaces(self);
        cleanup.release_render_resources(self);
        self.timestamp_state.deinit();
        self.release_copy_queue_resources();
        release_ref(&self.shared_event);
        if (builtin.os.tag == .macos) {
            if (HAS_PIPELINE_CACHE) {
                if (self.pipeline_binary_cache) |c| {
                    const typed: *metal_pipeline_cache.MetalPipelineCache = @ptrCast(@alignCast(c));
                    typed.deinit();
                    self.pipeline_binary_cache = null;
                }
            }
        }
        release_ref(&self.queue);
        release_ref(&self.device);
        self.has_device = false;
    }

    pub fn upload_bytes(self: *NativeMetalRuntime, bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        return metal_upload.upload_bytes(self, bytes, mode);
    }

    pub fn flush_queue(self: *NativeMetalRuntime) !u64 {
        const result = try self.flush_queue_timed();
        return result.submit_wait_ns;
    }

    pub fn flush_queue_timed(self: *NativeMetalRuntime) !FlushResult {
        if (!self.has_device) return .{};
        const has_streaming = self.streaming_cmd_buf != null;
        if (!has_streaming and !self.has_deferred_submissions) return .{};
        const start_ns = common_timing.now_ns();
        self.wait_outstanding();
        var gpu_timestamps_attempted = false;
        var gpu_elapsed_ns: u64 = 0;
        if (has_streaming) {
            // Flush copy queue first so its signal precedes the main queue's wait.
            if (self.has_pending_copies) self.flush_copy_queue();

            if (self.streaming_render_encoder) |enc| {
                metal_bridge_render_encoder_end(enc);
                metal_bridge_release(enc);
                self.streaming_render_encoder = null;
            }
            if (self.streaming_blit_encoder) |enc| {
                metal_bridge_end_blit_encoding(enc);
                self.streaming_blit_encoder = null;
            }

            const cmd_buf = self.streaming_cmd_buf.?;

            // If the copy queue signaled, encode a GPU-side wait on the main
            // queue so compute/render work waits for copy completion.
            if (self.copy_fence_value > 0) {
                if (self.shared_event) |ev| {
                    metal_bridge_command_buffer_encode_wait_event(cmd_buf, ev, self.copy_fence_value);
                }
            }

            // Record end GPU timestamp before commit (after all other encoders).
            gpu_timestamps_attempted = self.streaming_gpu_timestamps_active;
            if (self.streaming_gpu_timestamps_active) {
                self.timestamp_state.record_end(cmd_buf);
            }

            self.fence_value +%= 1;
            const use_fast_wait =
                !self.streaming_has_render and
                (self.streaming_has_copy or self.streaming_max_upload_bytes >= FAST_WAIT_UPLOAD_THRESHOLD);
            if (use_fast_wait) {
                if (self.shared_event) |ev| {
                    metal_bridge_command_buffer_encode_signal_event(cmd_buf, ev, self.fence_value);
                }
                metal_bridge_command_buffer_setup_fast_wait(cmd_buf);
            }
            metal_bridge_command_buffer_commit(cmd_buf);
            // When using fast wait with GPU timestamps, fall back to
            // waitUntilCompleted so counter data is guaranteed resolvable.
            if (gpu_timestamps_attempted) {
                metal_bridge_command_buffer_wait_completed(cmd_buf);
            } else if (use_fast_wait) {
                metal_bridge_command_buffer_wait_fast();
            } else {
                metal_bridge_command_buffer_wait_completed(cmd_buf);
            }

            // Resolve GPU timestamps after command buffer completion.
            if (gpu_timestamps_attempted) {
                gpu_elapsed_ns = self.timestamp_state.resolve_elapsed_ns();
            }

            metal_bridge_release(cmd_buf);
            self.streaming_cmd_buf = null;
            self.streaming_has_render = false;
            self.streaming_has_copy = false;
            self.streaming_max_upload_bytes = 0;
            self.streaming_gpu_timestamps_active = false;
            for (self.streaming_uploads.items) |item| {
                pool_push_or_release(&self.shared_pool, self.allocator, item.byte_count, item.src_buffer);
                pool_push_or_release(&self.private_pool, self.allocator, item.byte_count, item.dst_buffer);
            }
            self.streaming_uploads.clearRetainingCapacity();
        } else if (self.has_deferred_submissions) {
            if (self.outstanding_cmd_buf != null) {
                self.wait_outstanding();
            } else {
                const empty_cmd = metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
                metal_bridge_command_buffer_commit(empty_cmd);
                metal_bridge_command_buffer_wait_completed(empty_cmd);
                metal_bridge_release(empty_cmd);
            }
        }

        self.has_deferred_submissions = false;
        const end_ns = common_timing.now_ns();
        self.release_deferred_releases();
        // Batch-drain deferred texture/sampler releases collected since last flush.
        self.deferred_pool.drain();
        return .{
            .submit_wait_ns = common_timing.ns_delta(end_ns, start_ns),
            .gpu_elapsed_ns = gpu_elapsed_ns,
            .gpu_timestamps_attempted = gpu_timestamps_attempted,
            .gpu_timestamps_valid = gpu_timestamps_attempted and gpu_elapsed_ns > 0,
        };
    }

    fn wait_outstanding(self: *NativeMetalRuntime) void {
        if (self.outstanding_cmd_buf) |cb| {
            if (self.shared_event) |ev| {
                metal_bridge_shared_event_wait(ev, self.fence_value);
            } else {
                metal_bridge_command_buffer_wait_completed(cb);
            }
            metal_bridge_release(cb);
            self.outstanding_cmd_buf = null;
        }
    }

    pub fn barrier(self: *NativeMetalRuntime, queue_wait_mode: webgpu.QueueWaitMode, queue_sync_mode: webgpu.QueueSyncMode) !u64 {
        _ = queue_wait_mode;
        if (self.has_pending_copies) self.flush_copy_queue();
        if (queue_sync_mode == .deferred and self.streaming_cmd_buf == null and self.has_deferred_submissions) {
            const start_ns = common_timing.now_ns();
            if (self.outstanding_cmd_buf) |cb| {
                metal_bridge_release(cb);
                self.outstanding_cmd_buf = null;
            }
            const empty_cmd = metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
            self.fence_value +%= 1;
            if (self.shared_event) |ev| {
                metal_bridge_command_buffer_encode_signal_event(empty_cmd, ev, self.fence_value);
            }
            metal_bridge_command_buffer_commit(empty_cmd);
            self.outstanding_cmd_buf = empty_cmd;
            return common_timing.ns_delta(common_timing.now_ns(), start_ns);
        }

        const start_ns = common_timing.now_ns();
        if (self.streaming_cmd_buf != null or self.has_deferred_submissions) {
            _ = try self.flush_queue();
        }
        self.wait_outstanding();
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn prewarm_upload_path(self: *NativeMetalRuntime, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        return metal_upload.prewarm_upload_path(self, max_upload_bytes, mode);
    }

    pub const KernelDispatchResult = kernel_dispatch.KernelDispatchResult;

    pub fn run_kernel_dispatch(
        self: *NativeMetalRuntime,
        kernel: []const u8,
        x: u32,
        y: u32,
        z: u32,
        repeat: u32,
        warmup: u32,
        bindings: ?[]const model.KernelBinding,
    ) !DispatchMetrics {
        return kernel_dispatch.run_kernel_dispatch(self, kernel, x, y, z, repeat, warmup, bindings);
    }

    pub fn run_kernel_dispatch_timed(
        self: *NativeMetalRuntime,
        kernel: []const u8,
        x: u32,
        y: u32,
        z: u32,
        repeat: u32,
        warmup: u32,
        initialize_buffers_on_create: bool,
        bindings: ?[]const model.KernelBinding,
        record_timestamps: bool,
    ) !KernelDispatchResult {
        return kernel_dispatch.run_kernel_dispatch_timed(self, kernel, x, y, z, repeat, warmup, initialize_buffers_on_create, bindings, record_timestamps);
    }

    pub fn run_dispatch(self: *NativeMetalRuntime, x: u32, y: u32, z: u32, queue_sync_mode: webgpu.QueueSyncMode) !DispatchMetrics {
        const metrics = try dispatch_runtime.run_dispatch(self, x, y, z, queue_sync_mode);
        return .{ .setup_ns = 0, .encode_ns = metrics.encode_ns, .submit_wait_ns = metrics.submit_wait_ns, .dispatch_count = metrics.dispatch_count };
    }

    pub fn run_dispatch_indirect(self: *NativeMetalRuntime, x: u32, y: u32, z: u32, queue_sync_mode: webgpu.QueueSyncMode) !DispatchMetrics {
        const metrics = try dispatch_runtime.run_dispatch_indirect(self, x, y, z, queue_sync_mode);
        return .{ .setup_ns = 0, .encode_ns = metrics.encode_ns, .submit_wait_ns = metrics.submit_wait_ns, .dispatch_count = metrics.dispatch_count };
    }

    pub fn execute_map_async(self: *NativeMetalRuntime, cmd: model.MapAsyncCommand) !u64 {
        return async_runtime.execute_map_async(self, cmd);
    }

    pub fn sampler_create(self: *NativeMetalRuntime, cmd: model.SamplerCreateCommand) !void {
        return resource_commands.sampler_create(self, cmd);
    }

    pub fn sampler_destroy(self: *NativeMetalRuntime, cmd: model.SamplerDestroyCommand) !void {
        return resource_commands.sampler_destroy(self, cmd);
    }

    pub fn texture_write(self: *NativeMetalRuntime, cmd: model.TextureWriteCommand) !void {
        return resource_commands.texture_write(self, cmd);
    }

    pub fn write_buffer(self: *NativeMetalRuntime, cmd: model.BufferWriteCommand) !void {
        return resource_runtime.write_compute_buffer_words(self, cmd.handle, cmd.offset, cmd.buffer_size, cmd.data);
    }

    pub fn texture_query(self: *NativeMetalRuntime, cmd: model.TextureQueryCommand) !void {
        return resource_commands.texture_query(self, cmd);
    }

    pub fn texture_destroy(self: *NativeMetalRuntime, cmd: model.TextureDestroyCommand) !void {
        return resource_commands.texture_destroy(self, cmd);
    }

    pub fn render_draw(self: *NativeMetalRuntime, cmd: model.RenderDrawCommand, queue_sync_mode: webgpu.QueueSyncMode) !RenderMetrics {
        const fmt = cmd.target_format;
        const is_bundle = cmd.encode_mode == .render_bundle;
        const red_pl: c_int = if (cmd.pipeline_mode == .redundant) 1 else 0;

        // Quirk: Intel Metal R8/RG8Unorm small-mip workaround. When the flag
        // is set, render to a temporary texture then blit to the real target,
        // avoiding driver corruption on affected mip levels.
        const needs_temp_texture = cmd.uses_temporary_render_texture;

        // Setup: pipeline compile, texture alloc, ICB creation, encoder creation.
        const setup_start = common_timing.now_ns();
        try self.ensure_render_pipeline(fmt);
        try self.ensure_render_target(cmd.target_width, cmd.target_height, fmt);

        var temp_texture: ?*anyopaque = null;
        var saved_target: ?*anyopaque = null;
        if (needs_temp_texture) {
            saved_target = self.render_target;
            temp_texture = metal_bridge_device_new_render_target(
                self.device,
                cmd.target_width,
                cmd.target_height,
                fmt,
            ) orelse return error.InvalidState;
            self.render_target = temp_texture;
            // Force fresh render encoder targeting the temporary texture.
            if (self.streaming_render_encoder) |enc| {
                metal_bridge_render_encoder_end(enc);
                metal_bridge_release(enc);
                self.streaming_render_encoder = null;
            }
        }

        const icb = if (is_bundle) try self.ensure_icb(cmd.draw_count, cmd.vertex_count, cmd.instance_count, red_pl) else null;
        try self.ensure_streaming_render_encoder();
        const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

        // Encode: draw/execute calls.
        const encode_start = common_timing.now_ns();
        if (is_bundle) {
            metal_bridge_render_encoder_execute_icb(
                self.streaming_render_encoder,
                icb,
                cmd.draw_count,
            );
        } else {
            metal_bridge_render_encoder_draw(
                self.streaming_render_encoder,
                0x00000004,
                cmd.draw_count,
                cmd.vertex_count,
                cmd.instance_count,
                0,
                0,
                red_pl,
                self.render_pipeline,
            );
        }

        // Blit temporary texture to the real render target.
        if (needs_temp_texture) {
            if (self.streaming_render_encoder) |enc| {
                metal_bridge_render_encoder_end(enc);
                metal_bridge_release(enc);
                self.streaming_render_encoder = null;
            }
            self.render_target = saved_target.?;
            // Ensure blit encoder for the copy.
            if (self.streaming_blit_encoder == null) {
                if (self.streaming_cmd_buf == null) {
                    self.streaming_cmd_buf = metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
                }
                self.streaming_blit_encoder = metal_bridge_cmd_buf_blit_encoder(self.streaming_cmd_buf) orelse return error.InvalidState;
            }
            metal_bridge_blit_encoder_copy_texture_to_texture(
                self.streaming_blit_encoder,
                temp_texture,
                0,
                self.render_target,
                0,
                cmd.target_width,
                cmd.target_height,
                1,
            );
            metal_bridge_release(temp_texture.?);
            self.streaming_has_copy = true;
        }

        const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

        // Submit+wait: commit command buffer and wait for GPU completion.
        if (queue_sync_mode == .deferred) {
            return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = 0, .draw_count = cmd.draw_count };
        }
        const flush = try self.flush_queue_timed();
        return .{
            .setup_ns = setup_ns,
            .encode_ns = encode_ns,
            .submit_wait_ns = flush.submit_wait_ns,
            .draw_count = cmd.draw_count,
            .gpu_elapsed_ns = flush.gpu_elapsed_ns,
            .gpu_timestamps_attempted = flush.gpu_timestamps_attempted,
            .gpu_timestamps_valid = flush.gpu_timestamps_valid,
        };
    }

    pub fn copy_command(self: *NativeMetalRuntime, cmd: model.CopyCommand, queue_sync_mode: webgpu.QueueSyncMode) !copy_runtime.CopyMetrics {
        return try copy_runtime.execute_copy(self, cmd, queue_sync_mode);
    }

    pub fn surface_create(self: *NativeMetalRuntime, cmd: model.SurfaceCreateCommand) !void {
        return try surface_runtime.create_surface(self, cmd);
    }

    pub fn surface_capabilities(self: *NativeMetalRuntime, cmd: model.SurfaceCapabilitiesCommand) !void {
        return try surface_runtime.surface_capabilities(self, cmd);
    }

    pub fn surface_configure(self: *NativeMetalRuntime, cmd: model.SurfaceConfigureCommand) !void {
        return try surface_runtime.configure_surface(self, cmd);
    }

    pub fn surface_acquire(self: *NativeMetalRuntime, cmd: model.SurfaceAcquireCommand) !void {
        return try surface_runtime.acquire_surface(self, cmd);
    }

    pub fn surface_present(self: *NativeMetalRuntime, cmd: model.SurfacePresentCommand) !u64 {
        return try surface_runtime.present_surface(self, cmd);
    }

    pub fn surface_unconfigure(self: *NativeMetalRuntime, cmd: model.SurfaceUnconfigureCommand) !void {
        return try surface_runtime.unconfigure_surface(self, cmd);
    }

    pub fn surface_release(self: *NativeMetalRuntime, cmd: model.SurfaceReleaseCommand) !void {
        return try surface_runtime.release_surface(self, cmd);
    }

    pub fn attach_canvas_layer(self: *NativeMetalRuntime, handle: u64, layer: ?*anyopaque) !void {
        return try surface_runtime.attach_canvas_layer(self, handle, layer);
    }

    pub fn update_surface_size(self: *NativeMetalRuntime, handle: u64, width: u32, height: u32, dpi_scale: f32) !void {
        return try surface_runtime.update_surface_size(self, handle, width, height, dpi_scale);
    }

    fn bootstrap(self: *NativeMetalRuntime) !void {
        self.device = metal_bridge_create_default_device() orelse return error.UnsupportedFeature;
        self.queue = metal_bridge_device_new_command_queue(self.device) orelse return error.InvalidState;
        self.shared_event = metal_bridge_device_new_shared_event(self.device);
        // Create a dedicated copy queue for overlapping blit work. Priority 0
        // (low) avoids contending with compute/render on the main queue. Silent
        // fallback to single-queue mode when the device cannot create a second queue.
        const COPY_QUEUE_PRIORITY: u32 = 0;
        self.copy_queue = metal_bridge_device_new_command_queue_with_priority(self.device, COPY_QUEUE_PRIORITY);
        self.has_device = true;
        self.timestamp_state.init_resources(self.device);
        if (builtin.os.tag == .macos) {
            if (HAS_PIPELINE_CACHE) {
                const cache_dir = self.kernel_root orelse "bench/kernels";
                const cache_ptr = metal_pipeline_cache.MetalPipelineCache.init(
                    self.allocator,
                    self.device,
                    cache_dir,
                ) catch null;
                self.pipeline_binary_cache = if (cache_ptr) |c| @ptrCast(c) else null;
                // Phase 3: run startup warmup to pre-load cached pipeline binaries.
                if (cache_ptr) |cache| {
                    const compute_keys = cache.run_warmup();
                    const ct0 = common_timing.now_ns();
                    var compute_warmed: u64 = 0;
                    for (compute_keys) |key| {
                        if (resource_runtime.ensure_kernel_pipeline(self, key) catch null) |_| {
                            compute_warmed +%= 1;
                        }
                    }
                    const compute_ns = common_timing.ns_delta(common_timing.now_ns(), ct0);
                    cache.finalize_warmup_telemetry(compute_warmed, compute_ns);
                }
            }
        }
    }

    fn release_deferred_releases(self: *NativeMetalRuntime) void {
        cleanup.release_deferred(&self.deferred_releases);
    }

    pub fn ensure_kernel_pipeline(self: *NativeMetalRuntime, kernel: []const u8) !?*anyopaque {
        return resource_runtime.ensure_kernel_pipeline(self, kernel);
    }

    pub fn ensure_compute_buffer(self: *NativeMetalRuntime, handle: u64, size: u64, initialize_buffers_on_create: bool) !?*anyopaque {
        return resource_runtime.ensure_compute_buffer(self, handle, size, initialize_buffers_on_create);
    }

    pub fn ensure_render_pipeline(self: *NativeMetalRuntime, fmt: u32) !void {
        return resource_runtime.ensure_render_pipeline(self, fmt);
    }

    fn ensure_render_target(self: *NativeMetalRuntime, width: u32, height: u32, fmt: u32) !void {
        return resource_runtime.ensure_render_target(self, width, height, fmt);
    }

    fn ensure_streaming_render_encoder(self: *NativeMetalRuntime) !void {
        return resource_runtime.ensure_streaming_render_encoder(self);
    }

    fn ensure_icb(self: *NativeMetalRuntime, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pl: c_int) !?*anyopaque {
        return resource_runtime.ensure_icb(self, draw_count, vertex_count, instance_count, redundant_pl);
    }

    fn ensure_copy_blit_encoder(self: *NativeMetalRuntime) !void {
        return copy_queue.ensure_copy_blit_encoder(self);
    }

    fn flush_copy_queue(self: *NativeMetalRuntime) void {
        return copy_queue.flush_copy_queue(self);
    }

    fn release_copy_queue_resources(self: *NativeMetalRuntime) void {
        return copy_queue.release_copy_queue_resources(self);
    }

    pub fn activate_gpu_timestamps(self: *NativeMetalRuntime) !void {
        return metal_gpu_timestamps.activate_gpu_timestamps(self);
    }

    pub fn gpu_timestamps_supported(self: *const NativeMetalRuntime) bool {
        return metal_gpu_timestamps.gpu_timestamps_supported(self);
    }
};

pub const BufferPool = metal_buffer_pool.BufferPool;

pub const release_ref = cleanup.release_ref;

pub fn pool_pop(pool: *BufferPool, size: usize) ?*anyopaque {
    return metal_buffer_pool.pool_pop(pool, size);
}

fn pool_push_or_release(pool: *BufferPool, allocator: std.mem.Allocator, size: usize, buf: ?*anyopaque) void {
    metal_buffer_pool.pool_push_or_release(pool, allocator, size, buf);
}
