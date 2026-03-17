// doe_bundle_native.zig — C ABI exports for GPURenderBundle and GPURenderBundleEncoder.
// Sharded from doe_wgpu_native.zig to stay under the 777-line limit.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");
const bundle = @import("render_bundle.zig");

const alloc = native.alloc;
const cast = native.cast;
const toOpaque = native.toOpaque;
const DoeDevice = native.DoeDevice;
const DoeBuffer = native.DoeBuffer;
const DoeRenderPipeline = native.DoeRenderPipeline;
const DoeBindGroup = native.DoeBindGroup;
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
    bundle.bundle_destroy(b);
}

// ============================================================
// Render pass: executeBundles
// ============================================================

pub export fn doeNativeRenderPassExecuteBundles(
    pass_raw: ?*anyopaque,
    bundle_count: usize,
    bundles: [*]const ?*anyopaque,
) callconv(.c) void {
    const pass = cast(DoeRenderPass, pass_raw) orelse return;

    // Format and sample count for compatibility validation.
    // Pass sample count is always 1 on the Doe native Metal backend.
    const pass_fmt: types.WGPUTextureFormat = 0; // 0 = skip format check
    const pass_samples: u32 = 1;

    // Track the current pipeline PSO as bundle commands can update it.
    var cur_pso: ?*anyopaque = if (pass.pipeline) |p| p.mtl_pso else null;

    for (bundles[0..bundle_count]) |raw| {
        const b = bundle.cast_bundle(raw) orelse continue;
        bundle.check_compatibility(b, pass_fmt, pass_samples) catch |err| {
            std.debug.print("doe: executeBundles: compatibility check failed: {}\n", .{err});
            continue;
        };

        for (b.cmds) |cmd| {
            switch (cmd) {
                .set_pipeline => |p| {
                    cur_pso = p.mtl_pso;
                },
                .draw => |d| {
                    pass.enc.cmds.append(alloc, .{ .render_pass = .{
                        .pso = cur_pso,
                        .target = pass.target,
                        .draw_count = 1,
                        .vertex_count = d.vertex_count,
                        .instance_count = d.instance_count,
                    } }) catch std.debug.panic("doe: executeBundles OOM", .{});
                },
                // set_bind_group, set_vertex_buffer, set_index_buffer, draw_indexed,
                // draw_indirect, draw_indexed_indirect: require RecordedCmd union
                // extension. Recorded as no-ops until the union supports them.
                else => {},
            }
        }
    }
}
