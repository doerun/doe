const types = @import("../core/abi/wgpu_types.zig");

pub const NativeExecutionStatus = types.NativeExecutionStatus;
pub const NativeExecutionResult = types.NativeExecutionResult;

pub const UploadBufferUsageMode = enum {
    copy_dst_copy_src,
    copy_dst,
};

pub const QueueWaitMode = enum {
    process_events,
    wait_any,
};

pub const QueueSyncMode = enum {
    per_command,
    deferred,
};

pub const GpuTimestampMode = enum {
    auto,
    off,
    require,
};
