const std = @import("std");
const leases = @import("../../contracts/resource_lease.zig");
const objects = @import("../support/doe_native_object_types.zig");
const helpers = @import("../support/doe_native_object_helpers.zig");
const queries = @import("../resource/doe_query_native.zig");
const external = @import("../resource/doe_external_texture_native.zig");
const bundles = @import("../../runtime/render/render_bundle.zig");

pub const ValidationError = error{
    InvalidReference,
    BufferUnavailable,
    BufferMapped,
    TextureUnavailable,
    ExternalTextureExpired,
    QueryDestroyed,
    InvalidBundle,
};

pub fn message(err: ValidationError) []const u8 {
    return switch (err) {
        error.InvalidReference => "queue submission requires a valid retained resource",
        error.BufferUnavailable => "queue submission uses an invalid or destroyed buffer",
        error.BufferMapped => "queue submission requires buffers to be unmapped",
        error.TextureUnavailable => "queue submission uses an invalid or destroyed texture",
        error.ExternalTextureExpired => "queue submission uses an expired external texture",
        error.QueryDestroyed => "queue submission uses a destroyed query set",
        error.InvalidBundle => "queue submission uses an invalid render bundle",
    };
}

pub fn validate(references: []const leases.ResourceLease) ValidationError!void {
    for (references) |reference| switch (reference.kind) {
        .buffer => try validateBuffer(try object(objects.DoeBuffer, reference.handle)),
        .texture => try validateTexture(try object(objects.DoeTexture, reference.handle)),
        .texture_view => try validateView(try object(objects.DoeTextureView, reference.handle)),
        .bind_group => try validateGroup(try object(objects.DoeBindGroup, reference.handle)),
        .render_bundle => {
            const bundle = try object(bundles.DoeRenderBundle, reference.handle);
            if (bundle.error_object) return error.InvalidBundle;
            try validate(bundle.references.items);
        },
        .query_set => {
            const query = try object(queries.DoeQuerySet, reference.handle);
            if (query.destroyed) return error.QueryDestroyed;
        },
        .compute_pipeline => _ = try object(objects.DoeComputePipeline, reference.handle),
        .render_pipeline => _ = try object(objects.DoeRenderPipeline, reference.handle),
        .device => _ = try object(objects.DoeDevice, reference.handle),
        .untyped => return error.InvalidReference,
    };
}

fn object(comptime T: type, raw: ?*anyopaque) ValidationError!*T {
    return helpers.cast(T, raw) orelse error.InvalidReference;
}

fn validateBuffer(buffer: *const objects.DoeBuffer) ValidationError!void {
    if (buffer.error_object or buffer.destroyed) return error.BufferUnavailable;
    if (buffer.mapped) return error.BufferMapped;
}

fn validateTexture(texture: *const objects.DoeTexture) ValidationError!void {
    if (texture.isUnavailable()) return error.TextureUnavailable;
}

fn validateView(view: *const objects.DoeTextureView) ValidationError!void {
    try validateTexture(view.tex);
}

fn validateGroup(group: *const objects.DoeBindGroup) ValidationError!void {
    for (group.retained_buffers) |buffer| if (buffer) |value| try validateBuffer(value);
    for (group.retained_texture_views) |view| if (view) |value| try validateView(value);
    for (group.render_texture_views[0..group.render_texture_view_count]) |view| {
        try validateView(view orelse return error.InvalidReference);
    }
    for (group.retained_external_textures) |raw| if (raw != null) {
        const texture = try object(external.DoeExternalTexture, raw);
        if (texture.expired) return error.ExternalTextureExpired;
        if (!texture.native_imported) {
            try validateView(try object(objects.DoeTextureView, texture.plane0));
            if (!texture.is_single_plane) try validateView(try object(objects.DoeTextureView, texture.plane1));
        }
    };
}

fn testReference(kind: leases.ResourceLease.Kind, raw: ?*anyopaque) leases.ResourceLease {
    return .{ .kind = kind, .handle = raw, .release = struct {
        fn unused(_: ?*anyopaque) callconv(.c) void {}
    }.unused };
}

test "submission rechecks mutable resources through bind groups and bundles without taking ownership" {
    var buffer: objects.DoeBuffer = .{ .ref_count = 2 };
    var texture: objects.DoeTexture = .{};
    var view: objects.DoeTextureView = .{ .tex = &texture };
    var group: objects.DoeBindGroup = .{};
    group.retained_buffers[0] = &buffer;
    group.render_texture_views[0] = &view;
    group.render_texture_view_count = 1;
    var external_texture: external.DoeExternalTexture = .{ .plane0 = &view };
    group.retained_external_textures[1] = @ptrCast(&external_texture);
    var group_references = [_]leases.ResourceLease{testReference(.bind_group, &group)};
    var bundle: bundles.DoeRenderBundle = .{
        .allocator = std.testing.allocator,
        .color_format = 0,
        .depth_stencil_format = 0,
        .sample_count = 1,
        .cmds = &.{},
        .references = .{ .items = &group_references, .capacity = group_references.len },
    };
    const references = [_]leases.ResourceLease{testReference(.render_bundle, &bundle)};
    try validate(&references);
    buffer.mapped = true;
    try std.testing.expectError(error.BufferMapped, validate(&references));
    buffer.mapped = false;
    buffer.destroyed = true;
    try std.testing.expectError(error.BufferUnavailable, validate(&references));
    buffer.destroyed = false;
    buffer.error_object = true;
    try std.testing.expectError(error.BufferUnavailable, validate(&references));
    buffer.error_object = false;
    texture.destroyed = true;
    try std.testing.expectError(error.TextureUnavailable, validate(&references));
    texture.destroyed = false;
    external_texture.expired = true;
    try std.testing.expectError(error.ExternalTextureExpired, validate(&references));
    external_texture.expired = false;
    bundle.error_object = true;
    try std.testing.expectError(error.InvalidBundle, validate(&references));
    bundle.error_object = false;
    try validate(&references);
    try std.testing.expectEqual(@as(u32, 2), buffer.ref_count);
}

test "submission validates direct leases and rejects destroyed queries and untyped references" {
    var query: queries.DoeQuerySet = .{};
    const references = [_]leases.ResourceLease{testReference(.query_set, &query)};
    try validate(&references);
    query.destroyed = true;
    try std.testing.expectError(error.QueryDestroyed, validate(&references));
    try std.testing.expectError(error.InvalidReference, validate(&.{testReference(.untyped, &query)}));
    try std.testing.expectError(error.InvalidReference, validate(&.{testReference(.buffer, null)}));
    var buffer: objects.DoeBuffer = .{ .mapped = true };
    try std.testing.expectError(error.BufferMapped, validate(&.{testReference(.buffer, &buffer)}));
    var texture: objects.DoeTexture = .{ .destroyed = true };
    try std.testing.expectError(error.TextureUnavailable, validate(&.{testReference(.texture, &texture)}));
}
