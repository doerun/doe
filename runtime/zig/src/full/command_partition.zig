const std = @import("std");
const types = @import("../model_webgpu_types.zig");

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

/// Full-only command union — owns render, surface, sampler, and lifecycle commands.
/// This is the authoritative definition; model.zig re-exports it.
pub const Command = union(CommandKind) {
    render_draw: types.RenderDrawCommand,
    draw_indirect: types.DrawIndirectCommand,
    draw_indexed_indirect: types.DrawIndexedIndirectCommand,
    render_pass: types.RenderPassCommand,
    sampler_create: types.SamplerCreateCommand,
    sampler_destroy: types.SamplerDestroyCommand,
    surface_create: types.SurfaceCreateCommand,
    surface_capabilities: types.SurfaceCapabilitiesCommand,
    surface_configure: types.SurfaceConfigureCommand,
    surface_acquire: types.SurfaceAcquireCommand,
    surface_present: types.SurfacePresentCommand,
    surface_unconfigure: types.SurfaceUnconfigureCommand,
    surface_release: types.SurfaceReleaseCommand,
    async_diagnostics: types.AsyncDiagnosticsCommand,
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
