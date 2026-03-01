pub const VulkanError = error{
    InvalidArgument,
    Unsupported,
    UnsupportedFeature,
    ShaderToolchainUnavailable,
    ShaderCompileFailed,
    SyncUnavailable,
    TimingPolicyMismatch,
    SurfaceUnavailable,
};
