const builtin = @import("builtin");
const std = @import("std");
const queue_submit_ops = @import("backend/dropin_queue_submit.zig");
const native_types = @import("doe_native_object_types.zig");
const native_cmds = @import("doe_native_command_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");
const native_rt_helpers = @import("doe_native_runtime_helpers.zig");
const queue_flush_breakdown = @import("doe_queue_flush_breakdown.zig");
const error_scope = @import("error_scope.zig");

const cast = native_helpers.cast;
const DoeBuffer = native_types.DoeBuffer;
const DoeDevice = native_types.DoeDevice;
const DoeQueue = native_types.DoeQueue;
const MAX_DEFERRED_COPIES = native_cmds.MAX_DEFERRED_COPIES;
const bridge = queue_submit_ops.metal_bridge;
const has_vulkan = (builtin.os.tag == .linux);

pub fn flush_pending_work(q: *DoeQueue) void {
    queue_flush_breakdown.flushPendingWork(q);
}

pub fn flush_before_submit_if_needed(q: *DoeQueue) void {
    if (q.dev.backend != .metal or q.mtl_event == null or q.deferred_copy_count != 0 or q.deferred_resolve_count != 0) {
        flush_pending_work(q);
    }
}

pub fn finalize_submitted_metal_command_buffer(q: *DoeQueue, mtl_cmd: ?*anyopaque) void {
    if (q.mtl_event != null) {
        bridge.metal_bridge_release(mtl_cmd);
        q.pending_cmd = null;
        return;
    }
    q.pending_cmd = mtl_cmd;
}

pub fn deliverInternalError(dev: *DoeDevice, comptime fmt: []const u8, args: anytype) void {
    var buf: [256]u8 = undefined;
    const msg = std.fmt.bufPrint(&buf, fmt, args) catch "doe_queue_submit_internal_error";
    dev.error_scopes.deliver(error_scope.ERROR_TYPE_INTERNAL, msg);
}

pub fn try_schedule_deferred_copy(
    q: *DoeQueue,
    src_raw: ?*anyopaque,
    src_off: u64,
    dst_raw: ?*anyopaque,
    dst_off: u64,
    size: u64,
) bool {
    if (size == 0 or q.deferred_copy_count >= MAX_DEFERRED_COPIES) return false;
    const src = cast(DoeBuffer, src_raw) orelse return false;
    const dst = cast(DoeBuffer, dst_raw) orelse return false;
    const copy_size: usize = @intCast(size);
    const src_offset: usize = @intCast(src_off);
    const dst_offset: usize = @intCast(dst_off);
    if (src_offset + copy_size > src.size or dst_offset + copy_size > dst.size) return false;
    const src_ptr = bridge.metal_bridge_buffer_contents(src.mtl) orelse return false;
    const dst_ptr = bridge.metal_bridge_buffer_contents(dst.mtl) orelse return false;
    q.deferred_copies[q.deferred_copy_count] = .{
        .src = src_ptr + src_offset,
        .dst = dst_ptr + dst_offset,
        .size = copy_size,
    };
    q.deferred_copy_count += 1;
    return true;
}

pub fn flush_pending_work_dropin_sync(q: *DoeQueue) void {
    switch (q.dev.backend) {
        .vulkan => {
            if (comptime has_vulkan) {
                if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
                    _ = rt.flush_queue() catch |err| {
                        deliverInternalError(q.dev, "doe_queue_submit: dropin sync flush: {s}", .{@errorName(err)});
                    };
                }
            }
        },
        .d3d12 => {
            if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
                _ = rt.flush_queue() catch |err| {
                    deliverInternalError(q.dev, "doe_queue_submit: d3d12 dropin sync flush: {s}", .{@errorName(err)});
                };
            }
        },
        else => queue_flush_breakdown.flushPendingWork(q),
    }
}
