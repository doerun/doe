const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const backend_iface = @import("../backend_iface.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const command_info = @import("../common/command_info.zig");
const capabilities = @import("../common/capabilities.zig");
const artifact_meta = @import("../common/artifact_meta.zig");
const native_runtime = @import("native_runtime.zig");

const STATUS_MESSAGE_BYTES: usize = 256;

pub const ZigVulkanBackend = struct {
    allocator: std.mem.Allocator,
    kernel_root_owned: ?[]u8 = null,
    runtime: ?native_runtime.NativeVulkanRuntime = null,

    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    queue_wait_mode: webgpu.QueueWaitMode = .process_events,
    queue_sync_mode: webgpu.QueueSyncMode = .per_command,
    gpu_timestamp_mode: webgpu.GpuTimestampMode = .auto,
    pending_upload_commands: u32 = 0,

    capability_set: capabilities.CapabilitySet,

    status_message_storage: [STATUS_MESSAGE_BYTES]u8 = [_]u8{0} ** STATUS_MESSAGE_BYTES,
    status_message_len: usize = 0,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*ZigVulkanBackend {
        if (profile.api != .vulkan) return error.UnsupportedFeature;

        var caps = capabilities.CapabilitySet{};
        caps.declare_all(&.{
            .kernel_dispatch,
            .buffer_upload,
            .barrier_sync,
            .gpu_timestamps,
        });

        const owned_kernel_root = if (kernel_root) |root| try allocator.dupe(u8, root) else null;

        const ptr = try allocator.create(ZigVulkanBackend);
        errdefer allocator.destroy(ptr);

        ptr.* = .{
            .allocator = allocator,
            .kernel_root_owned = owned_kernel_root,
            .runtime = null,
            .upload_buffer_usage_mode = .copy_dst_copy_src,
            .upload_submit_every = 1,
            .queue_wait_mode = .process_events,
            .queue_sync_mode = .per_command,
            .gpu_timestamp_mode = .auto,
            .pending_upload_commands = 0,
            .capability_set = caps,
            .status_message_storage = [_]u8{0} ** STATUS_MESSAGE_BYTES,
            .status_message_len = 0,
        };

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
            },
        };
    }
};

fn cast(ctx: *anyopaque) *ZigVulkanBackend {
    return @as(*ZigVulkanBackend, @ptrCast(@alignCast(ctx)));
}

pub fn manifest_path_from_context(ctx: *anyopaque) ?[]const u8 {
    _ = ctx;
    return null;
}

pub fn manifest_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    _ = ctx;
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

fn unsupported_capability_result(self: *ZigVulkanBackend, command: model.Command, missing: capabilities.Capability) webgpu.NativeExecutionResult {
    _ = self;
    return .{
        .status = .unsupported,
        .status_message = capabilities.capability_name(missing),
        .dispatch_count = if (command_info.is_dispatch(command)) command_info.operation_count(command) else 0,
    };
}

fn annotate_result(self: *ZigVulkanBackend, command: model.Command, result: webgpu.NativeExecutionResult) webgpu.NativeExecutionResult {
    var out = result;
    const meta = artifact_meta.classify(
        .native_vulkan,
        out.gpu_timestamp_valid,
        out.gpu_timestamp_attempted,
    );
    out.status_message = write_status(
        self,
        "{s} timing={s} comparability={s}",
        .{ command_info.manifest_module(command), meta.timing_source.name(), meta.comparability.name() },
    );
    return out;
}

fn execute_upload(self: *ZigVulkanBackend, setup_ns: u64, upload: model.UploadCommand) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);

    const encode_start = common_timing.now_ns();
    try runtime.upload_bytes(@as(u64, @intCast(upload.bytes)), self.upload_buffer_usage_mode);
    const encode_end = common_timing.now_ns();
    const encode_ns = common_timing.ns_delta(encode_end, encode_start);

    var submit_wait_ns: u64 = 0;
    self.pending_upload_commands +|= 1;
    if (self.pending_upload_commands >= self.upload_submit_every) {
        self.pending_upload_commands = 0;
        submit_wait_ns = try runtime.flush_queue();
    }

    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
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

fn execute_kernel_dispatch(self: *ZigVulkanBackend, setup_ns: u64, kernel_dispatch: model.KernelDispatchCommand) !webgpu.NativeExecutionResult {
    const runtime = try ensure_runtime_bootstrapped(self);
    const spirv_words = try runtime.load_kernel_spirv(self.allocator, kernel_dispatch.kernel);
    defer self.allocator.free(spirv_words);
    try runtime.set_compute_shader_spirv(spirv_words);

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
    const required = capabilities.required_capabilities(command);
    if (self.capability_set.missing(required)) |missing| {
        return unsupported_capability_result(self, command, missing);
    }

    var setup_ns: u64 = 0;
    if (self.runtime == null) {
        const setup_start = common_timing.now_ns();
        _ = try ensure_runtime_bootstrapped(self);
        const setup_end = common_timing.now_ns();
        setup_ns = common_timing.ns_delta(setup_end, setup_start);
    }

    const pending_submit_wait_ns = try flush_pending_uploads_if_required(self, command);

    var result = switch (command) {
        .upload => |upload| try execute_upload(self, setup_ns, upload),
        .barrier => try execute_barrier(self, setup_ns),
        .dispatch => |dispatch| try execute_dispatch_command(self, setup_ns, dispatch.x, dispatch.y, dispatch.z, 1, 0),
        .kernel_dispatch => |kernel_dispatch| try execute_kernel_dispatch(self, setup_ns, kernel_dispatch),
        else => return error.Unsupported,
    };
    result.submit_wait_ns +|= pending_submit_wait_ns;

    return annotate_result(self, command, result);
}

pub fn run_contract_path_for_test(command: model.Command, queue_sync_mode: webgpu.QueueSyncMode) !webgpu.NativeExecutionResult {
    var caps = capabilities.CapabilitySet{};
    caps.declare_all(&.{
        .kernel_dispatch,
        .buffer_upload,
        .barrier_sync,
        .gpu_timestamps,
    });

    var backend = ZigVulkanBackend{
        .allocator = std.testing.allocator,
        .kernel_root_owned = null,
        .runtime = null,
        .upload_buffer_usage_mode = .copy_dst_copy_src,
        .upload_submit_every = 1,
        .queue_wait_mode = .process_events,
        .queue_sync_mode = queue_sync_mode,
        .gpu_timestamp_mode = .off,
        .pending_upload_commands = 0,
        .capability_set = caps,
        .status_message_storage = [_]u8{0} ** STATUS_MESSAGE_BYTES,
        .status_message_len = 0,
    };
    defer if (backend.runtime) |*runtime| runtime.deinit();

    return execute_runtime_command(&backend, command) catch |err| {
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = write_status(&backend, "{s}", .{common_errors.error_code(err)}),
            .setup_ns = 0,
            .encode_ns = 0,
            .submit_wait_ns = 0,
            .dispatch_count = if (command_info.is_dispatch(command)) command_info.operation_count(command) else 0,
            .gpu_timestamp_ns = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    return execute_runtime_command(self, command) catch |err| {
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = write_status(self, "{s}", .{common_errors.error_code(err)}),
            .setup_ns = 0,
            .encode_ns = 0,
            .submit_wait_ns = 0,
            .dispatch_count = if (command_info.is_dispatch(command)) command_info.operation_count(command) else 0,
            .gpu_timestamp_ns = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    self.upload_buffer_usage_mode = mode;
    self.upload_submit_every = if (submit_every > 0) submit_every else 1;
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
    const runtime = try ensure_runtime_bootstrapped(self);
    self.pending_upload_commands = 0;
    return try runtime.flush_queue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    const runtime = try ensure_runtime_bootstrapped(self);
    try runtime.prewarm_upload_path(max_upload_bytes, self.upload_buffer_usage_mode);
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
