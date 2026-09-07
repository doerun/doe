pub const BufferCopyError = error{
    InvalidArgument,
    BufferCopyDeviceMismatch,
    BufferCopyUsageMissing,
    BufferCopyUnaligned,
    BufferCopyOutOfBounds,
    BufferCopyAliasing,
};

pub const Failure = BufferCopyError || error{ OutOfMemory, InvalidState, ImmediateDataUnsupported };

pub fn message(cause: Failure) []const u8 {
    return switch (cause) {
        error.OutOfMemory => "GPU command recording could not allocate owned storage",
        error.InvalidState => "GPU command recording requires an open encoder or its active pass",
        error.InvalidArgument => "GPU command recording received an invalid dependency or payload",
        error.BufferCopyDeviceMismatch => "buffer copy requires both buffers to belong to the encoder's device",
        error.BufferCopyUsageMissing => "buffer copy requires COPY_SRC on source and COPY_DST on destination",
        error.BufferCopyUnaligned => "buffer copy offsets and size must be multiples of four bytes",
        error.BufferCopyOutOfBounds => "buffer copy range exceeds the source or destination size",
        error.BufferCopyAliasing => "buffer copy source and destination alias outside the permitted copy contract",
        error.ImmediateDataUnsupported => "setImmediates: shader-visible immediate data is unsupported; use buffer bindings",
    };
}

pub const State = union(enum) {
    open,
    pass: usize,
    failed: Failure,
    finished,

    pub fn fail(self: *State, cause: Failure) bool {
        if (self.* == .failed) return false;
        self.* = .{ .failed = cause };
        return true;
    }
};
