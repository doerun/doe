const std = @import("std");
const types = @import("../model_webgpu_types.zig");

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

/// Core command union — owns compute, copy, resource, and queue-sync commands.
/// This is the authoritative definition; model.zig re-exports it.
pub const Command = union(CommandKind) {
    upload: types.UploadCommand,
    copy_buffer_to_texture: types.CopyCommand,
    barrier: types.BarrierCommand,
    dispatch: types.DispatchCommand,
    dispatch_indirect: types.DispatchIndirectCommand,
    kernel_dispatch: types.KernelDispatchCommand,
    texture_write: types.TextureWriteCommand,
    texture_query: types.TextureQueryCommand,
    texture_destroy: types.TextureDestroyCommand,
    map_async: types.MapAsyncCommand,
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
