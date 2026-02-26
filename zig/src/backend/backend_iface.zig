const model = @import("../model.zig");
const webgpu = @import("../webgpu_ffi.zig");
const backend_ids = @import("backend_ids.zig");
const backend_telemetry = @import("backend_telemetry.zig");

pub const BackendVTable = struct {
    deinit: *const fn (ctx: *anyopaque) void,
    execute_command: *const fn (ctx: *anyopaque, command: model.Command) anyerror!webgpu.NativeExecutionResult,
    set_upload_behavior: *const fn (ctx: *anyopaque, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void,
    set_queue_wait_mode: *const fn (ctx: *anyopaque, mode: webgpu.QueueWaitMode) void,
    set_queue_sync_mode: *const fn (ctx: *anyopaque, mode: webgpu.QueueSyncMode) void,
    set_gpu_timestamp_mode: *const fn (ctx: *anyopaque, mode: webgpu.GpuTimestampMode) void,
    flush_queue: *const fn (ctx: *anyopaque) anyerror!u64,
    prewarm_upload_path: *const fn (ctx: *anyopaque, max_upload_bytes: u64) anyerror!void,
};

pub const BackendIface = struct {
    id: backend_ids.BackendId,
    context: *anyopaque,
    vtable: *const BackendVTable,
    telemetry: backend_telemetry.BackendTelemetry,

    pub fn deinit(self: *BackendIface) void {
        self.vtable.deinit(self.context);
    }

    pub fn execute_command(self: *BackendIface, command: model.Command) !webgpu.NativeExecutionResult {
        return try self.vtable.execute_command(self.context, command);
    }

    pub fn set_upload_behavior(self: *BackendIface, mode: webgpu.UploadBufferUsageMode, submit_every: u32) void {
        self.vtable.set_upload_behavior(self.context, mode, submit_every);
    }

    pub fn set_queue_wait_mode(self: *BackendIface, mode: webgpu.QueueWaitMode) void {
        self.vtable.set_queue_wait_mode(self.context, mode);
    }

    pub fn set_queue_sync_mode(self: *BackendIface, mode: webgpu.QueueSyncMode) void {
        self.vtable.set_queue_sync_mode(self.context, mode);
    }

    pub fn set_gpu_timestamp_mode(self: *BackendIface, mode: webgpu.GpuTimestampMode) void {
        self.vtable.set_gpu_timestamp_mode(self.context, mode);
    }

    pub fn flush_queue(self: *BackendIface) !u64 {
        return try self.vtable.flush_queue(self.context);
    }

    pub fn prewarm_upload_path(self: *BackendIface, max_upload_bytes: u64) !void {
        try self.vtable.prewarm_upload_path(self.context, max_upload_bytes);
    }
};
