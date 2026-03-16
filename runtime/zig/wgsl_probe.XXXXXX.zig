const std = @import("std");
const wgsl = @import("src/doe_wgsl/mod.zig");

pub fn main() !void {
    const source =
        "@group(0) @binding(0) var<storage, read_write> data: array<f32>;\n" ++
        "@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {\n" ++
        "    data[id.x] = data[id.x] * 2.0;\n" ++
        "}\n";
    var buf: [wgsl.MAX_OUTPUT]u8 = undefined;
    const len = wgsl.translateToMsl(std.heap.page_allocator, source, &buf) catch |err| {
        std.debug.print("ERR {s}\n", .{@errorName(err)});
        return;
    };
    std.debug.print("OK\n{s}\n", .{buf[0..len]});
}
