const std = @import("std");
const native_types = @import("doe_native_object_types.zig");
const queue_submit_ops = @import("backend/dropin_queue_submit.zig");
const bridge = queue_submit_ops.metal_bridge;

const DoeQueue = native_types.DoeQueue;
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_command_buffer_wait_completed = bridge.metal_bridge_command_buffer_wait_completed;
const metal_bridge_release = bridge.metal_bridge_release;
const metal_bridge_resolve_timestamps = bridge.metal_bridge_resolve_timestamps;
const metal_bridge_shared_event_wait = bridge.metal_bridge_shared_event_wait;

pub const QueueFlushBreakdown = extern struct {
    waitCompletedNs: u64 = 0,
    deferredCopyNs: u64 = 0,
    deferredResolveNs: u64 = 0,
};

fn monotonicNowNs() u64 {
    return @intCast(std.time.nanoTimestamp());
}

pub fn executeDeferredCopies(q: *DoeQueue) void {
    for (q.deferred_copies[0..q.deferred_copy_count]) |dc| {
        @memcpy(dc.dst[0..dc.size], dc.src[0..dc.size]);
    }
    q.deferred_copy_count = 0;
}

pub fn executeDeferredResolves(q: *DoeQueue) void {
    for (q.deferred_resolves[0..q.deferred_resolve_count]) |dr| {
        const contents = metal_bridge_buffer_contents(dr.dst_mtl) orelse continue;
        const d_off: usize = @intCast(dr.dst_offset);
        const dest: [*]u64 = @ptrCast(@alignCast(contents + d_off));
        _ = metal_bridge_resolve_timestamps(
            dr.counter_buffer,
            dr.first_query,
            dr.query_count,
            dest,
        );
    }
    q.deferred_resolve_count = 0;
}

pub fn flushPendingWorkTimed(q: *DoeQueue) QueueFlushBreakdown {
    var out = QueueFlushBreakdown{};
    if (q.mtl_event != null and q.event_counter > q.completed_event_counter) {
        const wait_started_ns = monotonicNowNs();
        metal_bridge_shared_event_wait(q.mtl_event, q.event_counter);
        out.waitCompletedNs = monotonicNowNs() - wait_started_ns;
        q.completed_event_counter = q.event_counter;
        if (q.pending_cmd) |cmd| {
            metal_bridge_release(cmd);
            q.pending_cmd = null;
        }
    } else if (q.pending_cmd) |cmd| {
        const wait_started_ns = monotonicNowNs();
        metal_bridge_command_buffer_wait_completed(cmd);
        out.waitCompletedNs = monotonicNowNs() - wait_started_ns;
        metal_bridge_release(cmd);
        q.pending_cmd = null;
    }
    const deferred_copy_started_ns = monotonicNowNs();
    executeDeferredCopies(q);
    out.deferredCopyNs = monotonicNowNs() - deferred_copy_started_ns;
    const deferred_resolve_started_ns = monotonicNowNs();
    executeDeferredResolves(q);
    out.deferredResolveNs = monotonicNowNs() - deferred_resolve_started_ns;
    return out;
}

pub fn flushPendingWork(q: *DoeQueue) void {
    _ = flushPendingWorkTimed(q);
}
