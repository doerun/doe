const std = @import("std");
const model = @import("model.zig");

pub const DispatchDecision = struct {
    matched_quirk_id: ?[]const u8,
    action: ?model.QuirkAction,
    score: u32,
    matched_count: u32,
    requires_lean: bool,
    is_blocking: bool,
    proof_level: ?model.ProofLevel,
    verification_mode: ?model.VerificationMode,
    applied_toggle: ?[]const u8,
    matched_scope: ?model.Scope,
    matched_safety_class: ?model.SafetyClass,
};

const ScoredQuirk = struct {
    quirk: model.Quirk,
    score: u32,
};

pub const CommandDispatchBucket = struct {
    best: ?model.Quirk = null,
    best_score: u32 = 0,
    matched_count: u32 = 0,
};

pub const DispatchContext = struct {
    allocator: std.mem.Allocator,
    upload: CommandDispatchBucket,
    copy_buffer_to_texture: CommandDispatchBucket,
    barrier: CommandDispatchBucket,
    dispatch: CommandDispatchBucket,
    kernel_dispatch: CommandDispatchBucket,
    render_draw: CommandDispatchBucket,

    pub fn deinit(self: DispatchContext) void {
        _ = self;
    }
};

pub fn buildDispatchContext(allocator: std.mem.Allocator, quirks: []const model.Quirk) !DispatchContext {
    if (quirks.len == 0) {
        return .{
            .allocator = allocator,
            .upload = .{},
            .copy_buffer_to_texture = .{},
            .barrier = .{},
            .dispatch = .{},
            .kernel_dispatch = .{},
            .render_draw = .{},
        };
    }

    const scoring_profile = model.DeviceProfile{
        .vendor = "",
        .api = quirks[0].match_spec.api,
        .device_family = null,
        .driver_version = .{ .major = 9999, .minor = 9999, .patch = 9999 },
    };

    var upload = std.array_list.Managed(ScoredQuirk).init(allocator);
    var copy_buffer_to_texture = std.array_list.Managed(ScoredQuirk).init(allocator);
    var barrier = std.array_list.Managed(ScoredQuirk).init(allocator);
    var dispatch_commands = std.array_list.Managed(ScoredQuirk).init(allocator);
    var kernel_dispatch = std.array_list.Managed(ScoredQuirk).init(allocator);
    var render_draw = std.array_list.Managed(ScoredQuirk).init(allocator);

    for (quirks) |quirk| {
        if (supportsCommand(quirk.scope, .upload)) {
            try appendScored(&upload, quirk, .upload, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .copy_buffer_to_texture)) {
            try appendScored(&copy_buffer_to_texture, quirk, .copy_buffer_to_texture, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .barrier)) {
            try appendScored(&barrier, quirk, .barrier, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .dispatch)) {
            try appendScored(&dispatch_commands, quirk, .dispatch, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .kernel_dispatch)) {
            try appendScored(&kernel_dispatch, quirk, .kernel_dispatch, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .render_draw)) {
            try appendScored(&render_draw, quirk, .render_draw, scoring_profile);
        }
    }

    return DispatchContext{
        .allocator = allocator,
        .upload = finalizeBucket(&upload),
        .copy_buffer_to_texture = finalizeBucket(&copy_buffer_to_texture),
        .barrier = finalizeBucket(&barrier),
        .dispatch = finalizeBucket(&dispatch_commands),
        .kernel_dispatch = finalizeBucket(&kernel_dispatch),
        .render_draw = finalizeBucket(&render_draw),
    };
}

pub fn buildProfileDispatchContext(
    allocator: std.mem.Allocator,
    profile: model.DeviceProfile,
    quirks: []const model.Quirk,
) !DispatchContext {
    var upload = std.array_list.Managed(ScoredQuirk).init(allocator);
    var copy_buffer_to_texture = std.array_list.Managed(ScoredQuirk).init(allocator);
    var barrier = std.array_list.Managed(ScoredQuirk).init(allocator);
    var dispatch_commands = std.array_list.Managed(ScoredQuirk).init(allocator);
    var kernel_dispatch = std.array_list.Managed(ScoredQuirk).init(allocator);
    var render_draw = std.array_list.Managed(ScoredQuirk).init(allocator);

    for (quirks) |quirk| {
        if (!matchesProfile(profile, quirk)) continue;

        if (supportsCommand(quirk.scope, .upload)) {
            try appendScored(&upload, quirk, .upload, profile);
        }
        if (supportsCommand(quirk.scope, .copy_buffer_to_texture)) {
            try appendScored(&copy_buffer_to_texture, quirk, .copy_buffer_to_texture, profile);
        }
        if (supportsCommand(quirk.scope, .barrier)) {
            try appendScored(&barrier, quirk, .barrier, profile);
        }
        if (supportsCommand(quirk.scope, .dispatch)) {
            try appendScored(&dispatch_commands, quirk, .dispatch, profile);
        }
        if (supportsCommand(quirk.scope, .kernel_dispatch)) {
            try appendScored(&kernel_dispatch, quirk, .kernel_dispatch, profile);
        }
        if (supportsCommand(quirk.scope, .render_draw)) {
            try appendScored(&render_draw, quirk, .render_draw, profile);
        }
    }

    return DispatchContext{
        .allocator = allocator,
        .upload = finalizeBucket(&upload),
        .copy_buffer_to_texture = finalizeBucket(&copy_buffer_to_texture),
        .barrier = finalizeBucket(&barrier),
        .dispatch = finalizeBucket(&dispatch_commands),
        .kernel_dispatch = finalizeBucket(&kernel_dispatch),
        .render_draw = finalizeBucket(&render_draw),
    };
}

pub fn dispatch(profile: model.DeviceProfile, context: DispatchContext, command: model.Command) struct {
    command: model.Command,
    decision: DispatchDecision,
} {
    _ = profile;
    const kind = model.command_kind(command);
    const bucket = bucketForKind(context, kind);

    if (bucket.best == null) {
        return .{
            .command = command,
            .decision = .{
                .matched_quirk_id = null,
                .action = null,
                .score = 0,
                .matched_count = bucket.matched_count,
                .requires_lean = false,
                .is_blocking = false,
                .proof_level = null,
                .verification_mode = null,
                .applied_toggle = null,
                .matched_scope = null,
                .matched_safety_class = null,
            },
        };
    }

    const quirk = bucket.best.?;
    const requires_lean = model.requiresProof(quirk.verification_mode);
    const is_blocking = requires_lean and quirk.proof_level != .proven;

    return .{
        .command = applyAction(quirk, command),
        .decision = .{
            .matched_quirk_id = quirk.quirk_id,
            .action = quirk.action,
            .score = bucket.best_score,
            .matched_count = bucket.matched_count,
            .requires_lean = requires_lean,
            .is_blocking = is_blocking,
            .proof_level = quirk.proof_level,
            .verification_mode = quirk.verification_mode,
            .applied_toggle = switch (quirk.action) {
                .toggle => |payload| payload.toggle_name,
                else => null,
            },
            .matched_scope = quirk.scope,
            .matched_safety_class = quirk.safety_class,
        },
    };
}

fn appendScored(
    storage: *std.array_list.Managed(ScoredQuirk),
    quirk: model.Quirk,
    command_kind: model.CommandKind,
    profile: model.DeviceProfile,
) !void {
    try storage.append(.{
        .quirk = quirk,
        .score = scoreRule(quirk, command_kind, profile),
    });
}

fn finalizeBucket(storage: *std.array_list.Managed(ScoredQuirk)) CommandDispatchBucket {
    if (storage.items.len == 0) {
        storage.deinit();
        return CommandDispatchBucket{};
    }

    std.mem.sort(ScoredQuirk, storage.items, {}, compareScoredQuirk);
    const best = storage.items[0];
    const result = CommandDispatchBucket{
        .best = best.quirk,
        .best_score = best.score,
        .matched_count = @intCast(storage.items.len),
    };
    storage.deinit();
    return result;
}

fn compareScoredQuirk(_: void, a: ScoredQuirk, b: ScoredQuirk) bool {
    if (a.score != b.score) return a.score > b.score;
    if (proofPriority(a.quirk.proof_level) != proofPriority(b.quirk.proof_level)) {
        return proofPriority(a.quirk.proof_level) > proofPriority(b.quirk.proof_level);
    }
    if (a.quirk.priority != b.quirk.priority) return a.quirk.priority > b.quirk.priority;
    return std.mem.lessThan(u8, a.quirk.quirk_id, b.quirk.quirk_id);
}

fn proofPriority(level: model.ProofLevel) u8 {
    return switch (level) {
        .proven => 3,
        .guarded => 2,
        .rejected => 1,
    };
}

fn supportsCommand(scope: model.Scope, command_kind: model.CommandKind) bool {
    return switch (scope) {
        .alignment => command_kind == .upload or command_kind == .copy_buffer_to_texture,
        .layout => command_kind == .dispatch or command_kind == .kernel_dispatch or command_kind == .render_draw or command_kind == .copy_buffer_to_texture,
        .barrier => command_kind == .barrier or command_kind == .dispatch or command_kind == .kernel_dispatch or command_kind == .render_draw,
        .driver_toggle => true,
        .memory => command_kind == .copy_buffer_to_texture or command_kind == .upload,
    };
}

fn scoreRule(quirk: model.Quirk, command_kind: model.CommandKind, profile: model.DeviceProfile) u32 {
    var score: u32 = quirk.priority;

    if (quirk.match_spec.device_family) |required_family| {
        if (profile.device_family) |actual_family| {
            if (std.mem.eql(u8, required_family, actual_family)) score += 50;
        }
    } else {
        score += 1;
    }

    if (quirk.match_spec.driver_range) |_| score += 10;
    if (quirk.safety_class == .critical) score += 15;
    if (quirk.safety_class == .high) score += 8;
    if (quirk.verification_mode == .lean_required) score += 12;
    if (quirk.scope == .memory and profile.device_family != null and quirk.match_spec.device_family != null) score += 20;

    switch (command_kind) {
        .upload => {
            if (quirk.scope == .alignment) score += 5;
        },
        .copy_buffer_to_texture => {
            if (quirk.scope == .memory) score += 8;
            if (quirk.scope == .alignment) score += 4;
        },
        .dispatch => {
            if (quirk.scope == .layout) score += 4;
            if (quirk.scope == .barrier) score += 6;
        },
        .barrier => {
            if (quirk.scope == .barrier) score += 8;
        },
        .kernel_dispatch => {
            if (quirk.scope == .layout) score += 7;
            if (quirk.scope == .barrier) score += 2;
        },
        .render_draw => {
            if (quirk.scope == .layout) score += 6;
            if (quirk.scope == .barrier) score += 3;
        },
    }

    return score;
}

fn matchesProfile(profile: model.DeviceProfile, quirk: model.Quirk) bool {
    if (!eqIgnoreCase(profile.vendor, quirk.match_spec.vendor)) return false;
    if (profile.api != quirk.match_spec.api) return false;

    if (quirk.match_spec.device_family) |required_family| {
        const actual = profile.device_family orelse return false;
        if (!std.mem.eql(u8, required_family, actual)) return false;
    }

    if (quirk.match_spec.driver_range) |range_expr| {
        if (!matchesDriverRange(profile.driver_version, range_expr)) return false;
    }

    return true;
}

fn matchesDriverRange(version: model.SemVer, expr: []const u8) bool {
    var it = std.mem.splitScalar(u8, expr, ',');
    while (it.next()) |raw| {
        const token = std.mem.trim(u8, raw, " ");
        if (token.len == 0) continue;

        if (std.mem.startsWith(u8, token, ">=")) {
            const rhs = parseVersion(token[2..]) orelse return false;
            if (!version.ge(rhs)) return false;
        } else if (std.mem.startsWith(u8, token, "<=")) {
            const rhs = parseVersion(token[2..]) orelse return false;
            if (version.gt(rhs)) return false;
        } else if (std.mem.startsWith(u8, token, ">")) {
            const rhs = parseVersion(token[1..]) orelse return false;
            if (!version.gt(rhs)) return false;
        } else if (std.mem.startsWith(u8, token, "<")) {
            const rhs = parseVersion(token[1..]) orelse return false;
            if (!version.lt(rhs)) return false;
        } else if (std.mem.startsWith(u8, token, "==")) {
            const rhs = parseVersion(token[2..]) orelse return false;
            if (!version.equals(rhs)) return false;
        } else {
            const rhs = parseVersion(token) orelse return false;
            if (!version.equals(rhs)) return false;
        }
    }
    return true;
}

fn parseVersion(text: []const u8) ?model.SemVer {
    return model.SemVer.parse(text) catch null;
}

fn eqIgnoreCase(lhs: []const u8, rhs: []const u8) bool {
    if (lhs.len != rhs.len) return false;
    for (lhs, 0..) |lhs_byte, idx| {
        if (std.ascii.toLower(lhs_byte) != std.ascii.toLower(rhs[idx])) return false;
    }
    return true;
}

fn bucketForKind(context: DispatchContext, kind: model.CommandKind) CommandDispatchBucket {
    return switch (kind) {
        .upload => context.upload,
        .copy_buffer_to_texture => context.copy_buffer_to_texture,
        .barrier => context.barrier,
        .dispatch => context.dispatch,
        .kernel_dispatch => context.kernel_dispatch,
        .render_draw => context.render_draw,
    };
}

fn applyAction(quirk: model.Quirk, command: model.Command) model.Command {
    switch (quirk.action) {
        .use_temporary_buffer => |payload| {
            return switch (command) {
                .copy_buffer_to_texture => |copy| .{
                    .copy_buffer_to_texture = .{
                        .direction = copy.direction,
                        .src = copy.src,
                        .dst = copy.dst,
                        .bytes = copy.bytes,
                        .uses_temporary_buffer = true,
                        .temporary_buffer_alignment = payload.alignment_bytes,
                    },
                },
                else => command,
            };
        },
        .toggle => |_| {
            return switch (command) {
                .dispatch => |dispatch_command| .{
                    .dispatch = .{
                        .x = dispatch_command.x,
                        .y = dispatch_command.y,
                        .z = dispatch_command.z,
                    },
                },
                .kernel_dispatch => |kernel_command| .{
                    .kernel_dispatch = .{
                        .kernel = kernel_command.kernel,
                        .entry_point = kernel_command.entry_point,
                        .x = kernel_command.x,
                        .y = kernel_command.y,
                        .z = kernel_command.z,
                        .repeat = kernel_command.repeat,
                        .bindings = kernel_command.bindings,
                    },
                },
                .render_draw => |render_command| .{
                    .render_draw = .{
                        .draw_count = render_command.draw_count,
                        .vertex_count = render_command.vertex_count,
                        .instance_count = render_command.instance_count,
                        .target_handle = render_command.target_handle,
                        .target_width = render_command.target_width,
                        .target_height = render_command.target_height,
                        .target_format = render_command.target_format,
                        .pipeline_mode = render_command.pipeline_mode,
                        .bind_group_mode = render_command.bind_group_mode,
                    },
                },
                else => command,
            };
        },
        .no_op => return command,
    }
}

test "vendor comparison ignores case" {
    try std.testing.expect(std.ascii.eqlIgnoreCase("Intel", "intel"));
}

test "proof priority ordering prefers proven over guarded" {
    try std.testing.expect(proofPriority(.proven) > proofPriority(.guarded));
}
