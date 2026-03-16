const std = @import("std");
const model = @import("../model.zig");
const toggle_registry = @import("toggle_registry.zig");

const BEHAVIORAL_TOGGLE_DEFAULT_ALIGNMENT: u32 = 256;

/// All known behavioral toggles that set uses_temporary_buffer on copy commands.
const STAGING_BUFFER_TOGGLES = [_][]const u8{
    "use_temporary_buffer_in_texture_to_texture_copy",
    "use_temp_buffer_in_small_format_texture_to_texture_copy_from_greater_to_less_mip_level",
    "d3d12_use_temp_buffer_in_depth_stencil_texture_and_buffer_copy_with_non_zero_buffer_offset",
    "d3d12_use_temp_buffer_in_texture_to_texture_copy_between_different_dimensions",
};

pub const RENDER_TEXTURE_TOGGLE = "MetalRenderR8RG8UnormSmallMipToTempTexture";
pub const RENDER_TEXTURE_DEFAULT_MIN_MIP_LEVEL: u32 = 2;

fn isStagingBufferToggle(toggle_name: []const u8) bool {
    for (&STAGING_BUFFER_TOGGLES) |known| {
        if (std.ascii.eqlIgnoreCase(toggle_name, known)) return true;
    }
    return false;
}

fn isRenderTextureToggle(toggle_name: []const u8) bool {
    return std.ascii.eqlIgnoreCase(toggle_name, RENDER_TEXTURE_TOGGLE);
}

pub fn applyTemporaryRenderTexture(payload: model.UseTemporaryRenderTextureAction, command: model.Command) model.Command {
    return switch (command) {
        .render_draw => |render| blk: {
            var modified = render;
            modified.uses_temporary_render_texture = true;
            modified.temporary_render_texture_min_mip_level = payload.min_mip_level;
            break :blk .{ .render_draw = modified };
        },
        .render_pass => |render| blk: {
            var modified = render;
            modified.uses_temporary_render_texture = true;
            modified.temporary_render_texture_min_mip_level = payload.min_mip_level;
            break :blk .{ .render_pass = modified };
        },
        else => command,
    };
}

pub fn applyBehavioralToggle(toggle_name: []const u8, command: model.Command) model.Command {
    if (isStagingBufferToggle(toggle_name)) {
        return switch (command) {
            .copy_buffer_to_texture => |copy| .{
                .copy_buffer_to_texture = .{
                    .direction = copy.direction,
                    .src = copy.src,
                    .dst = copy.dst,
                    .bytes = copy.bytes,
                    .uses_temporary_buffer = true,
                    .temporary_buffer_alignment = BEHAVIORAL_TOGGLE_DEFAULT_ALIGNMENT,
                },
            },
            else => command,
        };
    }
    if (isRenderTextureToggle(toggle_name)) {
        return applyTemporaryRenderTexture(.{ .min_mip_level = RENDER_TEXTURE_DEFAULT_MIN_MIP_LEVEL }, command);
    }
    return command;
}

pub fn applyAction(quirk: model.Quirk, command: model.Command) model.Command {
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
        .use_temporary_render_texture => |payload| {
            return applyTemporaryRenderTexture(payload, command);
        },
        .toggle => |toggle_payload| {
            if (toggle_registry.effect(toggle_payload.toggle_name) == .behavioral) {
                return applyBehavioralToggle(toggle_payload.toggle_name, command);
            }
            return command;
        },
        .no_op => return command,
    }
}

test "behavioral toggle sets uses_temporary_buffer on copy" {
    const toggles = [_][]const u8{
        "use_temporary_buffer_in_texture_to_texture_copy",
        "d3d12_use_temp_buffer_in_texture_to_texture_copy_between_different_dimensions",
    };
    for (&toggles) |toggle_name| {
        const copy_cmd: model.Command = .{
            .copy_buffer_to_texture = .{
                .direction = .texture_to_texture,
                .src = .{ .handle = 1 },
                .dst = .{ .handle = 2 },
                .bytes = 4096,
            },
        };
        const result = applyBehavioralToggle(toggle_name, copy_cmd);
        try std.testing.expect(result.copy_buffer_to_texture.uses_temporary_buffer);
        try std.testing.expectEqual(@as(u32, BEHAVIORAL_TOGGLE_DEFAULT_ALIGNMENT), result.copy_buffer_to_texture.temporary_buffer_alignment);
    }
}

test "behavioral toggle does not modify non-copy command" {
    const cmd: model.Command = .{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } };
    const result = applyBehavioralToggle("use_temporary_buffer_in_texture_to_texture_copy", cmd);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch.x);
}

test "use_temporary_render_texture sets flag on render_draw" {
    const quirk = model.Quirk{
        .schema_version = model.CURRENT_SCHEMA_VERSION,
        .quirk_id = "test_metal_render_tex",
        .match_spec = .{ .vendor = "intel", .api = .metal },
        .scope = .layout,
        .safety_class = .high,
        .action = .{ .use_temporary_render_texture = .{ .min_mip_level = 2 } },
        .verification_mode = .guard_only,
        .proof_level = .guarded,
        .provenance = .{ .source_repo = "test", .source_path = "test", .source_commit = "test", .observed_at = "test" },
        .priority = 10,
    };
    const cmd: model.Command = .{ .render_draw = .{ .draw_count = 1 } };
    const result = applyAction(quirk, cmd);
    try std.testing.expect(result.render_draw.uses_temporary_render_texture);
    try std.testing.expectEqual(@as(u32, 2), result.render_draw.temporary_render_texture_min_mip_level);
}

test "use_temporary_render_texture does not modify copy command" {
    const payload = model.UseTemporaryRenderTextureAction{ .min_mip_level = 2 };
    const cmd: model.Command = .{ .copy_buffer_to_texture = .{
        .direction = .buffer_to_texture,
        .src = .{ .handle = 1 },
        .dst = .{ .handle = 2 },
        .bytes = 4096,
    } };
    const result = applyTemporaryRenderTexture(payload, cmd);
    try std.testing.expect(!result.copy_buffer_to_texture.uses_temporary_buffer);
}

test "render texture behavioral toggle sets flag on render_draw" {
    const cmd: model.Command = .{ .render_draw = .{ .draw_count = 1 } };
    const result = applyBehavioralToggle(RENDER_TEXTURE_TOGGLE, cmd);
    try std.testing.expect(result.render_draw.uses_temporary_render_texture);
    try std.testing.expectEqual(RENDER_TEXTURE_DEFAULT_MIN_MIP_LEVEL, result.render_draw.temporary_render_texture_min_mip_level);
}

test "informational toggle produces identity transform" {
    const quirk = model.Quirk{
        .schema_version = model.CURRENT_SCHEMA_VERSION,
        .quirk_id = "test_info",
        .match_spec = .{ .vendor = "intel", .api = .vulkan },
        .scope = .driver_toggle,
        .safety_class = .low,
        .action = .{ .toggle = .{ .toggle_name = "disable_robustness" } },
        .verification_mode = .guard_only,
        .proof_level = .guarded,
        .provenance = .{ .source_repo = "test", .source_path = "test", .source_commit = "test", .observed_at = "test" },
        .priority = 10,
    };
    const cmd: model.Command = .{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } };
    const result = applyAction(quirk, cmd);
    try std.testing.expectEqual(@as(u32, 1), result.dispatch.x);
}
