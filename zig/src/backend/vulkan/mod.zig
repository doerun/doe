const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const backend_iface = @import("../backend_iface.zig");
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
    inner: webgpu.WebGPUBackend,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigVulkanBackend {
        var vulkan_profile = profile;
        vulkan_profile.api = .vulkan;

        const ptr = try allocator.create(ZigVulkanBackend);
        errdefer allocator.destroy(ptr);
        ptr.* = .{
            .allocator = allocator,
            .inner = try webgpu.WebGPUBackend.init(allocator, vulkan_profile, kernel_root),
        };
        try vulkan_instance.create_instance();
        try vulkan_adapter.select_adapter();
        try vulkan_device.create_device();
        try vulkan_proc_table.build_proc_table();
        try vulkan_proc_export.export_procs();
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
    self.inner.deinit();
    allocator.destroy(self);
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    switch (command) {
        .upload => {
            try vulkan_upload_path.upload_once();
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
            try vulkan_shader_manifest.emit();
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
            try vulkan_timing.operation_timing_ns();
            try vulkan_queue.wait_for_completion();
        },
    }
    return try self.inner.executeCommand(command);
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    self.inner.setUploadBehavior(mode, submit_every);
    vulkan_resource_table.lookup_resource() catch unreachable;
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    const self = cast(ctx);
    self.inner.setQueueWaitMode(mode);
    vulkan_queue.wait_for_completion() catch unreachable;
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    const self = cast(ctx);
    self.inner.setQueueSyncMode(mode);
    vulkan_queue.submit() catch unreachable;
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    const self = cast(ctx);
    self.inner.setGpuTimestampMode(mode);
    vulkan_timing.operation_timing_ns() catch unreachable;
}

fn flush_queue(ctx: *anyopaque) anyerror!u64 {
    const self = cast(ctx);
    _ = self;
    try vulkan_queue.wait_for_completion();
    return try self.inner.flushQueue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    try vulkan_upload_path.prewarm_upload_path(max_upload_bytes);
    return try self.inner.prewarmUploadPath(max_upload_bytes);
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
