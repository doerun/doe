const std = @import("std");

/// Only absence permits trying another candidate; access failures retain their cause.
pub fn file_exists(path: []const u8) !bool {
    std.fs.cwd().access(path, .{}) catch |err| switch (err) {
        error.FileNotFound => return false,
        else => return err,
    };
    return true;
}

test "path probe distinguishes missing paths from invalid paths" {
    var temporary = std.testing.tmpDir(.{});
    defer temporary.cleanup();
    const root = try temporary.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    try std.testing.expect(try file_exists(root));
    const missing = try std.fs.path.join(std.testing.allocator, &.{ root, "missing" });
    defer std.testing.allocator.free(missing);
    try std.testing.expect(!try file_exists(missing));
    const too_long = [_]u8{'x'} ** (std.fs.max_path_bytes + 1);
    try std.testing.expectError(error.NameTooLong, file_exists(&too_long));
}
