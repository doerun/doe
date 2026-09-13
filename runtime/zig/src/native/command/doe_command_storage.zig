const std = @import("std");
const contract = @import("../../contracts/command_storage.zig");
const build_options = @import("build_options");
const RecordedCmd = @import("../support/doe_native_command_types.zig").RecordedCmd;
const Commands = std.ArrayListUnmanaged(RecordedCmd);

pub const OBSERVATION_MODE = std.meta.stringToEnum(contract.ObservationMode, build_options.native_command_storage_observation_mode) orelse
    @compileError("invalid generated native command storage observation mode");
pub const Pool = StoragePool(OBSERVATION_MODE);

const Counters = struct {
    values: [contract.METRIC_COUNT]std.atomic.Value(u64) = @splat(.init(0)),
    overflow: std.atomic.Value(bool) = .init(false),

    fn add(self: *Counters, metric: contract.Metric, value: u64) void {
        const counter = &self.values[@intFromEnum(metric)];
        var before = counter.load(.monotonic);
        while (true) {
            const after = before +| value;
            if (counter.cmpxchgWeak(before, after, .monotonic, .monotonic)) |changed| {
                before = changed;
            } else {
                if (value > std.math.maxInt(u64) - before) self.overflow.store(true, .monotonic);
                return;
            }
        }
    }
};

pub fn StoragePool(comptime mode: contract.ObservationMode) type {
    return struct {
        const Self = @This();
        allocator: std.mem.Allocator,
        max_retained_bytes: usize,
        mutex: std.Thread.Mutex = .{},
        available: Commands = .{},
        counters: if (mode == .ordinary) void else Counters = if (mode == .ordinary) {} else .{},

        pub fn init(allocator: std.mem.Allocator, max_retained_bytes: usize) Self {
            return .{ .allocator = allocator, .max_retained_bytes = max_retained_bytes };
        }

        fn ownsAllocator(self: *const Self, allocator: std.mem.Allocator) bool {
            return self.allocator.ptr == allocator.ptr and self.allocator.vtable == allocator.vtable;
        }

        fn count(self: *Self, metric: contract.Metric, value: u64) void {
            if (comptime mode != .ordinary) self.counters.add(metric, value);
        }

        fn lock(self: *Self) void {
            if (comptime mode != .timed) {
                self.mutex.lock();
                return;
            }
            if (self.mutex.tryLock()) return;
            self.count(.contended_locks, 1);
            const before = std.time.Instant.now() catch null;
            self.mutex.lock();
            const after = std.time.Instant.now() catch null;
            if (before != null and after != null and after.?.order(before.?) != .lt) {
                self.count(.lock_wait_ns, after.?.since(before.?));
            } else {
                self.count(.unavailable_clock_reads, 1);
            }
        }

        pub fn take(self: *Self, allocator: std.mem.Allocator) Commands {
            self.count(.take_calls, 1);
            if (!self.ownsAllocator(allocator) or self.max_retained_bytes == 0) return .{};
            self.lock();
            defer self.mutex.unlock();
            const commands = self.available;
            self.available = .{};
            if (commands.capacity != 0) self.count(.reuse_hits, 1);
            return commands;
        }

        pub fn recycle(self: *Self, allocator: std.mem.Allocator, commands: *Commands) void {
            self.count(.recycle_calls, 1);
            const storage = commands.*;
            commands.* = .{};
            if (storage.capacity == 0) return;
            if (self.ownsAllocator(allocator) and storage.capacity <= self.max_retained_bytes / @sizeOf(RecordedCmd)) {
                self.lock();
                if (self.available.capacity == 0) {
                    self.available = storage;
                    self.available.clearRetainingCapacity();
                    self.count(.retained_returns, 1);
                    if (comptime mode != .ordinary) {
                        const counter = &self.counters.values[@intFromEnum(contract.Metric.peak_retained_bytes)];
                        const retained_bytes = storage.capacity * @sizeOf(RecordedCmd);
                        counter.store(@max(counter.load(.monotonic), retained_bytes), .monotonic);
                    }
                    self.mutex.unlock();
                    return;
                }
                self.mutex.unlock();
            }
            allocator.free(storage.allocatedSlice());
            self.count(.freed_returns, 1);
        }

        pub fn observeGrowth(self: *Self, before: usize, after: usize, failed: bool) void {
            if (comptime mode == .ordinary) return;
            self.count(.reservation_calls, 1);
            if (failed) self.count(.growth_failures, 1);
            if (after > before) {
                self.count(.capacity_growths, 1);
                self.count(.grown_bytes, (after - before) * @sizeOf(RecordedCmd));
            }
        }

        /// Snapshot only after device references have quiesced. This is host capacity,
        /// not GPU memory, process RSS, or allocations outside ordinary reservation.
        pub fn snapshot(self: *const Self) ?contract.Snapshot {
            if (comptime mode == .ordinary) return null;
            var result: contract.Snapshot = .{
                .mode = mode,
                .command_size_bytes = @sizeOf(RecordedCmd),
                .max_retained_bytes = self.max_retained_bytes,
                .retained_bytes = self.available.capacity * @sizeOf(RecordedCmd),
                .counter_overflow = self.counters.overflow.load(.monotonic),
                .measurements = contract.metadata(),
            };
            for (&result.measurements) |*measurement| {
                if (mode != .timed and measurement.scope == .contended_pool_lock) continue;
                if (measurement.id == .lock_wait_ns and self.counters.values[@intFromEnum(contract.Metric.unavailable_clock_reads)].load(.monotonic) != 0) continue;
                measurement.value = self.counters.values[@intFromEnum(measurement.id)].load(.monotonic);
            }
            return result;
        }

        // Device references held by encoders and command buffers outlive every loan.
        pub fn deinit(self: *Self) void {
            self.available.deinit(self.allocator);
            self.available = .{};
        }
    };
}

test "command storage ordinary mode has no diagnostic storage or snapshot" {
    const Ordinary = StoragePool(.ordinary);
    try std.testing.expectEqual(@as(usize, 0), @sizeOf(@FieldType(Ordinary, "counters")));
    var pool = Ordinary.init(std.testing.allocator, 0);
    defer pool.deinit();
    try std.testing.expectEqual(@as(?contract.Snapshot, null), pool.snapshot());
}

test "command storage diagnostics distinguish reuse from real capacity growth" {
    var pool = StoragePool(.counters).init(std.testing.allocator, @sizeOf(RecordedCmd));
    defer pool.deinit();
    var storage = try Commands.initCapacity(std.testing.allocator, 1);
    pool.observeGrowth(0, storage.capacity, false);
    pool.recycle(std.testing.allocator, &storage);
    storage = pool.take(std.testing.allocator);
    pool.observeGrowth(storage.capacity, storage.capacity, false);
    pool.observeGrowth(storage.capacity, storage.capacity, true);
    pool.recycle(std.testing.allocator, &storage);
    const snapshot = pool.snapshot().?;
    try std.testing.expectEqual(@as(?u64, 1), snapshot.measurements[@intFromEnum(contract.Metric.reuse_hits)].value);
    try std.testing.expectEqual(@as(?u64, 1), snapshot.measurements[@intFromEnum(contract.Metric.capacity_growths)].value);
    try std.testing.expectEqual(@as(?u64, 1), snapshot.measurements[@intFromEnum(contract.Metric.growth_failures)].value);
    try std.testing.expectEqual(@as(?u64, null), snapshot.measurements[@intFromEnum(contract.Metric.lock_wait_ns)].value);
    try std.testing.expectEqual(@sizeOf(RecordedCmd), snapshot.retained_bytes);
}

test "command storage timed mode records actual contended acquisition" {
    const Timed = StoragePool(.timed);
    const Worker = struct {
        fn run(pool: *Timed) void {
            var storage = pool.take(std.testing.allocator);
            pool.recycle(std.testing.allocator, &storage);
        }
    };
    var pool = Timed.init(std.testing.allocator, @sizeOf(RecordedCmd));
    defer pool.deinit();
    pool.mutex.lock();
    const thread = std.Thread.spawn(.{}, Worker.run, .{&pool}) catch |err| {
        pool.mutex.unlock();
        return err;
    };
    while (pool.counters.values[@intFromEnum(contract.Metric.contended_locks)].load(.monotonic) == 0) std.Thread.yield() catch {};
    pool.mutex.unlock();
    thread.join();
    try std.testing.expectEqual(@as(?u64, 1), pool.snapshot().?.measurements[@intFromEnum(contract.Metric.contended_locks)].value);
}

test "command storage counters saturate and disclose overflow" {
    var counters: Counters = .{};
    counters.add(.take_calls, std.math.maxInt(u64));
    counters.add(.take_calls, 1);
    try std.testing.expectEqual(std.math.maxInt(u64), counters.values[@intFromEnum(contract.Metric.take_calls)].load(.monotonic));
    try std.testing.expect(counters.overflow.load(.monotonic));
}

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
