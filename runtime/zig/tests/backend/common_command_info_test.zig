const std = @import("std");
const model = @import("../../src/contracts/command.zig");
const command_info = @import("../../src/contracts/command.zig");

test "manifest_module returns correct names for all commands" {
    const upload_cmd = model.Command{ .upload = .{ .bytes = 1024, .align_bytes = 256 } };
    try std.testing.expectEqualStrings("upload", command_info.manifest_module(upload_cmd));

    const barrier_cmd = model.Command{ .barrier = .{ .dependency_count = 1 } };
    try std.testing.expectEqualStrings("barrier", command_info.manifest_module(barrier_cmd));

    const dispatch_cmd = model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } };
    try std.testing.expectEqualStrings("dispatch", command_info.manifest_module(dispatch_cmd));

    const kernel_cmd = model.Command{ .kernel_dispatch = .{
        .kernel = "matvec.wgsl",
        .x = 1,
        .y = 1,
        .z = 1,
    } };
    try std.testing.expectEqualStrings("kernel_dispatch", command_info.manifest_module(kernel_cmd));
}

test "shader_artifact_module returns concrete kernel name for kernel dispatch" {
    const kernel_cmd = model.Command{ .kernel_dispatch = .{
        .kernel = "matvec.wgsl",
        .x = 1,
        .y = 1,
        .z = 1,
    } };
    try std.testing.expectEqualStrings("matvec.wgsl", command_info.shader_artifact_module(kernel_cmd));

    const dispatch_cmd = model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } };
    try std.testing.expectEqualStrings("dispatch", command_info.shader_artifact_module(dispatch_cmd));
}

test "is_dispatch identifies dispatch commands" {
    const dispatch = model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } };
    try std.testing.expect(command_info.is_dispatch(dispatch));

    const dispatch_indirect = model.Command{ .dispatch_indirect = .{ .x = 1, .y = 1, .z = 1 } };
    try std.testing.expect(command_info.is_dispatch(dispatch_indirect));

    const kernel = model.Command{ .kernel_dispatch = .{
        .kernel = "test",
        .x = 1,
        .y = 1,
        .z = 1,
    } };
    try std.testing.expect(command_info.is_dispatch(kernel));
}

test "is_dispatch rejects non-dispatch commands" {
    const upload = model.Command{ .upload = .{ .bytes = 1024, .align_bytes = 256 } };
    try std.testing.expect(!command_info.is_dispatch(upload));

    const barrier = model.Command{ .barrier = .{ .dependency_count = 1 } };
    try std.testing.expect(!command_info.is_dispatch(barrier));
}

test "operation_count returns repeat for kernel_dispatch" {
    const kernel = model.Command{ .kernel_dispatch = .{
        .kernel = "test",
        .x = 1,
        .y = 1,
        .z = 1,
        .repeat = 50,
    } };
    try std.testing.expectEqual(@as(u32, 50), command_info.operation_count(kernel));
}

test "operation_count returns 1 for zero repeat kernel_dispatch" {
    const kernel = model.Command{ .kernel_dispatch = .{
        .kernel = "test",
        .x = 1,
        .y = 1,
        .z = 1,
        .repeat = 0,
    } };
    try std.testing.expectEqual(@as(u32, 1), command_info.operation_count(kernel));
}

test "operation_count returns draw_count for render commands" {
    const render = model.Command{ .render_draw = .{ .draw_count = 10 } };
    try std.testing.expectEqual(@as(u32, 10), command_info.operation_count(render));
}

test "operation_count returns 1 for simple dispatch" {
    const dispatch = model.Command{ .dispatch = .{ .x = 1, .y = 1, .z = 1 } };
    try std.testing.expectEqual(@as(u32, 1), command_info.operation_count(dispatch));
}

test "operation accounting preserves payload counts and zero normalization" {
    const cases = [_]struct { requested: u32, expected: u32 }{
        .{ .requested = 0, .expected = 1 },
        .{ .requested = 1, .expected = 1 },
        .{ .requested = 37, .expected = 37 },
        .{ .requested = std.math.maxInt(u32), .expected = std.math.maxInt(u32) },
    };
    for (cases) |case| {
        const commands = [_]model.Command{
            .{ .kernel_dispatch = .{ .kernel = "accounting.wgsl", .x = 8, .y = 4, .z = 2, .repeat = case.requested } },
            .{ .render_draw = .{ .draw_count = case.requested, .vertex_count = 9, .instance_count = 3 } },
            .{ .draw_indirect = .{ .draw_count = case.requested } },
            .{ .draw_indexed_indirect = .{ .draw_count = case.requested } },
            .{ .render_pass = .{ .draw_count = case.requested } },
            .{ .async_diagnostics = .{ .iterations = case.requested } },
        };
        for (commands) |command| {
            try std.testing.expectEqual(case.expected, command_info.operation_count(command));
            try std.testing.expectEqual(case.expected, command_info.requirements(command).operation_count);
        }
    }
}

test "single operation accounting does not count bytes workgroups or dependencies" {
    const commands = [_]model.Command{
        .{ .upload = .{ .bytes = 4096, .align_bytes = 256 } },
        .{ .dispatch = .{ .x = 8, .y = 4, .z = 2 } },
        .{ .dispatch_indirect = .{ .x = 8, .y = 4, .z = 2 } },
        .{ .barrier = .{ .dependency_count = 7 } },
        .{ .map_async = .{ .bytes = 4096 } },
    };
    for (commands) |command| {
        try std.testing.expectEqual(@as(u32, 1), command_info.operation_count(command));
        try std.testing.expectEqual(@as(u32, 1), command_info.requirements(command).operation_count);
    }
}
