const std = @import("std");
const contract = @import("../../contracts/texture_copy.zig");
const objects = @import("../support/doe_native_object_types.zig");
const helpers = @import("../support/doe_native_object_helpers.zig");
const recording = @import("doe_command_recording.zig");
const references = @import("doe_command_references.zig");
const abi = @import("../../core/abi/wgpu_core_base_types.zig");
const texture_abi = @import("../../core/abi/wgpu_texture_base_types.zig");

pub const Request = struct {
    buffer: ?*objects.DoeBuffer,
    texture: ?*objects.DoeTexture,
    copy: contract.Copy,
    alignment: contract.Alignment = .native,
};

pub fn record(enc: *objects.DoeCommandEncoder, direction: contract.Direction, request: Request) void {
    if (!recording.requireOpen(enc)) return;
    const region = validate(enc.dev, direction, request) catch |err| {
        recording.fail(enc, err);
        return;
    };
    const copy = request.copy;
    if (copy.width == 0 or copy.height == 0 or copy.depth_or_layers == 0) return;
    if (!recording.reserve(enc, 1, 2)) return;
    const buffer = request.buffer.?;
    const texture = request.texture.?;
    references.retainBufferAssumeCapacity(&enc.references, buffer);
    references.retainTextureAssumeCapacity(&enc.references, texture);
    const raw_buffer = if (enc.dev.backend == .vulkan) helpers.toOpaque(buffer) else buffer.mtl;
    const raw_texture = if (enc.dev.backend == .vulkan) helpers.toOpaque(texture) else texture.mtl;
    switch (direction) {
        .buffer_to_texture => enc.cmds.appendAssumeCapacity(.{ .copy_buffer_to_texture = .{
            .src_buffer = raw_buffer,
            .src_offset = copy.offset,
            .src_bytes_per_row = region.pitch,
            .src_rows_per_image = region.image_rows,
            .dst_texture = raw_texture,
            .dst_mip_level = copy.mip,
            .width = copy.width,
            .height = copy.height,
            .depth_or_array_layers = copy.depth_or_layers,
            .origin = copy.origin,
            .aspect = copy.aspect,
        } }),
        .texture_to_buffer => enc.cmds.appendAssumeCapacity(.{ .copy_texture_to_buffer = .{
            .dst_buffer = raw_buffer,
            .dst_offset = copy.offset,
            .dst_bytes_per_row = region.pitch,
            .dst_rows_per_image = region.image_rows,
            .src_texture = raw_texture,
            .src_mip_level = copy.mip,
            .width = copy.width,
            .height = copy.height,
            .depth_or_array_layers = copy.depth_or_layers,
            .origin = copy.origin,
            .aspect = copy.aspect,
        } }),
    }
}

fn validate(device: *objects.DoeDevice, direction: contract.Direction, request: Request) @import("../../contracts/command_recording.zig").Failure!contract.Region {
    const buffer = request.buffer orelse return error.InvalidArgument;
    const texture = request.texture orelse return error.InvalidArgument;
    if (buffer.error_object or texture.error_object) return error.InvalidArgument;
    if (buffer.dev != device or texture.device_ref != device) return error.TextureCopyDeviceMismatch;
    const buffer_usage = if (direction == .buffer_to_texture) abi.WGPUBufferUsage_CopySrc else abi.WGPUBufferUsage_CopyDst;
    const texture_usage = if (direction == .buffer_to_texture) texture_abi.WGPUTextureUsage_CopyDst else texture_abi.WGPUTextureUsage_CopySrc;
    if (buffer.usage & buffer_usage == 0 or texture.usage & texture_usage == 0) return error.TextureCopyUsageMissing;
    if (device.backend == .d3d12) return error.TextureCopyUnsupported;
    return contract.validate(buffer.size, .{
        .width = texture.width,
        .height = texture.height,
        .layers = texture.depth_or_array_layers,
        .mip_levels = texture.mip_level_count,
        .samples = texture.sample_count,
        .dimension = texture.dimension,
        .format = texture.format,
    }, request.copy, direction, request.alignment);
}

test "invalid texture copies fail before allocation and retain no partial ownership" {
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    var device: objects.DoeDevice = .{ .backend = .vulkan };
    var buffer: objects.DoeBuffer = .{ .dev = &device, .usage = abi.WGPUBufferUsage_CopySrc, .size = 16 };
    var texture: objects.DoeTexture = .{
        .device_ref = &device,
        .usage = texture_abi.WGPUTextureUsage_CopyDst,
        .width = 4,
        .height = 1,
        .format = texture_abi.WGPUTextureFormat_RGBA8Unorm,
    };
    var encoder: objects.DoeCommandEncoder = .{ .dev = &device, .allocator = failing.allocator() };
    var request = Request{ .buffer = &buffer, .texture = &texture, .copy = .{ .offset = 0, .bytes_per_row = 0, .rows_per_image = 0, .mip = 0, .width = 4, .height = 1, .depth_or_layers = 1, .origin = .{ 1, 0, 0 } } };
    record(&encoder, .buffer_to_texture, request);
    try std.testing.expectEqual(error.TextureCopyRange, encoder.state.failed);
    try std.testing.expectEqual(@as(usize, 0), failing.alloc_index);
    try std.testing.expectEqual(@as(u32, 1), buffer.ref_count);
    try std.testing.expectEqual(@as(u32, 1), texture.ref_count);
    encoder.state = .open;
    request.copy.origin[0] = 0;
    record(&encoder, .buffer_to_texture, request);
    try std.testing.expectEqual(error.OutOfMemory, encoder.state.failed);
    try std.testing.expectEqual(@as(usize, 0), encoder.references.items.len);
}
