const std = @import("std");
const model = @import("model.zig");

const Allocator = std.mem.Allocator;

const ParseError = error{
    UnsupportedActionKind,
    InvalidSchemaVersion,
    InvalidPayload,
};

const RawMatchSpec = struct {
    vendor: []const u8,
    api: []const u8,
    deviceFamily: ?[]const u8 = null,
    driverRange: ?[]const u8 = null,
};

const RawAction = struct {
    kind: []const u8,
    params: ?std.json.Value = null,
};

const RawProvenance = struct {
    sourceRepo: []const u8,
    sourcePath: []const u8,
    sourceCommit: []const u8,
    observedAt: []const u8,
};

const RawQuirk = struct {
    schemaVersion: u8,
    quirkId: []const u8,
    scope: []const u8,
    match: RawMatchSpec,
    action: RawAction,
    safetyClass: []const u8,
    verificationMode: []const u8,
    proofLevel: []const u8,
    provenance: RawProvenance,
};

pub fn parseQuirks(allocator: Allocator, text: []const u8) ![]model.Quirk {
    const parsed = try std.json.parseFromSlice([]const RawQuirk, allocator, text, .{ .ignore_unknown_fields = true });
    defer parsed.deinit();

    var list = std.array_list.Managed(model.Quirk).init(allocator);
    try list.ensureTotalCapacity(parsed.value.len);

    for (parsed.value) |raw| {
        const q = try materializeQuirk(allocator, raw);
        try list.append(q);
    }
    return list.toOwnedSlice();
}

pub fn freeQuirks(allocator: Allocator, quirks: []model.Quirk) void {
    for (quirks) |quirk| {
        allocator.free(quirk.quirk_id);
        allocator.free(quirk.match_spec.vendor);
        if (quirk.match_spec.device_family) |value| allocator.free(value);
        if (quirk.match_spec.driver_range) |value| allocator.free(value);
        switch (quirk.action) {
            .toggle => |toggle| allocator.free(toggle.toggle_name),
            .use_temporary_buffer, .no_op => {},
        }
        allocator.free(quirk.provenance.source_repo);
        allocator.free(quirk.provenance.source_path);
        allocator.free(quirk.provenance.source_commit);
        allocator.free(quirk.provenance.observed_at);
    }
    allocator.free(quirks);
}

fn materializeQuirk(allocator: Allocator, raw: RawQuirk) !model.Quirk {
    if (raw.schemaVersion != model.CURRENT_SCHEMA_VERSION) return ParseError.InvalidSchemaVersion;

    const action = try parseAction(allocator, raw.action.kind, raw.action.params);
    const match_spec = model.MatchSpec{
        .vendor = try allocator.dupe(u8, raw.match.vendor),
        .api = try model.parse_api(raw.match.api),
        .device_family = if (raw.match.deviceFamily) |value| try allocator.dupe(u8, value) else null,
        .driver_range = if (raw.match.driverRange) |value| try allocator.dupe(u8, value) else null,
    };

    const provenance = model.Provenance{
        .source_repo = try allocator.dupe(u8, raw.provenance.sourceRepo),
        .source_path = try allocator.dupe(u8, raw.provenance.sourcePath),
        .source_commit = try allocator.dupe(u8, raw.provenance.sourceCommit),
        .observed_at = try allocator.dupe(u8, raw.provenance.observedAt),
    };

    return model.Quirk{
        .schema_version = raw.schemaVersion,
        .quirk_id = try allocator.dupe(u8, raw.quirkId),
        .scope = try model.parse_scope(raw.scope),
        .match_spec = match_spec,
        .action = action,
        .safety_class = try model.parse_safety(raw.safetyClass),
        .verification_mode = try model.parse_verification_mode(raw.verificationMode),
        .proof_level = try model.parse_proof_level(raw.proofLevel),
        .provenance = provenance,
        .priority = inferPriority(raw.scope, raw.verificationMode, raw.safetyClass),
    };
}

fn parseAction(allocator: Allocator, kind: []const u8, params: ?std.json.Value) !model.QuirkAction {
    if (std.ascii.eqlIgnoreCase(kind, "use_temporary_buffer")) {
        const alignment = if (params) |p| parseAlignment(p) else null;
        return model.QuirkAction{
            .use_temporary_buffer = model.UseTemporaryBufferAction{
                .alignment_bytes = alignment orelse 4,
            },
        };
    }
    if (std.ascii.eqlIgnoreCase(kind, "toggle")) {
        const toggle_name = if (params) |p| parseToggleName(p) else null;
        if (toggle_name == null) {
            return ParseError.InvalidPayload;
        }
        return model.QuirkAction{
            .toggle = model.ToggleAction{
                .toggle_name = try allocator.dupe(u8, toggle_name.?),
            },
        };
    }
    if (std.ascii.eqlIgnoreCase(kind, "no_op") or std.ascii.eqlIgnoreCase(kind, "noop")) {
        return model.QuirkAction{ .no_op = {} };
    }
    return ParseError.UnsupportedActionKind;
}

fn parseAlignment(raw: std.json.Value) ?u32 {
    switch (raw) {
        .object => |o| {
            if (o.get("bufferAlignmentBytes")) |field| {
                return jsonToU32(field);
            }
            if (o.get("alignmentBytes")) |field| {
                return jsonToU32(field);
            }
            if (o.get("alignment")) |field| {
                return jsonToU32(field);
            }
        },
        else => {},
    }
    return null;
}

fn parseToggleName(raw: std.json.Value) ?[]const u8 {
    switch (raw) {
        .object => |o| {
            if (o.get("toggle")) |field| {
                return jsonToString(field);
            }
            if (o.get("name")) |field| {
                return jsonToString(field);
            }
            if (o.get("toggle_name")) |field| {
                return jsonToString(field);
            }
        },
        else => {},
    }
    return null;
}

fn jsonToString(raw: std.json.Value) ?[]const u8 {
    return switch (raw) {
        .string => |value| value,
        else => null,
    };
}

fn jsonToU32(raw: std.json.Value) ?u32 {
    return switch (raw) {
        .integer => |value| @as(u32, @intCast(value)),
        .float => |value| if (value >= 0 and std.math.isFinite(value))
            @as(u32, @intFromFloat(value))
        else
            null,
        else => null,
    };
}

fn inferPriority(scope: []const u8, verification_mode: []const u8, safety: []const u8) u32 {
    var score: u32 = 0;
    if (std.mem.eql(u8, scope, "memory")) score += 30;
    if (std.mem.eql(u8, scope, "barrier")) score += 20;
    if (std.mem.eql(u8, verification_mode, "lean_required")) score += 10;
    if (std.mem.eql(u8, safety, "critical")) score += 100;
    return score;
}
