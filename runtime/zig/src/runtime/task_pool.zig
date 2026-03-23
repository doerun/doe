const std = @import("std");

pub const JobFn = *const fn (?*anyopaque) void;

pub const Job = struct {
    run: JobFn,
    ctx: ?*anyopaque,
};

const JobNode = struct {
    next: ?*JobNode = null,
    job: Job,
};

const State = struct {
    mutex: std.Thread.Mutex = .{},
    cond: std.Thread.Condition = .{},
    head: ?*JobNode = null,
    tail: ?*JobNode = null,
    threads: []std.Thread = &.{},
    started: bool = false,
    stop: bool = false,
};

var g_init_lock: std.Thread.Mutex = .{};
var g_state = State{};

fn worker_main(_: usize) void {
    while (true) {
        const node = blk: {
            g_state.mutex.lock();
            defer g_state.mutex.unlock();

            while (!g_state.stop and g_state.head == null) {
                g_state.cond.wait(&g_state.mutex);
            }
            if (g_state.stop) return;
            const head = g_state.head orelse continue;
            g_state.head = head.next;
            if (g_state.head == null) g_state.tail = null;
            break :blk head;
        };

        defer std.heap.c_allocator.destroy(node);
        node.job.run(node.job.ctx);
    }
}

fn worker_count() usize {
    const cpu_count = std.Thread.getCpuCount() catch 2;
    if (cpu_count <= 2) return 1;
    return @min(cpu_count - 1, 4);
}

pub fn ensure_started() !void {
    if (g_state.started) return;

    g_init_lock.lock();
    defer g_init_lock.unlock();

    if (g_state.started) return;

    const count = worker_count();
    const threads = try std.heap.c_allocator.alloc(std.Thread, count);
    errdefer std.heap.c_allocator.free(threads);

    for (threads, 0..) |*slot, index| {
        slot.* = try std.Thread.spawn(.{}, worker_main, .{index});
    }

    g_state.threads = threads;
    g_state.started = true;
}

pub fn submit(job: Job) !void {
    try ensure_started();

    const node = try std.heap.c_allocator.create(JobNode);
    node.* = .{ .job = job };

    g_state.mutex.lock();
    defer g_state.mutex.unlock();

    if (g_state.tail) |tail| {
        tail.next = node;
    } else {
        g_state.head = node;
    }
    g_state.tail = node;
    g_state.cond.signal();
}
