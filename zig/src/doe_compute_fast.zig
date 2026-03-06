const native = @import("doe_wgpu_native.zig");

extern fn metal_bridge_compute_dispatch_copy_signal_commit(
    queue: ?*anyopaque,
    pipeline: ?*anyopaque,
    bufs: ?[*]?*anyopaque,
    buf_count: u32,
    x: u32,
    y: u32,
    z: u32,
    wg_x: u32,
    wg_y: u32,
    wg_z: u32,
    copy_src: ?*anyopaque,
    copy_src_off: u64,
    copy_dst: ?*anyopaque,
    copy_dst_off: u64,
    copy_size: u64,
    event: ?*anyopaque,
    event_value: u64,
) callconv(.c) ?*anyopaque;
extern fn metal_bridge_shared_event_wait(event: ?*anyopaque, value: u64) callconv(.c) void;
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;

const MAX_BIND = native.MAX_BIND;

fn cast(comptime T: type, raw: ?*anyopaque) ?*T {
    const ptr = raw orelse return null;
    const typed: *T = @ptrCast(@alignCast(ptr));
    if (typed.magic != T.TYPE_MAGIC) return null;
    return typed;
}

fn flushPendingWork(q: *native.DoeQueue) void {
    if (q.pending_cmd) |cmd| {
        if (q.mtl_event) |ev| {
            metal_bridge_shared_event_wait(ev, q.event_counter);
        }
        metal_bridge_release(cmd);
        q.pending_cmd = null;
    }
}

/// Single-call compute dispatch + GPU blit copy + event signal + commit.
/// Everything happens in one ObjC bridge call for minimal overhead.
/// Wait deferred to flushPendingWork (mapAsync).
pub export fn doeNativeComputeDispatchFlush(
    q_raw: ?*anyopaque,
    pipe_raw: ?*anyopaque,
    bg_ptrs: [*]?*anyopaque,
    bg_count: u32,
    dx: u32,
    dy: u32,
    dz: u32,
    copy_src: ?*anyopaque,
    copy_src_off: u64,
    copy_dst: ?*anyopaque,
    copy_dst_off: u64,
    copy_size: u64,
) callconv(.c) void {
    const q = cast(native.DoeQueue, q_raw) orelse return;
    const pipe = cast(native.DoeComputePipeline, pipe_raw) orelse return;
    flushPendingWork(q);

    // Flatten bind groups into linear Metal buffer array.
    var bufs: [MAX_BIND * 4]?*anyopaque = [_]?*anyopaque{null} ** (MAX_BIND * 4);
    var buf_total: u32 = 0;
    for (0..@min(bg_count, 4)) |i| {
        const bg = cast(native.DoeBindGroup, bg_ptrs[i]) orelse continue;
        for (0..bg.count) |j| {
            const idx = i * MAX_BIND + j;
            if (idx < bufs.len) {
                bufs[idx] = bg.buffers[j];
                if (idx + 1 > buf_total) buf_total = @intCast(idx + 1);
            }
        }
    }

    // Resolve copy buffer Metal handles.
    var mtl_copy_src: ?*anyopaque = null;
    var mtl_copy_dst: ?*anyopaque = null;
    if (copy_size > 0) {
        if (cast(native.DoeBuffer, copy_src)) |sb| mtl_copy_src = sb.mtl;
        if (cast(native.DoeBuffer, copy_dst)) |db| mtl_copy_dst = db.mtl;
    }

    q.event_counter += 1;
    const mtl_cmd = metal_bridge_compute_dispatch_copy_signal_commit(
        q.dev.mtl_queue,
        pipe.mtl_pso,
        @ptrCast(&bufs),
        buf_total,
        dx, dy, dz,
        pipe.wg_x, pipe.wg_y, pipe.wg_z,
        mtl_copy_src, copy_src_off,
        mtl_copy_dst, copy_dst_off,
        copy_size,
        q.mtl_event,
        q.event_counter,
    ) orelse return;
    q.pending_cmd = mtl_cmd;
}
