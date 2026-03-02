const std = @import("std");
const model = @import("../model.zig");
const webgpu = @import("../webgpu_ffi.zig");
const backend_ids = @import("backend_ids.zig");
const backend_iface = @import("backend_iface.zig");
const backend_telemetry = @import("backend_telemetry.zig");

pub const DawnDelegateBackend = struct {
    allocator: std.mem.Allocator,
    inner: webgpu.WebGPUBackend,

    pub fn init(allocator: std.mem.Allocator, profile: model.DeviceProfile, kernel_root: ?[]const u8) !*DawnDelegateBackend {
        const ptr = try allocator.create(DawnDelegateBackend);
        errdefer allocator.destroy(ptr);
        ptr.* = .{
            .allocator = allocator,
            .inner = try webgpu.WebGPUBackend.init(allocator, profile, kernel_root),
        };
        return ptr;
    }

    pub fn as_iface(self: *DawnDelegateBackend, allocator: std.mem.Allocator, reason: []const u8, policy_hash: []const u8) !backend_iface.BackendIface {
        _ = allocator;
        return .{
            .id = .dawn_delegate,
            .context = self,
            .vtable = &VTABLE,
            .telemetry = .{
                .backend_id = .dawn_delegate,
                .backend_selection_reason = reason,
                .fallback_used = false,
                .selection_policy_hash = policy_hash,
                .shader_artifact_manifest_path = null,
                .shader_artifact_manifest_hash = null,
            },
        };
    }
};

fn cast(ctx: *anyopaque) *DawnDelegateBackend {
    return @as(*DawnDelegateBackend, @ptrCast(@alignCast(ctx)));
}

fn deinit(ctx: *anyopaque) void {
    const self = cast(ctx);
    const allocator = self.allocator;
    self.inner.deinit();
    allocator.destroy(self);
}

fn execute_command(ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult {
    const self = cast(ctx);
    return try self.inner.executeCommand(command);
}

fn set_upload_behavior(ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
    const self = cast(ctx);
    self.inner.setUploadBehavior(mode, submit_every);
}

fn set_queue_wait_mode(ctx: *anyopaque, mode: webgpu.QueueWaitMode) void {
    const self = cast(ctx);
    self.inner.setQueueWaitMode(mode);
}

fn set_queue_sync_mode(ctx: *anyopaque, mode: webgpu.QueueSyncMode) void {
    const self = cast(ctx);
    self.inner.setQueueSyncMode(mode);
}

fn set_gpu_timestamp_mode(ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void {
    const self = cast(ctx);
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
