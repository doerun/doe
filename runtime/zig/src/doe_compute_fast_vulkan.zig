const std = @import("std");
const native_helpers = @import("doe_native_object_helpers.zig");
const native_rt_helpers = @import("doe_native_runtime_helpers.zig");
const native_shared = @import("doe_native_shared_types.zig");
const native_types = @import("doe_native_object_types.zig");
const compute_preconditions = @import("doe_compute_preconditions_native.zig");
const vulkan_compute = @import("doe_vulkan_compute_native.zig");
const queue_submit_ops = @import("backend/dropin_queue_submit.zig");

const vk_upload = queue_submit_ops.vulkan_upload;
const DoeBuffer = native_types.DoeBuffer;
const DoeBindGroup = native_types.DoeBindGroup;
const DoeComputePipeline = native_types.DoeComputePipeline;
const DoeQueue = native_types.DoeQueue;
const MAX_COMPUTE_BIND_GROUPS = native_shared.MAX_COMPUTE_BIND_GROUPS;

pub const DispatchBatchCopyFlushTimings = struct {
    command_replay_ns: u64 = 0,
    command_replay_prepare_ns: u64 = 0,
    command_replay_record_ns: u64 = 0,
    command_replay_copy_ns: u64 = 0,
    queue_submit_ns: u64 = 0,
    queue_submit_command_buffer_end_ns: u64 = 0,
    queue_submit_sync_prepare_ns: u64 = 0,
    queue_submit_driver_submit_ns: u64 = 0,
};

fn monotonicNowNs() u64 {
    return @intCast(std.time.nanoTimestamp());
}

const BindGroupArray = [MAX_COMPUTE_BIND_GROUPS]?*DoeBindGroup;

fn validatedBindGroups(
    pipe: *DoeComputePipeline,
    bg_ptrs: [*]const ?*anyopaque,
    bg_count: u32,
    dx: u32,
    dy: u32,
    dz: u32,
) ?BindGroupArray {
    var bind_groups: BindGroupArray = [_]?*DoeBindGroup{null} ** MAX_COMPUTE_BIND_GROUPS;
    for (0..@min(bg_count, MAX_COMPUTE_BIND_GROUPS)) |i| {
        bind_groups[i] = native_helpers.cast(DoeBindGroup, bg_ptrs[i]);
    }
    compute_preconditions.validate_bind_groups(
        pipe.dispatch_preconditions,
        pipe.texture_dispatch_preconditions,
        bind_groups[0..],
        .{ dx, dy, dz },
        .{ pipe.wg_x, pipe.wg_y, pipe.wg_z },
    ) catch {
        std.log.err("doe_compute_fast_vulkan: dispatch precondition failed for proof-elided shader", .{});
        return null;
    };
    return bind_groups;
}

fn recordOrExecuteCopy(
    rt: anytype,
    q: *DoeQueue,
    copy_src: ?*anyopaque,
    copy_src_off: u64,
    copy_dst: ?*anyopaque,
    copy_dst_off: u64,
    copy_size: u64,
    executed_any_dispatch: *bool,
) void {
    if (copy_size == 0) return;
    const src_buf = native_helpers.cast(DoeBuffer, copy_src) orelse return;
    const dst_buf = native_helpers.cast(DoeBuffer, copy_dst) orelse return;
    if (src_buf.vk_id == 0 or dst_buf.vk_id == 0) return;
    const scb = rt.compute_buffers.get(src_buf.vk_id) orelse return;
    const dcb = rt.compute_buffers.get(dst_buf.vk_id) orelse return;
    const copy_end_src = std.math.add(u64, copy_src_off, copy_size) catch return;
    const copy_end_dst = std.math.add(u64, copy_dst_off, copy_size) catch return;
    if (copy_end_src > scb.size or copy_end_dst > dcb.size) return;
    const src_has_pending_compute_write =
        rt.has_pending_compute_writes and
        (!rt.current_compute_binding_tracking_complete or rt.pending_compute_write_buffers.contains(src_buf.vk_id));
    if (rt.replay_recording_active and (scb.mapped == null or src_has_pending_compute_write)) {
        vk_upload.record_replay_buffer_copy(
            rt,
            scb,
            copy_src_off,
            dcb,
            copy_dst_off,
            copy_size,
        ) catch |err| {
            std.log.err("doe_compute_fast_vulkan: record copy_buf failed: {s}", .{@errorName(err)});
        };
        return;
    }
    if (executed_any_dispatch.*) {
        _ = rt.flush_queue() catch |err| {
            std.log.err("doe_compute_fast_vulkan: flush before copy_buf failed: {s}", .{@errorName(err)});
        };
        executed_any_dispatch.* = false;
    }
    if (scb.mapped != null and dcb.mapped != null) {
        const n: usize = @intCast(copy_size);
        const so: usize = @intCast(copy_src_off);
        const doff: usize = @intCast(copy_dst_off);
        const src: [*]const u8 = @ptrCast(scb.mapped.?);
        const dst: [*]u8 = @ptrCast(dcb.mapped.?);
        @memcpy(dst[doff .. doff + n], src[so .. so + n]);
        return;
    }
    vk_upload.copy_buffer_region_and_wait(
        rt,
        scb.buffer,
        copy_src_off,
        dcb.buffer,
        copy_dst_off,
        copy_size,
    ) catch |err| {
        std.log.err("doe_compute_fast_vulkan: copy_buf failed: {s}", .{@errorName(err)});
    };
    _ = q;
}

pub fn dispatchBatchCopyFlush(
    q: *DoeQueue,
    dispatch_count: usize,
    pipe_ptrs: [*]?*anyopaque,
    bg_ptrs: [*]?*anyopaque,
    bg_counts: [*]const u32,
    dispatch_dims: [*]const u32,
    copy_src: ?*anyopaque,
    copy_src_off: u64,
    copy_dst: ?*anyopaque,
    copy_dst_off: u64,
    copy_size: u64,
) DispatchBatchCopyFlushTimings {
    var timings = DispatchBatchCopyFlushTimings{};
    if (dispatch_count == 0) return timings;
    const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return timings;
    const previous_replay_state = rt.recorded_submit_replay_active;
    rt.recorded_submit_replay_active = true;
    defer rt.recorded_submit_replay_active = previous_replay_state;

    const replay_started_ns = monotonicNowNs();
    var executed_any_dispatch = false;
    for (0..dispatch_count) |index| {
        const pipe = native_helpers.cast(DoeComputePipeline, pipe_ptrs[index]) orelse continue;
        const bg_offset = index * MAX_COMPUTE_BIND_GROUPS;
        const dim_offset = index * 3;
        const bind_groups = validatedBindGroups(
            pipe,
            bg_ptrs + bg_offset,
            bg_counts[index],
            dispatch_dims[dim_offset],
            dispatch_dims[dim_offset + 1],
            dispatch_dims[dim_offset + 2],
        ) orelse continue;
        const prepare_started_ns = monotonicNowNs();
        if (!vulkan_compute.vulkan_prepare_dispatch_bind_groups(rt, pipe, bind_groups[0..])) {
            timings.command_replay_prepare_ns += monotonicNowNs() - prepare_started_ns;
            continue;
        }
        timings.command_replay_prepare_ns += monotonicNowNs() - prepare_started_ns;
        const record_started_ns = monotonicNowNs();
        vulkan_compute.vulkan_run_prepared_dispatch(rt, .{
            .x = dispatch_dims[dim_offset],
            .y = dispatch_dims[dim_offset + 1],
            .z = dispatch_dims[dim_offset + 2],
        });
        timings.command_replay_record_ns += monotonicNowNs() - record_started_ns;
        executed_any_dispatch = true;
    }

    const copy_started_ns = monotonicNowNs();
    recordOrExecuteCopy(
        rt,
        q,
        copy_src,
        copy_src_off,
        copy_dst,
        copy_dst_off,
        copy_size,
        &executed_any_dispatch,
    );
    timings.command_replay_copy_ns = monotonicNowNs() - copy_started_ns;
    timings.command_replay_ns = monotonicNowNs() - replay_started_ns;
    if (executed_any_dispatch) {
        const submit_started_ns = monotonicNowNs();
        const submit_timings = rt.submit_recorded_replay_timed() catch |err| {
            std.log.err("doe_compute_fast_vulkan: submit recorded replay failed: {s}", .{@errorName(err)});
            timings.queue_submit_ns = monotonicNowNs() - submit_started_ns;
            return timings;
        };
        timings.queue_submit_ns = submit_timings.total();
        timings.queue_submit_command_buffer_end_ns = submit_timings.command_buffer_end_ns;
        timings.queue_submit_sync_prepare_ns = submit_timings.sync_prepare_ns;
        timings.queue_submit_driver_submit_ns = submit_timings.driver_submit_ns;
    }
    return timings;
}
