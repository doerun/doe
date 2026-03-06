const std = @import("std");
const model = @import("model.zig");
const webgpu = @import("webgpu_ffi.zig");
const backend_runtime = @import("backend/backend_runtime.zig");
const backend_ids = @import("backend/backend_ids.zig");
const backend_policy = @import("backend/backend_policy.zig");
const backend_telemetry = @import("backend/backend_telemetry.zig");

pub const BackendMode = enum {
    trace,
    native,
};

pub const ExecutionStatus = enum {
    skipped,
    ok,
    unsupported,
    @"error",
};

pub const ExecutionResult = struct {
    backend: []const u8,
    status: ExecutionStatus,
    status_code: []const u8,
    duration_ns: u64,
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
    dispatch_count: u32,
    gpu_timestamp_ns: u64,
    gpu_timestamp_attempted: bool,
    gpu_timestamp_valid: bool,
    backend_selection_reason: ?[]const u8,
    fallback_used: ?bool,
    selection_policy_hash: ?[]const u8,
    shader_artifact_manifest_path: ?[]const u8,
    shader_artifact_manifest_hash: ?[]const u8,
    backend_lane: ?[]const u8,
};

pub const ExecutionContext = struct {
    allocator: std.mem.Allocator,
    mode: BackendMode,
    backend_lane: backend_policy.BackendLane,
    backend: ?backend_runtime.BackendRuntime,

    pub fn init(
        allocator: std.mem.Allocator,
        mode: BackendMode,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        lane: backend_policy.BackendLane,
    ) !ExecutionContext {
        switch (mode) {
            .trace => {
                return .{
                    .allocator = allocator,
                    .mode = .trace,
                    .backend_lane = lane,
                    .backend = null,
                };
            },
            .native => {
                const native_backend = try backend_runtime.BackendRuntime.init(allocator, profile, kernel_root, lane);
                return .{
                    .allocator = allocator,
                    .mode = .native,
                    .backend_lane = lane,
                    .backend = native_backend,
                };
            },
        }
    }

    pub fn deinit(self: *ExecutionContext) void {
        if (self.backend) |*backend| {
            backend.deinit();
        }
        _ = self.allocator;
        self.backend = null;
    }

    pub fn telemetry(self: *ExecutionContext) ?backend_telemetry.BackendTelemetry {
        if (self.backend) |*backend| {
            return backend.telemetry();
        }
        return null;
    }

    pub fn execute(self: *ExecutionContext, command: model.Command) !ExecutionResult {
        const mode_name = executionModeName(self.mode);
        const mode_result = ExecutionResult{
            .backend = mode_name,
            .status = .skipped,
            .status_code = "disabled",
            .duration_ns = 0,
            .setup_ns = 0,
            .encode_ns = 0,
            .submit_wait_ns = 0,
            .dispatch_count = 0,
            .gpu_timestamp_ns = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
            .backend_selection_reason = null,
            .fallback_used = null,
            .selection_policy_hash = null,
            .shader_artifact_manifest_path = null,
            .shader_artifact_manifest_hash = null,
            .backend_lane = null,
        };

        if (self.mode == .trace) return mode_result;
        if (self.backend == null) {
            return .{
                .backend = mode_name,
                .status = .@"error",
                .status_code = "missing-backend",
                .duration_ns = 0,
                .setup_ns = 0,
                .encode_ns = 0,
                .submit_wait_ns = 0,
                .dispatch_count = 0,
                .gpu_timestamp_ns = 0,
                .gpu_timestamp_attempted = false,
                .gpu_timestamp_valid = false,
                .backend_selection_reason = null,
                .fallback_used = null,
                .selection_policy_hash = null,
                .shader_artifact_manifest_path = null,
                .shader_artifact_manifest_hash = null,
                .backend_lane = backendLaneName(self.backend_lane),
            };
        }

        if (self.backend) |*backend| {
            const backend_telemetry_snapshot = backend.telemetry();
            const command_start = std.time.nanoTimestamp();
            const status = backend.execute_command(command) catch |err| {
                const command_end = std.time.nanoTimestamp();
                const elapsed_ns = if (command_end > command_start)
                    @as(u64, @intCast(command_end - command_start))
                else
                    0;
                const command_telemetry = backend.telemetry();
                return .{
                    .backend = backendIdName(backend_telemetry_snapshot.backend_id),
                    .status = .@"error",
                    .status_code = @errorName(err),
                    .duration_ns = elapsed_ns,
                    .setup_ns = 0,
                    .encode_ns = 0,
                    .submit_wait_ns = 0,
                    .dispatch_count = 0,
                    .gpu_timestamp_ns = 0,
                    .gpu_timestamp_attempted = false,
                    .gpu_timestamp_valid = false,
                    .backend_selection_reason = command_telemetry.backend_selection_reason,
                    .fallback_used = command_telemetry.fallback_used,
                    .selection_policy_hash = command_telemetry.selection_policy_hash,
                    .shader_artifact_manifest_path = command_telemetry.shader_artifact_manifest_path,
                    .shader_artifact_manifest_hash = command_telemetry.shader_artifact_manifest_hash,
                    .backend_lane = backendLaneName(self.backend_lane),
                };
            };
            const command_end = std.time.nanoTimestamp();
            const elapsed_ns = if (command_end > command_start)
                @as(u64, @intCast(command_end - command_start))
            else
                0;
            const command_telemetry = backend.telemetry();

            return .{
                .backend = backendIdName(backend_telemetry_snapshot.backend_id),
                .status = if (status.status == .ok) .ok else if (status.status == .@"error") .@"error" else .unsupported,
                .status_code = status.status_message,
                .duration_ns = elapsed_ns,
                .setup_ns = status.setup_ns,
                .encode_ns = status.encode_ns,
                .submit_wait_ns = status.submit_wait_ns,
                .dispatch_count = status.dispatch_count,
                .gpu_timestamp_ns = status.gpu_timestamp_ns,
                .gpu_timestamp_attempted = status.gpu_timestamp_attempted,
                .gpu_timestamp_valid = status.gpu_timestamp_valid,
                .backend_selection_reason = command_telemetry.backend_selection_reason,
                .fallback_used = command_telemetry.fallback_used,
                .selection_policy_hash = command_telemetry.selection_policy_hash,
                .shader_artifact_manifest_path = command_telemetry.shader_artifact_manifest_path,
                .shader_artifact_manifest_hash = command_telemetry.shader_artifact_manifest_hash,
                .backend_lane = backendLaneName(self.backend_lane),
            };
        }

        return .{
            .backend = mode_name,
            .status = .@"error",
            .status_code = "missing-backend",
            .duration_ns = 0,
            .setup_ns = 0,
            .encode_ns = 0,
            .submit_wait_ns = 0,
            .dispatch_count = 0,
            .gpu_timestamp_ns = 0,
            .gpu_timestamp_attempted = false,
            .gpu_timestamp_valid = false,
            .backend_selection_reason = null,
            .fallback_used = null,
            .selection_policy_hash = null,
            .shader_artifact_manifest_path = null,
            .shader_artifact_manifest_hash = null,
            .backend_lane = backendLaneName(self.backend_lane),
        };
    }

    pub fn configureUploadBehavior(
        self: *ExecutionContext,
        usage_mode: UploadBufferUsageMode,
        submit_every: u32,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.set_upload_behavior(usage_mode, submit_every);
        }
    }

    pub fn configureQueueWaitMode(
        self: *ExecutionContext,
        wait_mode: QueueWaitMode,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.set_queue_wait_mode(wait_mode);
        }
    }

    pub fn configureQueueSyncMode(
        self: *ExecutionContext,
        sync_mode: QueueSyncMode,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.set_queue_sync_mode(sync_mode);
        }
    }

    pub fn configureGpuTimestampMode(
        self: *ExecutionContext,
        timestamp_mode: GpuTimestampMode,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.set_gpu_timestamp_mode(timestamp_mode);
        }
    }

    pub fn flushQueue(self: *ExecutionContext) !u64 {
        if (self.mode != .native) return 0;
        if (self.backend) |*backend| {
            return try backend.flush_queue();
        }
        return 0;
    }

    pub fn prewarmUploadPath(
        self: *ExecutionContext,
        max_upload_bytes: u64,
    ) !void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            try backend.prewarm_upload_path(max_upload_bytes);
        }
    }

    pub fn prewarmKernelDispatch(
        self: *ExecutionContext,
        kernel: []const u8,
        bindings: ?[]const model.KernelBinding,
    ) !void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            try backend.prewarm_kernel_dispatch(kernel, bindings);
        }
    }
};

pub const UploadBufferUsageMode = webgpu.UploadBufferUsageMode;
pub const QueueWaitMode = webgpu.QueueWaitMode;
pub const QueueSyncMode = webgpu.QueueSyncMode;
pub const GpuTimestampMode = webgpu.GpuTimestampMode;

pub fn parseUploadBufferUsage(raw: []const u8) ?UploadBufferUsageMode {
    if (std.ascii.eqlIgnoreCase(raw, "copy-dst-copy-src")) return .copy_dst_copy_src;
    if (std.ascii.eqlIgnoreCase(raw, "copy-dst")) return .copy_dst;
    return null;
}

pub fn parseQueueWaitMode(raw: []const u8) ?QueueWaitMode {
    if (std.ascii.eqlIgnoreCase(raw, "process-events")) return .process_events;
    if (std.ascii.eqlIgnoreCase(raw, "wait-any")) return .wait_any;
    return null;
}

pub fn parseQueueSyncMode(raw: []const u8) ?QueueSyncMode {
    if (std.ascii.eqlIgnoreCase(raw, "per-command")) return .per_command;
    if (std.ascii.eqlIgnoreCase(raw, "deferred")) return .deferred;
    return null;
}

pub fn parseGpuTimestampMode(raw: []const u8) ?GpuTimestampMode {
    if (std.ascii.eqlIgnoreCase(raw, "auto")) return .auto;
    if (std.ascii.eqlIgnoreCase(raw, "off")) return .off;
    if (std.ascii.eqlIgnoreCase(raw, "require")) return .require;
    return null;
}

pub fn parseBackend(raw: []const u8) ?BackendMode {
    if (std.ascii.eqlIgnoreCase(raw, "trace")) return .trace;
    if (std.ascii.eqlIgnoreCase(raw, "native")) return .native;
    if (std.ascii.eqlIgnoreCase(raw, "webgpu")) return .native;
    return null;
}

pub fn parseBackendLane(raw: []const u8) ?backend_policy.BackendLane {
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_release") or std.ascii.eqlIgnoreCase(raw, "vulkan-dawn-release") or std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_release") or std.ascii.eqlIgnoreCase(raw, "vulkan-dawn-release"))
        return .vulkan_dawn_release;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_doe_app") or std.ascii.eqlIgnoreCase(raw, "vulkan-doe-app") or std.ascii.eqlIgnoreCase(raw, "vulkan_doe_app") or std.ascii.eqlIgnoreCase(raw, "vulkan-doe-app"))
        return .vulkan_doe_app;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_app") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-app") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_app") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-app"))
        return .d3d12_doe_app;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_directional") or std.ascii.eqlIgnoreCase(raw, "metal-doe-directional") or std.ascii.eqlIgnoreCase(raw, "metal_doe_directional") or std.ascii.eqlIgnoreCase(raw, "metal-doe-directional"))
        return .metal_doe_directional;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "metal-doe-comparable") or std.ascii.eqlIgnoreCase(raw, "metal_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "metal-doe-comparable"))
        return .metal_doe_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_release") or std.ascii.eqlIgnoreCase(raw, "metal-doe-release") or std.ascii.eqlIgnoreCase(raw, "metal_doe_release") or std.ascii.eqlIgnoreCase(raw, "metal-doe-release"))
        return .metal_doe_release;
    if (std.ascii.eqlIgnoreCase(raw, "metal_dawn_release") or std.ascii.eqlIgnoreCase(raw, "metal-dawn-release"))
        return .metal_dawn_release;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_directional") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-directional") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_directional") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-directional"))
        return .d3d12_doe_directional;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-comparable") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-comparable"))
        return .d3d12_doe_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_release") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-release") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_release") or std.ascii.eqlIgnoreCase(raw, "d3d12-doe-release"))
        return .d3d12_doe_release;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_dawn_release") or std.ascii.eqlIgnoreCase(raw, "d3d12-dawn-release"))
        return .d3d12_dawn_release;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_directional") or std.ascii.eqlIgnoreCase(raw, "vulkan-dawn-directional") or std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_directional") or std.ascii.eqlIgnoreCase(raw, "vulkan-dawn-directional"))
        return .vulkan_dawn_directional;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "vulkan-doe-comparable") or std.ascii.eqlIgnoreCase(raw, "vulkan_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "vulkan-doe-comparable"))
        return .vulkan_doe_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_doe_release") or std.ascii.eqlIgnoreCase(raw, "vulkan-doe-release") or std.ascii.eqlIgnoreCase(raw, "vulkan_doe_release") or std.ascii.eqlIgnoreCase(raw, "vulkan-doe-release"))
        return .vulkan_doe_release;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_app") or std.ascii.eqlIgnoreCase(raw, "metal-doe-app") or std.ascii.eqlIgnoreCase(raw, "metal_doe_app") or std.ascii.eqlIgnoreCase(raw, "metal-doe-app"))
        return .metal_doe_app;
    return null;
}

pub fn defaultBackendLane(profile: model.DeviceProfile) backend_policy.BackendLane {
    return switch (profile.api) {
        .metal => .metal_doe_app,
        .d3d12 => .d3d12_doe_app,
        else => .vulkan_doe_app,
    };
}

pub fn backendLaneName(lane: backend_policy.BackendLane) []const u8 {
    return switch (lane) {
        .vulkan_dawn_release => "vulkan_dawn_release",
        .vulkan_doe_app => "vulkan_doe_app",
        .d3d12_doe_app => "d3d12_doe_app",
        .metal_doe_directional => "metal_doe_directional",
        .metal_doe_comparable => "metal_doe_comparable",
        .metal_doe_release => "metal_doe_release",
        .metal_dawn_release => "metal_dawn_release",
        .d3d12_doe_directional => "d3d12_doe_directional",
        .d3d12_doe_comparable => "d3d12_doe_comparable",
        .d3d12_doe_release => "d3d12_doe_release",
        .d3d12_dawn_release => "d3d12_dawn_release",
        .vulkan_dawn_directional => "vulkan_dawn_directional",
        .vulkan_doe_comparable => "vulkan_doe_comparable",
        .vulkan_doe_release => "vulkan_doe_release",
        .metal_doe_app => "metal_doe_app",
    };
}

pub fn backendIdName(id: backend_ids.BackendId) []const u8 {
    return backend_ids.backendIdName(id);
}

pub fn executionModeName(mode: BackendMode) []const u8 {
    return switch (mode) {
        .trace => "trace",
        .native => "webgpu-ffi",
    };
}

pub fn executionStatusName(status: ExecutionStatus) []const u8 {
    return switch (status) {
        .skipped => "skipped",
        .ok => "ok",
        .unsupported => "unsupported",
        .@"error" => "error",
    };
}
