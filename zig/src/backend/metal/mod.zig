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
const native_runtime = if (builtin.os.tag == .macos)
    @import("metal_native_runtime.zig")
else
    @import("metal_native_runtime_stub.zig");

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

pub const ZigMetalBackend = struct {
    allocator: std.mem.Allocator,
    runtime: ?native_runtime.NativeMetalRuntime = null,
    kernel_root_owned: ?[]u8 = null,

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
                .adapter_ordinal = null,
                .queue_family_index = null,
                .present_capable = null,
            },
        };
    }

    fn manifest_path(self: *const ZigMetalBackend) ?[]const u8 {
        if (self.manifest_path_len == 0) return null;
        return self.manifest_path_storage[0..self.manifest_path_len];
    }

    fn manifest_hash(self: *const ZigMetalBackend) ?[]const u8 {
        if (self.manifest_hash_len == 0) return null;
        return self.manifest_hash_storage[0..self.manifest_hash_len];
    }

    fn previous_manifest_hash(self: *const ZigMetalBackend) []const u8 {
        return self.manifest_hash() orelse ZERO_HASH;
    }

    fn flush_pending_artifact(self: *ZigMetalBackend) void {
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
        self: *ZigMetalBackend,
        module: []const u8,
        meta: artifact_meta.ArtifactMeta,
        status_code: []const u8,
    ) common_errors.BackendNativeError!void {
        self.manifest_emit_count +|= 1;

        var path_buffer: [MANIFEST_PATH_CAPACITY]u8 = undefined;
        const path = std.fmt.bufPrint(
            &path_buffer,
            "{s}/metal_shader_artifact_{d}.json",
            .{ SHADER_ARTIFACT_DIR, self.manifest_emit_count },
        ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

        var content_buffer: [MANIFEST_CONTENT_CAPACITY]u8 = undefined;
        const content = std.fmt.bufPrint(
            &content_buffer,
            "{{\"backendId\":\"doe_metal\",\"backendKind\":\"{s}\",\"timingSource\":\"{s}\",\"comparability\":\"{s}\",\"claimable\":{},\"module\":\"{s}\",\"statusCode\":\"{s}\",\"previousManifestHash\":\"{s}\"}}\n",
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
        .sampler_lifecycle,
        .texture_write,
        .texture_query,
        .texture_destroy,
        .render_draw,
        .render_pass,
        .indirect_draw,
        .indexed_indirect_draw,
        .async_diagnostics,
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

fn persist_manifest_path(self: *ZigMetalBackend, value: []const u8) void {
    if (value.len > self.manifest_path_storage.len) {
        self.manifest_path_len = 0;
        return;
    }
    std.mem.copyForwards(u8, self.manifest_path_storage[0..value.len], value);
    self.manifest_path_len = value.len;
}

fn persist_manifest_hash(self: *ZigMetalBackend, value: []const u8) void {
    if (value.len > self.manifest_hash_storage.len) {
        self.manifest_hash_len = 0;
        return;
    }
    std.mem.copyForwards(u8, self.manifest_hash_storage[0..value.len], value);
    self.manifest_hash_len = value.len;
}

fn manifest_signature_matches(
    self: *const ZigMetalBackend,
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
    self: *ZigMetalBackend,
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

fn execute_upload(self: *ZigMetalBackend, setup_ns: u64, upload: model.UploadCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);

    const encode_start = common_timing.now_ns();
    try rt.upload_bytes(@as(u64, @intCast(upload.bytes)), self.upload_buffer_usage_mode);
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

    // Uploads always deferred: batch-encode all blits into a single command
    // buffer at the next non-upload command (barrier, render_draw, etc.).
    // This matches Dawn's internal batching semantics.
    self.pending_upload_commands +|= 1;

    return ok_result(setup_ns, encode_ns, 0, 0);
}

fn execute_barrier(self: *ZigMetalBackend, setup_ns: u64) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const submit_wait_ns = try rt.barrier(self.queue_wait_mode);
    return ok_result(setup_ns, 0, submit_wait_ns, 0);
}

fn execute_kernel_dispatch(self: *ZigMetalBackend, setup_ns: u64, kd: model.KernelDispatchCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const metrics = try rt.run_kernel_dispatch(
        kd.kernel, kd.x, kd.y, kd.z,
        kd.repeat, kd.warmup_dispatch_count,
        kd.bindings,
    );
    return ok_result(setup_ns, metrics.encode_ns, metrics.submit_wait_ns, metrics.dispatch_count);
}

fn execute_sampler_create(self: *ZigMetalBackend, setup_ns: u64, cmd: model.SamplerCreateCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.sampler_create(cmd);
    return ok_result(setup_ns, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_sampler_destroy(self: *ZigMetalBackend, setup_ns: u64, cmd: model.SamplerDestroyCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.sampler_destroy(cmd);
    return ok_result(setup_ns, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_texture_write(self: *ZigMetalBackend, setup_ns: u64, cmd: model.TextureWriteCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.texture_write(cmd);
    return ok_result(setup_ns, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_texture_query(self: *ZigMetalBackend, setup_ns: u64, cmd: model.TextureQueryCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.texture_query(cmd);
    return ok_result(setup_ns, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_texture_destroy(self: *ZigMetalBackend, setup_ns: u64, cmd: model.TextureDestroyCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const encode_start = common_timing.now_ns();
    try rt.texture_destroy(cmd);
    return ok_result(setup_ns, common_timing.ns_delta(common_timing.now_ns(), encode_start), 0, 0);
}

fn execute_render_draw(self: *ZigMetalBackend, setup_ns: u64, cmd: model.RenderDrawCommand) !webgpu.NativeExecutionResult {
    const rt = get_runtime(self);
    const metrics = try rt.render_draw(cmd);
    return ok_result(setup_ns, metrics.encode_ns, metrics.submit_wait_ns, metrics.draw_count);
}

fn execute_async_diagnostics(self: *ZigMetalBackend, setup_ns: u64, cmd: model.AsyncDiagnosticsCommand) !webgpu.NativeExecutionResult {
    // Measures native render pipeline creation/cache time for the given format.
    // Equivalent to what Dawn's async pipeline creation diagnostic tests measure.
    const rt = get_runtime(self);
    const fmt = cmd.target_format;
    const encode_start = common_timing.now_ns();
    try rt.ensure_render_pipeline(fmt);
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
    return ok_result(setup_ns, encode_ns, 0, 1);
}

fn prewarm_kernel_dispatch(ctx: *anyopaque, kernel: []const u8, bindings: ?[]const model.KernelBinding) anyerror!void {
    const self = cast(ctx);
    const rt = get_runtime(self);
    _ = try rt.ensure_kernel_pipeline(kernel);
    if (bindings) |bs| {
        for (bs) |b| {
            if (b.resource_kind != .buffer) continue;
            _ = try rt.ensure_compute_buffer(b.resource_handle, b.buffer_size);
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

    const pending_submit_wait_ns = try flush_pending_uploads_if_required(self, command);

    var result = switch (command) {
        .upload => |upload| try execute_upload(self, 0, upload),
        .barrier => try execute_barrier(self, 0),
        .kernel_dispatch => |kd| try execute_kernel_dispatch(self, 0, kd),
        .sampler_create => |cmd| try execute_sampler_create(self, 0, cmd),
        .sampler_destroy => |cmd| try execute_sampler_destroy(self, 0, cmd),
        .texture_write => |cmd| try execute_texture_write(self, 0, cmd),
        .texture_query => |cmd| try execute_texture_query(self, 0, cmd),
        .texture_destroy => |cmd| try execute_texture_destroy(self, 0, cmd),
        .render_draw => |cmd| try execute_render_draw(self, 0, cmd),
        .draw_indirect => |cmd| try execute_render_draw(self, 0, cmd),
        .draw_indexed_indirect => |cmd| try execute_render_draw(self, 0, cmd),
        .render_pass => |cmd| try execute_render_draw(self, 0, cmd),
        .async_diagnostics => |cmd| try execute_async_diagnostics(self, 0, cmd),
        else => return error.Unsupported,
    };
    result.submit_wait_ns +|= pending_submit_wait_ns;

    if (should_emit_shader_artifact(command)) {
        const meta = artifact_meta.classify(
            .native_metal,
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
    const rt = get_runtime(self);
    self.pending_upload_commands = 0;
    return try rt.flush_queue();
}

fn prewarm_upload_path(ctx: *anyopaque, max_upload_bytes: u64) anyerror!void {
    const self = cast(ctx);
    const rt = get_runtime(self);
    try rt.prewarm_upload_path(max_upload_bytes, self.upload_buffer_usage_mode);
}

pub fn run_contract_path_for_test(command: model.Command, queue_sync_mode: webgpu.QueueSyncMode) !void {
    if (builtin.os.tag != .macos) return;
    const profile = model.DeviceProfile{
        .vendor = "apple",
        .api = .metal,
        .device_family = "m3",
        .driver_version = .{ .major = 1, .minor = 0, .patch = 0 },
    };

    const backend = ZigMetalBackend.init(std.testing.allocator, profile, null) catch |err| {
        if (is_runtime_unavailable_for_test(err)) return;
        return err;
    };
    var iface = try backend.as_iface(std.testing.allocator, "test_metal_contract", "test_policy_hash");
    defer iface.deinit();

    iface.set_queue_sync_mode(queue_sync_mode);
    _ = try iface.execute_command(command);
}

fn is_runtime_unavailable_for_test(err: anyerror) bool {
    return switch (err) {
        error.LibraryOpenFailed,
        error.SymbolMissing,
        error.AdapterUnavailable,
        error.AdapterRequestFailed,
        error.AdapterRequestNoCallback,
        error.DeviceRequestFailed,
        error.DeviceRequestNoCallback,
        error.NativeInstanceUnavailable,
        error.NativeQueueUnavailable,
        error.UnsupportedFeature,
        => true,
        else => false,
    };
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
