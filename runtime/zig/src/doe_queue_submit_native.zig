const builtin = @import("builtin");
const has_vulkan = (builtin.os.tag == .linux);
const std = @import("std");
const abi_core = @import("core/abi/wgpu_core_base_types.zig");
const abi_callback = @import("core/abi/wgpu_callback_descriptor_types.zig");
const abi_copy = @import("core/abi/wgpu_copy_descriptor_types.zig");
const abi_texture = @import("core/abi/wgpu_texture_base_types.zig");
const queue_submit_ops = @import("backend/dropin_queue_submit.zig");
const native_types = @import("doe_native_object_types.zig");
const native_shared = @import("doe_native_shared_types.zig");
const native_cmds = @import("doe_native_command_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");
const native_rt_helpers = @import("doe_native_runtime_helpers.zig");
const native_exports = @import("doe_native_exports.zig");
const queue_flush_breakdown = @import("doe_queue_flush_breakdown.zig");
const error_scope = @import("error_scope.zig");
const alloc = native_helpers.alloc;
const cast = native_helpers.cast;
const toOpaque = native_helpers.toOpaque;
const DoeQueue = native_types.DoeQueue;
const DoeBuffer = native_types.DoeBuffer;
const DoeCommandBuffer = native_types.DoeCommandBuffer;
const DoeTexture = native_types.DoeTexture;
const MAX_DEFERRED_COPIES = native_cmds.MAX_DEFERRED_COPIES;
const MAX_DEFERRED_RESOLVES = native_cmds.MAX_DEFERRED_RESOLVES;
const VERTEX_BUFFER_SLOT_BASE = native_shared.VERTEX_BUFFER_SLOT_BASE;
const MAX_FLAT_BIND = native_shared.MAX_FLAT_BIND;
const d3d12_native_render_pass = queue_submit_ops.d3d12_native_render_pass;
const emit_msl = @import("doe_wgsl/emit_msl_ir.zig");
const MSL_SIZES_SLOT: u32 = emit_msl.MSL_SIZES_SLOT;
const SIZES_BUF_BYTES: usize = (MSL_SIZES_SLOT + 1) * @sizeOf(u32);
const bridge = queue_submit_ops.metal_bridge;
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_blit_encoder_copy_buffer_to_texture = bridge.metal_bridge_blit_encoder_copy_buffer_to_texture;
const metal_bridge_blit_encoder_copy_texture_to_buffer = bridge.metal_bridge_blit_encoder_copy_texture_to_buffer;
const metal_bridge_cmd_buf_blit_encoder = bridge.metal_bridge_cmd_buf_blit_encoder;
const metal_bridge_cmd_buf_encode_blit_copy = bridge.metal_bridge_cmd_buf_encode_blit_copy;
const metal_bridge_cmd_buf_fill_buffer = bridge.metal_bridge_cmd_buf_fill_buffer;
const metal_bridge_cmd_buf_copy_texture_to_texture = bridge.metal_bridge_cmd_buf_copy_texture_to_texture;
const metal_bridge_cmd_buf_encode_compute_dispatch = bridge.metal_bridge_cmd_buf_encode_compute_dispatch;
const metal_bridge_cmd_buf_encode_compute_dispatch_indirect = bridge.metal_bridge_cmd_buf_encode_compute_dispatch_indirect;
const metal_bridge_cmd_buf_render_encoder = bridge.metal_bridge_cmd_buf_render_encoder;
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_command_buffer_encode_signal_event = bridge.metal_bridge_command_buffer_encode_signal_event;
const metal_bridge_command_buffer_wait_completed = bridge.metal_bridge_command_buffer_wait_completed;
const metal_bridge_create_command_buffer = bridge.metal_bridge_create_command_buffer;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_end_blit_encoding = bridge.metal_bridge_end_blit_encoding;
const metal_bridge_release = bridge.metal_bridge_release;
const metal_bridge_render_encoder_set_bind_buffer = bridge.metal_bridge_render_encoder_set_bind_buffer;
const metal_bridge_render_encoder_set_bind_sampler = bridge.metal_bridge_render_encoder_set_bind_sampler;
const metal_bridge_render_encoder_set_bind_texture = bridge.metal_bridge_render_encoder_set_bind_texture;
const metal_bridge_render_encoder_set_cull_mode = bridge.metal_bridge_render_encoder_set_cull_mode;
const metal_bridge_render_encoder_set_depth_clip_mode = bridge.metal_bridge_render_encoder_set_depth_clip_mode;
const metal_bridge_render_encoder_set_depth_stencil_state = bridge.metal_bridge_render_encoder_set_depth_stencil_state;
const metal_bridge_render_encoder_set_depth_stencil_values = bridge.metal_bridge_render_encoder_set_depth_stencil_values;
const metal_bridge_render_encoder_set_front_facing = bridge.metal_bridge_render_encoder_set_front_facing;
const metal_bridge_render_encoder_draw = bridge.metal_bridge_render_encoder_draw;
const metal_bridge_render_encoder_draw_indexed = bridge.metal_bridge_render_encoder_draw_indexed;
const metal_bridge_render_encoder_draw_indirect = bridge.metal_bridge_render_encoder_draw_indirect;
const metal_bridge_render_encoder_draw_indexed_indirect = bridge.metal_bridge_render_encoder_draw_indexed_indirect;
const metal_bridge_render_encoder_end = bridge.metal_bridge_render_encoder_end;
const metal_bridge_render_encoder_set_vertex_buffer = bridge.metal_bridge_render_encoder_set_vertex_buffer;
const metal_bridge_sample_timestamp = bridge.metal_bridge_sample_timestamp;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

const WGPU_MAP_ASYNC_STATUS_SUCCESS: u32 = 1;

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
        metal_bridge_release(mtl_cmd);
        q.pending_cmd = null;
        return;
    }
    q.pending_cmd = mtl_cmd;
}

fn deliverInternalError(dev: *native_types.DoeDevice, comptime fmt: []const u8, args: anytype) void {
    var buf: [256]u8 = undefined;
    const msg = std.fmt.bufPrint(&buf, fmt, args) catch "doe_queue_submit_internal_error";
    dev.error_scopes.deliver(error_scope.ERROR_TYPE_INTERNAL, msg);
}

fn submittedBuffersHaveRecordedCommands(count: usize, cmd_bufs: [*]const ?*anyopaque) bool {
    for (cmd_bufs[0..count]) |raw| {
        const cb = cast(DoeCommandBuffer, raw) orelse continue;
        if (cb.cmds.items.len != 0) return true;
    }
    return false;
}

fn read_indirect_dispatch_counts(buffer_raw: ?*anyopaque, offset: u64) ?struct { x: u32, y: u32, z: u32 } {
    const buffer = cast(DoeBuffer, buffer_raw) orelse return null;
    const byte_offset: usize = @intCast(offset);
    const counts_bytes = 3 * @sizeOf(u32);
    if (byte_offset + counts_bytes > buffer.size) return null;
    const contents = metal_bridge_buffer_contents(buffer.mtl) orelse return null;
    const base = contents + byte_offset;
    const ints: *align(1) const [3]u32 = @ptrCast(base);
    return .{ .x = ints[0], .y = ints[1], .z = ints[2] };
}

fn submit_d3d12_commands(q: *DoeQueue, count: usize, cmd_bufs: [*]const ?*anyopaque) void {
    const rt = native_rt_helpers.device_d3d12_runtime(q.dev) orelse return;
    rt.flush_before_dropin_submit_if_needed() catch |err| {
        deliverInternalError(q.dev, "doe_queue_submit: d3d12 pre-submit flush: {s}", .{@errorName(err)});
        return;
    };

    const cmd_allocator = d3d12_bridge_device_create_command_allocator(rt.device) orelse return;
    var owns_cmd_allocator = true;
    defer if (owns_cmd_allocator) d3d12_bridge_release(cmd_allocator);

    const cmd_list = d3d12_bridge_device_create_command_list(rt.device, cmd_allocator) orelse return;
    var owns_cmd_list = true;
    defer if (owns_cmd_list) d3d12_bridge_release(cmd_list);

    var retained_handles: std.ArrayListUnmanaged(?*anyopaque) = .{};
    var owns_retained_handles = true;
    defer if (owns_retained_handles) {
        for (retained_handles.items) |maybe_handle| {
            if (maybe_handle) |handle| d3d12_bridge_release(handle);
        }
        retained_handles.deinit(alloc);
    };

    var has_gpu_work = false;
    for (cmd_bufs[0..count]) |raw| {
        const cb = cast(DoeCommandBuffer, raw) orelse continue;
        for (cb.cmds.items) |cmd| {
            switch (cmd) {
                .render_pass => |render_pass_cmd| {
                    d3d12_native_render_pass.record_render_pass_command(
                        alloc,
                        &retained_handles,
                        rt.device,
                        cmd_list,
                        render_pass_cmd,
                        &rt.descriptor_state,
                        &rt.texture_view_state,
                        &rt.sampler_state,
                    ) catch continue;
                    has_gpu_work = true;
                },
                else => {},
            }
        }
    }

    if (!has_gpu_work) return;

    d3d12_bridge_command_list_close(cmd_list);
    d3d12_bridge_queue_execute_command_list(rt.queue, cmd_list);
    rt.fence_value +|= 1;
    d3d12_bridge_queue_signal(rt.queue, rt.fence, rt.fence_value);
    rt.trackDropinSubmission(cmd_allocator, cmd_list, &retained_handles) catch {
        d3d12_bridge_fence_wait(rt.fence, rt.fence_value);
        rt.noteCompletedFenceWait();
        return;
    };
    owns_cmd_allocator = false;
    owns_cmd_list = false;
    owns_retained_handles = false;
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
    const src_ptr = metal_bridge_buffer_contents(src.mtl) orelse return false;
    const dst_ptr = metal_bridge_buffer_contents(dst.mtl) orelse return false;
    q.deferred_copies[q.deferred_copy_count] = .{
        .src = src_ptr + src_offset,
        .dst = dst_ptr + dst_offset,
        .size = copy_size,
    };
    q.deferred_copy_count += 1;
    return true;
}

// ============================================================
// Queue submit
// ============================================================

pub export fn doeNativeQueueSubmit(q_raw: ?*anyopaque, count: usize, cmd_bufs: [*]const ?*anyopaque) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;

    // For the Vulkan C ABI path, commands are executed immediately during
    // recording (e.g. via doeNativeComputePassDispatch issuing vkCmdDispatch
    // synchronously). Queue submit therefore only needs to drain the recorded
    // command buffer handles without re-executing them. Ownership stays with
    // the command buffer object until the explicit release proc runs.
    if (q.dev.backend == .vulkan) {
        return;
    }

    if (q.dev.backend == .d3d12) {
        submit_d3d12_commands(q, count, cmd_bufs);
        return;
    }

    const queue = q.dev.mtl_queue;

    // Only flush at submit entry when later work depends on deferred CPU-side
    // copies/resolves or when the shared-event fast path is unavailable.
    flush_before_submit_if_needed(q);

    if (!submittedBuffersHaveRecordedCommands(count, cmd_bufs)) {
        return;
    }

    // Batch all recorded commands into a single MTLCommandBuffer.
    const mtl_cmd = metal_bridge_create_command_buffer(queue) orelse return;
    var has_gpu_work = false;

    for (cmd_bufs[0..count]) |raw| {
        const cb = cast(DoeCommandBuffer, raw) orelse continue;
        for (cb.cmds.items) |cmd| {
            switch (cmd) {
                .dispatch => |d| {
                    var bufs_copy = d.bufs;
                    var buf_count = d.buf_count;
                    var sizes_mtl: ?*anyopaque = null;
                    if (d.needs_sizes_buf) {
                        // Allocate a shared MTLBuffer for _doe_sizes and fill it with byte sizes.
                        sizes_mtl = metal_bridge_device_new_buffer_shared(q.dev.mtl_device, SIZES_BUF_BYTES);
                        if (sizes_mtl) |smtl| {
                            if (metal_bridge_buffer_contents(smtl)) |ptr| {
                                const sizes: *[MSL_SIZES_SLOT + 1]u32 = @ptrCast(@alignCast(ptr));
                                for (0..MSL_SIZES_SLOT + 1) |i| sizes[i] = 0;
                                for (0..d.buf_count) |i| sizes[i] = @intCast(d.buf_sizes[i]);
                            }
                            bufs_copy[MSL_SIZES_SLOT] = smtl;
                            if (buf_count <= MSL_SIZES_SLOT) buf_count = MSL_SIZES_SLOT + 1;
                        }
                    }
                    metal_bridge_cmd_buf_encode_compute_dispatch(
                        mtl_cmd,
                        d.pso,
                        @as(?[*]?*anyopaque, &bufs_copy),
                        buf_count,
                        d.x,
                        d.y,
                        d.z,
                        d.wg_x,
                        d.wg_y,
                        d.wg_z,
                    );
                    if (sizes_mtl) |smtl| metal_bridge_release(smtl);
                    has_gpu_work = true;
                },
                .copy_buf => |c| {
                    // Apple Silicon unified memory: defer as CPU memcpy after GPU completion
                    // whenever both buffers expose shared contents.
                    if (!try_schedule_deferred_copy(q, c.src, c.src_off, c.dst, c.dst_off, c.size)) {
                        metal_bridge_cmd_buf_encode_blit_copy(
                            mtl_cmd,
                            c.src,
                            @intCast(c.src_off),
                            c.dst,
                            @intCast(c.dst_off),
                            @intCast(c.size),
                        );
                        has_gpu_work = true;
                    }
                },
                .copy_buffer_to_texture => |c| {
                    const blit = metal_bridge_cmd_buf_blit_encoder(mtl_cmd) orelse continue;
                    metal_bridge_blit_encoder_copy_buffer_to_texture(
                        blit,
                        c.src_buffer,
                        c.src_offset,
                        c.src_bytes_per_row,
                        c.src_rows_per_image,
                        c.dst_texture,
                        c.dst_mip_level,
                        c.width,
                        c.height,
                        c.depth_or_array_layers,
                    );
                    metal_bridge_end_blit_encoding(blit);
                    has_gpu_work = true;
                },
                .copy_texture_to_buffer => |c| {
                    const blit = metal_bridge_cmd_buf_blit_encoder(mtl_cmd) orelse continue;
                    metal_bridge_blit_encoder_copy_texture_to_buffer(
                        blit,
                        c.src_texture,
                        c.src_mip_level,
                        c.dst_buffer,
                        c.dst_offset,
                        c.dst_bytes_per_row,
                        c.dst_rows_per_image,
                        c.width,
                        c.height,
                        c.depth_or_array_layers,
                    );
                    metal_bridge_end_blit_encoding(blit);
                    has_gpu_work = true;
                },
                .clear_buffer => |c| {
                    metal_bridge_cmd_buf_fill_buffer(mtl_cmd, c.buffer, c.offset, c.size);
                    has_gpu_work = true;
                },
                .copy_texture_to_texture => |c| {
                    metal_bridge_cmd_buf_copy_texture_to_texture(
                        mtl_cmd,
                        c.src_texture,
                        c.src_mip,
                        c.src_slice,
                        c.src_x,
                        c.src_y,
                        c.src_z,
                        c.dst_texture,
                        c.dst_mip,
                        c.dst_slice,
                        c.dst_x,
                        c.dst_y,
                        c.dst_z,
                        c.width,
                        c.height,
                        c.depth_or_layers,
                    );
                    has_gpu_work = true;
                },
                .dispatch_indirect => |d| {
                    var bufs_copy = d.bufs;
                    if (read_indirect_dispatch_counts(d.indirect_buf, d.offset)) |counts| {
                        metal_bridge_cmd_buf_encode_compute_dispatch(
                            mtl_cmd,
                            d.pso,
                            @as(?[*]?*anyopaque, &bufs_copy),
                            d.buf_count,
                            counts.x,
                            counts.y,
                            counts.z,
                            d.wg_x,
                            d.wg_y,
                            d.wg_z,
                        );
                    } else {
                        const indirect_buffer = cast(DoeBuffer, d.indirect_buf) orelse continue;
                        metal_bridge_cmd_buf_encode_compute_dispatch_indirect(
                            mtl_cmd,
                            d.pso,
                            @as(?[*]?*anyopaque, &bufs_copy),
                            d.buf_count,
                            indirect_buffer.mtl,
                            d.offset,
                            d.wg_x,
                            d.wg_y,
                            d.wg_z,
                        );
                    }
                    has_gpu_work = true;
                },
                .render_pass => |r| {
                    const renc = metal_bridge_cmd_buf_render_encoder(
                        mtl_cmd,
                        r.pso,
                        r.target,
                        r.depth_target,
                        if (r.depth_write_enabled) 1 else 0,
                        r.clear_r,
                        r.clear_g,
                        r.clear_b,
                        r.clear_a,
                    );
                    if (renc) |e| {
                        metal_bridge_render_encoder_set_front_facing(e, r.front_face);
                        metal_bridge_render_encoder_set_cull_mode(e, r.cull_mode);
                        if (r.unclipped_depth) {
                            metal_bridge_render_encoder_set_depth_clip_mode(e, 1);
                        }
                        if (r.depth_state) |depth_state| {
                            metal_bridge_render_encoder_set_depth_stencil_state(e, depth_state);
                            metal_bridge_render_encoder_set_depth_stencil_values(e, r.depth_compare, if (r.depth_write_enabled) 1 else 0);
                        }
                        for (r.bind_buffers, r.bind_buffer_offsets, 0..) |maybe_buf, offset, slot| {
                            if (maybe_buf) |buf| {
                                metal_bridge_render_encoder_set_bind_buffer(e, @intCast(slot), buf, offset);
                            }
                        }
                        for (r.bind_textures, 0..) |maybe_tex, slot| {
                            if (maybe_tex) |tex| {
                                metal_bridge_render_encoder_set_bind_texture(e, @intCast(slot), tex);
                            }
                        }
                        for (r.bind_samplers, 0..) |maybe_sampler, slot| {
                            if (maybe_sampler) |sampler| {
                                metal_bridge_render_encoder_set_bind_sampler(e, @intCast(slot), sampler);
                            }
                        }
                        for (r.vertex_buffers, r.vertex_buffer_offsets, 0..) |maybe_buf, offset, slot| {
                            if (maybe_buf) |buf| {
                                metal_bridge_render_encoder_set_vertex_buffer(e, VERTEX_BUFFER_SLOT_BASE + @as(u32, @intCast(slot)), buf, offset);
                            }
                        }
                        if (r.indirect) {
                            if (r.indexed) {
                                metal_bridge_render_encoder_draw_indexed_indirect(
                                    e,
                                    r.index_buffer,
                                    r.index_offset,
                                    r.index_format,
                                    r.indirect_buffer,
                                    r.indirect_offset,
                                );
                            } else {
                                metal_bridge_render_encoder_draw_indirect(
                                    e,
                                    r.indirect_buffer,
                                    r.indirect_offset,
                                );
                            }
                        } else if (r.indexed) {
                            metal_bridge_render_encoder_draw_indexed(
                                e,
                                r.topology,
                                r.draw_count,
                                r.index_count,
                                r.instance_count,
                                r.index_buffer,
                                r.index_offset,
                                r.index_format,
                                r.base_vertex,
                                r.first_instance,
                            );
                        } else {
                            metal_bridge_render_encoder_draw(
                                e,
                                r.topology,
                                r.draw_count,
                                r.vertex_count,
                                r.instance_count,
                                r.first_vertex,
                                r.first_instance,
                                0,
                                r.pso,
                            );
                        }
                        metal_bridge_render_encoder_end(e);
                        metal_bridge_release(e);
                    }
                    has_gpu_work = true;
                },
                .write_timestamp => |ts| {
                    metal_bridge_sample_timestamp(mtl_cmd, ts.counter_buffer, ts.query_index);
                    has_gpu_work = true;
                },
                .resolve_query_set => |rs| {
                    // Counter resolve is CPU-side — must run after GPU
                    // completion. Record as deferred resolve.
                    if (q.deferred_resolve_count < MAX_DEFERRED_RESOLVES) {
                        q.deferred_resolves[q.deferred_resolve_count] = .{
                            .counter_buffer = rs.counter_buffer,
                            .first_query = rs.first_query,
                            .query_count = rs.query_count,
                            .dst_mtl = rs.dst_mtl,
                            .dst_offset = rs.dst_offset,
                        };
                        q.deferred_resolve_count += 1;
                    }
                    // Timestamp sampling is GPU work.
                    has_gpu_work = true;
                },
            }
        }
    }

    if (has_gpu_work) {
        // Signal shared event after GPU work completes (direct GPU→CPU sync).
        q.event_counter += 1;
        if (q.mtl_event) |event| {
            metal_bridge_command_buffer_encode_signal_event(mtl_cmd, event, q.event_counter);
        }
        metal_bridge_command_buffer_commit(mtl_cmd);
        finalize_submitted_metal_command_buffer(q, mtl_cmd);
    } else {
        metal_bridge_release(mtl_cmd);
        queue_flush_breakdown.executeDeferredCopies(q);
    }
}

// ============================================================
// Queue lifecycle and write helpers
// ============================================================

/// Flush pending GPU work. Called before CPU reads (mapAsync) and at queue release.
pub export fn doeNativeQueueFlush(q_raw: ?*anyopaque) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;
            _ = rt.flush_queue() catch |err| {
                deliverInternalError(q.dev, "doe_queue_submit: queue flush: {s}", .{@errorName(err)});
            };
        }
        return;
    }
    if (q.dev.backend == .d3d12) {
        if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
            _ = rt.flush_queue() catch |err| {
                deliverInternalError(q.dev, "doe_queue_submit: d3d12 queue flush: {s}", .{@errorName(err)});
            };
        }
        return;
    }
    flush_pending_work(q);
}

pub export fn doeNativeQueueFlushBreakdown(
    q_raw: ?*anyopaque,
    wait_completed_ns_out: *u64,
    deferred_copy_ns_out: *u64,
    deferred_resolve_ns_out: *u64,
) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse {
        wait_completed_ns_out.* = 0;
        deferred_copy_ns_out.* = 0;
        deferred_resolve_ns_out.* = 0;
        return;
    };
    if (q.dev.backend == .vulkan) {
        doeNativeQueueFlush(q_raw);
        wait_completed_ns_out.* = 0;
        deferred_copy_ns_out.* = 0;
        deferred_resolve_ns_out.* = 0;
        return;
    }
    if (q.dev.backend == .d3d12) {
        if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
            wait_completed_ns_out.* = rt.flush_queue() catch |err| blk: {
                deliverInternalError(q.dev, "doe_queue_submit: d3d12 flush breakdown: {s}", .{@errorName(err)});
                break :blk 0;
            };
        } else {
            wait_completed_ns_out.* = 0;
        }
        deferred_copy_ns_out.* = 0;
        deferred_resolve_ns_out.* = 0;
        return;
    }
    const breakdown = queue_flush_breakdown.flushPendingWorkTimed(q);
    wait_completed_ns_out.* = breakdown.waitCompletedNs;
    deferred_copy_ns_out.* = breakdown.deferredCopyNs;
    deferred_resolve_ns_out.* = breakdown.deferredResolveNs;
}

pub export fn doeNativeQueueWriteBuffer(q_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64, data: [*]const u8, size: usize) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    const size_u64: u64 = @intCast(size);
    const write_end = std.math.add(u64, offset, size_u64) catch {
        q.dev.error_scopes.deliver(error_scope.ERROR_TYPE_VALIDATION, "wgpuQueueWriteBuffer range exceeds buffer size");
        return;
    };
    if (write_end > buf.size) {
        q.dev.error_scopes.deliver(error_scope.ERROR_TYPE_VALIDATION, "wgpuQueueWriteBuffer range exceeds buffer size");
        return;
    }
    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            // Fast path: use cached mapped pointer to avoid HashMap lookup per write.
            if (buf.vk_mapped_ptr) |base| {
                const o: usize = @intCast(offset);
                @memcpy(base[o .. o + size], data[0..size]);
                return;
            }
            // Fallback: HashMap lookup for buffers created before cached-pointer support.
            if (buf.vk_id != 0) {
                const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;
                if (rt.compute_buffers.get(buf.vk_id)) |cb| {
                    if (cb.mapped) |ptr| {
                        const o: usize = @intCast(offset);
                        const d: [*]u8 = @ptrCast(ptr);
                        @memcpy(d[o .. o + size], data[0..size]);
                    }
                }
            }
        }
        return;
    }
    const contents = metal_bridge_buffer_contents(buf.mtl) orelse return;
    const dst = (contents + @as(usize, @intCast(offset)))[0..size];
    @memcpy(dst, data[0..size]);
}

fn copy_texture_for_browser_passthrough(
    q: *DoeQueue,
    source: *const abi_copy.WGPUTexelCopyTextureInfo,
    destination: *const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size: *const abi_copy.WGPUExtent3D,
) void {
    const src_texture = cast(DoeTexture, source.texture) orelse return;
    const dst_texture = cast(DoeTexture, destination.texture) orelse return;

    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            const rt = native_rt_helpers.device_vk_runtime(q.dev) orelse return;
            if (src_texture.vk_id == 0 or dst_texture.vk_id == 0) return;
            rt.texture_copy(.{
                .src_handle = src_texture.vk_id,
                .src_mip = source.mipLevel,
                .src_x = source.origin.x,
                .src_y = source.origin.y,
                .src_z = source.origin.z,
                .dst_handle = dst_texture.vk_id,
                .dst_mip = destination.mipLevel,
                .dst_x = destination.origin.x,
                .dst_y = destination.origin.y,
                .dst_z = destination.origin.z,
                .width = copy_size.width,
                .height = copy_size.height,
                .depth_or_layers = copy_size.depthOrArrayLayers,
            }) catch |err| {
                deliverInternalError(q.dev, "doe_queue_submit: texture copy: {s}", .{@errorName(err)});
            };
        }
        return;
    }

    const encoder = native_exports.doeNativeDeviceCreateCommandEncoder(toOpaque(q.dev), null) orelse return;
    defer native_exports.doeNativeCommandEncoderRelease(encoder);

    @import("doe_command_texture_native.zig").doeNativeCommandEncoderCopyTextureToTexture(
        encoder,
        source.texture,
        source.mipLevel,
        source.origin.z,
        source.origin.x,
        source.origin.y,
        source.origin.z,
        destination.texture,
        destination.mipLevel,
        destination.origin.z,
        destination.origin.x,
        destination.origin.y,
        destination.origin.z,
        copy_size.width,
        copy_size.height,
        copy_size.depthOrArrayLayers,
    );

    const command_buffer = native_exports.doeNativeCommandEncoderFinish(encoder, null) orelse return;
    defer native_exports.doeNativeCommandBufferRelease(command_buffer);
    var command_buffers = [1]?*anyopaque{command_buffer};
    doeNativeQueueSubmit(toOpaque(q), command_buffers.len, &command_buffers);
}

pub export fn doeNativeQueueCopyTextureForBrowser(
    queue_raw: ?*anyopaque,
    source_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    destination_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size_raw: ?*const abi_copy.WGPUExtent3D,
    options_raw: ?*const abi_copy.WGPUCopyTextureForBrowserOptions,
) callconv(.c) void {
    _ = options_raw;
    const queue = cast(DoeQueue, queue_raw) orelse return;
    const source = source_raw orelse return;
    const destination = destination_raw orelse return;
    const copy_size = copy_size_raw orelse return;
    copy_texture_for_browser_passthrough(queue, source, destination, copy_size);
}

pub export fn doeNativeQueueRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeQueue, raw)) |q| {
        if (q.ref_count > 1) {
            q.ref_count -= 1;
            return;
        }
        native_helpers.label_store.remove(raw);
        if (q.dev.queue == q) {
            q.dev.queue = null;
        }
        if (q.dev.backend == .vulkan) {
            if (comptime has_vulkan) {
                if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
                    _ = rt.flush_queue() catch |err| {
                        deliverInternalError(q.dev, "doe_queue_submit: flush on queue release: {s}", .{@errorName(err)});
                    };
                }
            }
            const dev = q.dev;
            alloc.destroy(q);
            native_exports.doeNativeDeviceRelease(toOpaque(dev));
            return;
        }
        if (q.dev.backend == .d3d12) {
            if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
                _ = rt.flush_queue() catch |err| {
                    deliverInternalError(q.dev, "doe_queue_submit: d3d12 flush on queue release: {s}", .{@errorName(err)});
                };
            }
            const dev = q.dev;
            alloc.destroy(q);
            native_exports.doeNativeDeviceRelease(toOpaque(dev));
            return;
        }
        // Queue teardown is outside the measured package hot path. Prefer the
        // direct command-buffer completion wait here so native drop-in
        // consumers do not depend on the shared-event fast path during final
        // release cleanup.
        flush_pending_work_dropin_sync(q);
        if (q.mtl_event) |ev| metal_bridge_release(ev);
        const dev = q.dev;
        alloc.destroy(q);
        native_exports.doeNativeDeviceRelease(toOpaque(dev));
    }
}

pub export fn doeNativeQueueAddRef(raw: ?*anyopaque) callconv(.c) void {
    const q = cast(DoeQueue, raw) orelse return;
    q.ref_count +|= 1;
}

fn flush_pending_work_dropin_sync(q: *DoeQueue) void {
    if (q.dev.backend == .vulkan) {
        if (comptime has_vulkan) {
            if (native_rt_helpers.device_vk_runtime(q.dev)) |rt| {
                _ = rt.flush_queue() catch |err| {
                    deliverInternalError(q.dev, "doe_queue_submit: dropin sync flush: {s}", .{@errorName(err)});
                };
            }
        }
        return;
    }
    if (q.dev.backend == .d3d12) {
        if (native_rt_helpers.device_d3d12_runtime(q.dev)) |rt| {
            _ = rt.flush_queue() catch |err| {
                deliverInternalError(q.dev, "doe_queue_submit: d3d12 dropin sync flush: {s}", .{@errorName(err)});
            };
        }
        return;
    }
    queue_flush_breakdown.flushPendingWork(q);
}

// ============================================================
// Deferred work-done — drained by doeNativeInstanceProcessEvents
// ============================================================
//
// Chromium calls queueOnSubmittedWorkDone and expects the callback to fire
// during a subsequent instanceProcessEvents tick, not synchronously inside
// the C proc call. Firing synchronously corrupts Chromium's state machine
// (e.g. importExternalTexture lifetime tracking).
//
// All backends are synchronous at the GPU level (Vulkan executes inline,
// Metal flushes before mapAsync), so work is always complete by the time
// processEvents is called. We just need to defer the callback delivery.

const MAX_GLOBAL_WORK_DONE: usize = 128;

const WorkDoneEntry = struct {
    cb: ?*const fn (abi_callback.WGPUQueueWorkDoneStatus, abi_core.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

var global_work_done_buf: [MAX_GLOBAL_WORK_DONE]WorkDoneEntry = undefined;
var global_work_done_count: usize = 0;

/// Fire all deferred work-done callbacks. Called by doeNativeInstanceProcessEvents.
pub fn drain_global_work_done() void {
    const n = global_work_done_count;
    global_work_done_count = 0;
    for (global_work_done_buf[0..n]) |entry| {
        if (entry.cb) |f| {
            f(.success, .{ .data = null, .length = 0 }, entry.userdata1, entry.userdata2);
        }
    }
}

/// For the native drop-in ABI, flush before invoking the callback so
/// standalone consumers observe real completion before they map/read back.
pub export fn doeNativeQueueOnSubmittedWorkDone(q_raw: ?*anyopaque, info: abi_callback.WGPUQueueWorkDoneCallbackInfo) callconv(.c) abi_core.WGPUFuture {
    if (cast(DoeQueue, q_raw)) |q| {
        flush_pending_work_dropin_sync(q);
    }
    if (info.callback) |cb| {
        cb(.success, .{ .data = null, .length = 0 }, info.userdata1, info.userdata2);
    }
    return .{ .id = 4 };
}

// ============================================================
// copyExternalImageToTexture — plane0 blit from external texture
// ============================================================
//
// Two paths: DoeTextureView-backed planes go through the standard
// texture-to-texture copy; native-imported planes (raw MTLTexture
// from IOSurface/CVPixelBuffer) are blitted directly via Metal.

const ext_texture_mod = @import("doe_external_texture_native.zig");
const DoeExternalTexture = ext_texture_mod.DoeExternalTexture;

fn copy_external_texture_to_dst(
    queue: *DoeQueue,
    ext: *const DoeExternalTexture,
    origin: abi_copy.WGPUOrigin3D,
    destination: *const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size: *const abi_copy.WGPUExtent3D,
) void {
    if (ext_texture_mod.resolvePlane0DoeTexture(ext)) |src_tex| {
        const source_copy = abi_copy.WGPUTexelCopyTextureInfo{
            .texture = native_helpers.toOpaque(src_tex),
            .mipLevel = 0,
            .origin = origin,
            .aspect = abi_texture.WGPUTextureAspect_All,
        };
        copy_texture_for_browser_passthrough(queue, &source_copy, destination, copy_size);
        return;
    }
    // Native-imported: blit the raw MTLTexture handle directly.
    const src_mtl = ext_texture_mod.resolvePlane0MtlHandle(ext) orelse return;
    const dst_texture = cast(DoeTexture, destination.texture) orelse return;
    const dst_mtl = dst_texture.mtl orelse return;
    if (queue.dev.backend != .metal) return;
    const cmd_buf = bridge.metal_bridge_create_command_buffer(queue.dev.mtl_queue);
    if (cmd_buf == null) return;
    const blit = bridge.metal_bridge_cmd_buf_blit_encoder(cmd_buf);
    if (blit == null) {
        bridge.metal_bridge_release(cmd_buf);
        return;
    }
    bridge.metal_bridge_blit_encoder_copy_texture_to_texture(
        blit,
        src_mtl,
        0,
        dst_mtl,
        destination.mipLevel,
        copy_size.width,
        copy_size.height,
        copy_size.depthOrArrayLayers,
    );
    bridge.metal_bridge_end_blit_encoding(blit);
    bridge.metal_bridge_command_buffer_commit(cmd_buf);
    bridge.metal_bridge_command_buffer_wait_completed(cmd_buf);
    bridge.metal_bridge_release(cmd_buf);
}

pub export fn doeNativeQueueCopyExternalImageToTexture(
    queue_raw: ?*anyopaque,
    source_raw: ?*const abi_copy.WGPUImageCopyExternalTexture,
    destination_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size_raw: ?*const abi_copy.WGPUExtent3D,
) callconv(.c) void {
    const source = source_raw orelse return;
    const destination = destination_raw orelse return;
    const copy_size = copy_size_raw orelse return;
    const ext = ext_texture_mod.cast(source.externalTexture) orelse return;
    if (ext.expired) return;
    const queue = cast(DoeQueue, queue_raw) orelse return;
    copy_external_texture_to_dst(queue, ext, source.origin, destination, copy_size);
}

pub export fn doeNativeQueueCopyExternalTextureForBrowser(
    queue_raw: ?*anyopaque,
    source_raw: ?*const abi_copy.WGPUImageCopyExternalTexture,
    destination_raw: ?*const abi_copy.WGPUTexelCopyTextureInfo,
    copy_size_raw: ?*const abi_copy.WGPUExtent3D,
    options_raw: ?*const abi_copy.WGPUCopyTextureForBrowserOptions,
) callconv(.c) void {
    _ = options_raw;
    const source = source_raw orelse return;
    const destination = destination_raw orelse return;
    const copy_size = copy_size_raw orelse return;
    const ext = ext_texture_mod.cast(source.externalTexture) orelse return;
    if (ext.expired) return;
    const queue = cast(DoeQueue, queue_raw) orelse return;
    copy_external_texture_to_dst(queue, ext, source.origin, destination, copy_size);
}
