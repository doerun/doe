pub const BackendError = error{
    BackendNotConfigured,
    BackendUnsupported,
    BackendSelectionFailed,
    BackendFallbackForbidden,
    BackendTimingPolicyMismatch,
    BackendSyncPolicyMismatch,
    ShaderArtifactManifestMissing,
    ShaderArtifactInvalid,
};

pub fn backend_error_code(err: anyerror) []const u8 {
    return @errorName(err);
}
