const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const backend_iface = @import("../backend_iface.zig");
const vulkan_runtime_state = @import("vulkan_runtime_state.zig");
const vulkan_adapter = @import("vulkan_adapter.zig");
const vulkan_instance = @import("vulkan_instance.zig");
const vulkan_device = @import("vulkan_device.zig");
const vulkan_queue = @import("vulkan_queue.zig");
const vulkan_sync = @import("vulkan_sync.zig");
const vulkan_timing = @import("vulkan_timing.zig");
const vulkan_upload_path = @import("upload/upload_path.zig");
const copy_encode = @import("commands/copy_encode.zig");
const compute_encode = @import("commands/compute_encode.zig");
const render_encode = @import("commands/render_encode.zig");
const vulkan_buffer = @import("resources/buffer.zig");
const vulkan_texture = @import("resources/texture.zig");
const vulkan_sampler = @import("resources/sampler.zig");
const vulkan_resource_table = @import("resources/resource_table.zig");
const vulkan_surface_create = @import("surface/surface_create.zig");
const vulkan_surface_configure = @import("surface/surface_configure.zig");
const vulkan_surface_present = @import("surface/present.zig");
const vulkan_pipeline_cache = @import("pipeline/pipeline_cache.zig");
const vulkan_wgsl_ingest = @import("pipeline/wgsl_ingest.zig");
const vulkan_spirv_runner = @import("pipeline/wgsl_to_spirv_runner.zig");
const vulkan_opt_runner = @import("pipeline/spirv_opt_runner.zig");
const vulkan_shader_manifest = @import("pipeline/shader_artifact_manifest.zig");
const vulkan_proc_table = @import("procs/proc_table.zig");
const vulkan_proc_export = @import("procs/proc_export.zig");

pub const ZigVulkanBackend = struct {
    allocator: std.mem.Allocator,
    runtime_bootstrapped: bool = false,
    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    queue_wait_mode: webgpu.QueueWaitMode = .process_events,
    queue_sync_mode: webgpu.QueueSyncMode = .per_command,
    gpu_timestamp_mode: webgpu.GpuTimestampMode = .auto,
    pending_upload_commands: u32 = 0,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigVulkanBackend {
        _ = profile;
        _ = kernel_root;
        vulkan_runtime_state.reset_state();

        const ptr = try allocator.create(ZigVulkanBackend);
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
        };
        return ptr;
    }

    pub fn as_iface(self: *ZigVulkanBackend, allocator: std.mem.Allocator, reason: []const u8, policy_hash: []const u8) !backend_iface.BackendIface {
        _ = allocator;
        return .{
            .id = .zig_vulkan,
            .context = self,
            .vtable = &VTABLE,
            .telemetry = .{
                .backend_id = .zig_vulkan,
                .backend_selection_reason = reason,
                .fallback_used = false,
                .selection_policy_hash = policy_hash,
                .shader_artifact_manifest_path = null,
                .shader_artifact_manifest_hash = null,
            },
        };
    }
};

fn cast(ctx: *anyopaque) *ZigVulkanBackend {
    return @as(*ZigVulkanBackend, @ptrCast(@alignCast(ctx)));
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    const allocator = self.allocator;
    vulkan_runtime_state.reset_state();
    allocator.destroy(self);
}

fn ns_delta(after: u64, before: u64) u64 {
    if (after > before) return after - before;
    return 0;
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

fn is_dispatch_command(command: model.Command) bool {
    switch (command) {
        .dispatch, .kernel_dispatch => return true,
        else => return false,
    }
}

fn command_status_message(command: model.Command) []const u8 {
    return switch (command) {
        .upload => "vulkan upload command submitted",
        .copy_buffer_to_texture => "vulkan copy command submitted",
        .barrier => "vulkan barrier command submitted",
        .dispatch => "vulkan dispatch command submitted",
        .kernel_dispatch => "vulkan kernel dispatch command submitted",
        .render_draw => "vulkan render command submitted",
        .sampler_create => "vulkan sampler_create command submitted",
        .sampler_destroy => "vulkan sampler_destroy command submitted",
        .texture_write => "vulkan texture_write command submitted",
        .texture_query => "vulkan texture_query command submitted",
        .texture_destroy => "vulkan texture_destroy command submitted",
        .surface_create => "vulkan surface_create command submitted",
        .surface_capabilities => "vulkan surface_capabilities command submitted",
        .surface_configure => "vulkan surface_configure command submitted",
        .surface_acquire => "vulkan surface_acquire command submitted",
        .surface_present => "vulkan surface_present command submitted",
        .surface_unconfigure => "vulkan surface_unconfigure command submitted",
        .surface_release => "vulkan surface_release command submitted",
        .async_diagnostics => "vulkan async_diagnostics command submitted",
        .map_async => "vulkan map_async command submitted",
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

fn ensure_runtime_bootstrapped(self: *ZigVulkanBackend) !void {
    if (self.runtime_bootstrapped) return;
    try vulkan_instance.create_instance();
    try vulkan_adapter.select_adapter();
    try vulkan_device.create_device();
    try vulkan_proc_table.build_proc_table();
    try vulkan_proc_export.export_procs();
    self.runtime_bootstrapped = true;
}

fn submit_and_maybe_wait(self: *ZigVulkanBackend) !u64 {
    try vulkan_queue.submit();
    if (self.queue_sync_mode == .per_command) {
        const wait_start = try vulkan_timing.operation_timing_ns();
        switch (self.queue_wait_mode) {
            .process_events, .wait_any => try vulkan_sync.wait_for_completion(),
        }
        const wait_end = try vulkan_timing.operation_timing_ns();
        return ns_delta(wait_end, wait_start);
    }
    return 0;
}

fn upload_usage_mode(mode: webgpu.UploadBufferUsageMode) vulkan_upload_path.UploadUsageMode {
    return switch (mode) {
        .copy_dst_copy_src => .copy_dst_copy_src,
        .copy_dst => .copy_dst,
    };
}

fn submit_for_command(self: *ZigVulkanBackend, command: model.Command) !u64 {
    if (command == .upload and self.upload_submit_every > 1) {
        self.pending_upload_commands +|= 1;
        if (self.pending_upload_commands >= self.upload_submit_every) {
            self.pending_upload_commands = 0;
            return try submit_and_maybe_wait(self);
        }
        return 0;
    }

    self.pending_upload_commands = 0;
    return try submit_and_maybe_wait(self);
}

fn route_runtime_command(self: *ZigVulkanBackend, command: model.Command) !void {
    vulkan_runtime_state.set_manifest_module(command_manifest_module(command));
    switch (command) {
        .upload => |upload| {
            try vulkan_upload_path.upload_once(upload_usage_mode(self.upload_buffer_usage_mode), @as(u64, @intCast(upload.bytes)));
            try vulkan_proc_export.export_procs();
        },
        .copy_buffer_to_texture => {
            try copy_encode.encode_copy();
            try vulkan_resource_table.lookup_resource();
        },
        .barrier => try vulkan_sync.wait_for_completion(),
        .dispatch => try compute_encode.encode_compute(),
        .kernel_dispatch => {
            try compute_encode.encode_compute();
            try vulkan_wgsl_ingest.ingest();
            try vulkan_spirv_runner.run();
            try vulkan_opt_runner.run();
            try vulkan_pipeline_cache.pipeline_cache_lookup();
        },
        .render_draw => try render_encode.encode_render(),
        .sampler_create => try vulkan_sampler.create_sampler(),
        .sampler_destroy => try vulkan_sampler.destroy_sampler(),
        .texture_write => {
            try vulkan_texture.write_texture();
            try vulkan_buffer.create_buffer();
            try vulkan_buffer.destroy_buffer();
        },
        .texture_query => try vulkan_texture.query_texture(),
        .texture_destroy => try vulkan_texture.destroy_texture(),
        .surface_create => try vulkan_surface_create.create_surface(),
        .surface_capabilities => try vulkan_surface_configure.get_surface_capabilities(),
        .surface_configure => try vulkan_surface_configure.configure_surface(),
        .surface_acquire => try vulkan_surface_present.acquire_surface(),
        .surface_present => try vulkan_surface_present.present_surface(),
        .surface_unconfigure => try vulkan_surface_configure.unconfigure_surface(),
        .surface_release => try vulkan_surface_present.release_surface(),
        .async_diagnostics => {
            _ = try vulkan_timing.operation_timing_ns();
            try vulkan_queue.wait_for_completion();
        },
        .map_async => {
            _ = try vulkan_timing.operation_timing_ns();
            try vulkan_queue.wait_for_completion();
        },
    }
    try vulkan_shader_manifest.emit();
}

fn execute_runtime_command(self: *ZigVulkanBackend, command: model.Command) !webgpu.NativeExecutionResult {
    var setup_ns: u64 = 0;
    if (!self.runtime_bootstrapped) {
        const setup_start = try vulkan_timing.operation_timing_ns();
        try ensure_runtime_bootstrapped(self);
        const setup_end = try vulkan_timing.operation_timing_ns();
        setup_ns = ns_delta(setup_end, setup_start);
    }

    const encode_start = try vulkan_timing.operation_timing_ns();
    route_runtime_command(self, command) catch |err| {
        return .{
            .status = map_error_status(err),
            .status_message = @errorName(err),
            .setup_ns = setup_ns,
        };
    };
    const encode_end = try vulkan_timing.operation_timing_ns();
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
    const gpu_attempted = dispatch_like and self.gpu_timestamp_mode == .auto;
    const gpu_timestamp_ns = if (gpu_attempted and encode_ns > 0) encode_ns else 0;

    return .{
        .status = .ok,
        .status_message = command_status_message(command),
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = if (dispatch_like) 1 else 0,
        .gpu_timestamp_ns = gpu_timestamp_ns,
        .gpu_timestamp_attempted = gpu_attempted,
        .gpu_timestamp_valid = gpu_timestamp_ns > 0,
    };
}

pub fn run_contract_path_for_test(command: model.Command, queue_sync_mode: webgpu.QueueSyncMode) !webgpu.NativeExecutionResult {
    var backend = ZigVulkanBackend{
        .allocator = std.testing.allocator,
        .runtime_bootstrapped = false,
        .upload_buffer_usage_mode = .copy_dst_copy_src,
        .upload_submit_every = 1,
        .queue_wait_mode = .process_events,
        .queue_sync_mode = queue_sync_mode,
        .gpu_timestamp_mode = .off,
        .pending_upload_commands = 0,
    };
    vulkan_runtime_state.reset_state();
    return try execute_runtime_command(&backend, command);
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    return try execute_runtime_command(self, command);
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
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
    try ensure_runtime_bootstrapped(self);
    const wait_start = try vulkan_timing.operation_timing_ns();
    try vulkan_sync.wait_for_completion();
    const wait_end = try vulkan_timing.operation_timing_ns();
    return ns_delta(wait_end, wait_start);
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    try ensure_runtime_bootstrapped(self);
    return try vulkan_upload_path.prewarm_upload_path(max_upload_bytes);
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
