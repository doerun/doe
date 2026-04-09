const std = @import("std");
const builtin = @import("builtin");
const model_commands = @import("../../model_commands.zig");
const model_profile = @import("../../model_profile.zig");
const model_resource_types = @import("../../model_resource_types.zig");
const model_compute_types = @import("../../model_compute_types.zig");
const model_render_types = @import("../../model_render_types.zig");
const model_texture_types = @import("../../model_texture_types.zig");
const model_surface_control_types = @import("../../model_surface_control_types.zig");
const model_async_types = @import("../../model_async_types.zig");
const webgpu = @import("../runtime_types.zig");
const backend_iface = @import("../backend_iface.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const command_info = @import("../common/command_info.zig");
const command_requirements = @import("../common/command_requirements.zig");
const capabilities = @import("../common/capabilities.zig");
const artifact_meta = @import("../common/artifact_meta.zig");
const artifact_policy = @import("../common/artifact_policy.zig");
const hash_utils = @import("../common/hash_utils.zig");
const artifact_emit = @import("artifact_emit.zig");
const host_plan_artifact = @import("metal_host_plan_artifact.zig");
const native_runtime = @import("metal_native_runtime.zig");
const backend_policy = @import("../backend_policy.zig");
extern fn metal_bridge_buffer_contents(buffer: ?*anyopaque) callconv(.c) ?[*]u8;

const MANIFEST_PATH_CAPACITY: usize = 256;
const HASH_HEX_SIZE: usize = hash_utils.SHA256_HEX_SIZE;
const MANIFEST_MODULE_CAPACITY: usize = 64;
const MANIFEST_STATUS_CODE_CAPACITY: usize = 256;
const STATUS_MESSAGE_BYTES: usize = 256;
const BOOTSTRAP_MANIFEST_MODULE = "bootstrap";
const BOOTSTRAP_MANIFEST_STATUS_CODE = "backend_initialized";

const model = struct {
    pub const AsyncDiagnosticsCommand = model_async_types.AsyncDiagnosticsCommand;
    pub const BufferWriteCommand = model_resource_types.BufferWriteCommand;
    pub const Command = model_commands.Command;
    pub const CopyCommand = model_resource_types.CopyCommand;
    pub const DeviceProfile = model_profile.DeviceProfile;
    pub const DispatchCommand = model_compute_types.DispatchCommand;
    pub const DispatchIndirectCommand = model_compute_types.DispatchIndirectCommand;
    pub const KernelBinding = model_compute_types.KernelBinding;
    pub const KernelDispatchCommand = model_compute_types.KernelDispatchCommand;
    pub const MapAsyncCommand = model_async_types.MapAsyncCommand;
    pub const RenderDrawCommand = model_render_types.RenderDrawCommand;
    pub const SamplerCreateCommand = model_render_types.SamplerCreateCommand;
    pub const SamplerDestroyCommand = model_render_types.SamplerDestroyCommand;
    pub const SurfaceAcquireCommand = model_surface_control_types.SurfaceAcquireCommand;
    pub const SurfaceCapabilitiesCommand = model_surface_control_types.SurfaceCapabilitiesCommand;
    pub const SurfaceConfigureCommand = model_surface_control_types.SurfaceConfigureCommand;
    pub const SurfaceCreateCommand = model_surface_control_types.SurfaceCreateCommand;
    pub const SurfacePresentCommand = model_surface_control_types.SurfacePresentCommand;
    pub const SurfaceReleaseCommand = model_surface_control_types.SurfaceReleaseCommand;
    pub const SurfaceUnconfigureCommand = model_surface_control_types.SurfaceUnconfigureCommand;
    pub const TextureDestroyCommand = model_texture_types.TextureDestroyCommand;
    pub const TextureQueryCommand = model_texture_types.TextureQueryCommand;
    pub const TextureWriteCommand = model_texture_types.TextureWriteCommand;
    pub const UploadCommand = model_resource_types.UploadCommand;
};

pub const ZigMetalBackend = struct {
    allocator: std.mem.Allocator,
    runtime: ?native_runtime.NativeMetalRuntime = null,
    kernel_root_owned: ?[]u8 = null,
    upload_path_policy: backend_policy.UploadPathPolicy = .allow_mapped_shortcuts,

    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    queue_wait_mode: webgpu.QueueWaitMode = .process_events,
    queue_sync_mode: webgpu.QueueSyncMode = .per_command,
    gpu_timestamp_mode: webgpu.GpuTimestampMode = .auto,
    pending_upload_commands: u32 = 0,

    capability_set: capabilities.CapabilitySet,
    status_message_storage: [STATUS_MESSAGE_BYTES]u8 = [_]u8{0} ** STATUS_MESSAGE_BYTES,
    status_message_len: usize = 0,

    manifest_emit_count: u64 = 0,
    manifest_path_storage: [MANIFEST_PATH_CAPACITY]u8 = std.mem.zeroes([MANIFEST_PATH_CAPACITY]u8),
    manifest_path_len: usize = 0,
    manifest_hash_storage: [HASH_HEX_SIZE]u8 = std.mem.zeroes([HASH_HEX_SIZE]u8),
    manifest_hash_len: usize = 0,
    host_plan_emit_count: u64 = 0,
    host_plan_path_storage: [MANIFEST_PATH_CAPACITY]u8 = std.mem.zeroes([MANIFEST_PATH_CAPACITY]u8),
    host_plan_path_len: usize = 0,
    host_plan_hash_storage: [HASH_HEX_SIZE]u8 = std.mem.zeroes([HASH_HEX_SIZE]u8),
    host_plan_hash_len: usize = 0,
    last_manifest_meta: ?artifact_meta.ArtifactMeta = null,
    last_manifest_module_storage: [MANIFEST_MODULE_CAPACITY]u8 = std.mem.zeroes([MANIFEST_MODULE_CAPACITY]u8),
    last_manifest_module_len: usize = 0,
    last_manifest_status_storage: [MANIFEST_STATUS_CODE_CAPACITY]u8 = std.mem.zeroes([MANIFEST_STATUS_CODE_CAPACITY]u8),
    last_manifest_status_len: usize = 0,
    pending_artifact_write: bool = false,
    pending_artifact_module: []const u8 = "",
    pending_artifact_meta: artifact_meta.ArtifactMeta = undefined,
    pending_artifact_status_storage: [MANIFEST_STATUS_CODE_CAPACITY]u8 = std.mem.zeroes([MANIFEST_STATUS_CODE_CAPACITY]u8),
    pending_artifact_status_len: usize = 0,

    pub fn init(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
    ) !*ZigMetalBackend {
        return init_with_selection_policy(
            allocator,
            profile,
            kernel_root,
            backend_policy.default_policy_for_lane(.metal_doe_app),
        );
    }

    pub fn init_with_selection_policy(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        selection_policy: backend_policy.SelectionPolicy,
    ) !*ZigMetalBackend {
        if (profile.api != .metal) return common_errors.BackendNativeError.UnsupportedFeature;
        if (builtin.os.tag != .macos) return common_errors.BackendNativeError.UnsupportedFeature;

        const owned_root = if (kernel_root) |root| try allocator.dupe(u8, root) else null;
        errdefer if (owned_root) |r| allocator.free(r);

        const ptr = try allocator.create(ZigMetalBackend);
        errdefer allocator.destroy(ptr);

        var runtime = try native_runtime.NativeMetalRuntime.init(allocator, owned_root);
        errdefer runtime.deinit();

        ptr.* = .{
            .allocator = allocator,
            .runtime = runtime,
            .kernel_root_owned = owned_root,
            .upload_path_policy = selection_policy.upload_path_policy,
            .upload_buffer_usage_mode = .copy_dst_copy_src,
            .upload_submit_every = 1,
            .queue_wait_mode = .process_events,
            .queue_sync_mode = .per_command,
            .gpu_timestamp_mode = .auto,
            .pending_upload_commands = 0,
            .capability_set = native_capability_set(),
            .status_message_storage = [_]u8{0} ** STATUS_MESSAGE_BYTES,
            .status_message_len = 0,
            .manifest_emit_count = 0,
            .manifest_path_storage = std.mem.zeroes([MANIFEST_PATH_CAPACITY]u8),
            .manifest_path_len = 0,
            .manifest_hash_storage = std.mem.zeroes([HASH_HEX_SIZE]u8),
            .manifest_hash_len = 0,
            .host_plan_emit_count = 0,
            .host_plan_path_storage = std.mem.zeroes([MANIFEST_PATH_CAPACITY]u8),
            .host_plan_path_len = 0,
            .host_plan_hash_storage = std.mem.zeroes([HASH_HEX_SIZE]u8),
            .host_plan_hash_len = 0,
            .last_manifest_meta = null,
            .last_manifest_module_storage = std.mem.zeroes([MANIFEST_MODULE_CAPACITY]u8),
            .last_manifest_module_len = 0,
            .last_manifest_status_storage = std.mem.zeroes([MANIFEST_STATUS_CODE_CAPACITY]u8),
            .last_manifest_status_len = 0,
            .pending_artifact_write = false,
            .pending_artifact_module = "",
            .pending_artifact_meta = undefined,
            .pending_artifact_status_storage = std.mem.zeroes([MANIFEST_STATUS_CODE_CAPACITY]u8),
            .pending_artifact_status_len = 0,
        };

        ptr.emit_shader_artifact_manifest_for_signature(
            BOOTSTRAP_MANIFEST_MODULE,
            artifact_meta.classify(.native_metal, false, false),
            BOOTSTRAP_MANIFEST_STATUS_CODE,
        ) catch {};

        return ptr;
    }

    pub fn as_iface(
        self: *ZigMetalBackend,
        allocator: std.mem.Allocator,
        reason: []const u8,
        policy_hash: []const u8,
    ) !backend_iface.BackendIface {
        _ = allocator;
        return .{
            .id = .doe_metal,
            .context = self,
            .vtable = &VTABLE,
            .telemetry = .{
                .backend_id = .doe_metal,
                .backend_selection_reason = reason,
                .fallback_used = false,
                .selection_policy_hash = policy_hash,
                .shader_artifact_manifest_path = null,
                .shader_artifact_manifest_hash = null,
                .host_plan_artifact_path = null,
                .host_plan_artifact_hash = null,
                .adapter_ordinal = null,
                .queue_family_index = null,
                .present_capable = null,
            },
        };
    }

    fn manifest_path(self: *const ZigMetalBackend) ?[]const u8 {
        return artifact_emit.manifest_path(self);
    }

    fn manifest_hash(self: *const ZigMetalBackend) ?[]const u8 {
        return artifact_emit.manifest_hash(self);
    }

    fn host_plan_path(self: *const ZigMetalBackend) ?[]const u8 {
        return host_plan_artifact.hostPlanPath(self);
    }

    fn host_plan_hash(self: *const ZigMetalBackend) ?[]const u8 {
        return host_plan_artifact.hostPlanHash(self);
    }

    fn flush_pending_artifact(self: *ZigMetalBackend) void {
        artifact_emit.flush_pending_artifact(self);
    }

    fn emit_shader_artifact_manifest_for_signature(
        self: *ZigMetalBackend,
        module: []const u8,
        meta: artifact_meta.ArtifactMeta,
        status_code: []const u8,
    ) common_errors.BackendNativeError!void {
        return artifact_emit.emit_shader_artifact_manifest_for_signature(self, module, meta, status_code);
    }
};

fn native_capability_set() capabilities.CapabilitySet {
    var set = capabilities.CapabilitySet{};
    set.declare_all(&.{
        .compute_dispatch,
        .compute_dispatch_indirect,
        .buffer_upload,
        .buffer_write,
        .buffer_copy,
        .barrier_sync,
        .kernel_dispatch,
        .sampler_lifecycle,
        .texture_write,
        .texture_query,
        .texture_destroy,
        .surface_lifecycle,
        .surface_present,
        .render_draw,
        .render_pass,
        .indirect_draw,
        .indexed_indirect_draw,
        .async_pipeline_diagnostics,
        .async_capability_introspection,
        .async_resource_table_immediates,
        .async_lifecycle_refcount,
        .async_pixel_local_storage,
        .map_async,
        .gpu_timestamps,
        .timestamp_inside_passes,
    });
    return set;
}

fn write_status(self: *ZigMetalBackend, comptime fmt: []const u8, args: anytype) []const u8 {
    const rendered = std.fmt.bufPrint(&self.status_message_storage, fmt, args) catch "status_format_error";
    self.status_message_len = rendered.len;
    return self.status_message_storage[0..self.status_message_len];
}

fn cast(ctx: *anyopaque) *ZigMetalBackend {
    return @as(*ZigMetalBackend, @ptrCast(@alignCast(ctx)));
}

pub fn manifest_path_from_context(ctx: *anyopaque) ?[]const u8 {
    const self = cast(ctx);
    self.flush_pending_artifact();
    return self.manifest_path();
}

pub fn manifest_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).manifest_hash();
}

pub fn host_plan_path_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).host_plan_path();
}

pub fn host_plan_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).host_plan_hash();
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    const allocator = self.allocator;
    if (self.runtime) |*rt| {
        rt.deinit();
        self.runtime = null;
    }
    if (self.kernel_root_owned) |r| {
        allocator.free(r);
        self.kernel_root_owned = null;
    }
    allocator.destroy(self);
}

fn get_runtime(self: *ZigMetalBackend) *native_runtime.NativeMetalRuntime {
    return &self.runtime.?;
}

fn ok_result(setup_ns: u64, encode_ns: u64, submit_wait_ns: u64, dispatch_count: u32) webgpu.NativeExecutionResult {
    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = dispatch_count,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn gpu_timestamps_wanted(self: *const ZigMetalBackend) bool {
    return self.gpu_timestamp_mode != .off;
}

fn check_timestamp_requirement(self: *ZigMetalBackend) !void {
    if (self.gpu_timestamp_mode != .require) return;
    const rt = get_runtime(self);
    if (!rt.gpu_timestamps_supported()) return error.UnsupportedFeature;
}

fn execute_upload(self: *ZigMetalBackend, upload: model.UploadCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);

    if (gpu_timestamps_wanted(self)) rt.activate_gpu_timestamps() catch {};

    const setup_start = common_timing.now_ns();
    try rt.upload_bytes(@as(u64, @intCast(upload.bytes)), self.upload_buffer_usage_mode);
    const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

    self.pending_upload_commands +|= 1;

    var submit_wait_ns: u64 = 0;
    var gpu_ts_ns: u64 = 0;
    var gpu_ts_attempted = false;
    var gpu_ts_valid = false;
    if (self.queue_sync_mode == .per_command and self.pending_upload_commands >= self.upload_submit_every) {
        const flush = try rt.flush_queue_timed();
        submit_wait_ns = flush.submit_wait_ns;
        gpu_ts_ns = flush.gpu_elapsed_ns;
        gpu_ts_attempted = flush.gpu_timestamps_attempted;
        gpu_ts_valid = flush.gpu_timestamps_valid;
        self.pending_upload_commands = 0;
    }

    var r = ok_result(setup_ns, 0, submit_wait_ns, 0);
    r.gpu_timestamp_ns = gpu_ts_ns;
    r.gpu_timestamp_attempted = gpu_ts_attempted;
    r.gpu_timestamp_valid = gpu_ts_valid;
    return r;
}

fn execute_buffer_write(self: *ZigMetalBackend, cmd: model.BufferWriteCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const setup_start = common_timing.now_ns();
    if (self.upload_path_policy == .staged_copy_only) {
        try rt.stage_buffer_write_bytes(cmd.handle, cmd.offset, cmd.buffer_size, std.mem.sliceAsBytes(cmd.data));
    } else {
        try rt.write_buffer(cmd);
    }
    const setup_end = common_timing.now_ns();

    self.pending_upload_commands +|= 1;
    var submit_wait_ns: u64 = 0;
    if (self.queue_sync_mode == .per_command and self.pending_upload_commands >= self.upload_submit_every) {
        submit_wait_ns = try rt.flush_queue();
        self.pending_upload_commands = 0;
    } else {
        rt.has_deferred_submissions = true;
    }

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = common_timing.ns_delta(setup_end, setup_start),
        .encode_ns = 0,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = 0,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn execute_buffer_write_bytes(self: *ZigMetalBackend, handle: u64, offset: u64, buffer_size: u64, data: []const u8) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const setup_start = common_timing.now_ns();
    if (self.upload_path_policy == .staged_copy_only) {
        try rt.stage_buffer_write_bytes(handle, offset, buffer_size, data);
    } else {
        try rt.write_buffer_bytes(handle, offset, buffer_size, data);
    }
    const setup_end = common_timing.now_ns();

    self.pending_upload_commands +|= 1;
    var submit_wait_ns: u64 = 0;
    if (self.queue_sync_mode == .per_command and self.pending_upload_commands >= self.upload_submit_every) {
        submit_wait_ns = try rt.flush_queue();
        self.pending_upload_commands = 0;
    } else {
        rt.has_deferred_submissions = true;
    }

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = common_timing.ns_delta(setup_end, setup_start),
        .encode_ns = 0,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = 0,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn execute_barrier(self: *ZigMetalBackend) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    // barrier is a control operation, not a GPU workload — no timestamp
    // activation. Any pending streaming timestamps are flushed by barrier's
    // internal flush_queue call (timestamps resolve on that commit cycle).
    const submit_wait_ns = try rt.barrier(self.queue_wait_mode, self.queue_sync_mode);
    return ok_result(0, 0, submit_wait_ns, 0);
}

fn execute_dispatch(self: *ZigMetalBackend, dispatch: model.DispatchCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const metrics = try rt.run_dispatch(dispatch.x, dispatch.y, dispatch.z, self.queue_sync_mode);
    return ok_result(0, metrics.encode_ns, metrics.submit_wait_ns, metrics.dispatch_count);
}

fn execute_dispatch_indirect(self: *ZigMetalBackend, dispatch: model.DispatchIndirectCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const metrics = try rt.run_dispatch_indirect(dispatch.x, dispatch.y, dispatch.z, self.queue_sync_mode);
    return ok_result(0, metrics.encode_ns, metrics.submit_wait_ns, metrics.dispatch_count);
}

fn execute_kernel_dispatch(self: *ZigMetalBackend, kd: model.KernelDispatchCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const want_ts = gpu_timestamps_wanted(self);
    const result = try rt.run_kernel_dispatch_timed(
        kd.kernel,
        kd.entry_point,
        kd.x,
        kd.y,
        kd.z,
        kd.repeat,
        kd.warmup_dispatch_count,
        kd.initialize_buffers_on_create,
        kd.bindings,
        want_ts,
    );
    var r = ok_result(result.metrics.setup_ns, result.metrics.encode_ns, result.metrics.submit_wait_ns, result.metrics.dispatch_count);
    r.gpu_timestamp_ns = result.gpu_elapsed_ns;
    r.gpu_timestamp_attempted = result.gpu_timestamps_attempted;
    r.gpu_timestamp_valid = result.gpu_timestamps_valid;
    host_plan_artifact.emitForKernelDispatch(self, kd) catch {};
    return r;
}

fn execute_copy(self: *ZigMetalBackend, cmd: model.CopyCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    if (gpu_timestamps_wanted(self)) rt.activate_gpu_timestamps() catch {};
    const metrics = try rt.copy_command(cmd, self.queue_sync_mode);
    var r = ok_result(metrics.setup_ns, metrics.encode_ns, metrics.submit_wait_ns, 0);
    r.gpu_timestamp_ns = metrics.gpu_elapsed_ns;
    r.gpu_timestamp_attempted = metrics.gpu_timestamps_attempted;
    r.gpu_timestamp_valid = metrics.gpu_timestamps_valid;
    return r;
}

fn execute_sampler_create(self: *ZigMetalBackend, cmd: model.SamplerCreateCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.sampler_create(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_sampler_destroy(self: *ZigMetalBackend, cmd: model.SamplerDestroyCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.sampler_destroy(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_texture_write(self: *ZigMetalBackend, cmd: model.TextureWriteCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.texture_write(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_texture_query(self: *ZigMetalBackend, cmd: model.TextureQueryCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.texture_query(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_texture_destroy(self: *ZigMetalBackend, cmd: model.TextureDestroyCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.texture_destroy(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_surface_create(self: *ZigMetalBackend, cmd: model.SurfaceCreateCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.surface_create(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_surface_capabilities(self: *ZigMetalBackend, cmd: model.SurfaceCapabilitiesCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.surface_capabilities(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_surface_configure(self: *ZigMetalBackend, cmd: model.SurfaceConfigureCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.surface_configure(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_surface_acquire(self: *ZigMetalBackend, cmd: model.SurfaceAcquireCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.surface_acquire(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_surface_present(self: *ZigMetalBackend, cmd: model.SurfacePresentCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const submit_wait_ns = try rt.surface_present(cmd);
    return ok_result(0, 0, submit_wait_ns, 0);
}

fn execute_surface_unconfigure(self: *ZigMetalBackend, cmd: model.SurfaceUnconfigureCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.surface_unconfigure(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_surface_release(self: *ZigMetalBackend, cmd: model.SurfaceReleaseCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.surface_release(cmd);
    return ok_result(0, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_render_draw(self: *ZigMetalBackend, cmd: model.RenderDrawCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    if (gpu_timestamps_wanted(self)) rt.activate_gpu_timestamps() catch {};
    const metrics = try rt.render_draw(cmd, self.queue_sync_mode);
    var r = ok_result(metrics.setup_ns, metrics.encode_ns, metrics.submit_wait_ns, metrics.draw_count);
    r.gpu_timestamp_ns = metrics.gpu_elapsed_ns;
    r.gpu_timestamp_attempted = metrics.gpu_timestamps_attempted;
    r.gpu_timestamp_valid = metrics.gpu_timestamps_valid;
    return r;
}

fn execute_async_diagnostics(self: *ZigMetalBackend, cmd: model.AsyncDiagnosticsCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const setup_start = common_timing.now_ns();
    switch (cmd.mode) {
        .pipeline_async => {
            try rt.ensure_render_pipeline(cmd.target_format);
            const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
            return ok_result(setup_ns, 0, 0, 0);
        },
        else => {
            try rt.ensure_render_pipeline(cmd.target_format);
            const encode_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
            return ok_result(0, encode_ns, 0, 1);
        },
    }
}

fn execute_map_async(self: *ZigMetalBackend, cmd: model.MapAsyncCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_ns = try rt.execute_map_async(cmd);
    return ok_result(0, encode_ns, 0, 0);
}

fn prewarm_kernel_dispatch(ctx: *anyopaque, kernel: []const u8, bindings: ?[]const model.KernelBinding) anyerror!void {
    const self = cast(ctx);
    const rt = get_runtime(self);
    _ = try rt.ensure_kernel_pipeline(kernel, null);
    if (bindings) |bs| {
        for (bs) |b| {
            if (b.resource_kind != .buffer) continue;
            _ = try rt.ensure_compute_buffer(b.resource_handle, b.buffer_size, false);
        }
    }
}

fn flush_pending_uploads_if_required(self: *ZigMetalBackend, command: model.Command) !u64 {
    switch (command) {
        // All these commands share the streaming command buffer.
        // Metal guarantees in-order execution within a command buffer,
        // so uploads complete before subsequent render passes.
        .upload, .barrier, .render_draw, .draw_indirect, .draw_indexed_indirect, .render_pass => return 0,
        else => {},
    }
    if (self.pending_upload_commands == 0) return 0;
    const rt = get_runtime(self);
    self.pending_upload_commands = 0;
    return try rt.flush_queue();
}

fn execute_native_command(self: *ZigMetalBackend, command: model.Command) !webgpu.NativeExecutionResult {
    host_plan_artifact.clearHostPlanArtifact(self);

    // Fail fast when gpu_timestamp_mode=require but the device does not
    // support MTLCounterSamplingPointAtStageBoundary.
    try check_timestamp_requirement(self);

    const requirements = command_requirements.requirements(command);
    if (self.capability_set.missing(requirements.required_capabilities)) |missing_cap| {
        return .{
            .status = .unsupported,
            .status_message = capabilities.capability_name(missing_cap),
            .dispatch_count = if (requirements.is_dispatch) requirements.operation_count else 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    }

    // Time pre-command flush as setup — this captures upload-flush cost
    // in the correct phase bucket for all command types.
    const flush_start = common_timing.now_ns();
    const pending_submit_wait_ns = try flush_pending_uploads_if_required(self, command);
    const flush_setup_ns = common_timing.ns_delta(common_timing.now_ns(), flush_start) -| pending_submit_wait_ns;

    var result = switch (command) {
        .upload => |upload| try execute_upload(self, upload),
        .buffer_write => |cmd| try execute_buffer_write(self, cmd),
        .copy_buffer_to_texture => |copy| try execute_copy(self, copy),
        .barrier => try execute_barrier(self),
        .dispatch => |dispatch| try execute_dispatch(self, dispatch),
        .dispatch_indirect => |dispatch| try execute_dispatch_indirect(self, dispatch),
        .kernel_dispatch => |kd| try execute_kernel_dispatch(self, kd),
        .sampler_create => |cmd| try execute_sampler_create(self, cmd),
        .sampler_destroy => |cmd| try execute_sampler_destroy(self, cmd),
        .texture_write => |cmd| try execute_texture_write(self, cmd),
        .texture_query => |cmd| try execute_texture_query(self, cmd),
        .texture_destroy => |cmd| try execute_texture_destroy(self, cmd),
        .surface_create => |cmd| try execute_surface_create(self, cmd),
        .surface_capabilities => |cmd| try execute_surface_capabilities(self, cmd),
        .surface_configure => |cmd| try execute_surface_configure(self, cmd),
        .surface_acquire => |cmd| try execute_surface_acquire(self, cmd),
        .surface_present => |cmd| try execute_surface_present(self, cmd),
        .surface_unconfigure => |cmd| try execute_surface_unconfigure(self, cmd),
        .surface_release => |cmd| try execute_surface_release(self, cmd),
        .render_draw => |cmd| try execute_render_draw(self, cmd),
        .draw_indirect => |cmd| try execute_render_draw(self, cmd),
        .draw_indexed_indirect => |cmd| try execute_render_draw(self, cmd),
        .render_pass => |cmd| try execute_render_draw(self, cmd),
        .async_diagnostics => |cmd| try execute_async_diagnostics(self, cmd),
        .map_async => |cmd| try execute_map_async(self, cmd),
    };
    result.setup_ns +|= flush_setup_ns;
    result.submit_wait_ns +|= pending_submit_wait_ns;

    if (artifact_policy.should_emit_shader_artifact(command)) {
        const meta = artifact_meta.classify(
            .native_metal,
            result.gpu_timestamp_valid,
            result.gpu_timestamp_attempted,
        );
        const status_code = artifact_policy.artifact_status_code(result);
        const copy_len = @min(status_code.len, self.pending_artifact_status_storage.len);
        std.mem.copyForwards(u8, self.pending_artifact_status_storage[0..copy_len], status_code[0..copy_len]);
        self.pending_artifact_status_len = copy_len;
        self.pending_artifact_module = command_info.manifest_module(command);
        self.pending_artifact_meta = meta;
        self.pending_artifact_write = true;
    }

    return result;
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    return execute_native_command(self, command) catch |err| {
        const requirements = command_requirements.requirements(command);
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = write_status(self, "{s}", .{common_errors.error_code(err)}),
            .dispatch_count = if (requirements.is_dispatch) requirements.operation_count else 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
}

fn execute_buffer_write_bytes_iface(ctx: *anyopaque, handle: u64, offset: u64, buffer_size: u64, data: []const u8) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    return execute_buffer_write_bytes(self, handle, offset, buffer_size, data) catch |err| {
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = write_status(self, "{s}", .{common_errors.error_code(err)}),
            .dispatch_count = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    const normalized = if (submit_every == 0) @as(u32, 1) else submit_every;
    const effective_mode = if (self.upload_path_policy == .staged_copy_only) webgpu.UploadBufferUsageMode.copy_dst else mode;
    if (self.upload_buffer_usage_mode == effective_mode and self.upload_submit_every == normalized) return;
    self.upload_buffer_usage_mode = effective_mode;
    self.upload_submit_every = normalized;
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    const self = cast(ctx);
    if (self.queue_wait_mode == mode) return;
    self.queue_wait_mode = mode;
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    const self = cast(ctx);
    if (self.queue_sync_mode == mode) return;
    self.queue_sync_mode = mode;
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    const self = cast(ctx);
    if (self.gpu_timestamp_mode == mode) return;
    self.gpu_timestamp_mode = mode;
}

fn flush_queue(ctx: *anyopaque) anyerror!u64 {
    const self = cast(ctx);
    const rt = get_runtime(self);
    self.pending_upload_commands = 0;
    return try rt.flush_queue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    const rt = get_runtime(self);
    try rt.prewarm_upload_path(max_upload_bytes, self.upload_buffer_usage_mode);
}

fn capture_buffer(ctx: *anyopaque, allocator: std.mem.Allocator, handle: u64, offset: u64, size: u64) anyerror![]u8 {
    const self = cast(ctx);
    const runtime = get_runtime(self);
    if (size == 0) return error.InvalidArgument;
    const end = std.math.add(u64, offset, size) catch return error.InvalidArgument;
    const buffer = runtime.compute_buffers.get(handle) orelse return error.InvalidArgument;
    const mapped = metal_bridge_buffer_contents(buffer) orelse return error.InvalidState;
    const source = mapped[@intCast(offset)..@intCast(end)];
    return try allocator.dupe(u8, source);
}

const VTABLE = backend_iface.BackendVTable{
    .deinit = deinit,
    .execute_command = execute_command,
    .execute_buffer_write_bytes = execute_buffer_write_bytes_iface,
    .set_upload_behavior = set_upload_behavior,
    .set_queue_wait_mode = set_queue_wait_mode,
    .set_queue_sync_mode = set_queue_sync_mode,
    .set_gpu_timestamp_mode = set_gpu_timestamp_mode,
    .flush_queue = flush_queue,
    .prewarm_upload_path = prewarm_upload_path,
    .prewarm_kernel_dispatch = prewarm_kernel_dispatch,
    .capture_buffer = capture_buffer,
};
