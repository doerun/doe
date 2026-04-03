pub const NativeExecutionStatus = enum {
    ok,
    unsupported,
    @"error",
};

pub const NativeExecutionResult = struct {
    status: NativeExecutionStatus,
    status_message: []const u8,
    setup_ns: u64 = 0,
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    dispatch_count: u32 = 0,
    gpu_timestamp_ns: u64 = 0,
    gpu_timestamp_attempted: bool = false,
    gpu_timestamp_valid: bool = false,
};
