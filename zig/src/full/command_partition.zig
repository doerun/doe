const std = @import("std");

pub const CommandKind = enum(u8) {
    render_draw,
    draw_indirect,
    draw_indexed_indirect,
    render_pass,
    sampler_create,
    sampler_destroy,
    surface_create,
    surface_capabilities,
    surface_configure,
    surface_acquire,
    surface_present,
    surface_unconfigure,
    surface_release,
    async_diagnostics,
};

pub fn fromCombined(kind: anytype) ?CommandKind {
    return std.meta.stringToEnum(CommandKind, @tagName(kind));
}

pub fn contains(kind: anytype) bool {
    return fromCombined(kind) != null;
}

pub fn name(kind: CommandKind) []const u8 {
    return @tagName(kind);
}
