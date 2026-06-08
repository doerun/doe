const std = @import("std");
const native_cmds = @import("doe_native_command_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");
const native_rt_helpers = @import("doe_native_runtime_helpers.zig");
const native_shared = @import("doe_native_shared_types.zig");
const native_types = @import("doe_native_object_types.zig");
const compute_bind_groups = @import("doe_compute_bind_groups.zig");
const compute_preconditions = @import("doe_compute_preconditions_native.zig");
const vulkan_compute = @import("doe_vulkan_compute_native.zig");
const queue_submit_ops = @import("backend/dropin_queue_submit.zig");

const vk_upload = queue_submit_ops.vulkan_upload;
const RecordedCmd = native_cmds.RecordedCmd;
const DoeBuffer = native_types.DoeBuffer;
const DoeComputePipeline = native_types.DoeComputePipeline;
const DoeQueue = native_types.DoeQueue;
const MAX_COMPUTE_BIND_GROUPS = native_shared.MAX_COMPUTE_BIND_GROUPS;
const MAX_FLAT_BIND = native_shared.MAX_FLAT_BIND;
const toOpaque = native_helpers.toOpaque;

const DispatchReplayCache = struct {
    valid: bool = false,
    pipeline: ?*anyopaque = null,
    bg_count: u32 = 0,
    bg_ptrs: [MAX_COMPUTE_BIND_GROUPS]?*anyopaque = [_]?*anyopaque{null} ** MAX_COMPUTE_BIND_GROUPS,
    x: u32 = 0,
    y: u32 = 0,
    z: u32 = 0,
    cmd: RecordedCmd = undefined,

    fn matches(
        self: *const DispatchReplayCache,
        pipeline: ?*anyopaque,
        bg_slice: [*]const ?*anyopaque,
        bg_count: u32,
        x: u32,
        y: u32,
        z: u32,
    ) bool {
        if (!self.valid or self.pipeline != pipeline or self.bg_count != bg_count) return false;
        if (self.x != x or self.y != y or self.z != z) return false;
        for (0..@as(usize, @intCast(bg_count))) |index| {
            if (self.bg_ptrs[index] != bg_slice[index]) return false;
        }
        return true;
    }

    fn remember(
        self: *DispatchReplayCache,
        pipeline: ?*anyopaque,
        bg_slice: [*]const ?*anyopaque,
        bg_count: u32,
        x: u32,
        y: u32,
        z: u32,
        cmd: RecordedCmd,
    ) void {
        self.valid = true;
        self.pipeline = pipeline;
        self.bg_count = bg_count;
        self.x = x;
        self.y = y;
        self.z = z;
        self.cmd = cmd;
        for (0..MAX_COMPUTE_BIND_GROUPS) |index| {
            self.bg_ptrs[index] = if (index < bg_count) bg_slice[index] else null;
        }
    }

    fn invalidate(self: *DispatchReplayCache) void {
        self.valid = false;
    }
};

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

fn recordedDispatch(
    pipe: *DoeComputePipeline,
    bg_ptrs: [*]const ?*anyopaque,
    bg_count: u32,
    dx: u32,
    dy: u32,
    dz: u32,
) ?RecordedCmd {
    var bind_groups: [MAX_COMPUTE_BIND_GROUPS]?*native_types.DoeBindGroup = [_]?*native_types.DoeBindGroup{null} ** MAX_COMPUTE_BIND_GROUPS;
    for (0..@min(bg_count, MAX_COMPUTE_BIND_GROUPS)) |i| {
        bind_groups[i] = native_helpers.cast(native_types.DoeBindGroup, bg_ptrs[i]);
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

    var cmd = RecordedCmd{ .dispatch = .{
        .compute_pipeline = toOpaque(pipe),
        .pso = pipe.mtl_pso,
        .needs_sizes_buf = pipe.needs_sizes_buf,
        .bufs = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        .buf_offsets = [_]u64{0} ** MAX_FLAT_BIND,
        .buf_sizes = [_]u64{0} ** MAX_FLAT_BIND,
        .buf_count = 0,
        .x = dx,
        .y = dy,
        .z = dz,
        .wg_x = pipe.wg_x,
        .wg_y = pipe.wg_y,
        .wg_z = pipe.wg_z,
    } };
    cmd.dispatch.buf_count = compute_bind_groups.populateFlatBindings(
        bind_groups[0..],
        &cmd.dispatch.bufs,
        &cmd.dispatch.buf_offsets,
        &cmd.dispatch.buf_sizes,
    );
    return cmd;
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
    var replay_cache = DispatchReplayCache{};
    for (0..dispatch_count) |index| {
        const pipe_raw = pipe_ptrs[index];
        const pipe = native_helpers.cast(DoeComputePipeline, pipe_raw) orelse {
            replay_cache.invalidate();
            continue;
        };
        const bg_offset = index * MAX_COMPUTE_BIND_GROUPS;
        const dim_offset = index * 3;
        const bg_count = bg_counts[index];
        const x = dispatch_dims[dim_offset];
        const y = dispatch_dims[dim_offset + 1];
        const z = dispatch_dims[dim_offset + 2];
        if (bg_count <= MAX_COMPUTE_BIND_GROUPS and replay_cache.matches(pipe_raw, bg_ptrs + bg_offset, bg_count, x, y, z)) {
            const record_started_ns = monotonicNowNs();
            vulkan_compute.vulkan_run_prepared_dispatch(rt, replay_cache.cmd.dispatch);
            timings.command_replay_record_ns += monotonicNowNs() - record_started_ns;
            executed_any_dispatch = true;
            continue;
        }
        const cmd = recordedDispatch(
            pipe,
            bg_ptrs + bg_offset,
            bg_count,
            x,
            y,
            z,
        ) orelse {
            replay_cache.invalidate();
            continue;
        };
        const prepare_started_ns = monotonicNowNs();
        if (!vulkan_compute.vulkan_prepare_recorded_dispatch(rt, cmd.dispatch)) {
            timings.command_replay_prepare_ns += monotonicNowNs() - prepare_started_ns;
            replay_cache.invalidate();
            continue;
        }
        timings.command_replay_prepare_ns += monotonicNowNs() - prepare_started_ns;
        if (bg_count <= MAX_COMPUTE_BIND_GROUPS) {
            replay_cache.remember(pipe_raw, bg_ptrs + bg_offset, bg_count, x, y, z, cmd);
        } else {
            replay_cache.invalidate();
        }
        const record_started_ns = monotonicNowNs();
        vulkan_compute.vulkan_run_prepared_dispatch(rt, cmd.dispatch);
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
