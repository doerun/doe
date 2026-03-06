const backend_ids = @import("backend_ids.zig");

pub const BackendTelemetry = struct {
    backend_id: backend_ids.BackendId,
    backend_selection_reason: []const u8,
    fallback_used: bool,
    selection_policy_hash: []const u8,
    shader_artifact_manifest_path: ?[]const u8,
    shader_artifact_manifest_hash: ?[]const u8,
    adapter_ordinal: ?u32,
    queue_family_index: ?u32,
    present_capable: ?bool,
};

pub fn default_telemetry() BackendTelemetry {
    return .{
        .backend_id = .dawn_delegate,
        .backend_selection_reason = "legacy_native_default",
        .fallback_used = false,
        .selection_policy_hash = "backend-runtime-policy-v1",
        .shader_artifact_manifest_path = null,
        .shader_artifact_manifest_hash = null,
        .adapter_ordinal = null,
        .queue_family_index = null,
        .present_capable = null,
    };
}
