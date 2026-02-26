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
    requires_lean: bool = false,
    is_blocking: bool = false,
};

pub const DispatchContext = struct {
    allocator: std.mem.Allocator,
    upload: CommandDispatchBucket,
    copy_buffer_to_texture: CommandDispatchBucket,
    barrier: CommandDispatchBucket,
    dispatch: CommandDispatchBucket,
    kernel_dispatch: CommandDispatchBucket,
    render_draw: CommandDispatchBucket,
    sampler_create: CommandDispatchBucket,
    sampler_destroy: CommandDispatchBucket,
    texture_write: CommandDispatchBucket,
    texture_query: CommandDispatchBucket,
    texture_destroy: CommandDispatchBucket,
    surface_create: CommandDispatchBucket,
    surface_capabilities: CommandDispatchBucket,
    surface_configure: CommandDispatchBucket,
    surface_acquire: CommandDispatchBucket,
    surface_present: CommandDispatchBucket,
    surface_unconfigure: CommandDispatchBucket,
    surface_release: CommandDispatchBucket,
    async_diagnostics: CommandDispatchBucket,

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
            .sampler_create = .{},
            .sampler_destroy = .{},
            .texture_write = .{},
            .texture_query = .{},
            .texture_destroy = .{},
            .surface_create = .{},
            .surface_capabilities = .{},
            .surface_configure = .{},
            .surface_acquire = .{},
            .surface_present = .{},
            .surface_unconfigure = .{},
            .surface_release = .{},
            .async_diagnostics = .{},
        };
    }

    const scoring_profile = model.DeviceProfile{
        .vendor = "",
        .api = quirks[0].match_spec.api,
        .device_family = null,
        .driver_version = .{ .major = 9999, .minor = 9999, .patch = 9999 },
    };

    var upload = std.ArrayList(ScoredQuirk).empty;
    var copy_buffer_to_texture = std.ArrayList(ScoredQuirk).empty;
    var barrier = std.ArrayList(ScoredQuirk).empty;
    var dispatch_commands = std.ArrayList(ScoredQuirk).empty;
    var kernel_dispatch = std.ArrayList(ScoredQuirk).empty;
    var render_draw = std.ArrayList(ScoredQuirk).empty;
    var sampler_create = std.ArrayList(ScoredQuirk).empty;
    var sampler_destroy = std.ArrayList(ScoredQuirk).empty;
    var texture_write = std.ArrayList(ScoredQuirk).empty;
    var texture_query = std.ArrayList(ScoredQuirk).empty;
    var texture_destroy = std.ArrayList(ScoredQuirk).empty;
    var surface_create = std.ArrayList(ScoredQuirk).empty;
    var surface_capabilities = std.ArrayList(ScoredQuirk).empty;
    var surface_configure = std.ArrayList(ScoredQuirk).empty;
    var surface_acquire = std.ArrayList(ScoredQuirk).empty;
    var surface_present = std.ArrayList(ScoredQuirk).empty;
    var surface_unconfigure = std.ArrayList(ScoredQuirk).empty;
    var surface_release = std.ArrayList(ScoredQuirk).empty;
    var async_diagnostics = std.ArrayList(ScoredQuirk).empty;

    for (quirks) |quirk| {
        if (supportsCommand(quirk.scope, .upload)) {
            try appendScored(&upload, allocator, quirk, .upload, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .copy_buffer_to_texture)) {
            try appendScored(&copy_buffer_to_texture, allocator, quirk, .copy_buffer_to_texture, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .barrier)) {
            try appendScored(&barrier, allocator, quirk, .barrier, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .dispatch)) {
            try appendScored(&dispatch_commands, allocator, quirk, .dispatch, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .kernel_dispatch)) {
            try appendScored(&kernel_dispatch, allocator, quirk, .kernel_dispatch, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .render_draw)) {
            try appendScored(&render_draw, allocator, quirk, .render_draw, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .sampler_create)) {
            try appendScored(&sampler_create, allocator, quirk, .sampler_create, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .sampler_destroy)) {
            try appendScored(&sampler_destroy, allocator, quirk, .sampler_destroy, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .texture_write)) {
            try appendScored(&texture_write, allocator, quirk, .texture_write, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .texture_query)) {
            try appendScored(&texture_query, allocator, quirk, .texture_query, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .texture_destroy)) {
            try appendScored(&texture_destroy, allocator, quirk, .texture_destroy, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_create)) {
            try appendScored(&surface_create, allocator, quirk, .surface_create, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_capabilities)) {
            try appendScored(&surface_capabilities, allocator, quirk, .surface_capabilities, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_configure)) {
            try appendScored(&surface_configure, allocator, quirk, .surface_configure, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_acquire)) {
            try appendScored(&surface_acquire, allocator, quirk, .surface_acquire, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_present)) {
            try appendScored(&surface_present, allocator, quirk, .surface_present, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_unconfigure)) {
            try appendScored(&surface_unconfigure, allocator, quirk, .surface_unconfigure, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .surface_release)) {
            try appendScored(&surface_release, allocator, quirk, .surface_release, scoring_profile);
        }
        if (supportsCommand(quirk.scope, .async_diagnostics)) {
            try appendScored(&async_diagnostics, allocator, quirk, .async_diagnostics, scoring_profile);
        }
    }

    return DispatchContext{
        .allocator = allocator,
        .upload = finalizeBucket(&upload, allocator),
        .copy_buffer_to_texture = finalizeBucket(&copy_buffer_to_texture, allocator),
        .barrier = finalizeBucket(&barrier, allocator),
        .dispatch = finalizeBucket(&dispatch_commands, allocator),
        .kernel_dispatch = finalizeBucket(&kernel_dispatch, allocator),
        .render_draw = finalizeBucket(&render_draw, allocator),
        .sampler_create = finalizeBucket(&sampler_create, allocator),
        .sampler_destroy = finalizeBucket(&sampler_destroy, allocator),
        .texture_write = finalizeBucket(&texture_write, allocator),
        .texture_query = finalizeBucket(&texture_query, allocator),
        .texture_destroy = finalizeBucket(&texture_destroy, allocator),
        .surface_create = finalizeBucket(&surface_create, allocator),
        .surface_capabilities = finalizeBucket(&surface_capabilities, allocator),
        .surface_configure = finalizeBucket(&surface_configure, allocator),
        .surface_acquire = finalizeBucket(&surface_acquire, allocator),
        .surface_present = finalizeBucket(&surface_present, allocator),
        .surface_unconfigure = finalizeBucket(&surface_unconfigure, allocator),
        .surface_release = finalizeBucket(&surface_release, allocator),
        .async_diagnostics = finalizeBucket(&async_diagnostics, allocator),
    };
}

pub fn buildProfileDispatchContext(
    allocator: std.mem.Allocator,
    profile: model.DeviceProfile,
    quirks: []const model.Quirk,
) !DispatchContext {
    var upload = std.ArrayList(ScoredQuirk).empty;
    var copy_buffer_to_texture = std.ArrayList(ScoredQuirk).empty;
    var barrier = std.ArrayList(ScoredQuirk).empty;
    var dispatch_commands = std.ArrayList(ScoredQuirk).empty;
    var kernel_dispatch = std.ArrayList(ScoredQuirk).empty;
    var render_draw = std.ArrayList(ScoredQuirk).empty;
    var sampler_create = std.ArrayList(ScoredQuirk).empty;
    var sampler_destroy = std.ArrayList(ScoredQuirk).empty;
    var texture_write = std.ArrayList(ScoredQuirk).empty;
    var texture_query = std.ArrayList(ScoredQuirk).empty;
    var texture_destroy = std.ArrayList(ScoredQuirk).empty;
    var surface_create = std.ArrayList(ScoredQuirk).empty;
    var surface_capabilities = std.ArrayList(ScoredQuirk).empty;
    var surface_configure = std.ArrayList(ScoredQuirk).empty;
    var surface_acquire = std.ArrayList(ScoredQuirk).empty;
    var surface_present = std.ArrayList(ScoredQuirk).empty;
    var surface_unconfigure = std.ArrayList(ScoredQuirk).empty;
    var surface_release = std.ArrayList(ScoredQuirk).empty;
    var async_diagnostics = std.ArrayList(ScoredQuirk).empty;

    for (quirks) |quirk| {
        if (!matchesProfile(profile, quirk)) continue;

        if (supportsCommand(quirk.scope, .upload)) {
            try appendScored(&upload, allocator, quirk, .upload, profile);
        }
        if (supportsCommand(quirk.scope, .copy_buffer_to_texture)) {
            try appendScored(&copy_buffer_to_texture, allocator, quirk, .copy_buffer_to_texture, profile);
        }
        if (supportsCommand(quirk.scope, .barrier)) {
            try appendScored(&barrier, allocator, quirk, .barrier, profile);
        }
        if (supportsCommand(quirk.scope, .dispatch)) {
            try appendScored(&dispatch_commands, allocator, quirk, .dispatch, profile);
        }
        if (supportsCommand(quirk.scope, .kernel_dispatch)) {
            try appendScored(&kernel_dispatch, allocator, quirk, .kernel_dispatch, profile);
        }
        if (supportsCommand(quirk.scope, .render_draw)) {
            try appendScored(&render_draw, allocator, quirk, .render_draw, profile);
        }
        if (supportsCommand(quirk.scope, .sampler_create)) {
            try appendScored(&sampler_create, allocator, quirk, .sampler_create, profile);
        }
        if (supportsCommand(quirk.scope, .sampler_destroy)) {
            try appendScored(&sampler_destroy, allocator, quirk, .sampler_destroy, profile);
        }
        if (supportsCommand(quirk.scope, .texture_write)) {
            try appendScored(&texture_write, allocator, quirk, .texture_write, profile);
        }
        if (supportsCommand(quirk.scope, .texture_query)) {
            try appendScored(&texture_query, allocator, quirk, .texture_query, profile);
        }
        if (supportsCommand(quirk.scope, .texture_destroy)) {
            try appendScored(&texture_destroy, allocator, quirk, .texture_destroy, profile);
        }
        if (supportsCommand(quirk.scope, .surface_create)) {
            try appendScored(&surface_create, allocator, quirk, .surface_create, profile);
        }
        if (supportsCommand(quirk.scope, .surface_capabilities)) {
            try appendScored(&surface_capabilities, allocator, quirk, .surface_capabilities, profile);
        }
        if (supportsCommand(quirk.scope, .surface_configure)) {
            try appendScored(&surface_configure, allocator, quirk, .surface_configure, profile);
        }
        if (supportsCommand(quirk.scope, .surface_acquire)) {
            try appendScored(&surface_acquire, allocator, quirk, .surface_acquire, profile);
        }
        if (supportsCommand(quirk.scope, .surface_present)) {
            try appendScored(&surface_present, allocator, quirk, .surface_present, profile);
        }
        if (supportsCommand(quirk.scope, .surface_unconfigure)) {
            try appendScored(&surface_unconfigure, allocator, quirk, .surface_unconfigure, profile);
        }
        if (supportsCommand(quirk.scope, .surface_release)) {
            try appendScored(&surface_release, allocator, quirk, .surface_release, profile);
        }
        if (supportsCommand(quirk.scope, .async_diagnostics)) {
            try appendScored(&async_diagnostics, allocator, quirk, .async_diagnostics, profile);
        }
    }

    return DispatchContext{
        .allocator = allocator,
        .upload = finalizeBucket(&upload, allocator),
        .copy_buffer_to_texture = finalizeBucket(&copy_buffer_to_texture, allocator),
        .barrier = finalizeBucket(&barrier, allocator),
        .dispatch = finalizeBucket(&dispatch_commands, allocator),
        .kernel_dispatch = finalizeBucket(&kernel_dispatch, allocator),
        .render_draw = finalizeBucket(&render_draw, allocator),
        .sampler_create = finalizeBucket(&sampler_create, allocator),
        .sampler_destroy = finalizeBucket(&sampler_destroy, allocator),
        .texture_write = finalizeBucket(&texture_write, allocator),
        .texture_query = finalizeBucket(&texture_query, allocator),
        .texture_destroy = finalizeBucket(&texture_destroy, allocator),
        .surface_create = finalizeBucket(&surface_create, allocator),
        .surface_capabilities = finalizeBucket(&surface_capabilities, allocator),
        .surface_configure = finalizeBucket(&surface_configure, allocator),
        .surface_acquire = finalizeBucket(&surface_acquire, allocator),
        .surface_present = finalizeBucket(&surface_present, allocator),
        .surface_unconfigure = finalizeBucket(&surface_unconfigure, allocator),
        .surface_release = finalizeBucket(&surface_release, allocator),
        .async_diagnostics = finalizeBucket(&async_diagnostics, allocator),
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

    return .{
        .command = applyAction(quirk, command),
        .decision = .{
            .matched_quirk_id = quirk.quirk_id,
            .action = quirk.action,
            .score = bucket.best_score,
            .matched_count = bucket.matched_count,
            .requires_lean = bucket.requires_lean,
            .is_blocking = bucket.is_blocking,
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
    storage: *std.ArrayList(ScoredQuirk),
    allocator: std.mem.Allocator,
    quirk: model.Quirk,
    command_kind: model.CommandKind,
    profile: model.DeviceProfile,
) !void {
    try storage.append(allocator, .{
        .quirk = quirk,
        .score = scoreRule(quirk, command_kind, profile),
    });
}

fn finalizeBucket(storage: *std.ArrayList(ScoredQuirk), allocator: std.mem.Allocator) CommandDispatchBucket {
    if (storage.items.len == 0) {
        storage.deinit(allocator);
        return CommandDispatchBucket{};
    }

    std.mem.sort(ScoredQuirk, storage.items, {}, compareScoredQuirk);
    const best = storage.items[0];
    const requires_lean = model.requiresProof(best.quirk.verification_mode);
    const result = CommandDispatchBucket{
        .best = best.quirk,
        .best_score = best.score,
        .matched_count = @intCast(storage.items.len),
        .requires_lean = requires_lean,
        .is_blocking = requires_lean and best.quirk.proof_level != .proven,
    };
    storage.deinit(allocator);
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
        .layout => command_kind == .dispatch or
            command_kind == .kernel_dispatch or
            command_kind == .render_draw or
            command_kind == .copy_buffer_to_texture or
            command_kind == .sampler_create or
            command_kind == .sampler_destroy or
            command_kind == .texture_write or
            command_kind == .texture_query or
            command_kind == .texture_destroy or
            command_kind == .surface_create or
            command_kind == .surface_capabilities or
            command_kind == .surface_configure or
            command_kind == .surface_acquire or
            command_kind == .surface_present or
            command_kind == .surface_unconfigure or
            command_kind == .surface_release or
            command_kind == .async_diagnostics,
        .barrier => command_kind == .barrier or command_kind == .dispatch or command_kind == .kernel_dispatch or command_kind == .render_draw or command_kind == .surface_present,
        .driver_toggle => true,
        .memory => command_kind == .copy_buffer_to_texture or command_kind == .upload or command_kind == .texture_write or command_kind == .texture_query or command_kind == .texture_destroy,
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
        .sampler_create, .sampler_destroy => {
            if (quirk.scope == .layout) score += 3;
        },
        .texture_write, .texture_query, .texture_destroy => {
            if (quirk.scope == .memory) score += 6;
            if (quirk.scope == .layout) score += 2;
        },
        .surface_create, .surface_capabilities, .surface_configure, .surface_acquire, .surface_present, .surface_unconfigure, .surface_release => {
            if (quirk.scope == .layout) score += 5;
            if (quirk.scope == .barrier) score += 2;
        },
        .async_diagnostics => {
            if (quirk.scope == .layout) score += 4;
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
        .sampler_create => context.sampler_create,
        .sampler_destroy => context.sampler_destroy,
        .texture_write => context.texture_write,
        .texture_query => context.texture_query,
        .texture_destroy => context.texture_destroy,
        .surface_create => context.surface_create,
        .surface_capabilities => context.surface_capabilities,
        .surface_configure => context.surface_configure,
        .surface_acquire => context.surface_acquire,
        .surface_present => context.surface_present,
        .surface_unconfigure => context.surface_unconfigure,
        .surface_release => context.surface_release,
        .async_diagnostics => context.async_diagnostics,
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
                        .warmup_dispatch_count = kernel_command.warmup_dispatch_count,
                        .initialize_buffers_on_create = kernel_command.initialize_buffers_on_create,
                        .bindings = kernel_command.bindings,
                    },
                },
                .render_draw => |render_command| .{
                    .render_draw = render_command,
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
