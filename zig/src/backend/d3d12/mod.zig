const builtin = @import("builtin");
const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const backend_iface = @import("../backend_iface.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const command_info = @import("../common/command_info.zig");
const command_requirements = @import("../common/command_requirements.zig");
const capabilities = @import("../common/capabilities.zig");
const artifact_meta = @import("../common/artifact_meta.zig");
const native_runtime = if (builtin.os.tag == .windows)
    @import("d3d12_native_runtime.zig")
else
    @import("d3d12_native_runtime_stub.zig");

const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const MANIFEST_PATH_CAPACITY: usize = 256;
const HASH_HEX_SIZE: usize = 64;
const MANIFEST_CONTENT_CAPACITY: usize = 2048;
const MANIFEST_MODULE_CAPACITY: usize = 64;
const MANIFEST_STATUS_CODE_CAPACITY: usize = 256;
const STATUS_MESSAGE_BYTES: usize = 256;
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";
const HEX = "0123456789abcdef";
const BOOTSTRAP_MANIFEST_MODULE = "bootstrap";
const BOOTSTRAP_MANIFEST_STATUS_CODE = "backend_initialized";

pub const ZigD3D12Backend = struct {
    allocator: std.mem.Allocator,
    kernel_root_owned: ?[]u8 = null,
    runtime: ?native_runtime.NativeD3D12Runtime = null,

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
    ) !*ZigD3D12Backend {
        if (profile.api != .d3d12) return common_errors.BackendNativeError.UnsupportedFeature;
        if (builtin.os.tag != .windows) return common_errors.BackendNativeError.UnsupportedFeature;

        const owned_root = if (kernel_root) |root| try allocator.dupe(u8, root) else null;
        errdefer if (owned_root) |r| allocator.free(r);

        const ptr = try allocator.create(ZigD3D12Backend);
        errdefer allocator.destroy(ptr);

        ptr.* = .{
            .allocator = allocator,
            .kernel_root_owned = owned_root,
            .runtime = null,
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
            artifact_meta.classify(.native_d3d12, false, false),
            BOOTSTRAP_MANIFEST_STATUS_CODE,
        ) catch {};

        return ptr;
    }

    pub fn as_iface(
        self: *ZigD3D12Backend,
        allocator: std.mem.Allocator,
        reason: []const u8,
        policy_hash: []const u8,
    ) !backend_iface.BackendIface {
        _ = allocator;
        return .{
            .id = .doe_d3d12,
            .context = self,
            .vtable = &VTABLE,
            .telemetry = .{
                .backend_id = .doe_d3d12,
                .backend_selection_reason = reason,
                .fallback_used = false,
                .selection_policy_hash = policy_hash,
                .shader_artifact_manifest_path = null,
                .shader_artifact_manifest_hash = null,
            },
        };
    }

    fn manifest_path(self: *const ZigD3D12Backend) ?[]const u8 {
        if (self.manifest_path_len == 0) return null;
        return self.manifest_path_storage[0..self.manifest_path_len];
    }

    fn manifest_hash(self: *const ZigD3D12Backend) ?[]const u8 {
        if (self.manifest_hash_len == 0) return null;
        return self.manifest_hash_storage[0..self.manifest_hash_len];
    }

    fn previous_manifest_hash(self: *const ZigD3D12Backend) []const u8 {
        return self.manifest_hash() orelse ZERO_HASH;
    }

    fn flush_pending_artifact(self: *ZigD3D12Backend) void {
        if (!self.pending_artifact_write) return;
        self.pending_artifact_write = false;
        const status_code = self.pending_artifact_status_storage[0..self.pending_artifact_status_len];
        if (manifest_signature_matches(self, self.pending_artifact_module, self.pending_artifact_meta, status_code)) return;
        self.emit_shader_artifact_manifest_for_signature(
            self.pending_artifact_module,
            self.pending_artifact_meta,
            status_code,
        ) catch {};
    }

    fn emit_shader_artifact_manifest_for_signature(
        self: *ZigD3D12Backend,
        module: []const u8,
        meta: artifact_meta.ArtifactMeta,
        status_code: []const u8,
    ) common_errors.BackendNativeError!void {
        self.manifest_emit_count +|= 1;

        var path_buffer: [MANIFEST_PATH_CAPACITY]u8 = undefined;
        const path = std.fmt.bufPrint(
            &path_buffer,
            "{s}/d3d12_shader_artifact_{d}.json",
            .{ SHADER_ARTIFACT_DIR, self.manifest_emit_count },
        ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

        var content_buffer: [MANIFEST_CONTENT_CAPACITY]u8 = undefined;
        const content = std.fmt.bufPrint(
            &content_buffer,
            "{{\"backendId\":\"doe_d3d12\",\"backendKind\":\"{s}\",\"timingSource\":\"{s}\",\"comparability\":\"{s}\",\"claimable\":{},\"module\":\"{s}\",\"statusCode\":\"{s}\",\"previousManifestHash\":\"{s}\"}}\n",
            .{
                meta.backend_kind.name(),
                meta.timing_source.name(),
                meta.comparability.name(),
                meta.is_claimable(),
                module,
                status_code,
                self.previous_manifest_hash(),
            },
        ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

        const hash = sha256_hex(content);

        std.fs.cwd().makePath(SHADER_ARTIFACT_DIR) catch return common_errors.BackendNativeError.ShaderCompileFailed;
        const file = std.fs.cwd().createFile(path, .{ .truncate = true }) catch return common_errors.BackendNativeError.ShaderCompileFailed;
        defer file.close();
        file.writeAll(content) catch return common_errors.BackendNativeError.ShaderCompileFailed;

        persist_manifest_path(self, path);
        persist_manifest_hash(self, hash[0..]);
        persist_manifest_signature(self, module, meta, status_code);
    }
};

fn native_capability_set() capabilities.CapabilitySet {
    var set = capabilities.CapabilitySet{};
    set.declare_all(&.{
        .buffer_upload,
        .barrier_sync,
        .kernel_dispatch,
    });
    return set;
}

fn should_emit_shader_artifact(command: model.Command) bool {
    return switch (command) {
        .dispatch,
        .dispatch_indirect,
        .kernel_dispatch,
        .render_draw,
        .draw_indirect,
        .draw_indexed_indirect,
        .render_pass,
        => true,
        else => false,
    };
}

fn artifact_status_code(result: webgpu.NativeExecutionResult) []const u8 {
    if (result.status_message.len != 0) return result.status_message;
    return switch (result.status) {
        .ok => "ok",
        .unsupported => "unsupported",
        .@"error" => "error",
    };
}

fn sha256_hex(input: []const u8) [HASH_HEX_SIZE]u8 {
    var output: [HASH_HEX_SIZE]u8 = undefined;
    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &digest, .{});
    for (digest, 0..) |byte, index| {
        const output_index = index * 2;
        output[output_index] = HEX[(byte >> 4) & 0x0F];
        output[output_index + 1] = HEX[byte & 0x0F];
    }
    return output;
}

fn persist_manifest_path(self: *ZigD3D12Backend, value: []const u8) void {
    if (value.len > self.manifest_path_storage.len) {
        self.manifest_path_len = 0;
        return;
    }
    std.mem.copyForwards(u8, self.manifest_path_storage[0..value.len], value);
    self.manifest_path_len = value.len;
}

fn persist_manifest_hash(self: *ZigD3D12Backend, value: []const u8) void {
    if (value.len > self.manifest_hash_storage.len) {
        self.manifest_hash_len = 0;
        return;
    }
    std.mem.copyForwards(u8, self.manifest_hash_storage[0..value.len], value);
    self.manifest_hash_len = value.len;
}

fn manifest_signature_matches(
    self: *const ZigD3D12Backend,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    status_code: []const u8,
) bool {
    const last_meta = self.last_manifest_meta orelse return false;
    if (last_meta.backend_kind != meta.backend_kind or
        last_meta.timing_source != meta.timing_source or
        last_meta.comparability != meta.comparability)
    {
        return false;
    }
    if (!std.mem.eql(u8, self.last_manifest_module_storage[0..self.last_manifest_module_len], module)) return false;
    if (!std.mem.eql(u8, self.last_manifest_status_storage[0..self.last_manifest_status_len], status_code)) return false;
    return true;
}

fn persist_manifest_signature(
    self: *ZigD3D12Backend,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    status_code: []const u8,
) void {
    self.last_manifest_meta = meta;
    if (module.len > self.last_manifest_module_storage.len) {
        self.last_manifest_module_len = 0;
    } else {
        std.mem.copyForwards(u8, self.last_manifest_module_storage[0..module.len], module);
        self.last_manifest_module_len = module.len;
    }
    if (status_code.len > self.last_manifest_status_storage.len) {
        self.last_manifest_status_len = 0;
    } else {
        std.mem.copyForwards(u8, self.last_manifest_status_storage[0..status_code.len], status_code);
        self.last_manifest_status_len = status_code.len;
    }
}

fn write_status(self: *ZigD3D12Backend, comptime fmt: []const u8, args: anytype) []const u8 {
    const rendered = std.fmt.bufPrint(&self.status_message_storage, fmt, args) catch "status_format_error";
    self.status_message_len = rendered.len;
    return self.status_message_storage[0..self.status_message_len];
}

fn cast(ctx: *anyopaque) *ZigD3D12Backend {
    return @as(*ZigD3D12Backend, @ptrCast(@alignCast(ctx)));
}

pub fn manifest_path_from_context(ctx: *anyopaque) ?[]const u8 {
    const self = cast(ctx);
    self.flush_pending_artifact();
    return self.manifest_path();
}

pub fn manifest_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).manifest_hash();
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

fn ensure_runtime_bootstrapped(self: *ZigD3D12Backend) !*native_runtime.NativeD3D12Runtime {
    if (self.runtime == null) {
        self.runtime = try native_runtime.NativeD3D12Runtime.init(self.allocator, self.kernel_root_owned);
    }
    return &self.runtime.?;
}

fn execute_upload(self: *ZigD3D12Backend, setup_ns: u64, upload: model.UploadCommand) !webgpu.NativeExecutionResult {
    const rt = try ensure_runtime_bootstrapped(self);

    const encode_start = common_timing.now_ns();
    try rt.upload_bytes(@as(u64, @intCast(upload.bytes)), self.upload_buffer_usage_mode);
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

    var submit_wait_ns: u64 = 0;
    self.pending_upload_commands +|= 1;
    if (self.pending_upload_commands >= self.upload_submit_every) {
        self.pending_upload_commands = 0;
        submit_wait_ns = try rt.flush_queue();
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

fn execute_barrier(self: *ZigD3D12Backend, setup_ns: u64) !webgpu.NativeExecutionResult {
    const rt = try ensure_runtime_bootstrapped(self);
    const submit_wait_ns = try rt.barrier(self.queue_wait_mode);

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

fn execute_kernel_dispatch(self: *ZigD3D12Backend, setup_ns: u64, kd: model.KernelDispatchCommand) !webgpu.NativeExecutionResult {
    const rt = try ensure_runtime_bootstrapped(self);
    const bytecode = try rt.load_kernel_cso(self.allocator, kd.kernel);
    defer self.allocator.free(bytecode);
    try rt.set_compute_shader(bytecode);

    var warmup_i: u32 = 0;
    while (warmup_i < kd.warmup_dispatch_count) : (warmup_i += 1) {
        _ = try rt.run_dispatch(kd.x, kd.y, kd.z, 1);
    }

    const metrics = try rt.run_dispatch(kd.x, kd.y, kd.z, kd.repeat);
    return .{
        .status = .ok,
        .status_message = "",
        .setup_ns = setup_ns,
        .encode_ns = metrics.encode_ns,
        .submit_wait_ns = metrics.submit_wait_ns,
        .dispatch_count = metrics.dispatch_count,
        .gpu_timestamp_ns = 0,
        .gpu_timestamp_attempted = false,
        .gpu_timestamp_valid = false,
    };
}

fn flush_pending_uploads_if_required(self: *ZigD3D12Backend, command: model.Command) !u64 {
    switch (command) {
        .upload => return 0,
        else => {},
    }
    if (self.pending_upload_commands == 0) return 0;
    const rt = try ensure_runtime_bootstrapped(self);
    self.pending_upload_commands = 0;
    return try rt.flush_queue();
}

fn execute_native_command(self: *ZigD3D12Backend, command: model.Command) !webgpu.NativeExecutionResult {
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

    var setup_ns: u64 = 0;
    if (self.runtime == null) {
        const setup_start = common_timing.now_ns();
        _ = try ensure_runtime_bootstrapped(self);
        setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
    }

    const pending_submit_wait_ns = try flush_pending_uploads_if_required(self, command);

    var result = switch (command) {
        .upload => |upload| try execute_upload(self, setup_ns, upload),
        .barrier => try execute_barrier(self, setup_ns),
        .kernel_dispatch => |kd| try execute_kernel_dispatch(self, setup_ns, kd),
        else => return error.Unsupported,
    };
    result.submit_wait_ns +|= pending_submit_wait_ns;

    if (should_emit_shader_artifact(command)) {
        const meta = artifact_meta.classify(
            .native_d3d12,
            result.gpu_timestamp_valid,
            result.gpu_timestamp_attempted,
        );
        const status_code = artifact_status_code(result);
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

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    const normalized = if (submit_every == 0) @as(u32, 1) else submit_every;
    if (self.upload_buffer_usage_mode == mode and self.upload_submit_every == normalized) return;
    self.upload_buffer_usage_mode = mode;
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
    const rt = try ensure_runtime_bootstrapped(self);
    self.pending_upload_commands = 0;
    return try rt.flush_queue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    const rt = try ensure_runtime_bootstrapped(self);
    try rt.prewarm_upload_path(max_upload_bytes, self.upload_buffer_usage_mode);
}

pub fn run_contract_path_for_test(
    command: model.Command,
    queue_sync_mode: webgpu.QueueSyncMode,
) !webgpu.NativeExecutionResult {
    if (builtin.os.tag != .windows) {
        return .{
            .status = .unsupported,
            .status_message = "d3d12-native-tests-require-windows",
            .dispatch_count = if (command_info.is_dispatch(command)) command_info.operation_count(command) else 0,
        };
    }

    const profile = model.DeviceProfile{
        .vendor = "amd",
        .api = .d3d12,
        .device_family = "gfx11",
        .driver_version = .{ .major = 24, .minor = 0, .patch = 0 },
    };

    const backend = try ZigD3D12Backend.init(std.testing.allocator, profile, null);
    var iface = try backend.as_iface(std.testing.allocator, "d3d12_contract_test", "d3d12_contract_test_policy");
    defer iface.deinit();
    iface.set_queue_sync_mode(queue_sync_mode);
    return try iface.execute_command(command);
}

fn prewarm_kernel_dispatch(ctx: *anyopaque, kernel: []const u8, bindings: ?[]const model.KernelBinding) anyerror!void {
    _ = ctx;
    _ = kernel;
    _ = bindings;
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
};
