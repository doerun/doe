const std = @import("std");
const command_json_raw = @import("../command_json_raw.zig");

pub const ParseError = command_json_raw.ParseError;
pub const RawCommand = command_json_raw.RawCommand;

pub const NormalizedKind = enum {
    upload,
    buffer_write,
    copy,
    barrier,
    dispatch,
    dispatch_indirect,
    kernel_dispatch,
    render_draw,
    draw_indirect,
    draw_indexed_indirect,
    render_pass,
    sampler_create,
    sampler_destroy,
    texture_write,
    texture_query,
    texture_destroy,
    surface_create,
    surface_capabilities,
    surface_configure,
    surface_acquire,
    surface_present,
    surface_unconfigure,
    surface_release,
    async_diagnostics,
    map_async,
};

pub fn commandKindEquals(raw_kind: []const u8, kind: []const u8) bool {
    return std.ascii.eqlIgnoreCase(raw_kind, kind);
}

pub fn getCommandName(raw: RawCommand) ?[]const u8 {
    if (raw.map_async != null) return "map_async";
    return raw.command orelse raw.kind orelse raw.command_kind;
}

fn matchesAny(raw_kind: []const u8, comptime candidates: []const []const u8) bool {
    inline for (candidates) |candidate| {
        if (commandKindEquals(raw_kind, candidate)) {
            return true;
        }
    }
    return false;
}

pub fn parseKind(raw: RawCommand) ParseError!NormalizedKind {
    const kind = getCommandName(raw) orelse return ParseError.MissingCommandKind;

    if (matchesAny(kind, &.{ "upload", "buffer_upload" })) {
        return .upload;
    }
    if (matchesAny(kind, &.{ "buffer_write", "write_buffer", "queue_write_buffer" })) {
        return .buffer_write;
    }
    if (matchesAny(kind, &.{
        "copy_buffer_to_texture",
        "copy_texture",
        "texture_copy",
        "copy_texture_to_buffer",
        "copy_buffer_to_buffer",
        "buffer_copy",
        "copyBufferToTexture",
        "copyTextureToBuffer",
        "copyBufferToBuffer",
        "copy_texture_to_texture",
    })) {
        return .copy;
    }
    if (matchesAny(kind, &.{"barrier"})) {
        return .barrier;
    }
    if (matchesAny(kind, &.{ "dispatch", "dispatch_workgroups", "dispatch_invocations" })) {
        return .dispatch;
    }
    if (matchesAny(kind, &.{"dispatch_indirect"})) {
        return .dispatch_indirect;
    }
    if (matchesAny(kind, &.{"kernel_dispatch"})) {
        return .kernel_dispatch;
    }
    if (matchesAny(kind, &.{"draw_indirect"})) {
        return .draw_indirect;
    }
    if (matchesAny(kind, &.{"draw_indexed_indirect"})) {
        return .draw_indexed_indirect;
    }
    if (matchesAny(kind, &.{"render_pass"})) {
        return .render_pass;
    }
    if (matchesAny(kind, &.{ "render_draw", "draw", "draw_call", "draw_indexed" })) {
        return .render_draw;
    }
    if (matchesAny(kind, &.{ "sampler_create", "create_sampler" })) {
        return .sampler_create;
    }
    if (matchesAny(kind, &.{ "sampler_destroy", "destroy_sampler" })) {
        return .sampler_destroy;
    }
    if (matchesAny(kind, &.{ "texture_write", "write_texture", "queue_write_texture" })) {
        return .texture_write;
    }
    if (matchesAny(kind, &.{ "texture_query", "query_texture" })) {
        return .texture_query;
    }
    if (matchesAny(kind, &.{ "texture_destroy", "destroy_texture" })) {
        return .texture_destroy;
    }
    if (matchesAny(kind, &.{ "surface_create", "create_surface" })) {
        return .surface_create;
    }
    if (matchesAny(kind, &.{ "surface_capabilities", "surface_get_capabilities" })) {
        return .surface_capabilities;
    }
    if (matchesAny(kind, &.{ "surface_configure", "configure_surface" })) {
        return .surface_configure;
    }
    if (matchesAny(kind, &.{ "surface_acquire", "surface_get_current_texture", "surface_current_texture" })) {
        return .surface_acquire;
    }
    if (matchesAny(kind, &.{ "surface_present", "present_surface" })) {
        return .surface_present;
    }
    if (matchesAny(kind, &.{ "surface_unconfigure", "unconfigure_surface" })) {
        return .surface_unconfigure;
    }
    if (matchesAny(kind, &.{ "surface_release", "release_surface" })) {
        return .surface_release;
    }
    if (matchesAny(kind, &.{ "async_diagnostics", "pipeline_async_diagnostics" })) {
        return .async_diagnostics;
    }
    if (matchesAny(kind, &.{ "map_async", "buffer_map_async" })) {
        return .map_async;
    }

    return ParseError.UnknownCommandKind;
}
