const model = @import("../model.zig");

pub const runtime = @import("runtime.zig");
pub const actions = @import("quirk_actions.zig");
pub const parser = @import("quirk_json.zig");
pub const toggle_registry = @import("toggle_registry.zig");

pub const QuirkMode = enum {
    off,
    trace,
    active,

    pub fn parse(raw: []const u8) ?QuirkMode {
        const std = @import("std");
        if (std.ascii.eqlIgnoreCase(raw, "off")) return .off;
        if (std.ascii.eqlIgnoreCase(raw, "trace")) return .trace;
        if (std.ascii.eqlIgnoreCase(raw, "active")) return .active;
        return null;
    }

    pub fn name(self: QuirkMode) []const u8 {
        return switch (self) {
            .off => "off",
            .trace => "trace",
            .active => "active",
        };
    }

    pub fn loadsQuirks(self: QuirkMode) bool {
        return self != .off;
    }

    pub fn appliesActions(self: QuirkMode) bool {
        return self == .active;
    }
};

pub const DispatchResult = struct {
    command: model.Command,
    decision: runtime.DispatchDecision,
};

pub fn dispatchWithMode(
    mode: QuirkMode,
    profile: model.DeviceProfile,
    context: runtime.DispatchContext,
    command: model.Command,
) DispatchResult {
    if (mode == .off) {
        return .{
            .command = command,
            .decision = runtime.emptyDecision(context, command),
        };
    }

    const result = runtime.dispatch(profile, context, command);
    return .{
        .command = if (mode == .active) result.command else command,
        .decision = result.decision,
    };
}

test "QuirkMode.parse recognizes valid modes" {
    const std = @import("std");
    try std.testing.expectEqual(QuirkMode.off, QuirkMode.parse("off").?);
    try std.testing.expectEqual(QuirkMode.trace, QuirkMode.parse("trace").?);
    try std.testing.expectEqual(QuirkMode.active, QuirkMode.parse("active").?);
    try std.testing.expectEqual(QuirkMode.active, QuirkMode.parse("Active").?);
    try std.testing.expect(QuirkMode.parse("invalid") == null);
}

test "QuirkMode.loadsQuirks" {
    const std = @import("std");
    try std.testing.expect(!QuirkMode.off.loadsQuirks());
    try std.testing.expect(QuirkMode.trace.loadsQuirks());
    try std.testing.expect(QuirkMode.active.loadsQuirks());
}

test "QuirkMode.appliesActions" {
    const std = @import("std");
    try std.testing.expect(!QuirkMode.off.appliesActions());
    try std.testing.expect(!QuirkMode.trace.appliesActions());
    try std.testing.expect(QuirkMode.active.appliesActions());
}

test "dispatchWithMode active propagates uses_temporary_buffer to command" {
    const std = @import("std");
    const profile = model.DeviceProfile{
        .vendor = "intel",
        .api = .vulkan,
    };
    const quirks = [_]model.Quirk{.{
        .schema_version = model.CURRENT_SCHEMA_VERSION,
        .quirk_id = "test_staging",
        .match_spec = .{ .vendor = "intel", .api = .vulkan },
        .scope = .driver_toggle,
        .safety_class = .moderate,
        .action = .{ .use_temporary_buffer = .{ .alignment_bytes = 256 } },
        .verification_mode = .guard_only,
        .proof_level = .guarded,
        .provenance = .{ .source_repo = "test", .source_path = "test", .source_commit = "abc", .observed_at = "test" },
        .priority = 10,
    }};
    const ctx = runtime.buildProfileDispatchContext(std.testing.allocator, profile, &quirks) catch return;
    defer ctx.deinit();

    const copy_cmd: model.Command = .{ .copy_buffer_to_texture = .{
        .direction = .texture_to_texture,
        .src = .{ .handle = 1 },
        .dst = .{ .handle = 2 },
        .bytes = 4096,
    } };

    // Active mode: command should have uses_temporary_buffer set.
    const active_result = dispatchWithMode(.active, profile, ctx, copy_cmd);
    try std.testing.expect(active_result.command.copy_buffer_to_texture.uses_temporary_buffer);
    try std.testing.expectEqual(@as(u32, 256), active_result.command.copy_buffer_to_texture.temporary_buffer_alignment);

    // Trace mode: command should be unmodified.
    const trace_result = dispatchWithMode(.trace, profile, ctx, copy_cmd);
    try std.testing.expect(!trace_result.command.copy_buffer_to_texture.uses_temporary_buffer);

    // Off mode: command should be unmodified.
    const off_result = dispatchWithMode(.off, profile, ctx, copy_cmd);
    try std.testing.expect(!off_result.command.copy_buffer_to_texture.uses_temporary_buffer);
}

test "dispatchWithMode active propagates uses_temporary_render_texture to render_draw" {
    const std = @import("std");
    const profile = model.DeviceProfile{
        .vendor = "intel",
        .api = .metal,
    };
    const quirks = [_]model.Quirk{.{
        .schema_version = model.CURRENT_SCHEMA_VERSION,
        .quirk_id = "test_render_tex",
        .match_spec = .{ .vendor = "intel", .api = .metal },
        .scope = .layout,
        .safety_class = .high,
        .action = .{ .use_temporary_render_texture = .{ .min_mip_level = 2 } },
        .verification_mode = .guard_only,
        .proof_level = .guarded,
        .provenance = .{ .source_repo = "test", .source_path = "test", .source_commit = "abc", .observed_at = "test" },
        .priority = 10,
    }};
    const ctx = runtime.buildProfileDispatchContext(std.testing.allocator, profile, &quirks) catch return;
    defer ctx.deinit();

    const render_cmd: model.Command = .{ .render_draw = .{ .draw_count = 100 } };

    const active_result = dispatchWithMode(.active, profile, ctx, render_cmd);
    try std.testing.expect(active_result.command.render_draw.uses_temporary_render_texture);
    try std.testing.expectEqual(@as(u32, 2), active_result.command.render_draw.temporary_render_texture_min_mip_level);

    const trace_result = dispatchWithMode(.trace, profile, ctx, render_cmd);
    try std.testing.expect(!trace_result.command.render_draw.uses_temporary_render_texture);
}
