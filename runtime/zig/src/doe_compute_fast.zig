const std = @import("std");
const native = @import("doe_wgpu_native.zig");
const compute_bind_groups = @import("doe_compute_bind_groups.zig");
const compute_preconditions = @import("doe_compute_preconditions_native.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const emit_msl = @import("doe_wgsl/emit_msl_ir.zig");
const metal_bridge_compute_dispatch_copy_signal_commit = bridge.metal_bridge_compute_dispatch_copy_signal_commit;
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_release = bridge.metal_bridge_release;
const MAX_COMPUTE_BIND_GROUPS = compute_bind_groups.MAX_COMPUTE_BIND_GROUPS;
const MAX_FLAT_BIND = compute_bind_groups.MAX_FLAT_BIND;
const MSL_SIZES_SLOT: u32 = emit_msl.MSL_SIZES_SLOT;
const SIZES_BUF_BYTES: usize = (MSL_SIZES_SLOT + 1) * @sizeOf(u32);

/// Single-call compute dispatch + optional same-submit copy + event signal + commit.
/// When the follow-on copy is a CPU-visible shared-buffer readback, we schedule it as
/// a deferred CPU memcpy after GPU completion to preserve macOS correctness while
/// keeping the direct dispatch path.
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
    const q = native.cast(native.DoeQueue, q_raw) orelse return;
    const pipe = native.cast(native.DoeComputePipeline, pipe_raw) orelse return;
    native.flush_pending_work(q);

    var bind_groups: [MAX_COMPUTE_BIND_GROUPS]?*native.DoeBindGroup = [_]?*native.DoeBindGroup{null} ** MAX_COMPUTE_BIND_GROUPS;
    for (0..@min(bg_count, MAX_COMPUTE_BIND_GROUPS)) |i| {
        bind_groups[i] = native.cast(native.DoeBindGroup, bg_ptrs[i]);
    }
    compute_preconditions.validate_bind_groups(
        pipe.dispatch_preconditions,
        pipe.texture_dispatch_preconditions,
        bind_groups[0..],
        .{ dx, dy, dz },
        .{ pipe.wg_x, pipe.wg_y, pipe.wg_z },
    ) catch {
        std.log.err("doe_compute_fast: dispatch precondition failed for proof-elided shader", .{});
        return;
    };

    var bufs: [MAX_FLAT_BIND]?*anyopaque = [_]?*anyopaque{null} ** MAX_FLAT_BIND;
    var buf_sizes: [MAX_FLAT_BIND]u64 = [_]u64{0} ** MAX_FLAT_BIND;
    var buf_total = compute_bind_groups.populateFlatBindings(bind_groups[0..], &bufs, &buf_sizes);

    var sizes_mtl: ?*anyopaque = null;
    defer if (sizes_mtl) |smtl| metal_bridge_release(smtl);
    if (pipe.needs_sizes_buf) {
        sizes_mtl = metal_bridge_device_new_buffer_shared(q.dev.mtl_device, SIZES_BUF_BYTES);
        if (sizes_mtl) |smtl| {
            if (metal_bridge_buffer_contents(smtl)) |ptr| {
                const sizes: *[MSL_SIZES_SLOT + 1]u32 = @ptrCast(@alignCast(ptr));
                for (0..MSL_SIZES_SLOT + 1) |i| sizes[i] = 0;
                for (0..buf_total) |i| sizes[i] = @intCast(buf_sizes[i]);
            }
            bufs[MSL_SIZES_SLOT] = smtl;
            if (buf_total <= MSL_SIZES_SLOT) buf_total = MSL_SIZES_SLOT + 1;
        }
    }

    // Resolve copy path. Prefer the same deferred CPU-copy path used by the
    // generic queue submission on Apple Silicon shared-memory buffers.
    var mtl_copy_src: ?*anyopaque = null;
    var mtl_copy_dst: ?*anyopaque = null;
    var copy_src_off_local = copy_src_off;
    var copy_dst_off_local = copy_dst_off;
    var copy_size_local = copy_size;
    if (copy_size_local > 0) {
        if (native.try_schedule_deferred_copy(q, copy_src, copy_src_off_local, copy_dst, copy_dst_off_local, copy_size_local)) {
            copy_src_off_local = 0;
            copy_dst_off_local = 0;
            copy_size_local = 0;
        } else {
            if (native.cast(native.DoeBuffer, copy_src)) |sb| mtl_copy_src = sb.mtl;
            if (native.cast(native.DoeBuffer, copy_dst)) |db| mtl_copy_dst = db.mtl;
        }
    }

    q.event_counter += 1;
    const mtl_cmd = metal_bridge_compute_dispatch_copy_signal_commit(
        q.dev.mtl_queue,
        pipe.mtl_pso,
        @ptrCast(&bufs),
        buf_total,
        dx,
        dy,
        dz,
        pipe.wg_x,
        pipe.wg_y,
        pipe.wg_z,
        mtl_copy_src,
        copy_src_off_local,
        mtl_copy_dst,
        copy_dst_off_local,
        copy_size_local,
        q.mtl_event,
        q.event_counter,
    ) orelse return;
    q.pending_cmd = mtl_cmd;
    if (copy_size > 0) {
        native.flush_pending_work(q);
    }
}
