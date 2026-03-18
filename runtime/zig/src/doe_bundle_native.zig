// doe_bundle_native.zig — C ABI exports for GPURenderBundle and GPURenderBundleEncoder.
// Sharded from doe_wgpu_native.zig to stay under the 777-line limit.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");
const bundle = @import("render_bundle.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const DoeDevice = native.DoeDevice;
const DoeBuffer = native.DoeBuffer;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeBindGroup = native.DoeBindGroup;
const DoeBindGroupLayout = native.DoeBindGroupLayout;
const DoeRenderPass = native.DoeRenderPass;

const RenderBundleEncoderDescriptor = @import("full/render/wgpu_render_types.zig").RenderBundleEncoderDescriptor;
const RenderBundleDescriptor = @import("full/render/wgpu_render_types.zig").RenderBundleDescriptor;

// ============================================================
// Device: createRenderBundleEncoder
// ============================================================

pub export fn doeNativeDeviceCreateRenderBundleEncoder(
    dev_raw: ?*anyopaque,
    desc: ?*const RenderBundleEncoderDescriptor,
) callconv(.c) ?*anyopaque {
    _ = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;

    const color_fmt: types.WGPUTextureFormat = if (d.colorFormatCount > 0)
        d.colorFormats[0]
    else
        0;

    bundle.set_allocator(alloc);
    const enc = bundle.make_bundle_encoder(
        color_fmt,
        d.depthStencilFormat,
        if (d.sampleCount == 0) 1 else d.sampleCount,
        d.depthReadOnly != 0,
        d.stencilReadOnly != 0,
    ) orelse return null;
    return @ptrCast(enc);
}

pub export fn doeNativeRenderBundleEncoderRelease(raw: ?*anyopaque) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(raw) orelse return;
    native.label_store.remove(raw);
    const a = enc.allocator;
    enc.cmds.deinit(a);
    a.destroy(enc);
}

// ============================================================
// Bundle encoder: record commands
// ============================================================

pub export fn doeNativeRenderBundleEncoderSetPipeline(
    enc_raw: ?*anyopaque,
    pip_raw: ?*anyopaque,
) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    const pip = cast(DoeRenderPipeline, pip_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .set_pipeline = .{ .mtl_pso = pip.mtl_pso } });
}

pub export fn doeNativeRenderBundleEncoderSetBindGroup(
    enc_raw: ?*anyopaque,
    group_index: u32,
    bg_raw: ?*anyopaque,
    dynamic_offset_count: usize,
    dynamic_offsets: ?[*]const u32,
) callconv(.c) void {
    _ = dynamic_offset_count;
    _ = dynamic_offsets;
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    const bg = cast(DoeBindGroup, bg_raw) orelse return;

    var bg_entry = bundle.BundleBindGroup{
        .entries = undefined,
        .count = bg.count,
    };
    const copy_count = @min(@as(usize, bg.count), bundle.MAX_BINDINGS_PER_GROUP);
    for (0..copy_count) |i| {
        bg_entry.entries[i] = .{
            .mtl_buffer = bg.buffers[i],
            .offset = bg.offsets[i],
        };
    }
    bundle.bundle_encoder_push(enc, .{ .set_bind_group = .{
        .group = group_index,
        .bg = bg_entry,
    } });
}

pub export fn doeNativeRenderBundleEncoderSetVertexBuffer(
    enc_raw: ?*anyopaque,
    slot: u32,
    buf_raw: ?*anyopaque,
    offset: u64,
    size: u64,
) callconv(.c) void {
    _ = size;
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .set_vertex_buffer = .{
        .slot = slot,
        .mtl_buffer = buf.mtl,
        .offset = offset,
    } });
}

pub export fn doeNativeRenderBundleEncoderSetIndexBuffer(
    enc_raw: ?*anyopaque,
    buf_raw: ?*anyopaque,
    format: u32,
    offset: u64,
    size: u64,
) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    const buf = cast(DoeBuffer, buf_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .set_index_buffer = .{
        .mtl_buffer = buf.mtl,
        .format = format,
        .offset = offset,
        .size = size,
    } });
}

pub export fn doeNativeRenderBundleEncoderDraw(
    enc_raw: ?*anyopaque,
    vertex_count: u32,
    instance_count: u32,
    first_vertex: u32,
    first_instance: u32,
) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .draw = .{
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = first_vertex,
        .first_instance = first_instance,
    } });
}

pub export fn doeNativeRenderBundleEncoderDrawIndexed(
    enc_raw: ?*anyopaque,
    index_count: u32,
    instance_count: u32,
    first_index: u32,
    base_vertex: i32,
    first_instance: u32,
) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .draw_indexed = .{
        .index_count = index_count,
        .instance_count = instance_count,
        .first_index = first_index,
        .base_vertex = base_vertex,
        .first_instance = first_instance,
    } });
}

pub export fn doeNativeRenderBundleEncoderDrawIndirect(
    enc_raw: ?*anyopaque,
    indirect_buf_raw: ?*anyopaque,
    indirect_offset: u64,
) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    const ibuf = cast(DoeBuffer, indirect_buf_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .draw_indirect = .{
        .indirect_buffer = ibuf.mtl,
        .indirect_offset = indirect_offset,
    } });
}

pub export fn doeNativeRenderBundleEncoderDrawIndexedIndirect(
    enc_raw: ?*anyopaque,
    indirect_buf_raw: ?*anyopaque,
    indirect_offset: u64,
) callconv(.c) void {
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return;
    const ibuf = cast(DoeBuffer, indirect_buf_raw) orelse return;
    bundle.bundle_encoder_push(enc, .{ .draw_indexed_indirect = .{
        .indirect_buffer = ibuf.mtl,
        .indirect_offset = indirect_offset,
    } });
}

// ============================================================
// Bundle encoder: finish → GPURenderBundle
// ============================================================

pub export fn doeNativeRenderBundleEncoderFinish(
    enc_raw: ?*anyopaque,
    desc: ?*const RenderBundleDescriptor,
) callconv(.c) ?*anyopaque {
    _ = desc;
    const enc = bundle.cast_bundle_encoder(enc_raw) orelse return null;
    bundle.set_allocator(alloc);
    const b = bundle.bundle_encoder_finish(enc) orelse return null;
    return @ptrCast(b);
}

pub export fn doeNativeRenderBundleRelease(raw: ?*anyopaque) callconv(.c) void {
    const b = bundle.cast_bundle(raw) orelse return;
    native.label_store.remove(raw);
    bundle.bundle_destroy(b);
}

// ============================================================
// Render pipeline: getBindGroupLayout
// Returns a minimal DoeBindGroupLayout seeded with the group index.
// Full reflection requires shader metadata not yet stored on the render pipeline.
// ============================================================

pub export fn doeNativeRenderPipelineGetBindGroupLayout(
    pip_raw: ?*anyopaque,
    group_index: u32,
) callconv(.c) ?*anyopaque {
    _ = cast(DoeRenderPipeline, pip_raw) orelse return null;
    const bgl = make(DoeBindGroupLayout) orelse return null;
    bgl.* = .{ .entry_count = group_index };
    return toOpaque(bgl);
}

// ============================================================
// Debug markers — no-ops in headless runtime; symbols required for API surface completeness.
// ============================================================

pub export fn doeNativeRenderBundleEncoderInsertDebugMarker(
    _: ?*anyopaque,
    _: ?[*]const u8,
    _: usize,
) callconv(.c) void {}

pub export fn doeNativeRenderBundleEncoderPushDebugGroup(
    _: ?*anyopaque,
    _: ?[*]const u8,
    _: usize,
) callconv(.c) void {}

pub export fn doeNativeRenderBundleEncoderPopDebugGroup(
    _: ?*anyopaque,
) callconv(.c) void {}

// ============================================================
// Render pass: executeBundles
// ============================================================

const MAX_BIND = native.MAX_BIND;
const MAX_FLAT_BIND = native.MAX_FLAT_BIND;
const MAX_VERTEX_BUFFERS = native.MAX_VERTEX_BUFFERS;

// Accumulated render state for bundle replay. Tracks pipeline, bind groups,
// vertex buffers, and index buffer across commands within a bundle so that
// each draw emits a fully populated RecordedCmd.render_pass.
const BundleReplayState = struct {
    pso: ?*anyopaque,
    bind_buffers: [MAX_FLAT_BIND]?*anyopaque,
    bind_buffer_offsets: [MAX_FLAT_BIND]u64,
    vertex_buffers: [MAX_VERTEX_BUFFERS]?*anyopaque,
    vertex_buffer_offsets: [MAX_VERTEX_BUFFERS]u64,
    index_buffer: ?*anyopaque,
    index_offset: u64,
    index_format: u32,

    fn init(pass: *const DoeRenderPass) BundleReplayState {
        return .{
            .pso = if (pass.pipeline) |p| p.mtl_pso else null,
            .bind_buffers = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
            .bind_buffer_offsets = [_]u64{0} ** MAX_FLAT_BIND,
            .vertex_buffers = [_]?*anyopaque{null} ** MAX_VERTEX_BUFFERS,
            .vertex_buffer_offsets = [_]u64{0} ** MAX_VERTEX_BUFFERS,
            .index_buffer = null,
            .index_offset = 0,
            .index_format = 0x2, // default uint32
        };
    }
};

// Build a render_pass RecordedCmd with the accumulated bundle state.
fn bundleRenderPassCmd(
    state: *const BundleReplayState,
    pass: *const DoeRenderPass,
) native.RecordedCmd {
    return .{ .render_pass = .{
        .pso = state.pso,
        .depth_state = null,
        .target = pass.target,
        .depth_target = pass.depth_target,
        .topology = 0,
        .front_face = 0,
        .cull_mode = 0,
        .draw_count = 1,
        .vertex_count = 0,
        .instance_count = 1,
        .first_vertex = 0,
        .first_instance = 0,
        .bind_buffers = state.bind_buffers,
        .bind_buffer_offsets = state.bind_buffer_offsets,
        .vertex_buffers = state.vertex_buffers,
        .vertex_buffer_offsets = state.vertex_buffer_offsets,
        .clear_r = pass.clear_r,
        .clear_g = pass.clear_g,
        .clear_b = pass.clear_b,
        .clear_a = pass.clear_a,
    } };
}

fn require_index_buffer_for_bundle_draw(state: *const BundleReplayState, kind: []const u8) bool {
    if (state.index_buffer != null) return true;
    std.debug.print("doe: executeBundles: {s} missing index buffer; skipping\n", .{kind});
    return false;
}

pub export fn doeNativeRenderPassExecuteBundles(
    pass_raw: ?*anyopaque,
    bundle_count: usize,
    bundles: [*]const ?*anyopaque,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;

    // The pass format is not exposed through DoeRenderPass here, so we only
    // validate the bundle sample count and treat format compatibility as
    // caller-managed by the render pass path.
    const pass_samples: u32 = 1;

    for (bundles[0..bundle_count]) |raw| {
        const b = bundle.cast_bundle(raw) orelse continue;
        if (b.sample_count != 0 and b.sample_count != pass_samples) {
            std.debug.print("doe: executeBundles: sample count mismatch: bundle={} pass={}\n", .{
                b.sample_count,
                pass_samples,
            });
            continue;
        }

        // Each bundle starts with a fresh replay state seeded from the pass.
        var state = BundleReplayState.init(pass);

        for (b.cmds) |cmd| {
            switch (cmd) {
                .set_pipeline => |p| {
                    state.pso = p.mtl_pso;
                },
                .set_bind_group => |bg_cmd| {
                    const base = @as(usize, bg_cmd.group) * MAX_BIND;
                    const count = @min(@as(usize, bg_cmd.bg.count), bundle.MAX_BINDINGS_PER_GROUP);
                    for (0..count) |i| {
                        if (base + i < MAX_FLAT_BIND) {
                            state.bind_buffers[base + i] = bg_cmd.bg.entries[i].mtl_buffer;
                            state.bind_buffer_offsets[base + i] = bg_cmd.bg.entries[i].offset;
                        }
                    }
                },
                .set_vertex_buffer => |vb| {
                    const slot = @as(usize, @min(vb.slot, MAX_VERTEX_BUFFERS - 1));
                    state.vertex_buffers[slot] = vb.mtl_buffer;
                    state.vertex_buffer_offsets[slot] = vb.offset;
                },
                .set_index_buffer => |ib| {
                    state.index_buffer = ib.mtl_buffer;
                    state.index_offset = ib.offset;
                    state.index_format = ib.format;
                },
                .draw => |d| {
                    var rc = bundleRenderPassCmd(&state, pass);
                    rc.render_pass.vertex_count = d.vertex_count;
                    rc.render_pass.instance_count = d.instance_count;
                    rc.render_pass.first_vertex = d.first_vertex;
                    rc.render_pass.first_instance = d.first_instance;
                    pass.enc.cmds.append(alloc, rc) catch
                        std.debug.panic("doe: executeBundles OOM", .{});
                },
                .draw_indexed => |d| {
                    if (!require_index_buffer_for_bundle_draw(&state, "draw_indexed")) {
                        continue;
                    }
                    var rc = bundleRenderPassCmd(&state, pass);
                    rc.render_pass.indexed = true;
                    rc.render_pass.index_buffer = state.index_buffer;
                    rc.render_pass.index_format = state.index_format;
                    rc.render_pass.index_count = d.index_count;
                    rc.render_pass.instance_count = d.instance_count;
                    rc.render_pass.base_vertex = d.base_vertex;
                    rc.render_pass.first_instance = d.first_instance;
                    // first_index converts to a byte offset into the index buffer.
                    const bytes_per_index: u64 = if (state.index_format == 0x1) 2 else 4;
                    rc.render_pass.index_offset = state.index_offset + @as(u64, d.first_index) * bytes_per_index;
                    pass.enc.cmds.append(alloc, rc) catch
                        std.debug.panic("doe: executeBundles OOM", .{});
                },
                .draw_indirect => |d| {
                    var rc = bundleRenderPassCmd(&state, pass);
                    rc.render_pass.indirect = true;
                    rc.render_pass.indirect_buffer = d.indirect_buffer;
                    rc.render_pass.indirect_offset = d.indirect_offset;
                    pass.enc.cmds.append(alloc, rc) catch
                        std.debug.panic("doe: executeBundles OOM", .{});
                },
                .draw_indexed_indirect => |d| {
                    if (!require_index_buffer_for_bundle_draw(&state, "draw_indexed_indirect")) {
                        continue;
                    }
                    var rc = bundleRenderPassCmd(&state, pass);
                    rc.render_pass.indexed = true;
                    rc.render_pass.indirect = true;
                    rc.render_pass.index_buffer = state.index_buffer;
                    rc.render_pass.index_offset = state.index_offset;
                    rc.render_pass.index_format = state.index_format;
                    rc.render_pass.indirect_buffer = d.indirect_buffer;
                    rc.render_pass.indirect_offset = d.indirect_offset;
                    pass.enc.cmds.append(alloc, rc) catch
                        std.debug.panic("doe: executeBundles OOM", .{});
                },
            }
        }
    }
}
