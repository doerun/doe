const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");

pub const CopyMetrics = struct {
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
};

pub fn execute_copy(self: anytype, cmd: model.CopyCommand, queue_sync_mode: webgpu.QueueSyncMode) !CopyMetrics {
    _ = self;
    _ = cmd;
    _ = queue_sync_mode;
    return error.UnsupportedFeature;
}
