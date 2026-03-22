const std = @import("std");
const ir = @import("doe_wgsl/ir.zig");

pub const ValidationError = error{
    DispatchPreconditionFailed,
    Overflow,
};

pub fn required_buffer_bytes(
    precondition: ir.DispatchPrecondition,
    dispatch_workgroups: [3]u32,
    workgroup_size: [3]u32,
) ValidationError!u64 {
    return switch (precondition.kind) {
        .gid_component => blk: {
            const axis = precondition.gid_axis;
            if (axis >= dispatch_workgroups.len or axis >= workgroup_size.len) {
                return error.DispatchPreconditionFailed;
            }
            const total_invocations = try invocation_extent(dispatch_workgroups[axis], workgroup_size[axis]);
            const scaled_invocations = try std.math.mul(u64, total_invocations, precondition.element_multiplier);
            const loop_elements = try std.math.mul(u64, precondition.loop_limit, precondition.loop_limit_multiplier);
            const affine_elements = try std.math.add(u64, scaled_invocations, loop_elements);
            const total_elements = try std.math.add(u64, affine_elements, precondition.element_offset);
            break :blk try std.math.mul(u64, total_elements, precondition.element_stride_bytes);
        },
        .gid_component_tiled => blk: {
            const axis = precondition.gid_axis;
            if (axis >= dispatch_workgroups.len or axis >= workgroup_size.len) {
                return error.DispatchPreconditionFailed;
            }
            if (precondition.tile_width == 0) return error.DispatchPreconditionFailed;
            if (precondition.element_multiplier < precondition.tile_width) {
                return error.DispatchPreconditionFailed;
            }
            const total_invocations = try invocation_extent(dispatch_workgroups[axis], workgroup_size[axis]);
            const tiled_groups = try tiled_group_count(total_invocations, precondition.tile_width);
            const scaled_groups = try std.math.mul(u64, tiled_groups, precondition.element_multiplier);
            const total_elements = try std.math.add(u64, scaled_groups, precondition.element_offset);
            break :blk try std.math.mul(u64, total_elements, precondition.element_stride_bytes);
        },
        .flat_index_2d_dispatch_x => blk: {
            const total_x = try invocation_extent(dispatch_workgroups[0], workgroup_size[0]);
            const total_y = try invocation_extent(dispatch_workgroups[1], workgroup_size[1]);
            const element_count = try std.math.mul(u64, total_x, total_y);
            const total_elements = try std.math.add(u64, element_count, precondition.element_offset);
            break :blk try std.math.mul(u64, total_elements, precondition.element_stride_bytes);
        },
    };
}

pub fn invocation_extent(dispatch_workgroups: u32, workgroup_size: u32) ValidationError!u64 {
    return std.math.mul(u64, dispatch_workgroups, workgroup_size) catch error.Overflow;
}

fn tiled_group_count(total_invocations: u64, tile_width: u64) ValidationError!u64 {
    if (tile_width == 0) return error.DispatchPreconditionFailed;
    if (total_invocations == 0) return 0;
    const truncated = try std.math.sub(u64, total_invocations, 1);
    const whole_tiles = truncated / tile_width;
    return std.math.add(u64, whole_tiles, 1) catch error.Overflow;
}

test "required_buffer_bytes computes gid component bound in bytes" {
    const required = try required_buffer_bytes(.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 1,
        .loop_limit = 0,
        .loop_limit_multiplier = 0,
        .element_stride_bytes = 4,
        .element_offset = 0,
    }, .{ 8, 1, 1 }, .{ 64, 1, 1 });
    try std.testing.expectEqual(@as(u64, 2048), required);
}

test "required_buffer_bytes computes 2d flat dispatch bound in bytes" {
    const required = try required_buffer_bytes(.{
        .kind = .flat_index_2d_dispatch_x,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 1 },
        .element_multiplier = 1,
        .loop_limit = 0,
        .loop_limit_multiplier = 0,
        .element_stride_bytes = 16,
        .element_offset = 0,
    }, .{ 4, 3, 1 }, .{ 8, 2, 1 });
    try std.testing.expectEqual(@as(u64, 3072), required);
}

test "required_buffer_bytes accounts for affine gid offset" {
    const required = try required_buffer_bytes(.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 1,
        .loop_limit = 0,
        .loop_limit_multiplier = 0,
        .element_stride_bytes = 4,
        .element_offset = 4,
    }, .{ 8, 1, 1 }, .{ 64, 1, 1 });
    try std.testing.expectEqual(@as(u64, 2064), required);
}

test "required_buffer_bytes accounts for affine gid multiplier and offset" {
    const required = try required_buffer_bytes(.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 4,
        .loop_limit = 0,
        .loop_limit_multiplier = 0,
        .element_stride_bytes = 4,
        .element_offset = 2,
    }, .{ 8, 1, 1 }, .{ 64, 1, 1 });
    try std.testing.expectEqual(@as(u64, 8200), required);
}

test "required_buffer_bytes accounts for tiled gid stride and offset" {
    const required = try required_buffer_bytes(.{
        .kind = .gid_component_tiled,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 8,
        .tile_width = 4,
        .loop_limit = 0,
        .loop_limit_multiplier = 0,
        .element_stride_bytes = 4,
        .element_offset = 3,
    }, .{ 8, 1, 1 }, .{ 8, 1, 1 });
    try std.testing.expectEqual(@as(u64, 524), required);
}

test "required_buffer_bytes accounts for affine loop contribution" {
    const required = try required_buffer_bytes(.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_multiplier = 1,
        .loop_limit = 4,
        .loop_limit_multiplier = 3,
        .element_stride_bytes = 4,
        .element_offset = 2,
    }, .{ 8, 1, 1 }, .{ 8, 1, 1 });
    try std.testing.expectEqual(@as(u64, 312), required);
}
