pub const MetalError = error{
    InvalidState,
    Unsupported,
    UnsupportedFeature,
    ShaderToolchainUnavailable,
    ShaderCompileFailed,
    SyncUnavailable,
    TimingPolicyMismatch,
    SurfaceUnavailable,
};
