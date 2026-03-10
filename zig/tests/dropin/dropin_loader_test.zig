const std = @import("std");
const builtin = @import("builtin");
const loader = @import("../../src/core/abi/wgpu_loader.zig");

fn contains(candidates: []const []const u8, needle: []const u8) bool {
    for (candidates) |candidate| {
        if (std.mem.eql(u8, candidate, needle)) return true;
    }
    return false;
}

test "general loader candidates include the Doe runtime library" {
    const expected = switch (builtin.os.tag) {
        .windows => "webgpu_doe.dll",
        .macos => "libwebgpu_doe.dylib",
        else => "libwebgpu_doe.so",
    };
    try std.testing.expect(contains(loader.native_library_names, expected));
}

test "drop-in target candidates exclude the Doe runtime library" {
    const forbidden = switch (builtin.os.tag) {
        .windows => "webgpu_doe.dll",
        .macos => "libwebgpu_doe.dylib",
        else => "libwebgpu_doe.so",
    };
    try std.testing.expect(!contains(loader.dropin_target_library_names, forbidden));
}
