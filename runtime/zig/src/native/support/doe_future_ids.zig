const std = @import("std");
const abi_callback = @import("../../core/abi/wgpu_callback_descriptor_types.zig");

const FUTURE_SEQUENCE_BITS = 32;
const MAX_INSTANCE_ID = 0x7FFF_FFFF;
var next_instance_id: std.atomic.Value(u32) = .init(1);
var next_legacy_id: std.atomic.Value(u64) = .init(0x8000_0000_0000_0000);

/// Flat native calls without an instance retain their immediate-delivery contract.
pub fn legacyFuture() u64 {
    const id = next_legacy_id.fetchAdd(1, .monotonic);
    if (id == std.math.maxInt(u64)) @panic("NativeFutureIdentityExhausted");
    return id;
}

/// Borrowed from a request that owns its payload and retains the instance.
pub const Completion = struct {
    id: u64 = 0,
    next: ?*Completion = null,
    owner: ?*PendingCompletions = null,
    delivery_thread: ?std.Thread.Id = null,
    mode: u32 = abi_callback.WGPUCallbackMode_AllowSpontaneous,
    ready: bool = false,
    dispatch: ?*const fn (*Completion) void = null,

    pub fn beginDelivery(self: *Completion) void {
        const owner = self.owner orelse return;
        owner.mutex.lock();
        defer owner.mutex.unlock();
        self.delivery_thread = std.Thread.getCurrentId();
    }

    /// Publication wakes waiters; only spontaneous delivery can run on this thread.
    pub fn markReady(self: *Completion) void {
        const owner = self.owner orelse {
            if (self.dispatch) |dispatch| dispatch(self);
            return;
        };
        owner.mutex.lock();
        self.ready = true;
        const spontaneous = self.mode == abi_callback.WGPUCallbackMode_AllowSpontaneous or self.mode == 0;
        if (spontaneous) self.delivery_thread = std.Thread.getCurrentId();
        owner.changed.broadcast();
        owner.mutex.unlock();
        if (spontaneous) if (self.dispatch) |dispatch| dispatch(self);
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

/// Instance-owned identities and delivery obligations, without retired tombstones.
pub const PendingCompletions = struct {
    mutex: std.Thread.Mutex = .{},
    changed: std.Thread.Condition = .{},
    head: ?*Completion = null,
    instance_id: u32 = 0,
    next_sequence: u32 = 1,

    pub fn newFuture(self: *PendingCompletions) u64 {
        self.mutex.lock();
        defer self.mutex.unlock();
        if (self.instance_id == 0) {
            self.instance_id = next_instance_id.fetchAdd(1, .monotonic);
            if (self.instance_id == 0 or self.instance_id > MAX_INSTANCE_ID) @panic("NativeInstanceIdentityExhausted");
        }
        if (self.next_sequence == std.math.maxInt(u32)) @panic("NativeFutureIdentityExhausted");
        const id = (@as(u64, self.instance_id) << FUTURE_SEQUENCE_BITS) | self.next_sequence;
        self.next_sequence += 1;
        return id;
    }

    fn issued(self: *const PendingCompletions, id: u64) bool {
        const sequence: u32 = @truncate(id);
        return self.instance_id != 0 and id >> FUTURE_SEQUENCE_BITS == self.instance_id and sequence != 0 and sequence < self.next_sequence;
    }

    pub fn register(self: *PendingCompletions, completion: *Completion, id: u64) void {
        self.mutex.lock();
        defer self.mutex.unlock();
        std.debug.assert(completion.owner == null and self.issued(id));
        completion.owner = self;
        completion.id = id;
        completion.next = self.head;
        self.head = completion;
    }

    /// Capture an issuance boundary so reentrant producers belong to the next pump.
    pub fn processEvents(self: *PendingCompletions) void {
        self.mutex.lock();
        const boundary = self.next_sequence;
        while (true) {
            var selected: ?*Completion = null;
            var entry = self.head;
            while (entry) |completion| : (entry = completion.next) {
                if (!completion.ready or completion.delivery_thread != null or completion.mode == abi_callback.WGPUCallbackMode_WaitAnyOnly or @as(u32, @truncate(completion.id)) >= boundary) continue;
                if (selected == null or completion.id < selected.?.id) selected = completion;
            }
            const completion = selected orelse break;
            completion.delivery_thread = std.Thread.getCurrentId();
            const dispatch = completion.dispatch orelse unreachable;
            self.mutex.unlock();
            dispatch(completion);
            self.mutex.lock();
        }
        self.mutex.unlock();
    }

    pub fn waitAny(self: *PendingCompletions, infos: []abi_callback.WGPUFutureWaitInfo, timeout_ns: u64) !bool {
        if (infos.len == 0) return true;
        const started = if (timeout_ns == std.math.maxInt(u64)) null else try std.time.Instant.now();
        self.mutex.lock();
        defer self.mutex.unlock();
        for (infos) |*info| {
            info.completed = 0;
            if (!self.issued(info.future.id)) return error.UnknownFuture;
        }
        while (true) {
            var completed = false;
            var tracked_pending = false;
            var selected: ?*Completion = null;
            for (infos) |*info| {
                var pending = false;
                var entry = self.head;
                while (entry) |completion| : (entry = completion.next) {
                    if (completion.id == info.future.id) {
                        pending = completion.delivery_thread != std.Thread.getCurrentId();
                        tracked_pending = tracked_pending or pending;
                        if (completion.ready and completion.delivery_thread == null and (selected == null or completion.id < selected.?.id)) selected = completion;
                        break;
                    }
                }
                info.completed = @intFromBool(!pending);
                completed = completed or !pending;
            }
            if (selected) |completion| {
                completion.delivery_thread = std.Thread.getCurrentId();
                const dispatch = completion.dispatch orelse unreachable;
                self.mutex.unlock();
                dispatch(completion);
                self.mutex.lock();
                continue;
            }
            if (completed) return true;
            if (!tracked_pending) {
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
    const first_id = pending.newFuture();
    const second_id = pending.newFuture();
    pending.register(&first, first_id);
    pending.register(&second, second_id);
    var infos = [_]abi_callback.WGPUFutureWaitInfo{
        .{ .future = .{ .id = first_id }, .completed = 0 },
        .{ .future = .{ .id = second_id }, .completed = 0 },
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
    const id = pending.newFuture();
    pending.register(&completion, id);
    const Worker = struct {
        fn settle(entry: *Completion) void {
            entry.finish();
        }
    };
    const worker = try std.Thread.spawn(.{}, Worker.settle, .{&completion});
    defer worker.join();
    var infos = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = id }, .completed = 0 }};
    try std.testing.expect(try pending.waitAny(&infos, std.math.maxInt(u64)));
}

test "pipeline delivery can inspect its own completion without retiring another thread's obligation" {
    var pending: PendingCompletions = .{};
    var completion: Completion = .{};
    const id = pending.newFuture();
    pending.register(&completion, id);
    completion.beginDelivery();
    var infos = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = id }, .completed = 0 }};
    try std.testing.expect(try pending.waitAny(&infos, std.math.maxInt(u64)));
    const Worker = struct {
        fn poll(owner: *PendingCompletions, future: u64, observed: *bool) void {
            var other = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = future }, .completed = 0 }};
            observed.* = owner.waitAny(&other, 0) catch unreachable;
        }
    };
    var observed = true;
    const worker = try std.Thread.spawn(.{}, Worker.poll, .{ &pending, id, &observed });
    worker.join();
    try std.testing.expect(!observed);
    completion.finish();
}

test "manufactured device loss identities are not instance-issued futures" {
    var pending: PendingCompletions = .{};
    var infos = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = 0xD0E1_0000_0000_0000 }, .completed = 0 }};
    try std.testing.expectError(error.UnknownFuture, pending.waitAny(&infos, 0));
}

test "deferred callbacks obey mode and instance identity and do not fire twice" {
    const Probe = struct {
        completion: Completion = .{},
        count: usize = 0,
        fn deliver(entry: *Completion) void {
            const self: *@This() = @fieldParentPtr("completion", entry);
            self.count += 1;
            entry.finish();
        }
    };
    var owner: PendingCompletions = .{};
    var other: PendingCompletions = .{};
    var first: Probe = .{};
    var second: Probe = .{};
    first.completion.mode = abi_callback.WGPUCallbackMode_WaitAnyOnly;
    first.completion.dispatch = Probe.deliver;
    second.completion.mode = abi_callback.WGPUCallbackMode_AllowProcessEvents;
    second.completion.dispatch = Probe.deliver;
    const a = owner.newFuture();
    const b = owner.newFuture();
    owner.register(&first.completion, a);
    owner.register(&second.completion, b);
    first.completion.markReady();
    second.completion.markReady();
    other.processEvents();
    try std.testing.expectEqual(@as(usize, 0), second.count);
    var wrong = [_]abi_callback.WGPUFutureWaitInfo{.{ .future = .{ .id = a }, .completed = 0 }};
    try std.testing.expectError(error.UnknownFuture, other.waitAny(&wrong, 0));
    owner.processEvents();
    try std.testing.expectEqual(@as(usize, 0), first.count);
    try std.testing.expectEqual(@as(usize, 1), second.count);
    try std.testing.expect(try owner.waitAny(&wrong, 0));
    try std.testing.expectEqual(@as(usize, 1), first.count);
    owner.processEvents();
    try std.testing.expect(try owner.waitAny(&wrong, 0));
    try std.testing.expectEqual(@as(usize, 1), first.count);
    try std.testing.expect(owner.head == null);
}

test "event pump leaves reentrant registration for the next call" {
    const Probe = struct {
        completion: Completion = .{ .mode = abi_callback.WGPUCallbackMode_AllowProcessEvents },
        follower: ?*@This() = null,
        count: u32 = 0,
        fn deliver(entry: *Completion) void {
            const self: *@This() = @fieldParentPtr("completion", entry);
            self.count += 1;
            if (self.follower) |follower| {
                const owner = entry.owner.?;
                const id = owner.newFuture();
                follower.completion.dispatch = deliver;
                owner.register(&follower.completion, id);
                follower.completion.markReady();
            }
            entry.finish();
        }
    };
    var owner: PendingCompletions = .{};
    var follower: Probe = .{};
    var leader = Probe{ .follower = &follower };
    leader.completion.dispatch = Probe.deliver;
    owner.register(&leader.completion, owner.newFuture());
    leader.completion.markReady();
    owner.processEvents();
    try std.testing.expectEqual(@as(u32, 1), leader.count);
    try std.testing.expectEqual(@as(u32, 0), follower.count);
    owner.processEvents();
    try std.testing.expectEqual(@as(u32, 1), follower.count);
    try std.testing.expect(owner.head == null);
}
