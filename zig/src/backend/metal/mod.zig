const builtin = @import("builtin");
const std = @import("std");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");
const surface_procs = @import("../../wgpu_surface_procs.zig");
const backend_iface = @import("../backend_iface.zig");
const common_errors = @import("../common/errors.zig");
const common_timing = @import("../common/timing.zig");
const command_info = @import("../common/command_info.zig");
const capabilities = @import("../common/capabilities.zig");
const artifact_meta = @import("../common/artifact_meta.zig");

const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const MANIFEST_PATH_CAPACITY: usize = 256;
const HASH_HEX_SIZE: usize = 64;
const MANIFEST_CONTENT_CAPACITY: usize = 2048;
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";
const HEX = "0123456789abcdef";

pub const ZigMetalBackend = struct {
    allocator: std.mem.Allocator,
    inner: webgpu.WebGPUBackend,
    capability_set: capabilities.CapabilitySet,
    upload_buffer_usage_mode: webgpu.UploadBufferUsageMode = .copy_dst_copy_src,
    upload_submit_every: u32 = 1,
    queue_wait_mode: webgpu.QueueWaitMode = .process_events,
    queue_sync_mode: webgpu.QueueSyncMode = .per_command,
    gpu_timestamp_mode: webgpu.GpuTimestampMode = .auto,
    manifest_emit_count: u64 = 0,
    manifest_path_storage: [MANIFEST_PATH_CAPACITY]u8 = std.mem.zeroes([MANIFEST_PATH_CAPACITY]u8),
    manifest_path_len: usize = 0,
    manifest_hash_storage: [HASH_HEX_SIZE]u8 = std.mem.zeroes([HASH_HEX_SIZE]u8),
    manifest_hash_len: usize = 0,

    pub fn init(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
    ) !*ZigMetalBackend {
        if (profile.api != .metal) return common_errors.BackendNativeError.UnsupportedFeature;
        if (builtin.os.tag != .macos) return common_errors.BackendNativeError.UnsupportedFeature;

        const ptr = try allocator.create(ZigMetalBackend);
        errdefer allocator.destroy(ptr);

        var inner = try webgpu.WebGPUBackend.init(allocator, profile, kernel_root);
        errdefer inner.deinit();

        ptr.* = .{
            .allocator = allocator,
            .inner = inner,
            .capability_set = default_capability_set(),
            .upload_buffer_usage_mode = .copy_dst_copy_src,
            .upload_submit_every = 1,
            .queue_wait_mode = .process_events,
            .queue_sync_mode = .per_command,
            .gpu_timestamp_mode = .auto,
            .manifest_emit_count = 0,
            .manifest_path_storage = std.mem.zeroes([MANIFEST_PATH_CAPACITY]u8),
            .manifest_path_len = 0,
            .manifest_hash_storage = std.mem.zeroes([HASH_HEX_SIZE]u8),
            .manifest_hash_len = 0,
        };

        ptr.inner.setUploadBehavior(ptr.upload_buffer_usage_mode, ptr.upload_submit_every);
        ptr.inner.setQueueWaitMode(ptr.queue_wait_mode);
        ptr.inner.setQueueSyncMode(ptr.queue_sync_mode);
        ptr.inner.setGpuTimestampMode(ptr.gpu_timestamp_mode);
        ptr.refresh_capabilities();

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

    fn refresh_capabilities(self: *ZigMetalBackend) void {
        var caps = default_capability_set();

        if (self.inner.has_multi_draw_indirect) {
            caps.declare(.indirect_draw);
            caps.declare(.indexed_indirect_draw);
        }
        if (self.inner.has_timestamp_query) {
            caps.declare(.gpu_timestamps);
        }
        if (self.inner.has_timestamp_inside_passes) {
            caps.declare(.timestamp_inside_passes);
        }
        if (surface_procs.loadSurfaceProcs(self.inner.dyn_lib) != null) {
            caps.declare(.surface_lifecycle);
            caps.declare(.surface_present);
        }

        self.capability_set = caps;
    }

    fn previous_manifest_hash(self: *const ZigMetalBackend) []const u8 {
        return self.manifest_hash() orelse ZERO_HASH;
    }

    fn emit_shader_artifact_manifest(
        self: *ZigMetalBackend,
        command: model.Command,
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
                command_info.manifest_module(command),
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
    }
};

fn default_capability_set() capabilities.CapabilitySet {
    var set = capabilities.CapabilitySet{};
    set.declare_all(&.{
        .kernel_dispatch,
        .buffer_upload,
        .buffer_copy,
        .barrier_sync,
        .sampler_lifecycle,
        .texture_write,
        .texture_query,
        .texture_destroy,
        .async_diagnostics,
        .map_async,
        .render_pass,
        .render_draw,
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
        .async_diagnostics,
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

fn cast(ctx: *anyopaque) *ZigMetalBackend {
    return @as(*ZigMetalBackend, @ptrCast(@alignCast(ctx)));
}

pub fn manifest_path_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).manifest_path();
}

pub fn manifest_hash_from_context(ctx: *anyopaque) ?[]const u8 {
    return cast(ctx).manifest_hash();
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    const allocator = self.allocator;
    self.inner.deinit();
    allocator.destroy(self);
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    self.refresh_capabilities();
    const required = capabilities.required_capabilities(command);
    if (self.capability_set.missing(required)) |missing_cap| {
        return .{
            .status = .unsupported,
            .status_message = capabilities.capability_name(missing_cap),
            .dispatch_count = if (command_info.is_dispatch(command)) command_info.operation_count(command) else 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    }

    const execute_start = try common_timing.operation_timing_ns();
    var native_result = self.inner.executeCommand(command) catch |err| {
        const execute_end = try common_timing.operation_timing_ns();
        _ = common_timing.ns_delta(execute_end, execute_start);
        return .{
            .status = common_errors.map_error_status(err),
            .status_message = common_errors.error_code(err),
            .dispatch_count = if (command_info.is_dispatch(command)) command_info.operation_count(command) else 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
        };
    };
    const execute_end = try common_timing.operation_timing_ns();
    _ = common_timing.ns_delta(execute_end, execute_start);

    if (command_info.is_dispatch(command) and native_result.dispatch_count == 0) {
        native_result.dispatch_count = command_info.operation_count(command);
    }

    const meta = artifact_meta.classify(
        .native_metal,
        native_result.gpu_timestamp_valid,
        native_result.gpu_timestamp_attempted,
    );
    if (should_emit_shader_artifact(command)) {
        self.emit_shader_artifact_manifest(command, meta, artifact_status_code(native_result)) catch |err| {
            native_result.status = common_errors.map_error_status(err);
            native_result.status_message = common_errors.error_code(err);
        };
    }

    return native_result;
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    self.upload_buffer_usage_mode = mode;
    self.upload_submit_every = if (submit_every == 0) 1 else submit_every;
    self.inner.setUploadBehavior(self.upload_buffer_usage_mode, self.upload_submit_every);
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    const self = cast(ctx);
    self.queue_wait_mode = mode;
    self.inner.setQueueWaitMode(mode);
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    const self = cast(ctx);
    self.queue_sync_mode = mode;
    self.inner.setQueueSyncMode(mode);
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    const self = cast(ctx);
    self.gpu_timestamp_mode = mode;
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
        => true,
        else => false,
    };
}

pub fn run_contract_path_for_test(command: model.Command, queue_sync_mode: webgpu.QueueSyncMode) !void {
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
