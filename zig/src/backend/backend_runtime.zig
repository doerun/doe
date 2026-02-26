const std = @import("std");
const model = @import("../model.zig");
const webgpu = @import("../webgpu_ffi.zig");
const backend_iface = @import("backend_iface.zig");
const backend_policy = @import("backend_policy.zig");
const backend_registry = @import("backend_registry.zig");
const backend_selection = @import("backend_selection.zig");
const backend_telemetry = @import("backend_telemetry.zig");

pub const BackendRuntime = struct {
    allocator: std.mem.Allocator,
    backend: backend_iface.BackendIface,

    pub fn init(
        allocator: std.mem.Allocator,
        profile: model.DeviceProfile,
        kernel_root: ?[]const u8,
        lane: backend_policy.BackendLane,
    ) !BackendRuntime {
        const policy = backend_policy.default_policy_for_lane(lane);
        const selected = backend_selection.select_backend(profile, policy);
        return .{
            .allocator = allocator,
            .backend = try backend_registry.init_backend(
                allocator,
                selected.backend_id,
                profile,
                kernel_root,
                selected.reason,
                policy.policy_hash,
            ),
        };
    }

    pub fn deinit(self: *BackendRuntime) void {
        self.backend.deinit();
    }

    pub fn execute_command(self: *BackendRuntime, command: model.Command) !webgpu.NativeExecutionResult {
        return try self.backend.execute_command(command);
    }

    pub fn set_upload_behavior(self: *BackendRuntime, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
        self.backend.set_upload_behavior(mode, submit_every);
    }

    pub fn set_queue_wait_mode(self: *BackendRuntime, mode: webgpu.QueueWaitMode) void {
        self.backend.set_queue_wait_mode(mode);
    }

    pub fn set_queue_sync_mode(self: *BackendRuntime, mode: webgpu.QueueSyncMode) void {
        self.backend.set_queue_sync_mode(mode);
    }

    pub fn set_gpu_timestamp_mode(self: *BackendRuntime, mode: webgpu.GpuTimestampMode) void {
        self.backend.set_gpu_timestamp_mode(mode);
    }

    pub fn flush_queue(self: *BackendRuntime) !u64 {
        return try self.backend.flush_queue();
    }

    pub fn prewarm_upload_path(self: *BackendRuntime, max_upload_bytes: u64) !void {
        try self.backend.prewarm_upload_path(max_upload_bytes);
    }

    pub fn telemetry(self: *BackendRuntime) backend_telemetry.BackendTelemetry {
        return self.backend.telemetry;
    }
};
