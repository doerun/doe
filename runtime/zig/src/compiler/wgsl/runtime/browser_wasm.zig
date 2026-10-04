const std = @import("std");
const rewrite = @import("../emit/wgsl_rewrite.zig");

pub const MAX_SOURCE_BYTES: usize = 64 * 1024;
const allocator = std.heap.wasm_allocator;
var input: []u8 = &.{};
var output: []const u8 = &.{};

pub fn source_limit() u32 {
    return MAX_SOURCE_BYTES;
}

// One Worker owns one instance. No borrowed input/output escapes a compile job.
pub fn reserve_source(length: u32) u32 {
    if (length == 0 or length > MAX_SOURCE_BYTES) return 0;
    allocator.free(input);
    input = &.{};
    input = allocator.alloc(u8, length) catch return 0;
    return @intCast(@intFromPtr(input.ptr));
}

pub fn compile(length: u32, passes_enabled: u32) u32 {
    allocator.free(output);
    output = &.{};
    if (length != input.len or passes_enabled > 1) return 0;
    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();
    var diagnostic = rewrite.Diagnostic{};
    const result = rewrite.rewrite(arena.allocator(), input, passes_enabled == 1, &diagnostic) catch |err| {
        output = std.json.Stringify.valueAlloc(allocator, .{
            .schemaVersion = @as(u32, 1),
            .ok = false,
            .diagnostic = .{ .stage = diagnostic.stage, .message = @errorName(err), .byteOffset = diagnostic.byte_offset },
        }, .{}) catch return 0;
        return @intCast(@intFromPtr(output.ptr));
    };
    output = std.json.Stringify.valueAlloc(allocator, .{
        .schemaVersion = @as(u32, 1),
        .ok = true,
        .wgsl = result.wgsl,
        .rewrites = result.rewrites,
        .diagnostics = [_]u8{},
    }, .{}) catch return 0;
    return @intCast(@intFromPtr(output.ptr));
}

pub fn output_length() u32 {
    return @intCast(output.len);
}

pub fn release_job() void {
    allocator.free(input);
    allocator.free(output);
    input = &.{};
    output = &.{};
}
