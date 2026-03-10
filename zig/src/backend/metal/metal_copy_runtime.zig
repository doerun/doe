const std = @import("std");
const common_timing = @import("../common/timing.zig");
const model = @import("../../model.zig");
const webgpu = @import("../../webgpu_ffi.zig");

extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_device_new_buffer_shared(device: ?*anyopaque, length: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_texture(device: ?*anyopaque, width: u32, height: u32, mip_levels: u32, pixel_format: u32, usage: u32) callconv(.c) ?*anyopaque;
extern fn metal_bridge_create_command_buffer(queue: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_cmd_buf_blit_encoder(cmd_buf: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn metal_bridge_end_blit_encoding(encoder: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_render_encoder_end(encoder: ?*anyopaque) callconv(.c) void;
extern fn metal_bridge_blit_encoder_copy_region(encoder: ?*anyopaque, src: ?*anyopaque, src_offset: u64, dst: ?*anyopaque, dst_offset: u64, size: u64) callconv(.c) void;
extern fn metal_bridge_blit_encoder_copy_buffer_to_texture(encoder: ?*anyopaque, src: ?*anyopaque, src_offset: u64, src_bytes_per_row: u32, src_rows_per_image: u32, dst_texture: ?*anyopaque, dst_mip_level: u32, width: u32, height: u32, depth_or_array_layers: u32) callconv(.c) void;
extern fn metal_bridge_blit_encoder_copy_texture_to_buffer(encoder: ?*anyopaque, src_texture: ?*anyopaque, src_mip_level: u32, dst: ?*anyopaque, dst_offset: u64, dst_bytes_per_row: u32, dst_rows_per_image: u32, width: u32, height: u32, depth_or_array_layers: u32) callconv(.c) void;
extern fn metal_bridge_blit_encoder_copy_texture_to_texture(encoder: ?*anyopaque, src_texture: ?*anyopaque, src_mip_level: u32, dst_texture: ?*anyopaque, dst_mip_level: u32, width: u32, height: u32, depth_or_array_layers: u32) callconv(.c) void;

pub const CopyMetrics = struct {
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
};

pub fn execute_copy(self: anytype, cmd: model.CopyCommand, queue_sync_mode: webgpu.QueueSyncMode) !CopyMetrics {
    const setup_start = common_timing.now_ns();
    const src_buffer = if (cmd.direction == .buffer_to_buffer or cmd.direction == .buffer_to_texture)
        try ensure_buffer(self, cmd.src.handle, required_buffer_size(cmd.bytes, cmd.src.offset))
    else
        null;
    const dst_buffer = if (cmd.direction == .buffer_to_buffer or cmd.direction == .texture_to_buffer)
        try ensure_buffer(self, cmd.dst.handle, required_buffer_size(cmd.bytes, cmd.dst.offset))
    else
        null;
    const src_texture = if (cmd.direction == .texture_to_buffer or cmd.direction == .texture_to_texture)
        try ensure_texture(self, cmd.src, model.WGPUTextureUsage_CopySrc)
    else
        null;
    const dst_texture = if (cmd.direction == .buffer_to_texture or cmd.direction == .texture_to_texture)
        try ensure_texture(self, cmd.dst, model.WGPUTextureUsage_CopyDst)
    else
        null;
    const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

    try ensure_blit_encoder(self);

    const encode_start = common_timing.now_ns();
    switch (cmd.direction) {
        .buffer_to_buffer => metal_bridge_blit_encoder_copy_region(
            self.streaming_blit_encoder,
            src_buffer,
            cmd.src.offset,
            dst_buffer,
            cmd.dst.offset,
            cmd.bytes,
        ),
        .buffer_to_texture => metal_bridge_blit_encoder_copy_buffer_to_texture(
            self.streaming_blit_encoder,
            src_buffer,
            cmd.src.offset,
            normalize_copy_pitch(cmd.src.bytes_per_row, cmd.dst.width, 4),
            normalize_copy_rows(cmd.src.rows_per_image, cmd.dst.height),
            dst_texture,
            cmd.dst.mip_level,
            cmd.dst.width,
            cmd.dst.height,
            normalize_copy_depth(cmd.dst.depth_or_array_layers),
        ),
        .texture_to_buffer => metal_bridge_blit_encoder_copy_texture_to_buffer(
            self.streaming_blit_encoder,
            src_texture,
            cmd.src.mip_level,
            dst_buffer,
            cmd.dst.offset,
            normalize_copy_pitch(cmd.dst.bytes_per_row, cmd.src.width, 4),
            normalize_copy_rows(cmd.dst.rows_per_image, cmd.src.height),
            cmd.src.width,
            cmd.src.height,
            normalize_copy_depth(cmd.src.depth_or_array_layers),
        ),
        .texture_to_texture => metal_bridge_blit_encoder_copy_texture_to_texture(
            self.streaming_blit_encoder,
            src_texture,
            cmd.src.mip_level,
            dst_texture,
            cmd.dst.mip_level,
            cmd.src.width,
            cmd.src.height,
            normalize_copy_depth(cmd.src.depth_or_array_layers),
        ),
    }
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

    self.has_deferred_submissions = true;
    const submit_wait_ns = if (queue_sync_mode == .deferred) 0 else try self.flush_queue();
    return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns };
}

fn ensure_buffer(self: anytype, handle: u64, size: u64) !?*anyopaque {
    if (self.compute_buffers.get(handle)) |buf| return buf;
    const buffer = metal_bridge_device_new_buffer_shared(self.device, @intCast(size)) orelse return error.InvalidState;
    try self.compute_buffers.put(self.allocator, handle, buffer);
    return buffer;
}

fn ensure_texture(self: anytype, resource: model.CopyTextureResource, required_usage: model.WGPUFlags) !?*anyopaque {
    if (self.textures.get(resource.handle)) |tex| return tex;
    const usage = if (resource.usage != 0) resource.usage else required_usage;
    const mip_levels: u32 = if (resource.mip_level > 0) resource.mip_level + 1 else 1;
    const texture = metal_bridge_device_new_texture(
        self.device,
        max_dim(resource.width),
        max_dim(resource.height),
        mip_levels,
        resource.format,
        @intCast(usage),
    ) orelse return error.InvalidState;
    try self.textures.put(self.allocator, resource.handle, texture);
    return texture;
}

fn ensure_blit_encoder(self: anytype) !void {
    if (self.streaming_render_encoder) |enc| {
        metal_bridge_render_encoder_end(enc);
        metal_bridge_release(enc);
        self.streaming_render_encoder = null;
    }
    if (self.streaming_blit_encoder != null) return;
    if (self.streaming_cmd_buf == null) {
        self.streaming_cmd_buf = metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
    }
    self.streaming_blit_encoder = metal_bridge_cmd_buf_blit_encoder(self.streaming_cmd_buf) orelse return error.InvalidState;
}

fn required_buffer_size(bytes: usize, offset: u64) u64 {
    return @as(u64, @intCast(bytes)) + offset;
}

fn max_dim(value: u32) u32 {
    return if (value == 0) 1 else value;
}

fn normalize_copy_pitch(value: u32, width: u32, bytes_per_pixel: u32) u32 {
    return if (value == 0) width * bytes_per_pixel else value;
}

fn normalize_copy_rows(value: u32, height: u32) u32 {
    return if (value == 0) height else value;
}

fn normalize_copy_depth(value: u32) u32 {
    return if (value == 0) 1 else value;
}
