pub const MetalError = error{
    Unsupported,
    UnsupportedFeature,
    ShaderToolchainUnavailable,
    ShaderCompileFailed,
    SyncUnavailable,
    TimingPolicyMismatch,
    SurfaceUnavailable,
};
