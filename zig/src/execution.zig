const std = @import("std");
const model = @import("model.zig");
const webgpu = @import("webgpu_ffi.zig");

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
};

pub const ExecutionContext = struct {
    allocator: std.mem.Allocator,
    mode: BackendMode,
    backend: ?webgpu.WebGPUBackend,

    pub fn init(
        allocator: std.mem.Allocator,
        mode: BackendMode,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
    ) !ExecutionContext {
        switch (mode) {
            .trace => {
                return .{
                    .allocator = allocator,
                    .mode = .trace,
                    .backend = null,
                };
            },
            .native => {
                const native_backend = try webgpu.WebGPUBackend.init(allocator, profile, kernel_root);
                return .{
                    .allocator = allocator,
                    .mode = .native,
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

    pub fn execute(self: *ExecutionContext, command: model.Command) !ExecutionResult {
        const mode_name = executionModeName(self.mode);
        const fallback = ExecutionResult{
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
        };

        if (self.mode == .trace) return fallback;
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
            };
        }

        const command_start = std.time.nanoTimestamp();
        if (self.backend) |*backend| {
            const status = backend.executeCommand(command) catch |err| {
                const command_end = std.time.nanoTimestamp();
                const elapsed_ns = if (command_end > command_start)
                    @as(u64, @intCast(command_end - command_start))
                else
                    0;
                return .{
                    .backend = mode_name,
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
                };
            };
            const command_end = std.time.nanoTimestamp();
            const elapsed_ns = if (command_end > command_start)
                @as(u64, @intCast(command_end - command_start))
            else
                0;

            return .{
                .backend = mode_name,
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
        };
    }

    pub fn configureUploadBehavior(
        self: *ExecutionContext,
        usage_mode: UploadBufferUsageMode,
        submit_every: u32,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.setUploadBehavior(usage_mode, submit_every);
        }
    }

    pub fn configureQueueWaitMode(
        self: *ExecutionContext,
        wait_mode: QueueWaitMode,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.setQueueWaitMode(wait_mode);
        }
    }

    pub fn configureQueueSyncMode(
        self: *ExecutionContext,
        sync_mode: QueueSyncMode,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.setQueueSyncMode(sync_mode);
        }
    }

    pub fn configureGpuTimestampMode(
        self: *ExecutionContext,
        timestamp_mode: GpuTimestampMode,
    ) void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            backend.setGpuTimestampMode(timestamp_mode);
        }
    }

    pub fn flushQueue(self: *ExecutionContext) !u64 {
        if (self.mode != .native) return 0;
        if (self.backend) |*backend| {
            return try backend.flushQueue();
        }
        return 0;
    }

    pub fn prewarmUploadPath(
        self: *ExecutionContext,
        max_upload_bytes: u64,
    ) !void {
        if (self.mode != .native) return;
        if (self.backend) |*backend| {
            try backend.prewarmUploadPath(max_upload_bytes);
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
    return null;
}

pub fn parseBackend(raw: []const u8) ?BackendMode {
    if (std.ascii.eqlIgnoreCase(raw, "trace")) return .trace;
    if (std.ascii.eqlIgnoreCase(raw, "native")) return .native;
    if (std.ascii.eqlIgnoreCase(raw, "webgpu")) return .native;
    return null;
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
