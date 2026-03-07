const std = @import("std");
const common_timing = @import("../common/timing.zig");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");

// Metal on Apple Silicon supports large shared buffers up to device maxBufferLength.
// No artificial cap here — let allocation failure propagate as InvalidState.
const MAX_UPLOAD_BYTES: u64 = 0; // unused; retained for prewarm clamp only
const DEFAULT_KERNEL_ROOT: []const u8 = "bench/kernels";
const KERNEL_ENTRY_Z: [*:0]const u8 = "main_kernel";
const BRIDGE_ERROR_CAP: usize = 512;
const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;
const MAX_BINDING_SLOTS: usize = 32;
const SMALL_UPLOAD_CAPACITY: usize = 64 * 1024; // reuse staging pair for uploads <= 64KB

// Metal bridge C functions — symbols provided by metal_bridge.m.
extern fn metal_bridge_create_default_device() callconv(.c) ?*anyopaque;
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_device_new_command_queue(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_buffer_shared(device: ?*anyopaque, length: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_buffer_private(device: ?*anyopaque, length: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_buffer_contents(buffer: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_blit_copy(queue: ?*anyopaque, src: ?*anyopaque, dst: ?*anyopaque, length: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_blit_batch(queue: ?*anyopaque, srcs: ?[*]?*anyopaque, dsts: ?[*]?*anyopaque, lengths: ?[*]usize, count: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_begin_blit_encoding(queue: ?*anyopaque, encoder_out: *?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_blit_encoder_copy(encoder: ?*anyopaque, src: ?*anyopaque, dst: ?*anyopaque, byte_count: usize) callconv(.c) void;
extern fn metal_bridge_end_blit_encoding(encoder: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_command_buffer_commit(cmd_buf: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_command_buffer_wait_completed(cmd_buf: ?*anyopaque) callconv(.c) void;

// Streaming command buffer (shared across blit/render encoders)
extern fn metal_bridge_create_command_buffer(queue: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_cmd_buf_blit_encoder(cmd_buf: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_cmd_buf_encode_render_pass(cmd_buf: ?*anyopaque, pipeline: ?*anyopaque, target: ?*anyopaque, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pipeline: c_int, redundant_bindgroup: c_int) callconv(.c) void;
extern fn metal_bridge_cmd_buf_encode_icb_render_pass(cmd_buf: ?*anyopaque, pipeline: ?*anyopaque, icb: ?*anyopaque, target: ?*anyopaque, draw_count: u32) callconv(.c) void;
extern fn metal_bridge_cmd_buf_render_encoder(cmd_buf: ?*anyopaque, pipeline: ?*anyopaque, target: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_render_encoder_draw(encoder: ?*anyopaque, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pipeline: c_int, pipeline: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_render_encoder_execute_icb(encoder: ?*anyopaque, icb: ?*anyopaque, draw_count: u32) callconv(.c) void;
extern fn metal_bridge_render_encoder_end(encoder: ?*anyopaque) callconv(.c) void;

// Shared event (lightweight GPU fence)
extern fn metal_bridge_device_new_shared_event(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_command_buffer_encode_signal_event(cmd_buf: ?*anyopaque, event: ?*anyopaque, value: u64) callconv(.c) void;
extern fn metal_bridge_shared_event_wait(event: ?*anyopaque, value: u64) callconv(.c) void;

// Compute bridge
extern fn metal_bridge_device_new_library_msl(device: ?*anyopaque, src: [*]const u8, src_len: usize, error_buf: ?[*]u8, error_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_library_new_function(library: ?*anyopaque, name: [*:0]const u8) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_compute_pipeline(device: ?*anyopaque, function: ?*anyopaque, error_buf: ?[*]u8, error_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_compute_dispatch(queue: ?*anyopaque, pipeline: ?*anyopaque, buffers: ?[*]?*anyopaque, buffer_count: u32, x: u32, y: u32, z: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_compute_dispatch_batch(queue: ?*anyopaque, pipeline: ?*anyopaque, buffers: ?[*]?*anyopaque, buffer_count: u32, x: u32, y: u32, z: u32, repeat_count: u32) callconv(.c) ?*anyopaque;

// Texture bridge
extern fn metal_bridge_device_new_texture(device: ?*anyopaque, width: u32, height: u32, mip_levels: u32, pixel_format: u32, usage: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_texture_replace_region(texture: ?*anyopaque, width: u32, height: u32, data: *const anyopaque, bytes_per_row: u32, mip_level: u32) callconv(.c) void;
extern fn metal_bridge_texture_width(texture: ?*anyopaque) callconv(.c) u32;
extern fn metal_bridge_texture_height(texture: ?*anyopaque) callconv(.c) u32;
extern fn metal_bridge_texture_depth(texture: ?*anyopaque) callconv(.c) u32;
extern fn metal_bridge_texture_sample_count(texture: ?*anyopaque) callconv(.c) u32;

// Sampler bridge
extern fn metal_bridge_device_new_sampler(device: ?*anyopaque, min_filter: u32, mag_filter: u32, mipmap_filter: u32, addr_u: u32, addr_v: u32, addr_w: u32, lod_min: f32, lod_max: f32, max_aniso: u16) callconv(.c) ?*anyopaque;

// Render bridge
extern fn metal_bridge_device_new_render_pipeline(device: ?*anyopaque, pixel_format: u32, support_icb: c_int, error_buf: ?[*]u8, error_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_render_target(device: ?*anyopaque, width: u32, height: u32, pixel_format: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_encode_render_pass(queue: ?*anyopaque, pipeline: ?*anyopaque, target: ?*anyopaque, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pipeline: c_int, redundant_bindgroup: c_int) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_icb(device: ?*anyopaque, pipeline: ?*anyopaque, command_count: u32, redundant_pipeline: c_int) callconv(.c) ?*anyopaque;
extern fn metal_bridge_icb_encode_draws(icb: ?*anyopaque, pipeline: ?*anyopaque, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pipeline: c_int) callconv(.c) void;
extern fn metal_bridge_encode_icb_render_pass(queue: ?*anyopaque, pipeline: ?*anyopaque, icb: ?*anyopaque, target: ?*anyopaque, draw_count: u32) callconv(.c) ?*anyopaque;

// ============================================================
// Returned metric types
// ============================================================

pub const DispatchMetrics = struct {
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
    dispatch_count: u32,
};

pub const RenderMetrics = struct {
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
    draw_count: u32,
};

// ============================================================
// Internal data types
// ============================================================

const PendingUpload = struct {
    src_buffer: ?*anyopaque,
    dst_buffer: ?*anyopaque,
    byte_count: usize,
};

const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;

const KernelPipeline = struct {
    library: ?*anyopaque,
    pipeline: ?*anyopaque,
};

// ICB cache key — ICB encoding is fixed at creation time.
const IcbKey = struct {
    draw_count: u32,
    vertex_count: u32,
    instance_count: u32,
    redundant: bool,
};

// ============================================================
// NativeMetalRuntime
// ============================================================

pub const NativeMetalRuntime = struct {
    allocator: std.mem.Allocator,
    device: ?*anyopaque = null,
    queue: ?*anyopaque = null,
    has_device: bool = false,

    kernel_root: ?[]const u8 = null,

    has_deferred_submissions: bool = false,

    // Pipelined submission: commit without waiting, recycle on next flush.
    outstanding_cmd_buf: ?*anyopaque = null,
    in_flight_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},

    // Lightweight GPU fence via MTLSharedEvent (avoids kernel round-trip).
    shared_event: ?*anyopaque = null,
    fence_value: u64 = 0,

    // Streaming command buffer: shared across blit and render encoders.
    // Only one encoder active at a time. Barriers are no-ops (Metal
    // guarantees in-order execution within a command buffer).
    streaming_cmd_buf: ?*anyopaque = null,
    streaming_blit_encoder: ?*anyopaque = null,
    streaming_render_encoder: ?*anyopaque = null,
    streaming_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},

    // Buffer pool: reuse Metal buffers by size to avoid repeated allocations.
    shared_pool: std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque)) = .{},
    private_pool: std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque)) = .{},

    // Reused staging pair for small staged uploads.
    staging_src: ?*anyopaque = null,
    staging_dst: ?*anyopaque = null,
    staging_src_ptr: ?[*]u8 = null, // cached contents pointer

    // kernel base-name (owned) → KernelPipeline
    kernel_pipelines: std.StringHashMapUnmanaged(KernelPipeline) = .{},

    // resource_handle → MTLBuffer (compute bindings)
    compute_buffers: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},

    // handle → MTLTexture
    textures: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},

    // handle → MTLSamplerState
    samplers: std.AutoHashMapUnmanaged(u64, ?*anyopaque) = .{},

    // Render pipeline (one per pixel_format, shared across render-pass/ICB)
    render_pipeline: ?*anyopaque = null,
    render_pipeline_format: u32 = 0,

    // Render target cache
    render_target: ?*anyopaque = null,
    render_target_width: u32 = 0,
    render_target_height: u32 = 0,
    render_target_format: u32 = 0,

    // ICB cache
    cached_icb: ?*anyopaque = null,
    cached_icb_key: IcbKey = .{ .draw_count = 0, .vertex_count = 0, .instance_count = 0, .redundant = false },

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
        self.release_in_flight_uploads();
        self.in_flight_uploads.deinit(self.allocator);
        self.release_buffer_pool(&self.shared_pool);
        self.release_buffer_pool(&self.private_pool);
        if (self.staging_src) |s| { metal_bridge_release(s); self.staging_src = null; }
        if (self.staging_dst) |d| { metal_bridge_release(d); self.staging_dst = null; }
        self.release_kernel_pipelines();
        self.release_compute_buffers();
        self.release_textures();
        self.release_samplers();
        self.release_render_resources();
        if (self.shared_event) |e| { metal_bridge_release(e); self.shared_event = null; }
        if (self.queue) |q| { metal_bridge_release(q); self.queue = null; }
        if (self.device) |d| { metal_bridge_release(d); self.device = null; }
        self.has_device = false;
    }

    pub fn upload_bytes(self: *NativeMetalRuntime, bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        _ = mode;
        if (bytes == 0) return error.InvalidArgument;
        const len: usize = @intCast(bytes);
        const use_small_staging = len <= SMALL_UPLOAD_CAPACITY and
            self.staging_src != null and self.staging_dst != null and self.staging_src_ptr != null;
        const src = if (use_small_staging)
            self.staging_src.?
        else
            pool_pop(&self.shared_pool, len) orelse
                (metal_bridge_device_new_buffer_shared(self.device, len) orelse return error.InvalidState);
        const dst = if (use_small_staging)
            self.staging_dst.?
        else
            pool_pop(&self.private_pool, len) orelse
                (metal_bridge_device_new_buffer_private(self.device, len) orelse return error.InvalidState);
        if (use_small_staging) {
            @memset(self.staging_src_ptr.?[0..len], 0);
        } else {
            const raw = metal_bridge_buffer_contents(src) orelse return error.InvalidState;
            @memset(@as([*]u8, @ptrCast(raw))[0..len], 0);
        }

        // Close render encoder if transitioning from render to upload.
        if (self.streaming_render_encoder) |enc| {
            metal_bridge_render_encoder_end(enc);
            metal_bridge_release(enc);
            self.streaming_render_encoder = null;
        }

        // Open streaming blit encoder if not already open.
        if (self.streaming_blit_encoder == null) {
            if (self.streaming_cmd_buf == null) {
                var encoder: ?*anyopaque = null;
                self.streaming_cmd_buf = metal_bridge_begin_blit_encoding(self.queue, &encoder)
                    orelse return error.InvalidState;
                self.streaming_blit_encoder = encoder;
            } else {
                self.streaming_blit_encoder = metal_bridge_cmd_buf_blit_encoder(self.streaming_cmd_buf)
                    orelse return error.InvalidState;
            }
        }

        if (!use_small_staging) {
            try self.streaming_uploads.append(self.allocator, .{
                .src_buffer = src,
                .dst_buffer = dst,
                .byte_count = len,
            });
        }

        metal_bridge_blit_encoder_copy(self.streaming_blit_encoder, src, dst, len);
        self.has_deferred_submissions = true;
    }

    pub fn flush_queue(self: *NativeMetalRuntime) !u64 {
        if (!self.has_device) return 0;

        const has_streaming = self.streaming_cmd_buf != null;
        if (!has_streaming and !self.has_deferred_submissions) return 0;

        const start_ns = common_timing.now_ns();

        // Wait for any previous outstanding submission.
        self.wait_outstanding();

        // Primary path: close streaming encoders and commit.
        if (has_streaming) {
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
            self.fence_value +%= 1;
            if (self.shared_event) |ev| {
                metal_bridge_command_buffer_encode_signal_event(cmd_buf, ev, self.fence_value);
            }
            metal_bridge_command_buffer_commit(cmd_buf);

            // Wait synchronously — flush_queue is called before render/dispatch.
            if (self.shared_event) |ev| {
                metal_bridge_shared_event_wait(ev, self.fence_value);
            } else {
                metal_bridge_command_buffer_wait_completed(cmd_buf);
            }
            metal_bridge_release(cmd_buf);
            self.streaming_cmd_buf = null;

            // Recycle streaming uploads now that GPU is done.
            for (self.streaming_uploads.items) |item| {
                pool_push_or_release(&self.shared_pool, self.allocator, item.byte_count, item.src_buffer);
                pool_push_or_release(&self.private_pool, self.allocator, item.byte_count, item.dst_buffer);
            }
            self.streaming_uploads.clearRetainingCapacity();
        } else if (self.has_deferred_submissions) {
            // Deferred-only path (e.g. tiny uploads via shared-memory memset).
            // No command buffer to commit, but do a GPU fence round-trip so
            // the measured timing scope is comparable with Dawn's submit+wait.
            self.fence_value +%= 1;
            if (self.shared_event) |ev| {
                const empty_cmd = metal_bridge_create_command_buffer(self.queue)
                    orelse return error.InvalidState;
                metal_bridge_command_buffer_encode_signal_event(empty_cmd, ev, self.fence_value);
                metal_bridge_command_buffer_commit(empty_cmd);
                metal_bridge_shared_event_wait(ev, self.fence_value);
                metal_bridge_release(empty_cmd);
            }
        }

        self.has_deferred_submissions = false;
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    fn wait_outstanding(self: *NativeMetalRuntime) void {
        if (self.outstanding_cmd_buf) |cb| {
            // Use shared event for lightweight wait (avoids kernel round-trip).
            if (self.shared_event) |ev| {
                metal_bridge_shared_event_wait(ev, self.fence_value);
            } else {
                metal_bridge_command_buffer_wait_completed(cb);
            }
            metal_bridge_release(cb);
            self.outstanding_cmd_buf = null;
        }
        // Recycle in-flight buffers now that GPU is done.
        for (self.in_flight_uploads.items) |item| {
            pool_push_or_release(&self.shared_pool, self.allocator, item.byte_count, item.src_buffer);
            pool_push_or_release(&self.private_pool, self.allocator, item.byte_count, item.dst_buffer);
        }
        self.in_flight_uploads.clearRetainingCapacity();
    }

    pub fn barrier(self: *NativeMetalRuntime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        _ = queue_wait_mode;
        // With streaming encoder: barriers are no-ops for upload sequences.
        // Metal guarantees in-order execution within a command buffer, so
        // all preceding blit copies complete before subsequent ones start.
        if (self.streaming_cmd_buf != null) return 0;

        // No streaming encoder — wait for any outstanding pipelined submission.
        const start_ns = common_timing.now_ns();
        if (self.has_deferred_submissions) {
            _ = try self.flush_queue();
        }
        self.wait_outstanding();
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn prewarm_upload_path(self: *NativeMetalRuntime, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        if (max_upload_bytes == 0) return;
        // Pre-allocate staging pair for small uploads.
        if (self.staging_src == null and max_upload_bytes <= SMALL_UPLOAD_CAPACITY) {
            const cap = SMALL_UPLOAD_CAPACITY;
            self.staging_src = metal_bridge_device_new_buffer_shared(self.device, cap);
            self.staging_dst = metal_bridge_device_new_buffer_private(self.device, cap);
            if (self.staging_src) |s| {
                self.staging_src_ptr = @ptrCast(metal_bridge_buffer_contents(s));
            }
        }
        try self.upload_bytes(max_upload_bytes, mode);
        _ = try self.flush_queue();
    }

    // --------------------------------------------------------
    // Kernel dispatch
    // --------------------------------------------------------

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
        // Setup: pipeline compile, buffer allocation, warmup dispatches.
        const setup_start = common_timing.now_ns();
        const pipeline = try self.ensure_kernel_pipeline(kernel);

        var buf_slots: [MAX_BINDING_SLOTS]?*anyopaque = [_]?*anyopaque{null} ** MAX_BINDING_SLOTS;
        var slot_count: u32 = 0;

        if (bindings) |bs| {
            for (bs) |b| {
                if (b.resource_kind != .buffer) continue;
                if (b.binding >= MAX_BINDING_SLOTS) continue;
                buf_slots[b.binding] = try self.ensure_compute_buffer(b.resource_handle, b.buffer_size);
                if (b.binding + 1 > slot_count) slot_count = @intCast(b.binding + 1);
            }
        }

        const run_count: u32 = if (repeat == 0) 1 else repeat;
        const buf_ptr: ?[*]?*anyopaque = if (slot_count > 0) &buf_slots else null;

        if (warmup > 0) {
            const wcb = metal_bridge_encode_compute_dispatch_batch(
                self.queue, pipeline, buf_ptr, slot_count, x, y, z, warmup,
            ) orelse return error.InvalidState;
            metal_bridge_command_buffer_commit(wcb);
            metal_bridge_command_buffer_wait_completed(wcb);
            metal_bridge_release(wcb);
        }
        const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

        // Timed run: batch all repeat dispatches into one command buffer.
        const t_enc_start = common_timing.now_ns();
        const cmd_buf = metal_bridge_encode_compute_dispatch_batch(
            self.queue, pipeline, buf_ptr, slot_count, x, y, z, run_count,
        ) orelse return error.InvalidState;
        const encode_ns = common_timing.ns_delta(common_timing.now_ns(), t_enc_start);

        metal_bridge_command_buffer_commit(cmd_buf);
        const t_sub_start = common_timing.now_ns();
        metal_bridge_command_buffer_wait_completed(cmd_buf);
        const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), t_sub_start);
        metal_bridge_release(cmd_buf);

        return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns, .dispatch_count = run_count };
    }

    // --------------------------------------------------------
    // Sampler lifecycle
    // --------------------------------------------------------

    pub fn sampler_create(self: *NativeMetalRuntime, cmd: model.SamplerCreateCommand) !void {
        const h = metal_bridge_device_new_sampler(
            self.device,
            cmd.min_filter, cmd.mag_filter, cmd.mipmap_filter,
            cmd.address_mode_u, cmd.address_mode_v, cmd.address_mode_w,
            cmd.lod_min_clamp, cmd.lod_max_clamp, cmd.max_anisotropy,
        ) orelse return error.InvalidState;
        const gop = try self.samplers.getOrPut(self.allocator, cmd.handle);
        if (gop.found_existing) metal_bridge_release(gop.value_ptr.*);
        gop.value_ptr.* = h;
    }

    pub fn sampler_destroy(self: *NativeMetalRuntime, cmd: model.SamplerDestroyCommand) !void {
        if (self.samplers.fetchRemove(cmd.handle)) |e| metal_bridge_release(e.value);
    }

    // --------------------------------------------------------
    // Texture lifecycle
    // --------------------------------------------------------

    pub fn texture_write(self: *NativeMetalRuntime, cmd: model.TextureWriteCommand) !void {
        const t = &cmd.texture;
        const mip_w = @max(t.width >> @intCast(t.mip_level), 1);
        const mip_h = @max(t.height >> @intCast(t.mip_level), 1);

        const gop = try self.textures.getOrPut(self.allocator, t.handle);
        if (!gop.found_existing or gop.value_ptr.* == null) {
            const mip_count: u32 = if (t.mip_level > 0) t.mip_level + 1 else 1;
            const tex = metal_bridge_device_new_texture(
                self.device, t.width, t.height, mip_count, t.format, @intCast(t.usage),
            ) orelse return error.InvalidState;
            if (gop.found_existing and gop.value_ptr.* != null) metal_bridge_release(gop.value_ptr.*);
            gop.value_ptr.* = tex;
        }

        if (cmd.data.len > 0) {
            metal_bridge_texture_replace_region(
                gop.value_ptr.*, mip_w, mip_h,
                cmd.data.ptr, t.bytes_per_row, t.mip_level,
            );
        }
    }

    pub fn texture_query(self: *NativeMetalRuntime, cmd: model.TextureQueryCommand) !void {
        const tex = self.textures.get(cmd.handle) orelse return error.InvalidState;
        if (cmd.expected_width) |w| if (metal_bridge_texture_width(tex) != w) return error.InvalidState;
        if (cmd.expected_height) |h| if (metal_bridge_texture_height(tex) != h) return error.InvalidState;
        if (cmd.expected_depth_or_array_layers) |d| {
            if (d != 1 and metal_bridge_texture_depth(tex) != d) return error.InvalidState;
        }
        if (cmd.expected_sample_count) |sc| if (metal_bridge_texture_sample_count(tex) != sc) return error.InvalidState;
    }

    pub fn texture_destroy(self: *NativeMetalRuntime, cmd: model.TextureDestroyCommand) !void {
        if (self.textures.fetchRemove(cmd.handle)) |e| metal_bridge_release(e.value);
    }

    // --------------------------------------------------------
    // Render draw
    // --------------------------------------------------------

    pub fn render_draw(self: *NativeMetalRuntime, cmd: model.RenderDrawCommand) !RenderMetrics {
        const fmt = cmd.target_format;
        const is_bundle = cmd.encode_mode == .render_bundle;
        const red_pl: c_int = if (cmd.pipeline_mode == .redundant) 1 else 0;

        // Setup: pipeline compile, texture alloc, ICB creation, encoder creation.
        const setup_start = common_timing.now_ns();
        try self.ensure_render_pipeline(fmt);
        try self.ensure_render_target(cmd.target_width, cmd.target_height, fmt);
        const icb = if (is_bundle) try self.ensure_icb(cmd.draw_count, cmd.vertex_count, cmd.instance_count, red_pl) else null;
        try self.ensure_streaming_render_encoder();
        const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

        // Encode: draw/execute calls.
        const encode_start = common_timing.now_ns();
        if (is_bundle) {
            metal_bridge_render_encoder_execute_icb(
                self.streaming_render_encoder, icb, cmd.draw_count,
            );
        } else {
            metal_bridge_render_encoder_draw(
                self.streaming_render_encoder,
                cmd.draw_count, cmd.vertex_count, cmd.instance_count,
                red_pl, self.render_pipeline,
            );
        }
        const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

        // Submit+wait: commit command buffer and wait for GPU completion.
        const submit_wait_ns = try self.flush_queue();

        return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns, .draw_count = cmd.draw_count };
    }

    // --------------------------------------------------------
    // Private helpers
    // --------------------------------------------------------

    fn bootstrap(self: *NativeMetalRuntime) !void {
        self.device = metal_bridge_create_default_device() orelse return error.UnsupportedFeature;
        self.queue = metal_bridge_device_new_command_queue(self.device) orelse return error.InvalidState;
        self.shared_event = metal_bridge_device_new_shared_event(self.device);
        self.has_device = true;
    }

    fn release_in_flight_uploads(self: *NativeMetalRuntime) void {
        for (self.in_flight_uploads.items) |item| {
            metal_bridge_release(item.src_buffer);
            metal_bridge_release(item.dst_buffer);
        }
        self.in_flight_uploads.clearRetainingCapacity();
    }

    fn release_buffer_pool(self: *NativeMetalRuntime, pool: *std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque))) void {
        var it = pool.valueIterator();
        while (it.next()) |list| {
            for (list.items) |buf| metal_bridge_release(buf);
            var m = list.*;
            m.deinit(self.allocator);
        }
        pool.deinit(self.allocator);
    }

    fn release_kernel_pipelines(self: *NativeMetalRuntime) void {
        var it = self.kernel_pipelines.iterator();
        while (it.next()) |e| {
            self.allocator.free(e.key_ptr.*);
            metal_bridge_release(e.value_ptr.library);
            metal_bridge_release(e.value_ptr.pipeline);
        }
        self.kernel_pipelines.deinit(self.allocator);
    }

    fn release_compute_buffers(self: *NativeMetalRuntime) void {
        var it = self.compute_buffers.valueIterator();
        while (it.next()) |v| metal_bridge_release(v.*);
        self.compute_buffers.deinit(self.allocator);
    }

    fn release_textures(self: *NativeMetalRuntime) void {
        var it = self.textures.valueIterator();
        while (it.next()) |v| metal_bridge_release(v.*);
        self.textures.deinit(self.allocator);
    }

    fn release_samplers(self: *NativeMetalRuntime) void {
        var it = self.samplers.valueIterator();
        while (it.next()) |v| metal_bridge_release(v.*);
        self.samplers.deinit(self.allocator);
    }

    fn release_render_resources(self: *NativeMetalRuntime) void {
        if (self.cached_icb) |icb| { metal_bridge_release(icb); self.cached_icb = null; }
        if (self.render_pipeline) |p| { metal_bridge_release(p); self.render_pipeline = null; }
        if (self.render_target) |t| { metal_bridge_release(t); self.render_target = null; }
        self.render_pipeline_format = 0;
    }

    pub fn ensure_kernel_pipeline(self: *NativeMetalRuntime, kernel: []const u8) !?*anyopaque {
        const base = strip_extension(kernel);
        if (self.kernel_pipelines.get(base)) |kp| return kp.pipeline;

        const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
        const path = try std.fmt.allocPrint(self.allocator, "{s}/{s}.metal", .{ root, base });
        defer self.allocator.free(path);

        const source = std.fs.cwd().readFileAlloc(self.allocator, path, MAX_KERNEL_SOURCE_BYTES) catch {
            return error.ShaderToolchainUnavailable;
        };
        defer self.allocator.free(source);

        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        const lib = metal_bridge_device_new_library_msl(
            self.device, source.ptr, source.len, &err_buf, BRIDGE_ERROR_CAP,
        ) orelse return error.ShaderCompileFailed;
        errdefer metal_bridge_release(lib);

        const func = metal_bridge_library_new_function(lib, KERNEL_ENTRY_Z) orelse return error.ShaderCompileFailed;
        errdefer metal_bridge_release(func);

        const pso = metal_bridge_device_new_compute_pipeline(
            self.device, func, &err_buf, BRIDGE_ERROR_CAP,
        ) orelse return error.ShaderCompileFailed;
        metal_bridge_release(func);

        const key = try self.allocator.dupe(u8, base);
        errdefer self.allocator.free(key);
        try self.kernel_pipelines.put(self.allocator, key, .{ .library = lib, .pipeline = pso });
        return pso;
    }

    pub fn ensure_compute_buffer(self: *NativeMetalRuntime, handle: u64, size: u64) !?*anyopaque {
        if (self.compute_buffers.get(handle)) |b| return b;
        const buf = metal_bridge_device_new_buffer_shared(self.device, @intCast(size)) orelse return error.InvalidState;
        try self.compute_buffers.put(self.allocator, handle, buf);
        return buf;
    }

    pub fn ensure_render_pipeline(self: *NativeMetalRuntime, fmt: u32) !void {
        if (self.render_pipeline != null and self.render_pipeline_format == fmt) return;
        if (self.render_pipeline) |p| metal_bridge_release(p);
        if (self.cached_icb) |icb| { metal_bridge_release(icb); self.cached_icb = null; }
        var err_buf: [BRIDGE_ERROR_CAP]u8 = undefined;
        self.render_pipeline = metal_bridge_device_new_render_pipeline(
            self.device, fmt, 1, &err_buf, BRIDGE_ERROR_CAP,
        ) orelse return error.ShaderCompileFailed;
        self.render_pipeline_format = fmt;
    }

    fn ensure_render_target(self: *NativeMetalRuntime, w: u32, h: u32, fmt: u32) !void {
        if (self.render_target != null and
            self.render_target_width == w and
            self.render_target_height == h and
            self.render_target_format == fmt) return;
        if (self.render_target) |t| metal_bridge_release(t);
        self.render_target = metal_bridge_device_new_render_target(self.device, w, h, fmt) orelse return error.InvalidState;
        self.render_target_width = w;
        self.render_target_height = h;
        self.render_target_format = fmt;
    }

    /// Ensure a render encoder is open on the streaming command buffer.
    /// Creates the command buffer and encoder if needed. Closes blit encoder
    /// if transitioning from upload to render. This is a setup cost (outside timing).
    fn ensure_streaming_render_encoder(self: *NativeMetalRuntime) !void {
        if (self.streaming_render_encoder != null) return;

        // Close blit encoder if open (transitioning from upload to render).
        if (self.streaming_blit_encoder) |enc| {
            metal_bridge_end_blit_encoding(enc);
            self.streaming_blit_encoder = null;
        }

        // Ensure streaming command buffer exists.
        if (self.streaming_cmd_buf == null) {
            self.streaming_cmd_buf = metal_bridge_create_command_buffer(self.queue)
                orelse return error.InvalidState;
        }

        self.streaming_render_encoder = metal_bridge_cmd_buf_render_encoder(
            self.streaming_cmd_buf, self.render_pipeline, self.render_target,
        ) orelse return error.InvalidState;
    }

    fn ensure_icb(self: *NativeMetalRuntime, draw_count: u32, vertex_count: u32, instance_count: u32, redundant_pl: c_int) !?*anyopaque {
        const key = IcbKey{
            .draw_count = draw_count,
            .vertex_count = vertex_count,
            .instance_count = instance_count,
            .redundant = redundant_pl != 0,
        };
        if (self.cached_icb != null and std.meta.eql(self.cached_icb_key, key)) return self.cached_icb;
        if (self.cached_icb) |icb| metal_bridge_release(icb);
        const icb = metal_bridge_device_new_icb(self.device, self.render_pipeline, draw_count, redundant_pl) orelse return error.InvalidState;
        metal_bridge_icb_encode_draws(icb, self.render_pipeline, draw_count, vertex_count, instance_count, redundant_pl);
        self.cached_icb = icb;
        self.cached_icb_key = key;
        return icb;
    }
};

fn strip_extension(name: []const u8) []const u8 {
    const suffixes = [_][]const u8{ ".wgsl", ".spv", ".metal" };
    for (suffixes) |sfx| {
        if (std.mem.endsWith(u8, name, sfx)) return name[0 .. name.len - sfx.len];
    }
    return name;
}

const BufferPool = std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(?*anyopaque));

fn pool_pop(pool: *BufferPool, size: usize) ?*anyopaque {
    if (pool.getPtr(size)) |list| {
        if (list.items.len > 0) return list.pop() orelse null;
    }
    return null;
}

fn pool_push_or_release(pool: *BufferPool, allocator: std.mem.Allocator, size: usize, buf: ?*anyopaque) void {
    const entry = pool.getOrPut(allocator, size) catch {
        metal_bridge_release(buf);
        return;
    };
    if (!entry.found_existing) {
        entry.value_ptr.* = .{};
    }
    if (entry.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        metal_bridge_release(buf);
        return;
    }
    entry.value_ptr.append(allocator, buf) catch {
        metal_bridge_release(buf);
    };
}
