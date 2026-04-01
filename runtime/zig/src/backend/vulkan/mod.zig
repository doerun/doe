const std = @import("std");
const builtin = @import("builtin");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const backend_iface = @import("../backend_iface.zig");
const backend_policy = @import("../backend_policy.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const command_info = @import("../common/command_info.zig");
const command_requirements = @import("../common/command_requirements.zig");
const capabilities = @import("../common/capabilities.zig");
const artifact_meta = @import("../common/artifact_meta.zig");
const artifact_policy = @import("../common/artifact_policy.zig");
const hash_utils = @import("../common/hash_utils.zig");
const artifact_emit = @import("artifact_emit.zig");
const native_runtime = @import("native_runtime.zig");
const vk_async_dispatch = @import("vk_async_dispatch.zig");

const MANIFEST_PATH_CAPACITY: usize = 256;
const HASH_HEX_SIZE: usize = hash_utils.SHA256_HEX_SIZE;
const MANIFEST_MODULE_CAPACITY: usize = 64;
const MANIFEST_STATUS_CODE_CAPACITY: usize = 256;
const STATUS_MESSAGE_BYTES: usize = 256;
const BOOTSTRAP_MANIFEST_MODULE = "bootstrap";
const BOOTSTRAP_MANIFEST_STATUS_CODE = "backend_initialized";

// Uploads accumulate and flush lazily: flush_pending_uploads_if_required fires
// once before the first non-upload command that needs to see the written data.
// This matches Dawn's batched-upload behavior and eliminates per-upload fence overhead.
const UPLOAD_BATCH_LAZY: u32 = std.math.maxInt(u32);

pub const ZigVulkanBackend = struct {
    allocator: std.mem.Allocator,
    kernel_root_owned: ?[]u8 = null,
    runtime: ?native_runtime.NativeVulkanRuntime = null,

    upload_path_policy: backend_policy.UploadPathPolicy = .allow_mapped_shortcuts,
    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = UPLOAD_BATCH_LAZY,
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

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigVulkanBackend {
        return init_with_upload_path_policy(allocator, profile, kernel_root, .allow_mapped_shortcuts);
    }

    pub fn init_with_selection_policy(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        selection_policy: backend_policy.SelectionPolicy,
    ) !*ZigVulkanBackend {
        return init_with_upload_path_policy(allocator, profile, kernel_root, selection_policy.upload_path_policy);
    }

    fn init_with_upload_path_policy(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        upload_path_policy: backend_policy.UploadPathPolicy,
    ) !*ZigVulkanBackend {
        if (profile.api != .vulkan) return error.UnsupportedFeature;

        const owned_kernel_root = if (kernel_root) |root| try allocator.dupe(u8, root) else null;

        const ptr = try allocator.create(ZigVulkanBackend);
        errdefer allocator.destroy(ptr);

        ptr.* = .{
            .allocator = allocator,
            .kernel_root_owned = owned_kernel_root,
            .runtime = null,
            .upload_path_policy = upload_path_policy,
            .upload_buffer_usage_mode = .copy_dst_copy_src,
            .upload_submit_every = UPLOAD_BATCH_LAZY,
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
            artifact_meta.classify(.native_vulkan, false, false),
            BOOTSTRAP_MANIFEST_STATUS_CODE,
        ) catch {};

        return ptr;
    }

    pub fn as_iface(self: *ZigVulkanBackend, allocator: std.mem.Allocator, reason: []const u8, policy_hash: []const u8) !backend_iface.BackendIface {
        _ = allocator;
        return .{
            .id = .doe_vulkan,
            .context = self,
            .vtable = &VTABLE,
            .telemetry = .{
                .backend_id = .doe_vulkan,
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

    fn manifest_path(self: *const ZigVulkanBackend) ?[]const u8 {
        return artifact_emit.manifest_path(self);
    }

    fn manifest_hash(self: *const ZigVulkanBackend) ?[]const u8 {
        return artifact_emit.manifest_hash(self);
    }

    fn flush_pending_artifact(self: *ZigVulkanBackend) void {
        artifact_emit.flush_pending_artifact(self);
    }

    fn emit_shader_artifact_manifest_for_signature(
        self: *ZigVulkanBackend,
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
        .kernel_dispatch,
        .compute_dispatch,
        .compute_dispatch_indirect,
        .buffer_upload,
        .buffer_write,
        .buffer_copy,
        .barrier_sync,
        .sampler_lifecycle,
        .render_draw,
        .render_pass,
        .texture_write,
        .texture_query,
        .texture_destroy,
        .surface_lifecycle,
        .surface_present,
        .async_pipeline_diagnostics,
        .async_capability_introspection,
        .async_resource_table_immediates,
        .async_lifecycle_refcount,
        .async_pixel_local_storage,
        .gpu_timestamps,
        .render_bundle,
        .indirect_draw,
        .indexed_indirect_draw,
        .depth_stencil,
        .descriptor_binding,
    });
    return set;
}

fn cast(ctx: *anyopaque) *ZigVulkanBackend {
    return @as(*ZigVulkanBackend, @ptrCast(@alignCast(ctx)));
}

pub fn manifest_path_from_context(ctx: *anyopaque) ?[]const u8 {
    const self = cast(ctx);
    self.flush_pending_artifact();
    return self.manifest_path();
}

pub fn manifest_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).manifest_hash();
}

pub fn adapter_ordinal_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.adapter_ordinal();
    }
    return null;
}

pub fn queue_family_index_from_context(ctx: *anyopaque) ?u32 {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.queue_family_index_value();
    }
    return null;
}

pub fn present_capable_from_context(ctx: *anyopaque) ?bool {
    const self = cast(ctx);
    if (self.runtime) |*runtime| {
        return runtime.present_capable();
    }
    return null;
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    const allocator = self.allocator;
    if (self.runtime) |*runtime| {
        runtime.deinit();
        self.runtime = null;
    }

    if (self.kernel_root_owned) |kernel_root| {
        allocator.free(kernel_root);
        self.kernel_root_owned = null;
    }

    allocator.destroy(self);
}

fn write_status(self: *ZigVulkanBackend, comptime fmt: []const u8, args: anytype) []const u8 {
    const rendered = std.fmt.bufPrint(&self.status_message_storage, fmt, args) catch "status_format_error";
    self.status_message_len = rendered.len;
    return self.status_message_storage[0..self.status_message_len];
}

fn ensure_runtime_bootstrapped(self: *ZigVulkanBackend) !*native_runtime.NativeVulkanRuntime {
    if (self.runtime == null) {
        self.runtime = try native_runtime.NativeVulkanRuntime.init(self.allocator, self.kernel_root_owned);
    }
    return &self.runtime.?;
}

fn unsupported_capability_result(
    requirements: command_requirements.CommandRequirements,
    missing: capabilities.Capability,
) webgpu.NativeExecutionResult {
    return .{
        .status = .unsupported,
        .status_message = capabilities.capability_name(missing),
        .dispatch_count = if (requirements.is_dispatch) requirements.operation_count else 0,
    };
}

fn annotate_result(self: *ZigVulkanBackend, command: model.Command, result: webgpu.NativeExecutionResult) webgpu.NativeExecutionResult {
    var out = result;
    const meta = artifact_meta.classify(
        .native_vulkan,
        out.gpu_timestamp_valid,
        out.gpu_timestamp_attempted,
    );
    if (out.status == .ok or out.status_message.len == 0) {
        out.status_message = write_status(
            self,
            "{s} timing={s} comparability={s}",
            .{ command_info.manifest_module(command), meta.timing_source.name(), meta.comparability.name() },
        );
    }

    if (artifact_policy.should_emit_shader_artifact(command)) {
        const status_code = artifact_policy.artifact_status_code(out);
        const copy_len = @min(status_code.len, self.pending_artifact_status_storage.len);
        std.mem.copyForwards(u8, self.pending_artifact_status_storage[0..copy_len], status_code[0..copy_len]);
        self.pending_artifact_status_len = copy_len;
        self.pending_artifact_module = command_info.manifest_module(command);
        self.pending_artifact_meta = meta;
        self.pending_artifact_write = true;
    }

    return out;
}

fn execute_upload(self: *ZigVulkanBackend, setup_ns: u64, upload: model.UploadCommand) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);

    const upload_setup_start = common_timing.now_ns();
    try runtime.upload_bytes(
        @as(u64, @intCast(upload.bytes)),
        self.upload_buffer_usage_mode,
        self.upload_path_policy,
    );
    const upload_setup_ns = common_timing.ns_delta(common_timing.now_ns(), upload_setup_start);

    var submit_wait_ns: u64 = 0;
    self.pending_upload_commands +|= 1;
    if (self.pending_upload_commands >= self.upload_submit_every) {
        self.pending_upload_commands = 0;
        submit_wait_ns = try runtime.flush_queue();
    }

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns +| upload_setup_ns,
        .encode_ns = 0,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = 0,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn execute_barrier(self: *ZigVulkanBackend, setup_ns: u64) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const submit_wait_ns = try runtime.barrier(self.queue_wait_mode);

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = 0,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = 0,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn execute_buffer_write(self: *ZigVulkanBackend, setup_ns: u64, bw: model.BufferWriteCommand) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const write_start = common_timing.now_ns();

    const data_bytes = std.mem.sliceAsBytes(bw.data);
    if (data_bytes.len == 0) return error.InvalidArgument;

    const required_size = if (bw.buffer_size > 0)
        @max(bw.buffer_size, bw.offset + data_bytes.len)
    else
        bw.offset + data_bytes.len;

    const vk_resources = @import("vk_resources.zig");
    const compute_buffer = try vk_resources.ensure_compute_buffer(runtime, bw.handle, required_size, false);

    const mapped = compute_buffer.mapped orelse return error.InvalidArgument;
    const dst: [*]u8 = @ptrCast(mapped);
    @memcpy(dst[@intCast(bw.offset)..][0..data_bytes.len], data_bytes);

    const write_ns = common_timing.ns_delta(common_timing.now_ns(), write_start);

    return .{
        .status = .ok,
        .status_message = "buffer seeded via host-visible memcpy",
        .setup_ns = setup_ns +| write_ns,
        .encode_ns = 0,
        .submit_wait_ns = 0,
        .dispatch_count = 0,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn execute_dispatch_command(
    self: *ZigVulkanBackend,
    setup_ns: u64,
    x: u32,
    y: u32,
    z: u32,
    repeat: u32,
    warmup_dispatch_count: u32,
) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);

    if (!runtime.has_pipeline) {
        const noop_words = try runtime.load_kernel_spirv(self.allocator, "dispatch_noop.wgsl");
        defer self.allocator.free(noop_words);
        try runtime.set_compute_shader_spirv(noop_words, null, null, false);
    }

    var warmup_index: u32 = 0;
    while (warmup_index < warmup_dispatch_count) : (warmup_index += 1) {
        _ = try runtime.run_dispatch(x, y, z, .per_command, self.queue_wait_mode, .off);
    }

    const dispatch_count = if (repeat > 0) repeat else 1;

    var encode_ns: u64 = 0;
    var submit_wait_ns: u64 = 0;
    var gpu_timestamp_ns: u64 = 0;
    var gpu_timestamp_attempted = false;
    var gpu_timestamp_valid = true;

    var dispatch_index: u32 = 0;
    while (dispatch_index < dispatch_count) : (dispatch_index += 1) {
        const metrics = try runtime.run_dispatch(
            x,
            y,
            z,
            self.queue_sync_mode,
            self.queue_wait_mode,
            self.gpu_timestamp_mode,
        );

        encode_ns +|= metrics.encode_ns;
        submit_wait_ns +|= metrics.submit_wait_ns;

        gpu_timestamp_attempted = gpu_timestamp_attempted or metrics.gpu_timestamp_attempted;
        if (metrics.gpu_timestamp_attempted and metrics.gpu_timestamp_valid) {
            gpu_timestamp_ns +|= metrics.gpu_timestamp_ns;
        }
        if (metrics.gpu_timestamp_attempted and !metrics.gpu_timestamp_valid) {
            gpu_timestamp_valid = false;
        }
    }

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = dispatch_count,
        .gpu_timestamp_ns = if (gpu_timestamp_attempted and gpu_timestamp_valid) gpu_timestamp_ns else 0,
        .gpu_timestamp_attempted = gpu_timestamp_attempted,
        .gpu_timestamp_valid = gpu_timestamp_attempted and gpu_timestamp_valid,
    };
}

fn execute_dispatch_indirect_command(
    self: *ZigVulkanBackend,
    setup_ns: u64,
    x: u32,
    y: u32,
    z: u32,
) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);

    if (!runtime.has_pipeline) {
        const noop_words = try runtime.load_kernel_spirv(self.allocator, "dispatch_noop.wgsl");
        defer self.allocator.free(noop_words);
        try runtime.set_compute_shader_spirv(noop_words, null, null, false);
    }

    const metrics = try runtime.run_dispatch_indirect(
        x,
        y,
        z,
        self.queue_sync_mode,
        self.queue_wait_mode,
    );

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = metrics.encode_ns,
        .submit_wait_ns = metrics.submit_wait_ns,
        .dispatch_count = 1,
        .gpu_timestamp_ns = metrics.gpu_timestamp_ns,
        .gpu_timestamp_attempted = metrics.gpu_timestamp_attempted,
        .gpu_timestamp_valid = metrics.gpu_timestamp_valid,
    };
}

fn execute_kernel_dispatch(self: *ZigVulkanBackend, setup_ns: u64, kernel_dispatch: model.KernelDispatchCommand) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const spirv_words = runtime.load_kernel_spirv(self.allocator, kernel_dispatch.kernel) catch |err| {
        if (err == error.UnsupportedFeature and std.mem.endsWith(u8, kernel_dispatch.kernel, ".wgsl")) {
            return .{
                .status = .unsupported,
                .status_message = write_status(
                    self,
                    "missing Vulkan SPIR-V artifact for WGSL kernel {s}; add explicit .spv artifact in kernel-root",
                    .{kernel_dispatch.kernel},
                ),
                .setup_ns = setup_ns,
                .dispatch_count = if (kernel_dispatch.repeat > 0) kernel_dispatch.repeat else 1,
            };
        }
        return err;
    };
    defer self.allocator.free(spirv_words);
    try runtime.set_compute_shader_spirv(
        spirv_words,
        kernel_dispatch.entry_point,
        kernel_dispatch.bindings,
        kernel_dispatch.initialize_buffers_on_create,
    );

    return execute_dispatch_command(
        self,
        setup_ns,
        kernel_dispatch.x,
        kernel_dispatch.y,
        kernel_dispatch.z,
        kernel_dispatch.repeat,
        kernel_dispatch.warmup_dispatch_count,
    );
}

fn execute_render_draw_command(
    self: *ZigVulkanBackend,
    setup_ns: u64,
    render_draw: model.RenderDrawCommand,
) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const metrics = try runtime.run_render_draw(render_draw);
    const draw_count = if (render_draw.draw_count > 0) render_draw.draw_count else 1;

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = metrics.encode_ns,
        .submit_wait_ns = metrics.submit_wait_ns,
        .dispatch_count = draw_count,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn execute_async_diagnostics(
    self: *ZigVulkanBackend,
    setup_ns: u64,
    diagnostics: model.AsyncDiagnosticsCommand,
) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    return vk_async_dispatch.execute(runtime, self.allocator, setup_ns, diagnostics, self.upload_path_policy);
}

fn execute_surface_command(self: *ZigVulkanBackend, setup_ns: u64, command: model.Command) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const start_ns = common_timing.now_ns();
    switch (command) {
        .surface_create => |cmd| try runtime.create_surface(cmd.handle),
        .surface_capabilities => |cmd| try runtime.get_surface_capabilities(cmd.handle),
        .surface_configure => |cmd| try runtime.configure_surface(cmd),
        .surface_acquire => |cmd| try runtime.acquire_surface(cmd.handle),
        .surface_present => |cmd| try runtime.present_surface(cmd.handle),
        .surface_unconfigure => |cmd| try runtime.unconfigure_surface(cmd.handle),
        .surface_release => |cmd| try runtime.release_surface(cmd.handle),
        else => return error.InvalidArgument,
    }
    return result_without_gpu_timestamps(setup_ns, common_timing.ns_delta(common_timing.now_ns(), start_ns), 0, 0);
}

fn execute_sampler_command(self: *ZigVulkanBackend, setup_ns: u64, command: model.Command) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const start_ns = common_timing.now_ns();
    switch (command) {
        .sampler_create => |cmd| try runtime.sampler_create(cmd),
        .sampler_destroy => |cmd| try runtime.sampler_destroy(cmd),
        else => return error.InvalidArgument,
    }
    return result_without_gpu_timestamps(setup_ns, common_timing.ns_delta(common_timing.now_ns(), start_ns), 0, 0);
}

fn execute_texture_command(self: *ZigVulkanBackend, setup_ns: u64, command: model.Command) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const start_ns = common_timing.now_ns();
    switch (command) {
        .texture_write => |cmd| try runtime.texture_write(cmd),
        .texture_query => |cmd| try runtime.texture_query(cmd),
        .texture_destroy => |cmd| try runtime.texture_destroy(cmd),
        else => return error.InvalidArgument,
    }
    return result_without_gpu_timestamps(setup_ns, common_timing.ns_delta(common_timing.now_ns(), start_ns), 0, 0);
}

fn result_without_gpu_timestamps(setup_ns: u64, encode_ns: u64, submit_wait_ns: u64, dispatch_count: u32) webgpu.NativeExecutionResult {
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

fn flush_pending_uploads_if_required(self: *ZigVulkanBackend, command: model.Command) !u64 {
    switch (command) {
        .upload => return 0,
        else => {},
    }
    if (self.pending_upload_commands == 0) return 0;
    const runtime = try ensure_runtime_bootstrapped(self);
    self.pending_upload_commands = 0;
    return try runtime.flush_queue();
}

fn execute_runtime_command(self: *ZigVulkanBackend, command: model.Command) !webgpu.NativeExecutionResult {
    const requirements = command_requirements.requirements(command);
    if (self.capability_set.missing(requirements.required_capabilities)) |missing| {
        return unsupported_capability_result(requirements, missing);
    }

    var setup_ns: u64 = 0;
    if (self.runtime == null) {
        const setup_start = common_timing.now_ns();
        _ = try ensure_runtime_bootstrapped(self);
        const setup_end = common_timing.now_ns();
        setup_ns = common_timing.ns_delta(setup_end, setup_start);
    }

    const flush_start = common_timing.now_ns();
    const pending_submit_wait_ns = try flush_pending_uploads_if_required(self, command);
    const flush_setup_ns =
        common_timing.ns_delta(common_timing.now_ns(), flush_start) -| pending_submit_wait_ns;

    var result = switch (command) {
        .upload => |upload| try execute_upload(self, setup_ns, upload),
        .buffer_write => |bw| try execute_buffer_write(self, setup_ns, bw),
        .barrier => try execute_barrier(self, setup_ns),
        .dispatch => |dispatch| try execute_dispatch_command(self, setup_ns, dispatch.x, dispatch.y, dispatch.z, 1, 0),
        .dispatch_indirect => |dispatch| try execute_dispatch_indirect_command(self, setup_ns, dispatch.x, dispatch.y, dispatch.z),
        .kernel_dispatch => |kernel_dispatch| try execute_kernel_dispatch(self, setup_ns, kernel_dispatch),
        .render_draw => |render_draw| try execute_render_draw_command(self, setup_ns, render_draw),
        .draw_indirect => |render_draw| try execute_render_draw_command(self, setup_ns, render_draw),
        .draw_indexed_indirect => |render_draw| try execute_render_draw_command(self, setup_ns, render_draw),
        .render_pass => |render_draw| try execute_render_draw_command(self, setup_ns, render_draw),
        .async_diagnostics => |diagnostics| try execute_async_diagnostics(self, setup_ns, diagnostics),
        .sampler_create, .sampler_destroy => try execute_sampler_command(self, setup_ns, command),
        .texture_write,
        .texture_query,
        .texture_destroy,
        => try execute_texture_command(self, setup_ns, command),
        .surface_create,
        .surface_capabilities,
        .surface_configure,
        .surface_acquire,
        .surface_present,
        .surface_unconfigure,
        .surface_release,
        => try execute_surface_command(self, setup_ns, command),
        else => return error.Unsupported,
    };
    result.setup_ns +|= flush_setup_ns;
    result.submit_wait_ns +|= pending_submit_wait_ns;

    return annotate_result(self, command, result);
}

pub fn run_contract_path_for_test(command: model.Command, queue_sync_mode: webgpu.QueueSyncMode) !webgpu.NativeExecutionResult {
    var backend = ZigVulkanBackend{
        .allocator = std.testing.allocator,
        .kernel_root_owned = null,
        .runtime = null,
        .upload_path_policy = .allow_mapped_shortcuts,
        .upload_buffer_usage_mode = .copy_dst_copy_src,
        .upload_submit_every = UPLOAD_BATCH_LAZY,
        .queue_wait_mode = .process_events,
        .queue_sync_mode = queue_sync_mode,
        .gpu_timestamp_mode = .off,
        .pending_upload_commands = 0,
        .capability_set = native_capability_set(),
        .status_message_storage = [_]u8{0} ** STATUS_MESSAGE_BYTES,
        .status_message_len = 0,
    };
    defer if (backend.runtime) |*runtime| runtime.deinit();

    return execute_runtime_command(&backend, command) catch |err| {
        const requirements = command_requirements.requirements(command);
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = write_status(&backend, "{s}", .{common_errors.error_code(err)}),
            .setup_ns = 0,
            .encode_ns = 0,
            .submit_wait_ns = 0,
            .dispatch_count = if (requirements.is_dispatch) requirements.operation_count else 0,
            .gpu_timestamp_ns = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    const requirements = command_requirements.requirements(command);
    return execute_runtime_command(self, command) catch |err| {
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = write_status(self, "{s}", .{common_errors.error_code(err)}),
            .setup_ns = 0,
            .encode_ns = 0,
            .submit_wait_ns = 0,
            .dispatch_count = if (requirements.is_dispatch) requirements.operation_count else 0,
            .gpu_timestamp_ns = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    const normalized_submit_every = if (submit_every > 0) submit_every else 1;
    if (self.upload_buffer_usage_mode == mode and self.upload_submit_every == normalized_submit_every) return;
    self.upload_buffer_usage_mode = mode;
    self.upload_submit_every = normalized_submit_every;
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
    const runtime = try ensure_runtime_bootstrapped(self);
    self.pending_upload_commands = 0;
    return try runtime.flush_queue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    const runtime = try ensure_runtime_bootstrapped(self);
    try runtime.prewarm_upload_path(max_upload_bytes, self.upload_buffer_usage_mode, self.upload_path_policy);
}

fn prewarm_kernel_dispatch(ctx: *anyopaque, kernel: []const u8, bindings: ?[]const model.KernelBinding) anyerror!void {
    const self = cast(ctx);
    const runtime = try ensure_runtime_bootstrapped(self);
    const spirv_words = try runtime.load_kernel_spirv(self.allocator, kernel);
    defer self.allocator.free(spirv_words);
    try runtime.set_compute_shader_spirv(spirv_words, null, bindings, false);
}

fn capture_buffer(ctx: *anyopaque, allocator: std.mem.Allocator, handle: u64, offset: u64, size: u64) anyerror![]u8 {
    const self = cast(ctx);
    const runtime = try ensure_runtime_bootstrapped(self);
    if (size == 0) return error.InvalidArgument;
    const buffer = runtime.compute_buffers.get(handle) orelse return error.InvalidArgument;
    const end = std.math.add(u64, offset, size) catch return error.InvalidArgument;
    if (end > buffer.size) return error.InvalidArgument;
    const mapped = buffer.mapped orelse return error.InvalidState;
    const source = @as([*]u8, @ptrCast(mapped))[@intCast(offset)..@intCast(end)];
    return try allocator.dupe(u8, source);
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
    .prewarm_kernel_dispatch = prewarm_kernel_dispatch,
    .capture_buffer = capture_buffer,
};
