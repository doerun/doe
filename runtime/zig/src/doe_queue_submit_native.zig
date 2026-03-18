// doe_queue_submit_native.zig — Queue submit loop, deferred-work helpers, and queue lifecycle.
// Sharded from doe_wgpu_native.zig to stay under the 777-line limit.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");

const alloc = native.alloc;
const cast = native.cast;
const toOpaque = native.toOpaque;

const DoeQueue = native.DoeQueue;
const DoeBuffer = native.DoeBuffer;
const DoeCommandBuffer = native.DoeCommandBuffer;
const MAX_DEFERRED_COPIES = native.MAX_DEFERRED_COPIES;
const MAX_DEFERRED_RESOLVES = native.MAX_DEFERRED_RESOLVES;
const VERTEX_BUFFER_SLOT_BASE = native.VERTEX_BUFFER_SLOT_BASE;
const MAX_FLAT_BIND = native.MAX_FLAT_BIND;

const emit_msl = @import("doe_wgsl/emit_msl_ir.zig");
// Metal buffer slot where _doe_sizes is bound — must match MSL_SIZES_SLOT in emit_msl_ir.zig.
const MSL_SIZES_SLOT: u32 = emit_msl.MSL_SIZES_SLOT;
// Size of the _doe_sizes buffer: 32 uint32 slots × 4 bytes.
const SIZES_BUF_BYTES: usize = (MSL_SIZES_SLOT + 1) * @sizeOf(u32);

const bridge = @import("backend/metal/metal_bridge_decls.zig");
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
const metal_bridge_render_encoder_end = bridge.metal_bridge_render_encoder_end;
const metal_bridge_render_encoder_set_vertex_buffer = bridge.metal_bridge_render_encoder_set_vertex_buffer;
const metal_bridge_sample_timestamp = bridge.metal_bridge_sample_timestamp;
const metal_bridge_resolve_timestamps = bridge.metal_bridge_resolve_timestamps;

const WGPU_MAP_ASYNC_STATUS_SUCCESS: u32 = 1;

// ============================================================
// Deferred-work helpers (called from queue submit and flush)
// ============================================================

/// Wait for any pending GPU work on the queue, then release the command buffer.
/// Also executes deferred CPU copies and counter resolves that depend on the completed GPU work.
pub fn flush_pending_work(q: *DoeQueue) void {
    if (q.pending_cmd) |cmd| {
        metal_bridge_command_buffer_wait_completed(cmd);
        metal_bridge_release(cmd);
        q.pending_cmd = null;
    }
    executeDeferredCopies(q);
    executeDeferredResolves(q);
}

fn executeDeferredCopies(q: *DoeQueue) void {
    for (q.deferred_copies[0..q.deferred_copy_count]) |dc| {
        @memcpy(dc.dst[0..dc.size], dc.src[0..dc.size]);
    }
    q.deferred_copy_count = 0;
}

fn executeDeferredResolves(q: *DoeQueue) void {
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
    // command buffer handles without re-executing them.
    if (q.dev.backend == .vulkan) {
        for (cmd_bufs[0..count]) |raw| {
            if (cast(DoeCommandBuffer, raw)) |buf| {
                buf.cmds.deinit(alloc);
                alloc.destroy(buf);
            }
        }
        return;
    }

    const queue = q.dev.mtl_queue;

    // Flush any prior pending GPU work before encoding new commands.
    flush_pending_work(q);

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
                        if (r.indexed) {
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
        metal_bridge_command_buffer_encode_signal_event(mtl_cmd, q.mtl_event, q.event_counter);
        metal_bridge_command_buffer_commit(mtl_cmd);
        q.pending_cmd = mtl_cmd;
    } else {
        metal_bridge_release(mtl_cmd);
        executeDeferredCopies(q);
    }
}

// ============================================================
// Queue lifecycle and write helpers
// ============================================================

/// Flush pending GPU work. Called before CPU reads (mapAsync) and at queue release.
pub export fn doeNativeQueueFlush(q_raw: ?*anyopaque) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    if (q.dev.backend == .vulkan) {
        const rt = native.device_vk_runtime(q.dev) orelse return;
        _ = rt.flush_queue() catch {};
        return;
    }
    flush_pending_work(q);
}

pub export fn doeNativeQueueWriteBuffer(q_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64, data: [*]const u8, size: usize) callconv(.c) void {
    const q = cast(DoeQueue, q_raw) orelse return;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    if (q.dev.backend == .vulkan) {
        if (buf.vk_id != 0) {
            const rt = native.device_vk_runtime(q.dev) orelse return;
            if (rt.compute_buffers.get(buf.vk_id)) |cb| {
                if (cb.mapped) |ptr| {
                    const o: usize = @intCast(offset);
                    const d: [*]u8 = @ptrCast(ptr);
                    @memcpy(d[o .. o + size], data[0..size]);
                }
            }
        }
        return;
    }
    const contents = metal_bridge_buffer_contents(buf.mtl) orelse return;
    const dst = (contents + @as(usize, @intCast(offset)))[0..size];
    @memcpy(dst, data[0..size]);
}

pub export fn doeNativeQueueRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeQueue, raw)) |q| {
        native.label_store.remove(raw);
        if (q.dev.backend == .vulkan) {
            if (native.device_vk_runtime(q.dev)) |rt| {
                _ = rt.flush_queue() catch {};
            }
            alloc.destroy(q);
            return;
        }
        flush_pending_work(q);
        if (q.mtl_event) |ev| metal_bridge_release(ev);
        alloc.destroy(q);
    }
}

/// Doe is synchronous — call back immediately on submitted work done.
pub export fn doeNativeQueueOnSubmittedWorkDone(q_raw: ?*anyopaque, info: types.WGPUQueueWorkDoneCallbackInfo) callconv(.c) types.WGPUFuture {
    _ = q_raw;
    info.callback(.success, .{ .data = null, .length = 0 }, info.userdata1, info.userdata2);
    return .{ .id = 4 };
}
