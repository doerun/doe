const std = @import("std");
const doe_wgsl = @import("src/doe_wgsl/mod.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);
    if (args.len != 3) return error.InvalidArgument;

    const input_path = args[1];
    const output_path = args[2];
    const wgsl = try std.fs.cwd().readFileAlloc(allocator, input_path, 2 * 1024 * 1024);
    defer allocator.free(wgsl);

    var spirv_buf = try allocator.alloc(u8, doe_wgsl.MAX_SPIRV_OUTPUT);
    defer allocator.free(spirv_buf);
    const spirv_len = try doe_wgsl.translateToSpirv(allocator, wgsl, spirv_buf);
    try std.fs.cwd().writeFile(.{ .sub_path = output_path, .data = spirv_buf[0..spirv_len] });
}
