const std = @import("std");
const model = @import("../../contracts/command.zig");
const runtime_types = @import("../../contracts/runtime_types.zig");

pub fn should_emit_shader_artifact(command: model.Command) bool {
    return switch (command) {
        .dispatch,
        .dispatch_indirect,
        .kernel_dispatch,
        .render_draw,
        .draw_indirect,
        .draw_indexed_indirect,
        .render_pass,
        => true,
        .upload,
        .buffer_write,
        .copy_buffer_to_texture,
        .barrier,
        .sampler_create,
        .sampler_destroy,
        .texture_write,
        .texture_query,
        .texture_destroy,
        .surface_create,
        .surface_capabilities,
        .surface_configure,
        .surface_acquire,
        .surface_present,
        .surface_unconfigure,
        .surface_release,
        .async_diagnostics,
        .map_async,
        => false,
    };
}

pub fn artifact_status_code(result: runtime_types.NativeExecutionResult) []const u8 {
    if (result.status_message.len != 0) return result.status_message;
    return switch (result.status) {
        .ok => "ok",
        .unsupported => "unsupported",
        .@"error" => "error",
    };
}

const STATUS_FORMAT_ERROR = "status_format_error";

/// Returns either the formatted buffer view or a static diagnostic; callers
/// must use this returned slice instead of reading an unwritten buffer prefix.
pub fn formatStatus(storage: []u8, comptime fmt: []const u8, args: anytype) []const u8 {
    return std.fmt.bufPrint(storage, fmt, args) catch STATUS_FORMAT_ERROR;
}

test "artifact policy selects shader commands and preserves explicit errors" {
    inline for (std.meta.fields(model.Kind)) |field| {
        const kind = @field(model.Kind, field.name);
        const command = @unionInit(model.Command, field.name, undefined);
        const expected = std.mem.indexOfScalar(model.Kind, &.{
            .dispatch,      .dispatch_indirect,     .kernel_dispatch, .render_draw,
            .draw_indirect, .draw_indexed_indirect, .render_pass,
        }, kind) != null;
        try std.testing.expectEqual(expected, should_emit_shader_artifact(command));
    }
    try std.testing.expectEqualStrings("original", artifact_status_code(.{ .status = .@"error", .status_message = "original" }));
    try std.testing.expectEqualStrings("unsupported", artifact_status_code(.{ .status = .unsupported, .status_message = "" }));
}

test "status formatting overflow returns initialized fallback bytes" {
    var storage: [4]u8 = @splat(0xaa);
    try std.testing.expectEqualStrings(STATUS_FORMAT_ERROR, formatStatus(&storage, "{s}", .{"too long"}));
    try std.testing.expectEqualStrings("ok", formatStatus(&storage, "{s}", .{"ok"}));
}
