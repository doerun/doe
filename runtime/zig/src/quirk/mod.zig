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
