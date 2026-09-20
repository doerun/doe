const std = @import("std");
const model_resource_types = @import("src/contracts/model/model_resource_types.zig");
fn alignedStagingSize(cmd: model_resource_types.CopyCommand) !u64 {
    const raw: u64 = if (cmd.bytes > 0) @intCast(cmd.bytes) else blk: {
        const w: u64 = if (cmd.src.width > 0) cmd.src.width else 1;
        const h: u64 = if (cmd.src.height > 0) cmd.src.height else 1;
        const d: u64 = if (cmd.src.depth_or_array_layers > 0) cmd.src.depth_or_array_layers else 1;
        const pixels = std.math.mul(u64, w, h) catch return error.InvalidArgument;
        const volume = std.math.mul(u64, pixels, d) catch return error.InvalidArgument;
        break :blk std.math.mul(u64, volume, 4) catch return error.InvalidArgument;
    };
    const a: u64 = if (cmd.temporary_buffer_alignment > 1) cmd.temporary_buffer_alignment else 1;
    const rounded = std.math.add(u64, raw, a - 1) catch return error.InvalidArgument;
    return rounded / a * a;
}
test "predecessor must retain the padded texture footprint" {
    const cmd = model_resource_types.CopyCommand{
        .direction = .texture_to_texture,
        .src = .{ .handle = 1, .width = 4, .height = 4, .depth_or_array_layers = 2, .bytes_per_row = 256, .rows_per_image = 6 },
        .dst = .{ .handle = 2 },
        .bytes = 128,
        .uses_temporary_buffer = true,
        .temporary_buffer_alignment = 256,
    };
    try std.testing.expectEqual(@as(u64, 2560), try alignedStagingSize(cmd));
}
