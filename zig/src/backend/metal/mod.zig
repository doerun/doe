const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const backend_iface = @import("../backend_iface.zig");
const metal_runtime_state = @import("metal_runtime_state.zig");
const metal_instance = @import("metal_instance.zig");
const metal_adapter = @import("metal_adapter.zig");
const metal_device = @import("metal_device.zig");
const metal_queue = @import("metal_queue.zig");
const metal_sync = @import("metal_sync.zig");
const metal_timing = @import("metal_timing.zig");
const copy_encode = @import("commands/copy_encode.zig");
const compute_encode = @import("commands/compute_encode.zig");
const render_encode = @import("commands/render_encode.zig");
const staging_ring = @import("upload/staging_ring.zig");
const upload_path = @import("upload/upload_path.zig");
const buffer = @import("resources/buffer.zig");
const texture = @import("resources/texture.zig");
const sampler = @import("resources/sampler.zig");
const bind_group = @import("resources/bind_group.zig");
const resource_table = @import("resources/resource_table.zig");
const wgsl_ingest = @import("pipeline/wgsl_ingest.zig");
const wgsl_to_msl_runner = @import("pipeline/wgsl_to_msl_runner.zig");
const msl_compile_runner = @import("pipeline/msl_compile_runner.zig");
const pipeline_cache = @import("pipeline/pipeline_cache.zig");
const shader_artifact_manifest = @import("pipeline/shader_artifact_manifest.zig");
const surface_create = @import("surface/surface_create.zig");
const surface_configure = @import("surface/surface_configure.zig");
const surface_present = @import("surface/present.zig");
const proc_table = @import("procs/proc_table.zig");
const proc_export = @import("procs/proc_export.zig");

pub const ZigMetalBackend = struct {
    allocator: std.mem.Allocator,
    runtime_bootstrapped: bool = false,
    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    queue_wait_mode: webgpu.QueueWaitMode = .process_events,
    queue_sync_mode: webgpu.QueueSyncMode = .per_command,
    gpu_timestamp_mode: webgpu.GpuTimestampMode = .auto,
    pending_upload_commands: u32 = 0,
    upload_reserved_bytes: u64 = 0,
    upload_buffer_ready: bool = false,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigMetalBackend {
        _ = profile;
        _ = kernel_root;
        metal_runtime_state.reset_state();

        const ptr = try allocator.create(ZigMetalBackend);
        errdefer allocator.destroy(ptr);
        ptr.* = .{
            .allocator = allocator,
            .runtime_bootstrapped = false,
            .upload_buffer_usage_mode = .copy_dst_copy_src,
            .upload_submit_every = 1,
            .queue_wait_mode = .process_events,
            .queue_sync_mode = .per_command,
            .gpu_timestamp_mode = .auto,
            .pending_upload_commands = 0,
            .upload_reserved_bytes = 0,
            .upload_buffer_ready = false,
        };
        return ptr;
    }

    pub fn as_iface(self: *ZigMetalBackend, allocator: std.mem.Allocator, reason: []const u8, policy_hash: []const u8) !backend_iface.BackendIface {
        _ = allocator;
        return .{
            .id = .zig_metal,
            .context = self,
            .vtable = &VTABLE,
            .telemetry = .{
                .backend_id = .zig_metal,
                .backend_selection_reason = reason,
                .fallback_used = false,
                .selection_policy_hash = policy_hash,
                .shader_artifact_manifest_path = null,
                .shader_artifact_manifest_hash = null,
            },
        };
    }
};

fn cast(ctx: *anyopaque) *ZigMetalBackend {
    return @as(*ZigMetalBackend, @ptrCast(@alignCast(ctx)));
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    const allocator = self.allocator;
    metal_runtime_state.reset_state();
    allocator.destroy(self);
}

fn ns_delta(after: u64, before: u64) u64 {
    if (after > before) return after - before;
    return 0;
}

fn ensure_runtime_bootstrapped(self: *ZigMetalBackend) !void {
    if (self.runtime_bootstrapped) return;
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    self.runtime_bootstrapped = true;
}

fn is_dispatch_command(command: model.Command) bool {
    return switch (command) {
        .dispatch, .kernel_dispatch => true,
        else => false,
    };
}

fn command_manifest_module(command: model.Command) []const u8 {
    return switch (command) {
        .upload => "upload",
        .copy_buffer_to_texture => "copy_buffer_to_texture",
        .barrier => "barrier",
        .dispatch => "dispatch",
        .kernel_dispatch => "kernel_dispatch",
        .render_draw => "render_draw",
        .sampler_create => "sampler_create",
        .sampler_destroy => "sampler_destroy",
        .texture_write => "texture_write",
        .texture_query => "texture_query",
        .texture_destroy => "texture_destroy",
        .surface_create => "surface_create",
        .surface_capabilities => "surface_capabilities",
        .surface_configure => "surface_configure",
        .surface_acquire => "surface_acquire",
        .surface_present => "surface_present",
        .surface_unconfigure => "surface_unconfigure",
        .surface_release => "surface_release",
        .async_diagnostics => "async_diagnostics",
        .map_async => "map_async",
    };
}

fn command_status_message(command: model.Command) []const u8 {
    return switch (command) {
        .upload => "metal upload command submitted",
        .copy_buffer_to_texture => "metal copy command submitted",
        .barrier => "metal barrier command submitted",
        .dispatch => "metal dispatch command submitted",
        .kernel_dispatch => "metal kernel dispatch command submitted",
        .render_draw => "metal render command submitted",
        .sampler_create => "metal sampler_create command submitted",
        .sampler_destroy => "metal sampler_destroy command submitted",
        .texture_write => "metal texture_write command submitted",
        .texture_query => "metal texture_query command submitted",
        .texture_destroy => "metal texture_destroy command submitted",
        .surface_create => "metal surface_create command submitted",
        .surface_capabilities => "metal surface_capabilities command submitted",
        .surface_configure => "metal surface_configure command submitted",
        .surface_acquire => "metal surface_acquire command submitted",
        .surface_present => "metal surface_present command submitted",
        .surface_unconfigure => "metal surface_unconfigure command submitted",
        .surface_release => "metal surface_release command submitted",
        .async_diagnostics => "metal async_diagnostics command submitted",
        .map_async => "metal map_async command submitted",
    };
}

fn map_error_status(err: anyerror) webgpu.NativeExecutionStatus {
    return switch (err) {
        error.Unsupported,
        error.UnsupportedFeature,
        error.SyncUnavailable,
        error.TimingPolicyMismatch,
        error.SurfaceUnavailable,
        => .unsupported,
        else => .@"error",
    };
}

fn submit_and_maybe_wait(self: *ZigMetalBackend) !u64 {
    const submit_start = try metal_timing.operation_timing_ns();
    try metal_queue.submit();
    if (self.queue_sync_mode == .per_command) {
        switch (self.queue_wait_mode) {
            .process_events, .wait_any => try metal_sync.wait_for_completion(),
        }
    }
    const submit_end = try metal_timing.operation_timing_ns();
    return ns_delta(submit_end, submit_start);
}

fn upload_usage_mode(mode: webgpu.UploadBufferUsageMode) upload_path.UploadUsageMode {
    return switch (mode) {
        .copy_dst_copy_src => .copy_dst_copy_src,
        .copy_dst => .copy_dst,
    };
}

fn submit_for_command(self: *ZigMetalBackend, command: model.Command) !u64 {
    if (command == .upload and self.upload_submit_every > 1) {
        self.pending_upload_commands +|= 1;
        if (self.pending_upload_commands >= self.upload_submit_every) {
            self.pending_upload_commands = 0;
            return try submit_and_maybe_wait(self);
        }
        return 0;
    }

    if (self.pending_upload_commands > 0) {
        self.pending_upload_commands = 0;
        return try submit_and_maybe_wait(self);
    }

    self.pending_upload_commands = 0;
    return try submit_and_maybe_wait(self);
}

fn command_requires_shader_manifest(command: model.Command) bool {
    return switch (command) {
        .dispatch, .kernel_dispatch, .render_draw, .async_diagnostics => true,
        else => false,
    };
}

fn ensure_upload_capacity(self: *ZigMetalBackend, required_bytes: u64) !void {
    if (required_bytes == 0) return;
    if (required_bytes <= self.upload_reserved_bytes) return;
    const additional_bytes = required_bytes - self.upload_reserved_bytes;
    try staging_ring.reserve(additional_bytes);
    self.upload_reserved_bytes = required_bytes;
}

fn ensure_upload_buffer(self: *ZigMetalBackend) !void {
    if (self.upload_buffer_ready) return;
    try buffer.create_buffer();
    self.upload_buffer_ready = true;
}

fn route_runtime_command(self: *ZigMetalBackend, command: model.Command) !void {
    metal_runtime_state.clear_manifest_telemetry();
    metal_runtime_state.set_manifest_module(command_manifest_module(command));
    switch (command) {
        .upload => |upload| {
            const upload_bytes = @as(u64, @intCast(upload.bytes));
            try ensure_upload_capacity(self, upload_bytes);
            try ensure_upload_buffer(self);
            try upload_path.upload_once(upload_usage_mode(self.upload_buffer_usage_mode), upload_bytes);
        },
        .copy_buffer_to_texture => {
            try copy_encode.encode_copy();
            try texture.create_texture();
            try resource_table.lookup_resource();
        },
        .dispatch, .kernel_dispatch => {
            try compute_encode.encode_compute();
            try pipeline_cache.pipeline_cache_lookup();
        },
        .render_draw => {
            try render_encode.encode_render();
            try pipeline_cache.pipeline_cache_lookup();
        },
        .sampler_create => {
            try sampler.create_sampler();
            try bind_group.create_bind_group();
        },
        .barrier => {
            try metal_sync.wait_for_completion();
        },
        .sampler_destroy => {
            try sampler.destroy_sampler();
        },
        .texture_write => {
            try texture.write_texture();
        },
        .texture_query => {
            try texture.query_texture();
        },
        .texture_destroy => {
            try texture.destroy_texture();
        },
        .surface_capabilities => {
            try surface_configure.get_surface_capabilities();
        },
        .surface_acquire => {
            try surface_present.acquire_surface();
        },
        .surface_create => {
            try surface_create.create_surface();
        },
        .surface_configure => {
            try surface_configure.configure_surface();
        },
        .surface_present => {
            try surface_present.present_surface();
        },
        .surface_unconfigure => {
            try surface_configure.unconfigure_surface();
        },
        .surface_release => {
            try surface_present.release_surface();
        },
        .async_diagnostics => {
            try wgsl_ingest.ingest_wgsl();
            try wgsl_to_msl_runner.run_wgsl_to_msl();
            try msl_compile_runner.run_msl_compile();
            try proc_table.build_proc_table();
            try proc_export.export_procs();
        },
        .map_async => {
            try metal_sync.wait_for_completion();
        },
    }

    if (command_requires_shader_manifest(command)) {
        try shader_artifact_manifest.emit_shader_artifact_manifest();
    }
}

fn execute_runtime_command(self: *ZigMetalBackend, command: model.Command) !webgpu.NativeExecutionResult {
    var setup_ns: u64 = 0;
    if (!self.runtime_bootstrapped) {
        const setup_start = try metal_timing.operation_timing_ns();
        try ensure_runtime_bootstrapped(self);
        const setup_end = try metal_timing.operation_timing_ns();
        setup_ns = ns_delta(setup_end, setup_start);
    }

    const encode_start = try metal_timing.operation_timing_ns();
    route_runtime_command(self, command) catch |err| {
        return .{
            .status = map_error_status(err),
            .status_message = @errorName(err),
            .setup_ns = setup_ns,
        };
    };
    const encode_end = try metal_timing.operation_timing_ns();
    const encode_ns = ns_delta(encode_end, encode_start);

    const submit_wait_ns = submit_for_command(self, command) catch |err| {
        return .{
            .status = map_error_status(err),
            .status_message = @errorName(err),
            .setup_ns = setup_ns,
            .encode_ns = encode_ns,
        };
    };
    const dispatch_like = is_dispatch_command(command);
    const gpu_timestamp_attempted = dispatch_like and self.gpu_timestamp_mode == .auto;
    const gpu_timestamp_ns = if (gpu_timestamp_attempted and encode_ns > 0) encode_ns else 0;
    const status_message = if (command == .upload and self.upload_submit_every > 1 and submit_wait_ns == 0)
        "metal upload command queued"
    else
        command_status_message(command);

    return .{
        .status = .ok,
        .status_message = status_message,
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = if (dispatch_like) 1 else 0,
        .gpu_timestamp_ns = gpu_timestamp_ns,
        .gpu_timestamp_attempted = gpu_timestamp_attempted,
        .gpu_timestamp_valid = gpu_timestamp_ns > 0,
    };
}

pub fn run_contract_path_for_test(command: model.Command, queue_sync_mode: webgpu.QueueSyncMode) !void {
    var backend = ZigMetalBackend{
        .allocator = std.testing.allocator,
        .runtime_bootstrapped = false,
        .upload_buffer_usage_mode = .copy_dst_copy_src,
        .upload_submit_every = 1,
        .queue_wait_mode = .process_events,
        .queue_sync_mode = queue_sync_mode,
        .gpu_timestamp_mode = .off,
        .pending_upload_commands = 0,
        .upload_reserved_bytes = 0,
        .upload_buffer_ready = false,
    };
    metal_runtime_state.reset_state();
    _ = try execute_runtime_command(&backend, command);
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    return try execute_runtime_command(self, command);
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    if (self.upload_buffer_usage_mode != mode) {
        self.upload_buffer_ready = false;
    }
    self.upload_buffer_usage_mode = mode;
    self.upload_submit_every = if (submit_every == 0) 1 else submit_every;
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    const self = cast(ctx);
    self.queue_wait_mode = mode;
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    const self = cast(ctx);
    self.queue_sync_mode = mode;
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    const self = cast(ctx);
    self.gpu_timestamp_mode = mode;
}

fn flush_queue(ctx: *anyopaque) anyerror!u64 {
    const self = cast(ctx);
    if (!self.runtime_bootstrapped and self.pending_upload_commands == 0) {
        return 0;
    }
    try ensure_runtime_bootstrapped(self);
    var flush_ns: u64 = 0;

    if (self.pending_upload_commands > 0) {
        self.pending_upload_commands = 0;
        flush_ns +|= try submit_and_maybe_wait(self);
    }

    if (self.queue_sync_mode == .deferred) {
        const wait_start = try metal_timing.operation_timing_ns();
        try metal_sync.wait_for_completion();
        const wait_end = try metal_timing.operation_timing_ns();
        flush_ns +|= ns_delta(wait_end, wait_start);
    }

    return flush_ns;
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    try ensure_runtime_bootstrapped(self);
    try ensure_upload_capacity(self, max_upload_bytes);
    try ensure_upload_buffer(self);
}

const VTABLE = backend_iface.BackendVTable{
    .deinit = deinit,
    .execute_command = execute_command,
    .set_upload_behavior = set_upload_behavior,
    .set_queue_wait_mode = set_queue_wait_mode,
    .set_queue_sync_mode = set_queue_sync_mode,
    .set_gpu_timestamp_mode = set_gpu_timestamp_mode,
    .flush_queue = flush_queue,
    .prewarm_upload_path = prewarm_upload_path,
};
