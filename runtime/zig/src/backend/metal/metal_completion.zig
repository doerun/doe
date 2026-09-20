//! Submitted command-buffer references live here until their own result is read.
const std = @import("std");
const bridge = @import("metal_bridge_decls.zig");

pub const Completion = struct {
    pending: std.ArrayListUnmanaged(*anyopaque) = .{},
    // Preserve the first native NSError code, including an unavailable code (0).
    failure_code: ?i64 = null,

    pub fn check(self: *const Completion) error{MetalCommandFailed}!void {
        if (self.failure_code != null) return error.MetalCommandFailed;
    }

    /// Reserve before committing; failure leaves the unsubmitted buffer with its caller.
    pub fn reserve(self: *Completion, allocator: std.mem.Allocator) !void {
        try self.check();
        try self.pending.ensureUnusedCapacity(allocator, 1);
    }

    /// Transfers a +1 reference after commit. Call reserve before native submission.
    pub fn retainSubmitted(self: *Completion, command: *anyopaque) void {
        self.pending.appendAssumeCapacity(command);
    }

    /// Retire every submission even after failure, then let the caller clean resources
    /// and call check. A successful successor never clears an earlier failure.
    pub fn retire(self: *Completion) void {
        self.retireWithBridge(bridge);
    }

    pub fn retireOne(self: *Completion, command: *anyopaque) void {
        self.retireOneWithBridge(command, bridge);
    }

    pub fn deinit(self: *Completion, allocator: std.mem.Allocator) void {
        self.retire();
        self.pending.deinit(allocator);
        self.pending = .{};
    }

    fn retireWithBridge(self: *Completion, comptime native: type) void {
        for (self.pending.items) |command| self.retireOneWithBridge(command, native);
        self.pending.clearRetainingCapacity();
    }

    fn retireOneWithBridge(self: *Completion, command: *anyopaque, comptime native: type) void {
        var code: i64 = 0;
        const succeeded = native.metal_bridge_command_buffer_wait_result(command, &code);
        if (succeeded == 0 and self.failure_code == null) self.failure_code = code;
        native.metal_bridge_release(command);
    }
};

test "Metal completion retains every failure until all submitted references retire" {
    const Probe = struct {
        var waits: usize = 0;
        var releases: usize = 0;
        pub fn metal_bridge_command_buffer_wait_result(command: ?*anyopaque, code: *i64) c_int {
            const tag: *u8 = @ptrCast(@alignCast(command.?));
            waits += 1;
            code.* = tag.*;
            return if (tag.* == 0) 1 else 0;
        }
        pub fn metal_bridge_release(_: ?*anyopaque) void {
            std.testing.expect(waits == releases + 1) catch @panic("release before wait");
            releases += 1;
        }
    };
    Probe.waits = 0;
    Probe.releases = 0;
    var completion: Completion = .{};
    defer completion.pending.deinit(std.testing.allocator);
    var commands = [_]u8{ 2, 0, 3 };
    for (&commands) |*command| {
        try completion.reserve(std.testing.allocator);
        completion.retainSubmitted(command);
    }
    completion.retireWithBridge(Probe);
    try std.testing.expectError(error.MetalCommandFailed, completion.check());
    try std.testing.expectEqual(@as(?i64, 2), completion.failure_code);
    try std.testing.expectEqual(@as(usize, 3), Probe.releases);
    try std.testing.expectEqual(@as(usize, 0), completion.pending.items.len);
    completion.retireWithBridge(Probe);
    try std.testing.expectEqual(@as(usize, 3), Probe.releases);
    try std.testing.expectError(error.MetalCommandFailed, completion.reserve(std.testing.allocator));
}

test "Metal completion reservation fails without taking native ownership" {
    var allocator = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    var completion: Completion = .{};
    try std.testing.expectError(error.OutOfMemory, completion.reserve(allocator.allocator()));
    try std.testing.expectEqual(@as(usize, 0), completion.pending.items.len);
    try completion.check();
}

test "Metal completion distinguishes successful retirement from failure without a native code" {
    const Probe = struct {
        var succeed = true;
        var releases: usize = 0;
        pub fn metal_bridge_command_buffer_wait_result(_: ?*anyopaque, code: *i64) c_int {
            code.* = 0;
            return if (succeed) 1 else 0;
        }
        pub fn metal_bridge_release(_: ?*anyopaque) void {
            releases += 1;
        }
    };
    Probe.succeed = true;
    Probe.releases = 0;
    var completion: Completion = .{};
    var command: u8 = 0;
    completion.retireOneWithBridge(&command, Probe);
    try completion.check();
    Probe.succeed = false;
    completion.retireOneWithBridge(&command, Probe);
    try std.testing.expectError(error.MetalCommandFailed, completion.check());
    try std.testing.expectEqual(@as(?i64, 0), completion.failure_code);
    try std.testing.expectEqual(@as(usize, 2), Probe.releases);
}
