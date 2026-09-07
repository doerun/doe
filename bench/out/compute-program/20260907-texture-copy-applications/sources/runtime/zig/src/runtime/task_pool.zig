const std = @import("std");

pub const JobFn = *const fn (?*anyopaque) void;

pub const Job = struct {
    run: JobFn,
    ctx: ?*anyopaque,
};

const DEFAULT_QUEUE_CAPACITY: usize = 64;

const State = struct {
    allocator: ?std.mem.Allocator = null,
    mutex: std.Thread.Mutex = .{},
    cond: std.Thread.Condition = .{},
    jobs: []Job = &.{},
    head: usize = 0,
    count: usize = 0,
    threads: []std.Thread = &.{},
    started: bool = false,
    stop: bool = false,
};

var g_init_lock: std.Thread.Mutex = .{};
var g_state = State{};

fn queueTail(state: *const State) usize {
    if (state.jobs.len == 0) return 0;
    return (state.head + state.count) % state.jobs.len;
}

fn workerMain(_: usize) void {
    while (true) {
        const job = blk: {
            g_state.mutex.lock();
            defer g_state.mutex.unlock();

            while (!g_state.stop and g_state.count == 0) {
                g_state.cond.wait(&g_state.mutex);
            }
            if (g_state.stop and g_state.count == 0) return;

            const job = g_state.jobs[g_state.head];
            g_state.head = if (g_state.jobs.len == 0) 0 else (g_state.head + 1) % g_state.jobs.len;
            g_state.count -= 1;
            break :blk job;
        };

        job.run(job.ctx);
    }
}

fn workerCount() usize {
    const cpu_count = std.Thread.getCpuCount() catch 2;
    if (cpu_count <= 2) return 1;
    return @min(cpu_count - 1, 4);
}

fn waitForCounter(counter: *const std.atomic.Value(u32), expected: u32) !void {
    var spin_count: usize = 0;
    while (counter.load(.acquire) < expected) : (spin_count += 1) {
        if (spin_count > 1000) return error.TestUnexpectedResult;
        std.Thread.sleep(std.time.ns_per_ms);
    }
}

fn growQueueLocked(state: *State, allocator: std.mem.Allocator) !void {
    const old_jobs = state.jobs;
    const new_len = if (old_jobs.len == 0) DEFAULT_QUEUE_CAPACITY else old_jobs.len * 2;
    const new_jobs = try allocator.alloc(Job, new_len);
    if (old_jobs.len > 0) {
        var index: usize = 0;
        while (index < state.count) : (index += 1) {
            new_jobs[index] = old_jobs[(state.head + index) % old_jobs.len];
        }
        allocator.free(old_jobs);
    }
    state.jobs = new_jobs;
    state.head = 0;
}

pub fn ensureStartedWithAllocator(allocator: std.mem.Allocator) !void {
    if (g_state.started) return;

    g_init_lock.lock();
    defer g_init_lock.unlock();

    if (g_state.started) return;

    try growQueueLocked(&g_state, allocator);
    const count = workerCount();
    const threads = try allocator.alloc(std.Thread, count);
    errdefer allocator.free(threads);

    for (threads, 0..) |*slot, index| {
        slot.* = try std.Thread.spawn(.{}, workerMain, .{index});
    }

    g_state.allocator = allocator;
    g_state.threads = threads;
    g_state.started = true;
}

pub fn submitWithAllocator(allocator: std.mem.Allocator, job: Job) !void {
    try ensureStartedWithAllocator(allocator);

    g_state.mutex.lock();
    defer g_state.mutex.unlock();

    if (g_state.jobs.len == 0 or g_state.count == g_state.jobs.len) {
        const state_allocator = g_state.allocator orelse allocator;
        try growQueueLocked(&g_state, state_allocator);
    }
    const tail = queueTail(&g_state);
    g_state.jobs[tail] = job;
    g_state.count += 1;
    g_state.cond.signal();
}

pub fn shutdown() void {
    g_init_lock.lock();
    defer g_init_lock.unlock();
    if (!g_state.started) return;

    const allocator = g_state.allocator orelse return;

    g_state.mutex.lock();
    g_state.stop = true;
    g_state.cond.broadcast();
    g_state.mutex.unlock();

    for (g_state.threads) |thread| {
        thread.join();
    }

    allocator.free(g_state.threads);
    allocator.free(g_state.jobs);
    g_state = .{};
}

test "task pool ring queue stores jobs without per-job nodes" {
    const testing = std.testing;
    var state = State{};
    defer {
        if (state.jobs.len > 0) testing.allocator.free(state.jobs);
    }

    try growQueueLocked(&state, testing.allocator);
    try testing.expect(state.jobs.len >= DEFAULT_QUEUE_CAPACITY);

    state.jobs[0] = .{ .run = undefined, .ctx = @ptrFromInt(1) };
    state.jobs[1] = .{ .run = undefined, .ctx = @ptrFromInt(2) };
    state.count = 2;
    try testing.expectEqual(@as(usize, 2), queueTail(&state));
}

fn runCounterJob(ctx_raw: ?*anyopaque) void {
    const counter: *std.atomic.Value(u32) = @ptrCast(@alignCast(ctx_raw orelse return));
    _ = counter.fetchAdd(1, .acq_rel);
}

test "task pool can shutdown and restart with the same allocator owner" {
    const testing = std.testing;
    var counter = std.atomic.Value(u32).init(0);

    defer shutdown();

    try ensureStartedWithAllocator(testing.allocator);
    try submitWithAllocator(testing.allocator, .{ .run = runCounterJob, .ctx = &counter });
    try waitForCounter(&counter, 1);
    shutdown();

    try ensureStartedWithAllocator(testing.allocator);
    try submitWithAllocator(testing.allocator, .{ .run = runCounterJob, .ctx = &counter });
    try waitForCounter(&counter, 2);
}
