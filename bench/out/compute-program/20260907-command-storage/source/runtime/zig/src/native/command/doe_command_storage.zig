const std = @import("std");
const RecordedCmd = @import("../support/doe_native_command_types.zig").RecordedCmd;
const Commands = std.ArrayListUnmanaged(RecordedCmd);

pub const Pool = struct {
    allocator: std.mem.Allocator,
    max_retained_bytes: usize,
    mutex: std.Thread.Mutex = .{},
    available: Commands = .{},

    pub fn init(allocator: std.mem.Allocator, max_retained_bytes: usize) Pool {
        return .{ .allocator = allocator, .max_retained_bytes = max_retained_bytes };
    }

    fn ownsAllocator(self: *const Pool, allocator: std.mem.Allocator) bool {
        return self.allocator.ptr == allocator.ptr and self.allocator.vtable == allocator.vtable;
    }

    pub fn take(self: *Pool, allocator: std.mem.Allocator) Commands {
        if (!self.ownsAllocator(allocator) or self.max_retained_bytes == 0) return .{};
        self.mutex.lock();
        defer self.mutex.unlock();
        const commands = self.available;
        self.available = .{};
        return commands;
    }

    pub fn recycle(self: *Pool, allocator: std.mem.Allocator, commands: *Commands) void {
        const storage = commands.*;
        commands.* = .{};
        if (storage.capacity == 0) return;
        if (self.ownsAllocator(allocator) and storage.capacity <= self.max_retained_bytes / @sizeOf(RecordedCmd)) {
            self.mutex.lock();
            if (self.available.capacity == 0) {
                self.available = storage;
                self.available.clearRetainingCapacity();
                self.mutex.unlock();
                return;
            }
            self.mutex.unlock();
        }
        allocator.free(storage.allocatedSlice());
    }

    // Device references held by encoders and command buffers outlive every loan.
    pub fn deinit(self: *Pool) void {
        self.available.deinit(self.allocator);
        self.available = .{};
    }
};

test "command storage loans are exclusive and retain only bounded empty capacity" {
    const allocator = std.testing.allocator;
    var pool = Pool.init(allocator, @sizeOf(RecordedCmd));
    defer pool.deinit();
    var first = try Commands.initCapacity(allocator, 1);
    first.appendAssumeCapacity(.{ .clear_buffer = .{ .buffer = null, .offset = 0, .size = 4 } });
    const address = first.items.ptr;
    pool.recycle(allocator, &first);
    try std.testing.expectEqual(@as(usize, 0), first.capacity);
    var loan = pool.take(allocator);
    try std.testing.expectEqual(address, loan.items.ptr);
    try std.testing.expectEqual(@as(usize, 0), loan.items.len);
    try std.testing.expectEqual(@as(usize, 0), pool.take(allocator).capacity);
    var another = try Commands.initCapacity(allocator, 1);
    const other_address = another.items.ptr;
    pool.recycle(allocator, &another);
    pool.recycle(allocator, &loan);
    try std.testing.expectEqual(other_address, pool.available.items.ptr);
    var oversized = try Commands.initCapacity(allocator, 2);
    pool.recycle(allocator, &oversized);
    try std.testing.expectEqual(other_address, pool.available.items.ptr);
}

test "command storage does not mix allocator identities or devices" {
    const allocator = std.testing.allocator;
    var tracked = std.testing.FailingAllocator.init(allocator, .{});
    var pool = Pool.init(allocator, @sizeOf(RecordedCmd));
    defer pool.deinit();
    var other = Pool.init(allocator, @sizeOf(RecordedCmd));
    defer other.deinit();
    var storage = try Commands.initCapacity(allocator, 1);
    pool.recycle(allocator, &storage);
    try std.testing.expectEqual(@as(usize, 0), other.take(allocator).capacity);
    try std.testing.expectEqual(@as(usize, 0), pool.take(tracked.allocator()).capacity);
    var foreign = try Commands.initCapacity(tracked.allocator(), 1);
    pool.recycle(tracked.allocator(), &foreign);
    try std.testing.expectEqual(tracked.allocated_bytes, tracked.freed_bytes);
    var disabled = Pool.init(allocator, 0);
    defer disabled.deinit();
    var loan = pool.take(allocator);
    disabled.recycle(allocator, &loan);
    try std.testing.expectEqual(@as(usize, 0), disabled.take(allocator).capacity);
}

test "concurrent command storage loans preserve each recording" {
    const Worker = struct {
        fn run(pool: *Pool, value: u64) void {
            for (0..64) |_| {
                var commands = pool.take(std.testing.allocator);
                defer pool.recycle(std.testing.allocator, &commands);
                std.testing.expectEqual(@as(usize, 0), commands.items.len) catch @panic("recycled commands are not empty");
                commands.append(std.testing.allocator, .{ .clear_buffer = .{ .buffer = null, .offset = value, .size = 4 } }) catch @panic("command allocation failed");
                std.Thread.yield() catch {};
                std.testing.expectEqual(value, commands.items[0].clear_buffer.offset) catch @panic("command storage aliases another loan");
            }
        }
    };
    var pool = Pool.init(std.testing.allocator, 8 * @sizeOf(RecordedCmd));
    defer pool.deinit();
    var threads: [4]std.Thread = undefined;
    var spawned: usize = 0;
    defer for (threads[0..spawned]) |thread| thread.join();
    for (&threads, 0..) |*thread, index| {
        thread.* = try std.Thread.spawn(.{}, Worker.run, .{ &pool, index });
        spawned += 1;
    }
}
