const std = @import("std");
const command = @import("../contracts/command.zig");
const command_json_raw = @import("command_json_raw.zig");

pub const ParseError = command_json_raw.ParseError;
pub const RawCommand = command_json_raw.RawCommand;

pub const NormalizedKind = command.Kind;
const ALIAS_VALIDATION_BRANCH_QUOTA = 100_000;

pub fn commandKindEquals(raw_kind: []const u8, kind: []const u8) bool {
    return std.ascii.eqlIgnoreCase(raw_kind, kind);
}

pub fn getCommandName(raw: RawCommand) ?[]const u8 {
    if (raw.map_async != null) return command.name(.map_async);
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

const KindAliases = struct {
    kind: NormalizedKind,
    aliases: []const []const u8,
};

const KIND_ALIASES = [_]KindAliases{
    .{ .kind = .upload, .aliases = &.{"buffer_upload"} },
    .{ .kind = .buffer_write, .aliases = &.{ "write_buffer", "queue_write_buffer" } },
    .{ .kind = .copy_buffer_to_texture, .aliases = &.{
        "copy_texture",
        "texture_copy",
        "copy_texture_to_buffer",
        "copy_buffer_to_buffer",
        "buffer_copy",
        "copyBufferToTexture",
        "copyTextureToBuffer",
        "copyBufferToBuffer",
        "copy_texture_to_texture",
    } },
    .{ .kind = .barrier, .aliases = &.{} },
    .{ .kind = .dispatch, .aliases = &.{ "dispatch_workgroups", "dispatch_invocations" } },
    .{ .kind = .dispatch_indirect, .aliases = &.{} },
    .{ .kind = .kernel_dispatch, .aliases = &.{} },
    .{ .kind = .draw_indirect, .aliases = &.{} },
    .{ .kind = .draw_indexed_indirect, .aliases = &.{} },
    .{ .kind = .render_pass, .aliases = &.{} },
    .{ .kind = .render_draw, .aliases = &.{ "draw", "draw_call", "draw_indexed" } },
    .{ .kind = .sampler_create, .aliases = &.{"create_sampler"} },
    .{ .kind = .sampler_destroy, .aliases = &.{"destroy_sampler"} },
    .{ .kind = .texture_write, .aliases = &.{ "write_texture", "queue_write_texture" } },
    .{ .kind = .texture_query, .aliases = &.{"query_texture"} },
    .{ .kind = .texture_destroy, .aliases = &.{"destroy_texture"} },
    .{ .kind = .surface_create, .aliases = &.{"create_surface"} },
    .{ .kind = .surface_capabilities, .aliases = &.{"surface_get_capabilities"} },
    .{ .kind = .surface_configure, .aliases = &.{"configure_surface"} },
    .{ .kind = .surface_acquire, .aliases = &.{ "surface_get_current_texture", "surface_current_texture" } },
    .{ .kind = .surface_present, .aliases = &.{"present_surface"} },
    .{ .kind = .surface_unconfigure, .aliases = &.{"unconfigure_surface"} },
    .{ .kind = .surface_release, .aliases = &.{"release_surface"} },
    .{ .kind = .async_diagnostics, .aliases = &.{"pipeline_async_diagnostics"} },
    .{ .kind = .map_async, .aliases = &.{"buffer_map_async"} },
};

comptime {
    @setEvalBranchQuota(ALIAS_VALIDATION_BRANCH_QUOTA);
    var covered = std.EnumSet(NormalizedKind).initEmpty();
    for (KIND_ALIASES, 0..) |entry, index| {
        if (covered.contains(entry.kind)) @compileError("duplicate command alias owner: " ++ @tagName(entry.kind));
        covered.insert(entry.kind);
        for (entry.aliases, 0..) |alias, alias_index| {
            if (alias.len == 0) @compileError("empty command alias: " ++ @tagName(entry.kind));
            for (std.enums.values(NormalizedKind)) |kind| {
                if (commandKindEquals(alias, command.name(kind))) @compileError("command alias duplicates a canonical name: " ++ alias);
            }
            for (KIND_ALIASES[0 .. index + 1], 0..) |previous, previous_index| {
                const limit = if (previous_index == index) alias_index else previous.aliases.len;
                for (previous.aliases[0..limit]) |previous_alias| {
                    if (commandKindEquals(alias, previous_alias)) @compileError("ambiguous command alias: " ++ alias);
                }
            }
        }
    }
    for (std.enums.values(NormalizedKind)) |kind| {
        if (!covered.contains(kind)) @compileError("missing command alias owner: " ++ @tagName(kind));
    }
}

pub fn parseKind(raw: RawCommand) ParseError!NormalizedKind {
    const kind = getCommandName(raw) orelse return ParseError.MissingCommandKind;
    inline for (KIND_ALIASES) |entry| {
        if (commandKindEquals(kind, command.name(entry.kind)) or matchesAny(kind, entry.aliases)) return entry.kind;
    }
    return ParseError.UnknownCommandKind;
}
