const std = @import("std");

pub const CommandKind = enum(u8) {
    upload,
    copy_buffer_to_texture,
    barrier,
    dispatch,
    dispatch_indirect,
    kernel_dispatch,
    texture_write,
    texture_query,
    texture_destroy,
    map_async,
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
