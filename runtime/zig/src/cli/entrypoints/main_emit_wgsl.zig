const std = @import("std");
const compiler = @import("doe").compiler.wgsl_emit.wgsl();

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();
    const args = try std.process.argsAlloc(allocator);
    if (args.len == 2 and std.mem.eql(u8, args[1], "--help")) {
        try std.fs.File.stdout().deprecatedWriter().writeAll("doe-emit-wgsl <source.wgsl> <output.wgsl>\n");
        return;
    }
    if (args.len != 3) return error.ExpectedSourceAndOutputPaths;
    const source = try std.fs.cwd().readFileAlloc(allocator, args[1], 64 * 1024);
    var diagnostic = compiler.Diagnostic{};
    const result = compiler.rewrite(allocator, source, true, &diagnostic) catch |err| {
        try std.fs.File.stderr().deprecatedWriter().print("{s} at source byte {d}: {s}\n", .{
            diagnostic.stage, diagnostic.byte_offset, @errorName(err),
        });
        return err;
    };
    const output = try std.fs.cwd().createFile(args[2], .{});
    defer output.close();
    try output.writeAll(result.wgsl);
}
