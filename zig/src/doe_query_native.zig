// doe_query_native.zig — QuerySet (GPU timestamp query) support for Doe Metal backend.
//
// Uses Metal MTLCounterSampleBuffer for GPU timeline timestamps.
// Timestamps are sampled via blit encoder at command recording time and
// resolved from the counter sample buffer after GPU completion.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");

const MAGIC_QUERY_SET: u32 = 0xD0E1_0020;
const TIMESTAMP_BYTES: usize = @sizeOf(u64);

pub const DoeQuerySet = struct {
    pub const TYPE_MAGIC = MAGIC_QUERY_SET;
    magic: u32 = TYPE_MAGIC,
    count: u32 = 0,
    /// Opaque handle to MTLCounterSampleBuffer for GPU timestamp sampling.
    counter_sample_buffer: ?*anyopaque = null,
};

pub export fn doeNativeDeviceCreateQuerySet(
    dev_raw: ?*anyopaque,
    query_type: u32,
    count: u32,
) callconv(.c) ?*anyopaque {
    // Only timestamp queries are supported (WGPUQueryType_Timestamp = 2).
    if (query_type != 0x00000002) return null;
    if (count == 0) return null;

    const dev = native.cast(native.DoeDevice, dev_raw) orelse return null;
    const qs = native.make(DoeQuerySet) orelse return null;
    qs.* = .{ .count = count };

    qs.counter_sample_buffer = bridge.metal_bridge_create_counter_sample_buffer(dev.mtl_device, count);
    if (qs.counter_sample_buffer == null) {
        native.alloc.destroy(qs);
        return null;
    }

    return native.toOpaque(qs);
}

pub export fn doeNativeCommandEncoderWriteTimestamp(
    enc_raw: ?*anyopaque,
    qs_raw: ?*anyopaque,
    query_index: u32,
) callconv(.c) void {
    const enc = native.cast(native.DoeCommandEncoder, enc_raw) orelse return;
    const qs = native.cast(DoeQuerySet, qs_raw) orelse return;
    if (query_index >= qs.count) return;

    // Record a write_timestamp command; executed on the Metal command buffer at submit.
    enc.cmds.append(native.alloc, .{ .write_timestamp = .{
        .counter_buffer = qs.counter_sample_buffer,
        .query_index = query_index,
    } }) catch std.debug.panic("doe_query_native: OOM recording write_timestamp", .{});
}

pub export fn doeNativeCommandEncoderResolveQuerySet(
    enc_raw: ?*anyopaque,
    qs_raw: ?*anyopaque,
    first_query: u32,
    query_count: u32,
    dst_raw: ?*anyopaque,
    dst_offset: u64,
) callconv(.c) void {
    const enc = native.cast(native.DoeCommandEncoder, enc_raw) orelse return;
    const qs = native.cast(DoeQuerySet, qs_raw) orelse return;
    const dst = native.cast(native.DoeBuffer, dst_raw) orelse return;

    if (first_query + query_count > qs.count) return;

    const copy_bytes = @as(usize, query_count) * TIMESTAMP_BYTES;
    const d_off: usize = @intCast(dst_offset);
    if (d_off + copy_bytes > @as(usize, @intCast(dst.size))) return;

    // Record a resolve_query_set command; executed after GPU completion at submit.
    enc.cmds.append(native.alloc, .{ .resolve_query_set = .{
        .counter_buffer = qs.counter_sample_buffer,
        .first_query = first_query,
        .query_count = query_count,
        .dst_mtl = dst.mtl,
        .dst_offset = dst_offset,
    } }) catch std.debug.panic("doe_query_native: OOM recording resolve_query_set", .{});
}

pub export fn doeNativeQuerySetDestroy(qs_raw: ?*anyopaque) callconv(.c) void {
    const qs = native.cast(DoeQuerySet, qs_raw) orelse return;
    if (qs.counter_sample_buffer) |csb| bridge.metal_bridge_destroy_counter_sample_buffer(csb);
    native.alloc.destroy(qs);
}
