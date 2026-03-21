const std = @import("std");
const dispatch_preconditions = @import("dispatch_preconditions.zig");
const native = @import("doe_wgpu_native.zig");
const ir = @import("doe_wgsl/ir.zig");

pub const ValidationError = dispatch_preconditions.ValidationError;

pub fn validate_bind_groups(
    preconditions: []const ir.DispatchPrecondition,
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
}

test "validate_bind_groups accepts matching gid component coverage" {
    var bind_group = native.DoeBindGroup{};
    bind_group.buffers[0] = @ptrFromInt(1);
    bind_group.buffer_sizes[0] = 2048;

    try validate_bind_groups(&.{.{
        .kind = .gid_component,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 0 },
        .element_stride_bytes = 4,
    }}, &.{&bind_group}, .{ 8, 1, 1 }, .{ 64, 1, 1 });
}

test "validate_bind_groups rejects undersized 2d flat coverage" {
    var bind_group = native.DoeBindGroup{};
    bind_group.buffers[1] = @ptrFromInt(1);
    bind_group.buffer_sizes[1] = 2047;

    try std.testing.expectError(error.DispatchPreconditionFailed, validate_bind_groups(&.{.{
        .kind = .flat_index_2d_dispatch_x,
        .gid_axis = 0,
        .storage_binding = .{ .group = 0, .binding = 1 },
        .element_stride_bytes = 16,
    }}, &.{&bind_group}, .{ 4, 3, 1 }, .{ 8, 2, 1 }));
}
