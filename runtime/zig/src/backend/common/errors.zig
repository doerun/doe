const runtime_types = @import("../runtime_types.zig");

pub const BackendNativeError = error{
    InvalidArgument,
    InvalidState,
    Unsupported,
    UnsupportedFeature,
    ShaderToolchainUnavailable,
    ShaderCompileFailed,
    SyncUnavailable,
    TimingPolicyMismatch,
    SurfaceUnavailable,
};

pub fn map_error_status(err: anyerror) runtime_types.NativeExecutionStatus {
    return switch (err) {
        error.Unsupported,
        error.UnsupportedFeature,
        error.ShaderToolchainUnavailable,
        error.SyncUnavailable,
        error.TimingPolicyMismatch,
        error.SurfaceUnavailable,
        => .unsupported,
        else => .@"error",
    };
}

pub fn error_code(err: anyerror) []const u8 {
    return @errorName(err);
}
