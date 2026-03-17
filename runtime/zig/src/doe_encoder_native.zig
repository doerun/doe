// doe_encoder_native.zig — Bind group layout, bind group, pipeline layout,
// command encoder, and command buffer exports for Doe native Metal backend.
// Sharded from doe_wgpu_native.zig to stay under the 777-line limit.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const native = @import("doe_wgpu_native.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const MAX_BIND = native.MAX_BIND;

const DoeDevice = native.DoeDevice;
const DoeBuffer = native.DoeBuffer;
const DoeBindGroup = native.DoeBindGroup;
const DoeCommandEncoder = native.DoeCommandEncoder;
const DoeCommandBuffer = native.DoeCommandBuffer;
const DoeComputePass = native.DoeComputePass;
const DoeTexture = native.DoeTexture;

// DoePipelineLayout is private in doe_wgpu_native; redeclare compatible layout here.
// Magic must match MAGIC_PIPE_LAYOUT = 0xD0E1_0009.
const MAGIC_PIPE_LAYOUT: u32 = 0xD0E1_0009;
const DoePipelineLayoutLocal = struct {
    const TYPE_MAGIC = MAGIC_PIPE_LAYOUT;
    magic: u32 = TYPE_MAGIC,
};

// ============================================================
// Command Encoder / Command Buffer

pub export fn doeNativeDeviceCreateCommandEncoder(dev_raw: ?*anyopaque, desc: ?*const types.WGPUCommandEncoderDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const enc = make(DoeCommandEncoder) orelse return null;
    enc.* = .{ .dev = dev };
    return toOpaque(enc);
}

pub export fn doeNativeCommandEncoderRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeCommandEncoder, raw)) |e| {
        e.cmds.deinit(alloc);
        alloc.destroy(e);
    }
}

pub export fn doeNativeCommandEncoderBeginComputePass(enc_raw: ?*anyopaque, desc: ?*const types.WGPUComputePassDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const pass = make(DoeComputePass) orelse return null;
    pass.* = .{ .enc = enc };
    return toOpaque(pass);
}

pub export fn doeNativeCopyBufferToBuffer(enc_raw: ?*anyopaque, src_raw: ?*anyopaque, src_off: u64, dst_raw: ?*anyopaque, dst_off: u64, size: u64) callconv(.c) void {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return;
    const src = cast(DoeBuffer, src_raw) orelse return;
    const dst = cast(DoeBuffer, dst_raw) orelse return;
    enc.cmds.append(alloc, .{ .copy_buf = .{
        .src = src.mtl,
        .src_off = src_off,
        .dst = dst.mtl,
        .dst_off = dst_off,
        .size = size,
    } }) catch std.debug.panic("doe_encoder_native: OOM recording copy command", .{});
}

pub export fn doeNativeCommandEncoderCopyBufferToTexture(
    enc_raw: ?*anyopaque,
    src_buffer_raw: ?*anyopaque,
    src_offset: u64,
    src_bytes_per_row: u32,
    src_rows_per_image: u32,
    dst_texture_raw: ?*anyopaque,
    dst_mip_level: u32,
    width: u32,
    height: u32,
    depth_or_array_layers: u32,
) callconv(.c) void {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return;
    const src_buffer = cast(DoeBuffer, src_buffer_raw) orelse return;
    const dst_texture = cast(DoeTexture, dst_texture_raw) orelse return;
    enc.cmds.append(alloc, .{ .copy_buffer_to_texture = .{
        .src_buffer = src_buffer.mtl,
        .src_offset = src_offset,
        .src_bytes_per_row = src_bytes_per_row,
        .src_rows_per_image = src_rows_per_image,
        .dst_texture = dst_texture.mtl,
        .dst_mip_level = dst_mip_level,
        .width = width,
        .height = height,
        .depth_or_array_layers = depth_or_array_layers,
    } }) catch std.debug.panic("doe_encoder_native: OOM recording buffer-to-texture copy command", .{});
}

pub export fn doeNativeCommandEncoderCopyTextureToBuffer(
    enc_raw: ?*anyopaque,
    src_texture_raw: ?*anyopaque,
    src_mip_level: u32,
    dst_buffer_raw: ?*anyopaque,
    dst_offset: u64,
    dst_bytes_per_row: u32,
    dst_rows_per_image: u32,
    width: u32,
    height: u32,
    depth_or_array_layers: u32,
) callconv(.c) void {
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return;
    const src_texture = cast(DoeTexture, src_texture_raw) orelse return;
    const dst_buffer = cast(DoeBuffer, dst_buffer_raw) orelse return;
    enc.cmds.append(alloc, .{ .copy_texture_to_buffer = .{
        .src_texture = src_texture.mtl,
        .src_mip_level = src_mip_level,
        .dst_buffer = dst_buffer.mtl,
        .dst_offset = dst_offset,
        .dst_bytes_per_row = dst_bytes_per_row,
        .dst_rows_per_image = dst_rows_per_image,
        .width = width,
        .height = height,
        .depth_or_array_layers = depth_or_array_layers,
    } }) catch std.debug.panic("doe_encoder_native: OOM recording texture copy command", .{});
}

pub export fn doeNativeCommandEncoderFinish(enc_raw: ?*anyopaque, desc: ?*const types.WGPUCommandBufferDescriptor) callconv(.c) ?*anyopaque {
    _ = desc;
    const enc = cast(DoeCommandEncoder, enc_raw) orelse return null;
    const cb = make(DoeCommandBuffer) orelse return null;
    cb.* = .{ .dev = enc.dev, .cmds = enc.cmds };
    enc.cmds = .{}; // Transfer ownership.
    return toOpaque(cb);
}

pub export fn doeNativeCommandBufferRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeCommandBuffer, raw)) |cb| {
        cb.cmds.deinit(alloc);
        alloc.destroy(cb);
    }
}
