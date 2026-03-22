const std = @import("std");
const dispatch_preconditions = @import("dispatch_preconditions.zig");
const native = @import("doe_wgpu_native.zig");
const ir = @import("doe_wgsl/ir.zig");

pub const ValidationError = dispatch_preconditions.ValidationError;

pub fn validate_bind_groups(
    preconditions: []const ir.DispatchPrecondition,
    texture_preconditions: []const ir.TextureDispatchPrecondition,
    bind_groups: []const ?*native.DoeBindGroup,
    dispatch_workgroups: [3]u32,
    workgroup_size: [3]u32,
) ValidationError!void {
    for (preconditions) |precondition| {
        const group = precondition.storage_binding.group;
        const binding = precondition.storage_binding.binding;
        if (group >= bind_groups.len) return error.DispatchPreconditionFailed;
        const bind_group = bind_groups[group] orelse return error.DispatchPreconditionFailed;
        if (binding >= bind_group.buffers.len) return error.DispatchPreconditionFailed;
        if (bind_group.buffers[binding] == null) return error.DispatchPreconditionFailed;
        const required = try dispatch_preconditions.required_buffer_bytes(precondition, dispatch_workgroups, workgroup_size);
        if (required > bind_group.buffer_sizes[binding]) return error.DispatchPreconditionFailed;
    }
    for (texture_preconditions) |precondition| {
        const group = precondition.texture_binding.group;
        const binding = precondition.texture_binding.binding;
        if (group >= bind_groups.len) return error.DispatchPreconditionFailed;
        const bind_group = bind_groups[group] orelse return error.DispatchPreconditionFailed;
        if (binding >= bind_group.texture_views.len) return error.DispatchPreconditionFailed;
        const raw_view = bind_group.texture_views[binding] orelse return error.DispatchPreconditionFailed;
        const view = native.cast(native.DoeTextureView, raw_view) orelse return error.DispatchPreconditionFailed;
        const required_x = try dispatch_preconditions.invocation_extent(dispatch_workgroups[0], workgroup_size[0]);
        const required_y = try dispatch_preconditions.invocation_extent(dispatch_workgroups[1], workgroup_size[1]);
        if (required_x > mip_extent(view.tex.width, precondition.mip_level)) return error.DispatchPreconditionFailed;
        if (required_y > mip_extent(view.tex.height, precondition.mip_level)) return error.DispatchPreconditionFailed;
        switch (precondition.kind) {
            .gid_coords_2d => {},
            .gid_coords_3d => {
                const required_z = try dispatch_preconditions.invocation_extent(dispatch_workgroups[2], workgroup_size[2]);
                if (required_z > mip_extent(view.tex.depth_or_array_layers, precondition.mip_level)) {
                    return error.DispatchPreconditionFailed;
                }
            },
        }
    }
}

fn mip_extent(base: u32, level: u32) u64 {
    if (base == 0) return 0;
    if (level >= 31) return 1;
    const shifted = base >> @intCast(level);
    return if (shifted > 0) shifted else 1;
}

test "validate_bind_groups accepts matching gid component coverage" {
    var bind_group = native.DoeBindGroup{};
    bind_group.buffers[0] = @ptrFromInt(1);
    bind_group.buffer_sizes[0] = 2048;

    try validate_bind_groups(&.{.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 1,
        .element_stride_bytes = 4,
        .element_offset = 0,
    }}, &.{}, &.{&bind_group}, .{ 8, 1, 1 }, .{ 64, 1, 1 });
}

test "validate_bind_groups rejects undersized 2d flat coverage" {
    var bind_group = native.DoeBindGroup{};
    bind_group.buffers[1] = @ptrFromInt(1);
    bind_group.buffer_sizes[1] = 2047;

    try std.testing.expectError(error.DispatchPreconditionFailed, validate_bind_groups(&.{.{
        .kind = .flat_index_2d_dispatch_x,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 1 },
        .element_multiplier = 1,
        .element_stride_bytes = 16,
        .element_offset = 0,
    }}, &.{}, &.{&bind_group}, .{ 4, 3, 1 }, .{ 8, 2, 1 }));
}

test "validate_bind_groups accepts affine gid multiplier coverage" {
    var bind_group = native.DoeBindGroup{};
    bind_group.buffers[0] = @ptrFromInt(1);
    bind_group.buffer_sizes[0] = 8200;

    try validate_bind_groups(&.{.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 4,
        .element_stride_bytes = 4,
        .element_offset = 2,
    }}, &.{}, &.{&bind_group}, .{ 8, 1, 1 }, .{ 64, 1, 1 });
}

test "validate_bind_groups accepts tiled gid coverage" {
    var bind_group = native.DoeBindGroup{};
    bind_group.buffers[0] = @ptrFromInt(1);
    bind_group.buffer_sizes[0] = 524;

    try validate_bind_groups(&.{.{
        .kind = .gid_component_tiled,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 8,
        .tile_width = 4,
        .element_stride_bytes = 4,
        .element_offset = 3,
    }}, &.{}, &.{&bind_group}, .{ 8, 1, 1 }, .{ 8, 1, 1 });
}

test "validate_bind_groups accepts matching 2d texture coverage" {
    var texture = native.DoeTexture{
        .width = 64,
        .height = 32,
    };
    var view = native.DoeTextureView{
        .tex = &texture,
    };
    var bind_group = native.DoeBindGroup{};
    bind_group.texture_views[0] = native.toOpaque(&view);

    try validate_bind_groups(&.{}, &.{.{
        .kind = .gid_coords_2d,
        .texture_binding = .{ .group = 0, .binding = 0 },
        .mip_level = 0,
    }}, &.{&bind_group}, .{ 8, 4, 1 }, .{ 8, 8, 1 });
}

test "validate_bind_groups rejects undersized 2d texture coverage" {
    var texture = native.DoeTexture{
        .width = 63,
        .height = 32,
    };
    var view = native.DoeTextureView{
        .tex = &texture,
    };
    var bind_group = native.DoeBindGroup{};
    bind_group.texture_views[0] = native.toOpaque(&view);

    try std.testing.expectError(error.DispatchPreconditionFailed, validate_bind_groups(&.{}, &.{.{
        .kind = .gid_coords_2d,
        .texture_binding = .{ .group = 0, .binding = 0 },
        .mip_level = 0,
    }}, &.{&bind_group}, .{ 8, 4, 1 }, .{ 8, 8, 1 }));
}
