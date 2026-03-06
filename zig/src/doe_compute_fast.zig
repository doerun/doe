const native = @import("doe_wgpu_native.zig");

extern fn metal_bridge_create_command_buffer(queue: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_cmd_buf_encode_compute_dispatch(cmd_buf: ?*anyopaque, pipeline: ?*anyopaque, bufs: ?[*]?*anyopaque, buf_count: u32, x: u32, y: u32, z: u32, wg_x: u32, wg_y: u32, wg_z: u32) callconv(.c) void;
extern fn metal_bridge_command_buffer_commit(cmd: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_command_buffer_encode_signal_event(cmd: ?*anyopaque, event: ?*anyopaque, value: u64) callconv(.c) void;
extern fn metal_bridge_shared_event_wait(event: ?*anyopaque, value: u64) callconv(.c) void;
extern fn metal_bridge_buffer_contents(buffer: ?*anyopaque) callconv(.c) ?[*]u8;
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;

const MAX_BIND = native.MAX_BIND;
const MAX_DEFERRED_COPIES = 16;

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
    for (q.deferred_copies[0..q.deferred_copy_count]) |dc| {
        @memcpy(dc.dst[0..dc.size], dc.src[0..dc.size]);
    }
    q.deferred_copy_count = 0;
}

/// Single-call compute dispatch + deferred copy + commit.
/// Bypasses Zig command recording. Wait deferred to flushPendingWork (mapAsync).
/// Uses MTLSharedEvent for GPU→CPU signaling (no GCD completion handler overhead).
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
    const mtl_cmd = metal_bridge_create_command_buffer(q.dev.mtl_queue) orelse return;
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
    metal_bridge_cmd_buf_encode_compute_dispatch(
        mtl_cmd, pipe.mtl_pso, @ptrCast(&bufs), buf_total,
        dx, dy, dz, pipe.wg_x, pipe.wg_y, pipe.wg_z,
    );
    if (copy_size > 0) {
        const sb = cast(native.DoeBuffer, copy_src);
        const db = cast(native.DoeBuffer, copy_dst);
        if (sb != null and db != null) {
            const sp = metal_bridge_buffer_contents(sb.?.mtl);
            const dp = metal_bridge_buffer_contents(db.?.mtl);
            if (sp != null and dp != null and q.deferred_copy_count < MAX_DEFERRED_COPIES) {
                q.deferred_copies[q.deferred_copy_count] = .{
                    .src = sp.? + @as(usize, @intCast(copy_src_off)),
                    .dst = dp.? + @as(usize, @intCast(copy_dst_off)),
                    .size = @intCast(copy_size),
                };
                q.deferred_copy_count += 1;
            }
        }
    }
    // Signal shared event after compute work completes on GPU.
    q.event_counter += 1;
    metal_bridge_command_buffer_encode_signal_event(mtl_cmd, q.mtl_event, q.event_counter);
    metal_bridge_command_buffer_commit(mtl_cmd);
    q.pending_cmd = mtl_cmd;
}
