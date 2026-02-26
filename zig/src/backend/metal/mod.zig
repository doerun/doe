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
    inner: webgpu.WebGPUBackend,
    runtime_bootstrapped: bool = false,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigMetalBackend {
        var metal_profile = profile;
        metal_profile.api = .metal;

        const ptr = try allocator.create(ZigMetalBackend);
        errdefer allocator.destroy(ptr);
        ptr.* = .{
            .allocator = allocator,
            .inner = try webgpu.WebGPUBackend.init(allocator, metal_profile, kernel_root),
            .runtime_bootstrapped = false,
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
    self.inner.deinit();
    metal_runtime_state.reset_state();
    allocator.destroy(self);
}

fn ensure_runtime_bootstrapped(self: *ZigMetalBackend) !void {
    if (self.runtime_bootstrapped) return;
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    self.runtime_bootstrapped = true;
}

fn track_runtime_command(self: *ZigMetalBackend, command: model.Command) !void {
    try ensure_runtime_bootstrapped(self);
    switch (command) {
        .upload => {
            try staging_ring.reserve();
            try upload_path.upload_once();
            try buffer.create_buffer();
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
        .sampler_destroy, .texture_query, .texture_destroy, .surface_capabilities, .surface_acquire, .surface_unconfigure, .surface_release, .barrier => {
            try resource_table.lookup_resource();
        },
        .texture_write => {
            try texture.create_texture();
            try resource_table.lookup_resource();
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
        .async_diagnostics => {
            try wgsl_ingest.ingest_wgsl();
            try wgsl_to_msl_runner.run_wgsl_to_msl();
            try msl_compile_runner.run_msl_compile();
            try shader_artifact_manifest.emit_shader_artifact_manifest();
            try proc_table.build_proc_table();
            try proc_export.export_procs();
        },
    }
    try metal_queue.submit();
    if (self.inner.queue_sync_mode == .per_command) {
        try metal_sync.wait_for_completion();
    }
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    try track_runtime_command(self, command);
    return try self.inner.executeCommand(command);
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    self.inner.setUploadBehavior(mode, submit_every);
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    const self = cast(ctx);
    self.inner.setQueueWaitMode(mode);
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    const self = cast(ctx);
    self.inner.setQueueSyncMode(mode);
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    const self = cast(ctx);
    self.inner.setGpuTimestampMode(mode);
}

fn flush_queue(ctx: *anyopaque) anyerror!u64 {
    const self = cast(ctx);
    return try self.inner.flushQueue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    try self.inner.prewarmUploadPath(max_upload_bytes);
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
