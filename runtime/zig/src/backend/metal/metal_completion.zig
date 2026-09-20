//! Submitted references remain owned until their individual terminal result is observed.
const std = @import("std");
const configuration = @import("../../contracts/runtime_configuration.zig");
const bridge = @import("metal_bridge_decls.zig");
const wait_policy = @import("metal_wait_policy.zig");

pub const Result = union(enum) {
    succeeded,
    failed: i64,
    pending,
    unknown,
};

fn readResult(command: *anyopaque, comptime native: type, comptime blocking: bool) Result {
    var code: i64 = 0;
    const status = if (blocking)
        native.metal_bridge_command_buffer_wait_result(command, &code)
    else
        native.metal_bridge_command_buffer_poll_result(command, &code);
    return switch (status) {
        1 => .succeeded,
        0 => .{ .failed = code },
        2 => if (blocking) .unknown else .pending,
        else => .unknown,
    };
}

const Clock = struct {
    timer: std.time.Timer,
    fn start() !Clock {
        return .{ .timer = try std.time.Timer.start() };
    }
    fn read(self: *Clock) u64 {
        return self.timer.read();
    }
    fn sleep(_: *Clock, ns: u64) void {
        sleepUnbounded(ns);
    }
    fn sleepUnbounded(ns: u64) void {
        std.Thread.sleep(ns);
    }
};

const WaitState = enum { ready, unknown, timed_out, clock_unavailable };
pub const WaitError = error{ MetalCompletionUnknown, MetalWaitTimeout, MetalWaitClockUnavailable };

pub const Completion = struct {
    pending: std.ArrayListUnmanaged(*anyopaque) = .{},
    // Preserve the first native NSError code, including an unavailable code (0).
    failure_code: ?i64 = null,
    wait_state: WaitState = .ready,
    retiring: bool = false,
    wait_mode: configuration.QueueWaitMode = .process_events,
    timeout_ns: u64 = wait_policy.compiled().timeoutNs,

    pub fn check(self: *const Completion) (WaitError || error{MetalCommandFailed})!void {
        if (self.failure_code != null) return error.MetalCommandFailed;
        if (self.retiring) return error.MetalCompletionUnknown;
        switch (self.wait_state) {
            .ready => {},
            .unknown => return error.MetalCompletionUnknown,
            .timed_out => return error.MetalWaitTimeout,
            .clock_unavailable => return error.MetalWaitClockUnavailable,
        }
    }

    /// Reserve before committing; failure leaves the unsubmitted buffer with its caller.
    pub fn reserve(self: *Completion, allocator: std.mem.Allocator) !void {
        try self.check();
        try self.pending.ensureUnusedCapacity(allocator, 1);
    }

    /// Registration occurs before commit. Neither reservation nor notification takes
    /// the caller's command reference; failure must leave it unsubmitted.
    pub fn prepare(self: *Completion, allocator: std.mem.Allocator, command: *anyopaque, comptime native: type) !void {
        try self.reserve(allocator);
        if (native.metal_bridge_command_buffer_prepare_wait(command) == 0) return error.MetalWaitPreparationFailed;
    }

    /// Transfers a +1 reference after commit. Call prepare before native submission.
    pub fn retainSubmitted(self: *Completion, command: *anyopaque) void {
        self.pending.appendAssumeCapacity(command);
    }

    /// One elapsed budget covers the batch. Timeout/unknown retain unfinished work;
    /// a later call may retire it. Terminal failure still requires check before use.
    pub fn retire(self: *Completion) WaitError!void {
        try self.retireWithMode(self.wait_mode);
    }

    pub fn retireWithMode(self: *Completion, mode: configuration.QueueWaitMode) WaitError!void {
        var policy = wait_policy.compiled();
        policy.timeoutNs = self.timeout_ns;
        try self.retireWithClock(bridge, Clock, policy, mode);
    }

    /// Destruction is a blocking drain, not an operational wait or cancellation.
    /// It cannot authorize destruction while native completion remains unknown.
    pub fn deinit(self: *Completion, allocator: std.mem.Allocator) void {
        while (self.pending.items.len != 0) {
            self.retireWithBridge(bridge) catch {
                std.Thread.sleep(wait_policy.compiled().pollIntervalNs);
            };
        }
        self.pending.deinit(allocator);
        self.pending = .{};
    }

    fn retireWithClock(self: *Completion, comptime native: type, comptime Timer: type, policy: wait_policy.Policy, mode: configuration.QueueWaitMode) WaitError!void {
        if (self.retiring) return error.MetalCompletionUnknown;
        self.retiring = true;
        defer self.retiring = false;
        if (self.pending.items.len == 0) {
            self.wait_state = .ready;
            return;
        }
        var clock: ?Timer = if (policy.timeoutNs == 0 or policy.timeoutNs == std.math.maxInt(u64)) null else Timer.start() catch {
            self.wait_state = .clock_unavailable;
            return error.MetalWaitClockUnavailable;
        };
        while (true) {
            const unknown = self.retirePass(native, false);
            if (unknown) {
                self.wait_state = .unknown;
                return error.MetalCompletionUnknown;
            }
            if (self.pending.items.len == 0) {
                self.wait_state = .ready;
                return;
            }
            const elapsed = if (clock) |*timer| timer.read() else 0;
            if (policy.timeoutNs != std.math.maxInt(u64) and elapsed >= policy.timeoutNs) {
                self.wait_state = .timed_out;
                return error.MetalWaitTimeout;
            }
            const remaining = policy.timeoutNs - elapsed;
            switch (mode) {
                .process_events => {
                    const interval = @min(policy.pollIntervalNs, remaining);
                    if (clock) |*timer| timer.sleep(interval) else Timer.sleepUnbounded(interval);
                },
                .wait_any => {
                    // Notification only wakes observation. Recheck every native status
                    // before releasing anything, including errors from later commands.
                    if (native.metal_bridge_command_buffer_wait_notification(self.pending.items[0], remaining) < 0) {
                        self.wait_state = .unknown;
                        return error.MetalCompletionUnknown;
                    }
                },
            }
        }
    }

    fn retireWithBridge(self: *Completion, comptime native: type) error{MetalCompletionUnknown}!void {
        if (self.retiring) return error.MetalCompletionUnknown;
        self.retiring = true;
        defer self.retiring = false;
        self.wait_state = if (self.retirePass(native, true)) .unknown else .ready;
        if (self.wait_state == .unknown) return error.MetalCompletionUnknown;
    }

    fn retirePass(self: *Completion, comptime native: type, comptime blocking: bool) bool {
        var retained: usize = 0;
        var unknown = false;
        for (self.pending.items) |command| {
            const result = readResult(command, native, blocking);
            switch (result) {
                .succeeded => native.metal_bridge_release(command),
                .failed => |code| {
                    if (self.failure_code == null) self.failure_code = code;
                    native.metal_bridge_release(command);
                },
                .pending, .unknown => {
                    unknown = unknown or result == .unknown;
                    self.pending.items[retained] = command;
                    retained += 1;
                },
            }
        }
        self.pending.items.len = retained;
        return unknown;
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
            std.testing.expectError(if (owner.failure_code != null) error.MetalCommandFailed else error.MetalCompletionUnknown, owner.reserve(std.testing.allocator)) catch @panic("reentrant submission accepted");
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

const TimedProbe = struct {
    const Command = struct { ready_at: u64, status: c_int = 1, code: i64 = 0 };
    var now: u64 = 0;
    var releases: usize = 0;
    var polls: usize = 0;
    var fail_clock = false;
    var reenter: ?*Completion = null;
    var notification_budgets: [8]u64 = undefined;
    var notifications: usize = 0;
    var fail_notification = false;
    const policy: wait_policy.Policy = .{ .schemaVersion = wait_policy.VERSION, .timeoutNs = 5, .pollIntervalNs = 2 };
    const Timer = struct {
        origin: u64,
        fn start() !Timer {
            if (fail_clock) return error.TimerUnsupported;
            return .{ .origin = now };
        }
        fn read(self: *Timer) u64 {
            return now - self.origin;
        }
        fn sleep(_: *Timer, ns: u64) void {
            sleepUnbounded(ns);
        }
        fn sleepUnbounded(ns: u64) void {
            now += ns;
        }
    };
    fn reset() void {
        now = 0;
        releases = 0;
        polls = 0;
        fail_clock = false;
        reenter = null;
        notifications = 0;
        fail_notification = false;
    }
    pub fn metal_bridge_command_buffer_wait_notification(handle: ?*anyopaque, budget: u64) c_int {
        notification_budgets[notifications] = budget;
        notifications += 1;
        if (fail_notification) return -1;
        const command: *Command = @ptrCast(@alignCast(handle.?));
        now += @min(command.ready_at -| now, budget);
        return if (now >= command.ready_at) 1 else 0;
    }
    pub fn metal_bridge_command_buffer_poll_result(handle: ?*anyopaque, code: *i64) c_int {
        polls += 1;
        if (reenter) |owner| {
            std.testing.expectError(error.MetalCompletionUnknown, owner.retireWithClock(@This(), Timer, policy, .process_events)) catch @panic("reentrant retirement accepted");
            std.testing.expectError(if (owner.failure_code != null) error.MetalCommandFailed else error.MetalCompletionUnknown, owner.reserve(std.testing.allocator)) catch @panic("reentrant submission accepted");
        }
        const command: *Command = @ptrCast(@alignCast(handle.?));
        code.* = command.code;
        return if (now >= command.ready_at) command.status else 2;
    }
    pub fn metal_bridge_release(_: ?*anyopaque) void {
        releases += 1;
    }
};

test "Metal wait shares one deadline retains unfinished work and permits a later drain" {
    TimedProbe.reset();
    var owner = Completion{};
    defer owner.pending.deinit(std.testing.allocator);
    var commands = [_]TimedProbe.Command{ .{ .ready_at = 0 }, .{ .ready_at = 3 }, .{ .ready_at = 8 } };
    for (&commands) |*command| {
        try owner.reserve(std.testing.allocator);
        owner.retainSubmitted(command);
    }
    TimedProbe.reenter = &owner;
    try std.testing.expectError(error.MetalWaitTimeout, owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events));
    try std.testing.expectEqual(@as(u64, 5), TimedProbe.now);
    try std.testing.expectEqual(@as(usize, 2), TimedProbe.releases);
    try std.testing.expectEqual(@as(usize, 1), owner.pending.items.len);
    try std.testing.expectEqual(@as(*anyopaque, @ptrCast(&commands[2])), owner.pending.items[0]);
    try std.testing.expectError(error.MetalWaitTimeout, owner.reserve(std.testing.allocator));
    try owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events);
    try owner.check();
    try std.testing.expectEqual(@as(usize, 0), owner.pending.items.len);
    try std.testing.expectEqual(@as(usize, 3), TimedProbe.releases);
}

test "Metal timed wait preserves native failure while retaining another timed out submission" {
    TimedProbe.reset();
    var owner = Completion{};
    defer owner.pending.deinit(std.testing.allocator);
    var commands = [_]TimedProbe.Command{ .{ .ready_at = 0, .status = 0, .code = 42 }, .{ .ready_at = 8, .status = 0, .code = 99 } };
    for (&commands) |*command| {
        try owner.reserve(std.testing.allocator);
        owner.retainSubmitted(command);
    }
    try std.testing.expectError(error.MetalWaitTimeout, owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events));
    try std.testing.expectEqual(@as(?i64, 42), owner.failure_code);
    try std.testing.expectEqual(@as(usize, 1), owner.pending.items.len);
    try std.testing.expectError(error.MetalCommandFailed, owner.check());
    try owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events);
    try std.testing.expectEqual(@as(?i64, 42), owner.failure_code);
    try std.testing.expectEqual(@as(usize, 2), TimedProbe.releases);
    try std.testing.expectError(error.MetalCommandFailed, owner.check());
}

test "Metal wait clock failure and unknown status preserve ownership without polling forever" {
    TimedProbe.reset();
    var owner = Completion{};
    defer owner.pending.deinit(std.testing.allocator);
    var command = TimedProbe.Command{ .ready_at = 0, .status = -1 };
    try owner.reserve(std.testing.allocator);
    owner.retainSubmitted(&command);
    TimedProbe.fail_clock = true;
    try std.testing.expectError(error.MetalWaitClockUnavailable, owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events));
    try std.testing.expectError(error.MetalWaitClockUnavailable, owner.check());
    try std.testing.expectEqual(@as(usize, 0), TimedProbe.polls);
    TimedProbe.fail_clock = false;
    try std.testing.expectError(error.MetalCompletionUnknown, owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events));
    try std.testing.expectEqual(@as(u64, 0), TimedProbe.now);
    try std.testing.expectEqual(@as(usize, 1), owner.pending.items.len);
    try std.testing.expectEqual(@as(usize, 0), TimedProbe.releases);
    command.status = 1;
    try owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .process_events);
    try owner.check();
    try std.testing.expectEqual(@as(usize, 1), TimedProbe.releases);
}

test "Metal notification waits share a deadline and retain error code zero across late completion" {
    TimedProbe.reset();
    var owner = Completion{};
    defer owner.pending.deinit(std.testing.allocator);
    var commands = [_]TimedProbe.Command{ .{ .ready_at = 0, .status = 0 }, .{ .ready_at = 3 }, .{ .ready_at = 8 } };
    for (&commands) |*command| {
        try owner.reserve(std.testing.allocator);
        owner.retainSubmitted(command);
    }
    TimedProbe.reenter = &owner;
    try std.testing.expectError(error.MetalWaitTimeout, owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .wait_any));
    try std.testing.expectEqualSlices(u64, &.{ 5, 2 }, TimedProbe.notification_budgets[0..TimedProbe.notifications]);
    try std.testing.expectEqual(@as(u64, 5), TimedProbe.now);
    try std.testing.expectEqual(@as(usize, 2), TimedProbe.releases);
    try std.testing.expectEqual(@as(?i64, 0), owner.failure_code);
    try std.testing.expectEqual(@as(*anyopaque, @ptrCast(&commands[2])), owner.pending.items[0]);
    try owner.retireWithClock(TimedProbe, TimedProbe.Timer, TimedProbe.policy, .wait_any);
    try std.testing.expectEqual(@as(usize, 3), TimedProbe.releases);
    try std.testing.expectError(error.MetalCommandFailed, owner.check());
}

test "Metal zero and indefinite waits need no clock and missing notifications retain ownership" {
    for ([_]configuration.QueueWaitMode{ .process_events, .wait_any }) |mode| {
        TimedProbe.reset();
        TimedProbe.fail_clock = true;
        var owner = Completion{};
        defer owner.pending.deinit(std.testing.allocator);
        var command = TimedProbe.Command{ .ready_at = 3 };
        try owner.reserve(std.testing.allocator);
        owner.retainSubmitted(&command);
        var policy = TimedProbe.policy;
        policy.timeoutNs = 0;
        try std.testing.expectError(error.MetalWaitTimeout, owner.retireWithClock(TimedProbe, TimedProbe.Timer, policy, mode));
        try std.testing.expectEqual(@as(usize, 0), TimedProbe.notifications);
        try std.testing.expectEqual(@as(u64, 0), TimedProbe.now);
        try std.testing.expectEqual(@as(usize, 0), TimedProbe.releases);
        policy.timeoutNs = std.math.maxInt(u64);
        if (mode == .wait_any) {
            TimedProbe.fail_notification = true;
            try std.testing.expectError(error.MetalCompletionUnknown, owner.retireWithClock(TimedProbe, TimedProbe.Timer, policy, mode));
            try std.testing.expectEqual(@as(usize, 1), owner.pending.items.len);
            TimedProbe.fail_notification = false;
        }
        try owner.retireWithClock(TimedProbe, TimedProbe.Timer, policy, mode);
        try owner.check();
        try std.testing.expectEqual(@as(usize, 1), TimedProbe.releases);
    }
}

test "Metal precommit notification failure neither transfers ownership nor bypasses allocation and reentry checks" {
    const Native = struct {
        var calls: usize = 0;
        pub fn metal_bridge_command_buffer_prepare_wait(_: ?*anyopaque) c_int {
            calls += 1;
            return 0;
        }
    };
    Native.calls = 0;
    var owner = Completion{};
    defer owner.pending.deinit(std.testing.allocator);
    var command: u8 = 0;
    var allocator = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    try std.testing.expectError(error.OutOfMemory, owner.prepare(allocator.allocator(), &command, Native));
    try std.testing.expectEqual(@as(usize, 0), Native.calls);
    try std.testing.expectError(error.MetalWaitPreparationFailed, owner.prepare(std.testing.allocator, &command, Native));
    owner.retiring = true;
    try std.testing.expectError(error.MetalCompletionUnknown, owner.prepare(std.testing.allocator, &command, Native));
    try std.testing.expectEqual(@as(usize, 1), Native.calls);
    try std.testing.expectEqual(@as(usize, 0), owner.pending.items.len);
}
