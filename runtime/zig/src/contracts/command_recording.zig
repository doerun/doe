pub const Failure = error{ OutOfMemory, InvalidState, InvalidArgument, ImmediateDataUnsupported };

pub fn message(cause: Failure) []const u8 {
    return switch (cause) {
        error.OutOfMemory => "GPU command recording could not allocate owned storage",
        error.InvalidState => "GPU command recording requires an open encoder or its active pass",
        error.InvalidArgument => "GPU command recording received an invalid dependency or payload",
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
