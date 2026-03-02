pub const D3D12Error = error{
    InvalidArgument,
    Unsupported,
    UnsupportedFeature,
    ShaderToolchainUnavailable,
    ShaderCompileFailed,
    SyncUnavailable,
    TimingPolicyMismatch,
    SurfaceUnavailable,
};
