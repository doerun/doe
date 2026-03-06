const std = @import("std");
const build_options = @import("build_options");

pub const lean_verified: bool = build_options.lean_verified;

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

comptime {
    @setEvalBranchQuota(100_000);
    if (build_options.lean_verified) {
        const json = proof_json.?;

        if (!comptimeContains(json, "\"schemaVersion\": 1"))
            @compileError("lean proof artifact: schemaVersion is not 1");

        if (!comptimeContains(json, "\"status\": \"verified\""))
            @compileError("lean proof artifact: status is not 'verified'");

        if (!comptimeContains(json, "\"toggleAlwaysSupported\""))
            @compileError("lean proof artifact: missing required theorem toggleAlwaysSupported");

        if (!comptimeContains(json, "\"requiredProof_forbidden_reject_from_rank\""))
            @compileError("lean proof artifact: missing required theorem requiredProof_forbidden_reject_from_rank");

        if (!comptimeContains(json, "\"strongerSafetyRaisesProofDemand\""))
            @compileError("lean proof artifact: missing required theorem strongerSafetyRaisesProofDemand");

        if (!comptimeContains(json, "\"identityActionComplete\""))
            @compileError("lean proof artifact: missing required theorem identityActionComplete");
    }
}
