const model = @import("../../model.zig");
const wgpu_types = @import("../../wgpu_types.zig");

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

pub fn map_error_status(err: anyerror) wgpu_types.NativeExecutionStatus {
    return switch (err) {
        error.Unsupported,
        error.UnsupportedFeature,
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
