const std = @import("std");
const doe_wgsl = @import("src/doe_wgsl/mod.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();
    const source = try std.fs.cwd().readFileAlloc(allocator, "../../bench/kernels/workgroup_atomic.wgsl", 1 << 20);
    defer allocator.free(source);
    var out: [doe_wgsl.MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try doe_wgsl.translateToSpirv(allocator, source, &out);
    try std.fs.cwd().writeFile(.{ .sub_path = "/tmp/workgroup_atomic.spv", .data = out[0..len] });
}
