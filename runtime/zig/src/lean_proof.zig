const std = @import("std");
const build_options = @import("build_options");

pub const lean_verified: bool = build_options.lean_verified;
pub const comparability_obligations_sha256: []const u8 = build_options.comparability_obligations_sha256;

const proof_json: ?[]const u8 = if (build_options.lean_verified)
    build_options.lean_proof_json
else
    null;

fn comptimeContains(haystack: []const u8, needle: []const u8) bool {
    if (needle.len > haystack.len) return false;
    var i: usize = 0;
    while (i + needle.len <= haystack.len) : (i += 1) {
        if (std.mem.eql(u8, haystack[i..][0..needle.len], needle)) return true;
    }
    return false;
}

fn requireTheorem(comptime json: []const u8, comptime theorem: []const u8) void {
    if (!comptimeContains(json, theorem)) {
        @compileError("lean proof artifact: missing required theorem " ++ theorem);
    }
}

/// Bounds elimination is available when -Dlean-verified=true AND the proof
/// artifact contains both the core theorem (gid_inbounds_when_dispatch_fits)
/// and the connecting theorem (clamp_noop_when_inbounds). These together
/// prove that min(gid, len-1) = gid when dispatch fits, so the clamp is a
/// no-op and can be elided.
pub const bounds_elimination_available: bool = blk: {
    if (!build_options.lean_verified) break :blk false;
    @setEvalBranchQuota(100_000);
    const json = proof_json.?;
    break :blk comptimeContains(json, "\"gid_inbounds_when_dispatch_fits\"") and
        comptimeContains(json, "\"clamp_noop_when_inbounds\"") and
        comptimeContains(json, "\"boundsEliminations\"");
};

/// Access pattern covered by a proven bounds elimination theorem.
pub const BoundsPattern = enum {
    /// buf[global_invocation_id.x] on a runtime-sized storage buffer.
    /// Theorem: gid_inbounds_when_dispatch_fits
    /// Precondition: workgroup_size.x * num_workgroups.x <= arrayLength(&buf)
    gid_1d_storage_buffer,

    /// buf[gid.y * width + gid.x] on a runtime-sized storage buffer.
    /// Theorem: flat_index_2d_inbounds
    /// Precondition: ws.x * nwg.x <= width AND ws.y * nwg.y <= height
    ///               AND width * height <= arrayLength(&buf)
    gid_2d_flat_storage_buffer,
};

/// Check whether a specific bounds pattern has a proven elimination.
/// Returns true only when the build was compiled with -Dlean-verified=true
/// and the proof artifact covers the requested pattern.
pub fn boundsProven(comptime pattern: BoundsPattern) bool {
    if (!bounds_elimination_available) return false;
    return switch (pattern) {
        .gid_1d_storage_buffer => true,
        .gid_2d_flat_storage_buffer => comptime blk: {
            @setEvalBranchQuota(100_000);
            break :blk comptimeContains(proof_json.?, "\"flat_index_2d_inbounds\"");
        },
    };
}

comptime {
    @setEvalBranchQuota(100_000);
    if (build_options.lean_verified) {
        const json = proof_json.?;

        if (!comptimeContains(json, "\"schemaVersion\": 1"))
            @compileError("lean proof artifact: schemaVersion is not 1");

        if (!comptimeContains(json, "\"status\": \"verified\""))
            @compileError("lean proof artifact: status is not 'verified'");

        if (!comptimeContains(json, "\"comparabilityObligationsSha256\": \"" ++ comparability_obligations_sha256 ++ "\""))
            @compileError("lean proof artifact: comparability obligation contract hash mismatch");

        if (!comptimeContains(json, "\"toggleAlwaysSupported\""))
            @compileError("lean proof artifact: missing required theorem toggleAlwaysSupported");

        if (!comptimeContains(json, "\"requiredProof_forbidden_reject_from_rank\""))
            @compileError("lean proof artifact: missing required theorem requiredProof_forbidden_reject_from_rank");

        if (!comptimeContains(json, "\"strongerSafetyRaisesProofDemand\""))
            @compileError("lean proof artifact: missing required theorem strongerSafetyRaisesProofDemand");

        if (!comptimeContains(json, "\"identityActionComplete\""))
            @compileError("lean proof artifact: missing required theorem identityActionComplete");

        if (!comptimeContains(json, "\"scopeCommandTableComplete\""))
            @compileError("lean proof artifact: missing required theorem scopeCommandTableComplete");

        if (!comptimeContains(json, "\"identityActionPreservesCommand\""))
            @compileError("lean proof artifact: missing required theorem identityActionPreservesCommand");

        requireTheorem(json, "\"gid_component_lt_total\"");
        requireTheorem(json, "\"gid_inbounds_when_dispatch_fits\"");
        requireTheorem(json, "\"clamp_noop_when_inbounds\"");
        requireTheorem(json, "\"gid_2d_inbounds\"");
        requireTheorem(json, "\"flat_index_2d_inbounds\"");

        // Validate that bounds eliminations section is present when shader
        // bounds theorems are listed.
        if (!comptimeContains(json, "\"boundsEliminations\""))
            @compileError("lean proof artifact: shader bounds theorems present but boundsEliminations section missing");
    }
}
