const std = @import("std");

pub const SchemaVersion = u8;
pub const CURRENT_SCHEMA_VERSION: SchemaVersion = 2;

pub const Api = enum(u8) {
    vulkan,
    metal,
    d3d12,
    webgpu,
};

pub const Scope = enum(u8) {
    alignment,
    barrier,
    layout,
    driver_toggle,
    memory,
};

pub const SafetyClass = enum(u8) {
    low,
    moderate,
    high,
    critical,
};

pub const VerificationMode = enum(u8) {
    guard_only,
    lean_preferred,
    lean_required,
};

pub const ProofLevel = enum(u8) {
    proven,
    guarded,
    rejected,
};

pub fn parse_api(raw: []const u8) !Api {
    if (std.ascii.eqlIgnoreCase(raw, "vulkan")) return .vulkan;
    if (std.ascii.eqlIgnoreCase(raw, "metal")) return .metal;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12")) return .d3d12;
    if (std.ascii.eqlIgnoreCase(raw, "webgpu")) return .webgpu;
    return error.InvalidApi;
}

pub fn parse_scope(raw: []const u8) !Scope {
    if (std.ascii.eqlIgnoreCase(raw, "alignment")) return .alignment;
    if (std.ascii.eqlIgnoreCase(raw, "barrier")) return .barrier;
    if (std.ascii.eqlIgnoreCase(raw, "layout")) return .layout;
    if (std.ascii.eqlIgnoreCase(raw, "driver_toggle")) return .driver_toggle;
    if (std.ascii.eqlIgnoreCase(raw, "memory")) return .memory;
    return error.InvalidScope;
}

pub fn parse_safety(raw: []const u8) !SafetyClass {
    if (std.ascii.eqlIgnoreCase(raw, "low")) return .low;
    if (std.ascii.eqlIgnoreCase(raw, "moderate")) return .moderate;
    if (std.ascii.eqlIgnoreCase(raw, "high")) return .high;
    if (std.ascii.eqlIgnoreCase(raw, "critical")) return .critical;
    return error.InvalidSafetyClass;
}

pub fn parse_verification_mode(raw: []const u8) !VerificationMode {
    if (std.ascii.eqlIgnoreCase(raw, "guard_only")) return .guard_only;
    if (std.ascii.eqlIgnoreCase(raw, "lean_preferred")) return .lean_preferred;
    if (std.ascii.eqlIgnoreCase(raw, "lean_required")) return .lean_required;
    return error.InvalidVerificationMode;
}

pub fn parse_proof_level(raw: []const u8) !ProofLevel {
    if (std.ascii.eqlIgnoreCase(raw, "proven")) return .proven;
    if (std.ascii.eqlIgnoreCase(raw, "guarded")) return .guarded;
    if (std.ascii.eqlIgnoreCase(raw, "rejected")) return .rejected;
    return error.InvalidProofLevel;
}

pub fn verification_mode_name(mode: VerificationMode) []const u8 {
    return switch (mode) {
        .guard_only => "guard_only",
        .lean_preferred => "lean_preferred",
        .lean_required => "lean_required",
    };
}

pub fn proof_level_name(level: ProofLevel) []const u8 {
    return switch (level) {
        .proven => "proven",
        .guarded => "guarded",
        .rejected => "rejected",
    };
}

pub fn requiresProof(mode: VerificationMode) bool {
    return mode == .lean_required;
}

pub fn needsStrongestProof(level: ProofLevel) bool {
    return level == .proven;
}

pub fn scope_name(scope: Scope) []const u8 {
    return switch (scope) {
        .alignment => "alignment",
        .barrier => "barrier",
        .layout => "layout",
        .driver_toggle => "driver_toggle",
        .memory => "memory",
    };
}

pub fn safety_class_name(class: SafetyClass) []const u8 {
    return switch (class) {
        .low => "low",
        .moderate => "moderate",
        .high => "high",
        .critical => "critical",
    };
}

const testing = std.testing;

test "parse_api accepts all backends case-insensitively" {
    try testing.expectEqual(Api.vulkan, try parse_api("vulkan"));
    try testing.expectEqual(Api.metal, try parse_api("Metal"));
    try testing.expectEqual(Api.d3d12, try parse_api("D3D12"));
    try testing.expectEqual(Api.webgpu, try parse_api("WEBGPU"));
    try testing.expectError(error.InvalidApi, parse_api("opengl"));
}

test "parse_scope accepts all scopes and rejects unknown" {
    try testing.expectEqual(Scope.alignment, try parse_scope("alignment"));
    try testing.expectEqual(Scope.barrier, try parse_scope("BARRIER"));
    try testing.expectEqual(Scope.layout, try parse_scope("layout"));
    try testing.expectEqual(Scope.driver_toggle, try parse_scope("driver_toggle"));
    try testing.expectEqual(Scope.memory, try parse_scope("memory"));
    try testing.expectError(error.InvalidScope, parse_scope("unknown"));
}

test "parse_safety accepts all classes and rejects unknown" {
    try testing.expectEqual(SafetyClass.low, try parse_safety("low"));
    try testing.expectEqual(SafetyClass.moderate, try parse_safety("Moderate"));
    try testing.expectEqual(SafetyClass.high, try parse_safety("HIGH"));
    try testing.expectEqual(SafetyClass.critical, try parse_safety("critical"));
    try testing.expectError(error.InvalidSafetyClass, parse_safety("extreme"));
}

test "parse_verification_mode accepts all modes and rejects unknown" {
    try testing.expectEqual(VerificationMode.guard_only, try parse_verification_mode("guard_only"));
    try testing.expectEqual(VerificationMode.lean_preferred, try parse_verification_mode("lean_preferred"));
    try testing.expectEqual(VerificationMode.lean_required, try parse_verification_mode("LEAN_REQUIRED"));
    try testing.expectError(error.InvalidVerificationMode, parse_verification_mode("auto"));
}

test "parse_proof_level accepts all levels and rejects unknown" {
    try testing.expectEqual(ProofLevel.proven, try parse_proof_level("proven"));
    try testing.expectEqual(ProofLevel.guarded, try parse_proof_level("guarded"));
    try testing.expectEqual(ProofLevel.rejected, try parse_proof_level("REJECTED"));
    try testing.expectError(error.InvalidProofLevel, parse_proof_level("pending"));
}

test "verification_mode_name round-trips with parse_verification_mode" {
    inline for (.{ VerificationMode.guard_only, VerificationMode.lean_preferred, VerificationMode.lean_required }) |mode| {
        const name = verification_mode_name(mode);
        const parsed = try parse_verification_mode(name);
        try testing.expectEqual(mode, parsed);
    }
}

test "proof_level_name round-trips with parse_proof_level" {
    inline for (.{ ProofLevel.proven, ProofLevel.guarded, ProofLevel.rejected }) |level| {
        const name = proof_level_name(level);
        const parsed = try parse_proof_level(name);
        try testing.expectEqual(level, parsed);
    }
}

test "requiresProof only true for lean_required" {
    try testing.expect(requiresProof(.lean_required));
    try testing.expect(!requiresProof(.lean_preferred));
    try testing.expect(!requiresProof(.guard_only));
}

test "needsStrongestProof only true for proven" {
    try testing.expect(needsStrongestProof(.proven));
    try testing.expect(!needsStrongestProof(.guarded));
    try testing.expect(!needsStrongestProof(.rejected));
}

test "scope_name and safety_class_name return correct strings" {
    try testing.expectEqualStrings("alignment", scope_name(.alignment));
    try testing.expectEqualStrings("memory", scope_name(.memory));
    try testing.expectEqualStrings("low", safety_class_name(.low));
    try testing.expectEqualStrings("critical", safety_class_name(.critical));
}
