//! Submitted command-buffer references live here until their own result is read.
const std = @import("std");
const bridge = @import("metal_bridge_decls.zig");

pub const Result = union(enum) {
    succeeded,
    failed: i64,
    unknown,
};

fn waitResult(command: *anyopaque, comptime native: type) Result {
    var code: i64 = 0;
    return switch (native.metal_bridge_command_buffer_wait_result(command, &code)) {
        1 => .succeeded,
        0 => .{ .failed = code },
        else => .unknown,
    };
}

pub const Completion = struct {
    pending: std.ArrayListUnmanaged(*anyopaque) = .{},
    // Preserve the first native NSError code, including an unavailable code (0).
    failure_code: ?i64 = null,

    completion_unknown: bool = false,
    retiring: bool = false,

    pub fn check(self: *const Completion) error{ MetalCommandFailed, MetalCompletionUnknown }!void {
        if (self.failure_code != null) return error.MetalCommandFailed;
        if (self.completion_unknown or self.retiring) return error.MetalCompletionUnknown;
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

    /// Unknown completion keeps the reference and forbids resource retirement.
    /// Terminal failures retire normally and remain observable through check.
    pub fn retire(self: *Completion) error{MetalCompletionUnknown}!void {
        try self.retireWithBridge(bridge);
    }

    pub fn deinit(self: *Completion, allocator: std.mem.Allocator) void {
        // A void destructor must finish waiting; it cannot turn an interrupted
        // wait into permission to destroy potentially live native resources.
        while (self.pending.items.len != 0) self.retire() catch {};
        self.pending.deinit(allocator);
        self.pending = .{};
    }

    fn retireWithBridge(self: *Completion, comptime native: type) error{MetalCompletionUnknown}!void {
        if (self.retiring) return error.MetalCompletionUnknown;
        self.retiring = true;
        defer self.retiring = false;
        var retained: usize = 0;
        for (self.pending.items) |command| {
            switch (waitResult(command, native)) {
                .succeeded => native.metal_bridge_release(command),
                .failed => |code| {
                    if (self.failure_code == null) self.failure_code = code;
                    native.metal_bridge_release(command);
                },
                .unknown => {
                    self.pending.items[retained] = command;
                    retained += 1;
                },
            }
        }
        self.pending.items.len = retained;
        self.completion_unknown = retained != 0;
        if (self.completion_unknown) return error.MetalCompletionUnknown;
    }
};

test "Metal unknown completion retains submitted references until a later terminal result" {
    const Probe = struct {
        var unknown = true;
        var releases: usize = 0;
        pub fn metal_bridge_command_buffer_wait_result(command: ?*anyopaque, code: *i64) c_int {
            const identity: *u8 = @ptrCast(@alignCast(command.?));
            code.* = identity.*;
            if (identity.* == 1 and unknown) return -1;
            return if (identity.* == 2) 0 else 1;
        }
        pub fn metal_bridge_release(_: ?*anyopaque) void {
            releases += 1;
        }
    };
    Probe.unknown = true;
    Probe.releases = 0;
    var completion = Completion{};
    defer completion.pending.deinit(std.testing.allocator);
    var commands = [_]u8{ 1, 2, 0 };
    for (&commands) |*command| {
        try completion.reserve(std.testing.allocator);
        completion.retainSubmitted(command);
    }
    try std.testing.expectError(error.MetalCompletionUnknown, completion.retireWithBridge(Probe));
    try std.testing.expectEqual(@as(usize, 1), completion.pending.items.len);
    try std.testing.expectEqual(@as(usize, 2), Probe.releases);
    try std.testing.expectEqual(@as(?i64, 2), completion.failure_code);
    try std.testing.expectError(error.MetalCommandFailed, completion.check());
    Probe.unknown = false;
    try completion.retireWithBridge(Probe);
    try std.testing.expectEqual(@as(usize, 0), completion.pending.items.len);
    try std.testing.expectEqual(@as(usize, 3), Probe.releases);
    try std.testing.expectError(error.MetalCommandFailed, completion.check());
}

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
    try completion.retireWithBridge(Probe);
    try std.testing.expectError(error.MetalCommandFailed, completion.check());
    try std.testing.expectEqual(@as(?i64, 2), completion.failure_code);
    try std.testing.expectEqual(@as(usize, 3), Probe.releases);
    try std.testing.expectEqual(@as(usize, 0), completion.pending.items.len);
    try completion.retireWithBridge(Probe);
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

test "Metal completion rejects reentrant retirement and submission during a native wait" {
    const Probe = struct {
        var owner: *Completion = undefined;
        var releases: usize = 0;
        pub fn metal_bridge_command_buffer_wait_result(_: ?*anyopaque, code: *i64) c_int {
            std.testing.expectError(error.MetalCompletionUnknown, owner.retireWithBridge(@This())) catch @panic("reentrant retirement accepted");
            std.testing.expectError(error.MetalCompletionUnknown, owner.reserve(std.testing.allocator)) catch @panic("reentrant submission accepted");
            code.* = 0;
            return 1;
        }
        pub fn metal_bridge_release(_: ?*anyopaque) void {
            releases += 1;
        }
    };
    var completion = Completion{};
    defer completion.pending.deinit(std.testing.allocator);
    Probe.owner = &completion;
    Probe.releases = 0;
    var command: u8 = 0;
    try completion.reserve(std.testing.allocator);
    completion.retainSubmitted(&command);
    try completion.retireWithBridge(Probe);
    try completion.check();
    try std.testing.expectEqual(@as(usize, 1), Probe.releases);
    try std.testing.expectEqual(@as(usize, 0), completion.pending.items.len);
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
    defer completion.pending.deinit(std.testing.allocator);
    var command: u8 = 0;
    try completion.reserve(std.testing.allocator);
    completion.retainSubmitted(&command);
    try completion.retireWithBridge(Probe);
    try completion.check();
    Probe.succeed = false;
    try completion.reserve(std.testing.allocator);
    completion.retainSubmitted(&command);
    try completion.retireWithBridge(Probe);
    try std.testing.expectError(error.MetalCommandFailed, completion.check());
    try std.testing.expectEqual(@as(?i64, 0), completion.failure_code);
    try std.testing.expectEqual(@as(usize, 2), Probe.releases);
}
