pub const DEVICE_LOST_FUTURE_ID_BASE: u64 = 0xD0E1_0000_0000_0000;
const FUTURE_ID_KIND_MASK: u64 = 0xFFFF_0000_0000_0000;
const FUTURE_ID_PAYLOAD_MASK: u64 = 0x0000_FFFF_FFFF_FFFF;

pub fn device_lost_future_id(raw: ?*anyopaque) u64 {
    const payload = if (raw) |ptr| @intFromPtr(ptr) & FUTURE_ID_PAYLOAD_MASK else 0;
    return DEVICE_LOST_FUTURE_ID_BASE | payload;
}

pub fn is_device_lost_future_id(id: u64) bool {
    return (id & FUTURE_ID_KIND_MASK) == DEVICE_LOST_FUTURE_ID_BASE;
}

/// Borrowed from an async request that retains the device and its instance.
pub const Completion = struct {
    id: u64 = 0,
    next: ?*Completion = null,
    owner: ?*PendingCompletions = null,
    delivery_thread: ?std.Thread.Id = null,

    pub fn beginDelivery(self: *Completion) void {
        const owner = self.owner orelse return;
        owner.mutex.lock();
        defer owner.mutex.unlock();
        self.delivery_thread = std.Thread.getCurrentId();
    }

    pub fn finish(self: *Completion) void {
        const owner = self.owner orelse return;
        owner.mutex.lock();
        defer owner.mutex.unlock();
        var link = &owner.head;
        while (link.*) |entry| {
            if (entry == self) {
                link.* = entry.next;
                self.owner = null;
                self.next = null;
                owner.changed.broadcast();
                return;
            }
            link = &entry.next;
        }
        unreachable;
    }
};

/// Instance-owned obligations; settled requests leave no tombstones or allocations.
pub const PendingCompletions = struct {
    mutex: std.Thread.Mutex = .{},
    changed: std.Thread.Condition = .{},
    head: ?*Completion = null,

    pub fn register(self: *PendingCompletions, completion: *Completion, id: u64) void {
        self.mutex.lock();
        defer self.mutex.unlock();
        std.debug.assert(completion.owner == null);
        completion.* = .{ .owner = self, .id = id, .next = self.head };
        self.head = completion;
    }

    pub fn waitAny(self: *PendingCompletions, infos: []abi_callback.WGPUFutureWaitInfo, timeout_ns: u64) !bool {
        if (infos.len == 0) return true;
        const started = if (timeout_ns == std.math.maxInt(u64)) null else try std.time.Instant.now();
        self.mutex.lock();
        defer self.mutex.unlock();
        while (true) {
            var completed = false;
            var pipeline_pending = false;
            for (infos) |*info| {
                var pending = is_device_lost_future_id(info.future.id);
                var entry = self.head;
                while (entry) |completion| : (entry = completion.next) {
                    if (completion.id == info.future.id) {
                        pending = completion.delivery_thread != std.Thread.getCurrentId();
                        pipeline_pending = pipeline_pending or pending;
                        break;
                    }
                }
                info.completed = @intFromBool(!pending);
                completed = completed or !pending;
            }
            if (completed) return true;
            if (!pipeline_pending) {
                if (timeout_ns != 0) return error.UnsupportedFutureWait;
                return false;
            }
            if (started) |begin| {
                const elapsed = (try std.time.Instant.now()).since(begin);
                if (elapsed >= timeout_ns) return false;
                self.changed.timedWait(&self.mutex, timeout_ns - elapsed) catch |err| switch (err) {
                    error.Timeout => return false,
                };
            } else {
                self.changed.wait(&self.mutex);
            }
        }
    }
};

test "pipeline futures remain pending until callback delivery finishes" {
    var pending: PendingCompletions = .{};
    var first: Completion = .{};
    var second: Completion = .{};
    pending.register(&first, 32);
    pending.register(&second, 33);
    var infos = [_]abi_callback.WGPUFutureWaitInfo{
        .{ .future = .{ .id = 32 }, .completed = 0 },
        .{ .future = .{ .id = 33 }, .completed = 0 },
    };
    try std.testing.expect(!try pending.waitAny(&infos, 0));
    first.finish();
    try std.testing.expect(try pending.waitAny(&infos, 0));
    try std.testing.expectEqual(@as(u32, 1), infos[0].completed);
    try std.testing.expectEqual(@as(u32, 0), infos[1].completed);
    second.finish();
    try std.testing.expect(pending.head == null);
    try std.testing.expect(try pending.waitAny(&infos, 0));
}

test "pipeline completion wakes an indefinite instance wait" {
    var pending: PendingCompletions = .{};
    var completion: Completion = .{};
    pending.register(&completion, 32);
    const Worker = struct {
        fn settle(entry: *Completion) void {
            entry.finish();
        }
    };
    const worker = try std.Thread.spawn(.{}, Worker.settle, .{&completion});
    defer worker.join();
    var infos = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = 32 }, .completed = 0 }};
    try std.testing.expect(try pending.waitAny(&infos, std.math.maxInt(u64)));
}

test "pipeline delivery can inspect its own completion without retiring another thread's obligation" {
    var pending: PendingCompletions = .{};
    var completion: Completion = .{};
    pending.register(&completion, 32);
    completion.beginDelivery();
    var infos = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = 32 }, .completed = 0 }};
    try std.testing.expect(try pending.waitAny(&infos, std.math.maxInt(u64)));
    const Worker = struct {
        fn poll(owner: *PendingCompletions, observed: *bool) void {
            var other = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = 32 }, .completed = 0 }};
            observed.* = owner.waitAny(&other, 0) catch unreachable;
        }
    };
    var observed = true;
    const worker = try std.Thread.spawn(.{}, Worker.poll, .{ &pending, &observed });
    worker.join();
    try std.testing.expect(!observed);
    completion.finish();
}

test "untracked device-loss waits fail explicitly instead of waiting on an unwakeable condition" {
    var pending: PendingCompletions = .{};
    var infos = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = device_lost_future_id(null) }, .completed = 0 }};
    try std.testing.expect(!try pending.waitAny(&infos, 0));
    try std.testing.expectError(error.UnsupportedFutureWait, pending.waitAny(&infos, std.math.maxInt(u64)));
}
const std = @import("std");
const abi_callback = @import("../../core/abi/wgpu_callback_descriptor_types.zig");
