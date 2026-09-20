const std = @import("std");
const model_gpu_types = @import("../../../contracts/model/model_texture_value_types.zig");
const model_texture_types = @import("../../../contracts/model/model_texture_types.zig");
const common_timing = @import("../../common/timing.zig");
const dc = @import("../d3d12_constants.zig");
const bridge = @import("../d3d12_bridge_decls.zig");

const copy_contract = @import("../../../contracts/texture_copy.zig");
const format_layout = @import("../../../contracts/texture_format_layout.zig");
const texture_formats = @import("../../../contracts/texture_format.zig");

const PLACEMENT_ALIGNMENT: usize = 512;
const MAX_TEXTURE_WRITE_BYTES: usize = 64 * 1024 * 1024;

pub const TextureEntry = struct {
    handle: u64,
    resource: ?*anyopaque,
    width: u32,
    height: u32,
    depth_or_array_layers: u32 = 1,
    format: u32,
    usage: u64 = 0,
    dimension: u32 = model_gpu_types.WGPUTextureDimension_2D,
    sample_count: u32 = 1,
    mip_levels: u32 = 1,
    state: c_int = dc.RESOURCE_STATE_COPY_DEST,
};

pub const TextureMap = std.AutoHashMapUnmanaged(u64, TextureEntry);

pub const WriteMetrics = struct { encode_ns: u64, submit_wait_ns: u64 };

const UploadLayout = struct {
    texture: copy_contract.Texture,
    width: u32,
    height: u32,
    depth: u32,
    source_offset: usize,
    source_pitch: usize,
    source_image_stride: usize,
    row_bytes: usize,
    rows: usize,
    pitch: u32,
    image_stride: usize,
    size: usize,

    fn init(cmd: model_texture_types.TextureWriteCommand) !UploadLayout {
        const res = cmd.texture;
        if (res.width == 0 or res.height == 0 or res.depth_or_array_layers == 0 or res.mip_level >= @bitSizeOf(u32)) return error.InvalidArgument;
        if (cmd.data.len == 0) return error.InvalidArgument;
        if (cmd.data.len > MAX_TEXTURE_WRITE_BYTES) return error.UnsupportedFeature;
        const dimension = if (res.dimension == model_gpu_types.WGPUTextureDimension_Undefined) model_gpu_types.WGPUTextureDimension_2D else res.dimension;
        if (dimension != model_gpu_types.WGPUTextureDimension_2D and dimension != model_gpu_types.WGPUTextureDimension_3D) return error.UnsupportedFeature;
        if (res.sample_count > 1 or res.depth_or_array_layers > std.math.maxInt(u16) or res.usage > std.math.maxInt(u32)) return error.UnsupportedFeature;
        const format = if (res.format == model_gpu_types.WGPUTextureFormat_Undefined) model_gpu_types.WGPUTextureFormat_RGBA8Unorm else res.format;
        _ = try dc.formats.wgpu_format_to_dxgi(format);
        // Depth/stencil uploads need plane-specific native footprints.
        if (texture_formats.isDepthStencilFormat(format)) return error.UnsupportedFeature;
        const is_3d = dimension == model_gpu_types.WGPUTextureDimension_3D;
        const max_dimension = @max(res.width, @max(res.height, if (is_3d) res.depth_or_array_layers else 1));
        if (res.mip_level > std.math.log2_int(u32, max_dimension)) return error.InvalidArgument;
        const shift: u5 = @intCast(res.mip_level);
        const width = @max(res.width >> shift, 1);
        const height = @max(res.height >> shift, 1);
        const depth = if (is_3d) @max(res.depth_or_array_layers >> shift, 1) else res.depth_or_array_layers;
        const texture = copy_contract.Texture{ .width = res.width, .height = res.height, .layers = res.depth_or_array_layers, .mip_levels = res.mip_level + 1, .samples = 1, .dimension = dimension, .format = format };
        const region = try copy_contract.validate(cmd.data.len, texture, .{ .offset = res.offset, .bytes_per_row = res.bytes_per_row, .rows_per_image = res.rows_per_image, .mip = res.mip_level, .width = width, .height = height, .depth_or_layers = depth, .aspect = res.aspect }, .buffer_to_texture, .native);
        const block = format_layout.copy_block_extent(format);
        const rows = try std.math.divCeil(usize, height, block[1]);
        const row_bytes = (try std.math.divCeil(usize, width, block[0])) * try format_layout.bytes_per_pixel(format);
        const pitch = std.mem.alignForward(usize, row_bytes, copy_contract.ROW_ALIGNMENT);
        const image_stride = if (is_3d) pitch * rows else std.mem.alignForward(usize, pitch * rows, PLACEMENT_ALIGNMENT);
        const size = std.math.mul(usize, image_stride, depth) catch return error.InvalidArgument;
        if (size > MAX_TEXTURE_WRITE_BYTES) return error.UnsupportedFeature;
        return .{ .texture = texture, .width = width, .height = height, .depth = depth, .source_offset = @intCast(res.offset), .source_pitch = region.pitch, .source_image_stride = @as(usize, region.pitch) * region.image_rows, .row_bytes = row_bytes, .rows = rows, .pitch = @intCast(pitch), .image_stride = image_stride, .size = size };
    }

    fn pack(self: UploadLayout, destination: []u8, data: []const u8) void {
        @memset(destination, 0);
        for (0..self.depth) |layer| {
            for (0..self.rows) |row| {
                const source = self.source_offset + layer * self.source_image_stride + row * self.source_pitch;
                const target = layer * self.image_stride + row * self.pitch;
                @memcpy(destination[target..][0..self.row_bytes], data[source..][0..self.row_bytes]);
            }
        }
    }
};

pub fn texture_write(device: ?*anyopaque, queue: ?*anyopaque, fence: ?*anyopaque, fence_value: *u64, texture_map: *TextureMap, allocator: std.mem.Allocator, cmd: model_texture_types.TextureWriteCommand) !WriteMetrics {
    if (device == null or queue == null or fence == null) return error.InvalidArgument;
    if (fence_value.* >= std.math.maxInt(u64) - 1) return error.InvalidState;
    const layout = try UploadLayout.init(cmd);
    const res = cmd.texture;
    const texture = layout.texture;
    const encode_start = common_timing.now_ns();
    var entry = texture_map.get(res.handle);
    if (entry) |existing| {
        if (existing.width != texture.width or existing.height != texture.height or existing.depth_or_array_layers != texture.layers or existing.format != texture.format or existing.dimension != texture.dimension or existing.sample_count != 1 or existing.mip_levels < texture.mip_levels or existing.usage != res.usage) return error.InvalidArgument;
    } else {
        try texture_map.ensureUnusedCapacity(allocator, 1);
        const resource = if (texture.dimension == model_gpu_types.WGPUTextureDimension_3D)
            bridge.c.d3d12_bridge_device_create_texture_3d(device, texture.width, texture.height, texture.layers, texture.mip_levels, texture.format, @intCast(res.usage))
        else
            bridge.c.d3d12_bridge_device_create_texture_2d_layered(device, texture.width, texture.height, texture.layers, texture.mip_levels, 1, texture.format, @intCast(res.usage));
        entry = .{ .handle = res.handle, .resource = resource orelse return error.InvalidState, .width = texture.width, .height = texture.height, .depth_or_array_layers = texture.layers, .format = texture.format, .usage = res.usage, .dimension = texture.dimension, .mip_levels = texture.mip_levels, .state = if (texture.dimension == model_gpu_types.WGPUTextureDimension_2D and res.usage & model_gpu_types.WGPUTextureUsage_RenderAttachment != 0) dc.RESOURCE_STATE_RENDER_TARGET else if (res.usage & model_gpu_types.WGPUTextureUsage_StorageBinding != 0) dc.RESOURCE_STATE_UNORDERED_ACCESS else dc.RESOURCE_STATE_COPY_DEST };
        texture_map.putAssumeCapacity(res.handle, entry.?);
    }
    const staging = bridge.c.d3d12_bridge_device_create_buffer(device, layout.size, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
    defer bridge.c.d3d12_bridge_release(staging);
    const mapped = bridge.c.d3d12_bridge_resource_map(staging) orelse return error.InvalidState;
    layout.pack(@as([*]u8, @ptrCast(mapped))[0..layout.size], cmd.data);
    bridge.c.d3d12_bridge_resource_unmap(staging);
    const cmd_alloc = bridge.c.d3d12_bridge_device_create_command_allocator(device) orelse return error.InvalidState;
    defer bridge.c.d3d12_bridge_release(cmd_alloc);
    const cmd_list = bridge.c.d3d12_bridge_device_create_command_list(device, cmd_alloc) orelse return error.InvalidState;
    defer bridge.c.d3d12_bridge_release(cmd_list);
    if (entry.?.state != dc.RESOURCE_STATE_COPY_DEST) bridge.c.d3d12_bridge_command_list_resource_barrier_transition(cmd_list, entry.?.resource, entry.?.state, dc.RESOURCE_STATE_COPY_DEST);
    if (texture.dimension == model_gpu_types.WGPUTextureDimension_3D) {
        bridge.c.d3d12_bridge_command_list_copy_texture_region_subresource(cmd_list, entry.?.resource, res.mip_level, staging, 0, layout.width, layout.height, layout.depth, layout.pitch, texture.format);
    } else {
        for (0..layout.depth) |layer| {
            const subresource = @as(u32, @intCast(layer)) * entry.?.mip_levels + res.mip_level;
            bridge.c.d3d12_bridge_command_list_copy_texture_region_subresource(cmd_list, entry.?.resource, subresource, staging, layout.image_stride * layer, layout.width, layout.height, 1, layout.pitch, texture.format);
        }
    }
    const final_state = if (res.usage & model_gpu_types.WGPUTextureUsage_StorageBinding != 0) dc.RESOURCE_STATE_UNORDERED_ACCESS else dc.RESOURCE_STATE_PIXEL_SHADER_RESOURCE | dc.RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
    bridge.c.d3d12_bridge_command_list_resource_barrier_transition(cmd_list, entry.?.resource, dc.RESOURCE_STATE_COPY_DEST, final_state);
    if (bridge.c.d3d12_bridge_command_list_close_checked(cmd_list) != 0) return error.InvalidState;
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
    const submit_start = common_timing.now_ns();
    bridge.c.d3d12_bridge_queue_execute_command_list(queue, cmd_list);
    fence_value.* += 1;
    // These draining adapters retain the temporary resources until completion or device loss.
    bridge.c.d3d12_bridge_queue_signal(queue, fence, fence_value.*);
    bridge.c.d3d12_bridge_fence_wait(fence, fence_value.*);
    if (bridge.c.d3d12_bridge_fence_completed_value(fence) == std.math.maxInt(u64)) return error.DeviceLost;
    texture_map.getPtr(res.handle).?.state = final_state;
    return .{ .encode_ns = encode_ns, .submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start) };
}

pub fn texture_query(
    texture_map: *const TextureMap,
    cmd: model_texture_types.TextureQueryCommand,
) !u64 {
    const encode_start = common_timing.now_ns();

    const entry = texture_map.get(cmd.handle) orelse return error.InvalidArgument;

    if (cmd.expected_width) |ew| {
        if (ew != entry.width) return error.InvalidArgument;
    }
    if (cmd.expected_height) |eh| {
        if (eh != entry.height) return error.InvalidArgument;
    }
    if (cmd.expected_depth_or_array_layers) |ed| {
        if (ed != entry.depth_or_array_layers) return error.InvalidArgument;
    }
    if (cmd.expected_format) |ef| {
        if (ef != entry.format) return error.InvalidArgument;
    }
    if (cmd.expected_sample_count) |esc| {
        if (esc != entry.sample_count) return error.InvalidArgument;
    }

    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}

pub fn texture_destroy(
    texture_map: *TextureMap,
    cmd: model_texture_types.TextureDestroyCommand,
) !u64 {
    const encode_start = common_timing.now_ns();

    if (texture_map.fetchRemove(cmd.handle)) |kv| {
        if (kv.value.resource) |res| {
            bridge.c.d3d12_bridge_release(res);
        }
    }

    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}

pub fn release_all(texture_map: *TextureMap, allocator: std.mem.Allocator) void {
    var it = texture_map.valueIterator();
    while (it.next()) |entry| {
        if (entry.resource) |res| bridge.c.d3d12_bridge_release(res);
    }
    texture_map.clearAndFree(allocator);
}

test "D3D12 texture upload packs compact array rows into aligned native footprints" {
    const data = [_]u8{ 1, 2, 3, 4, 5, 6, 7, 8 };
    const cmd = model_texture_types.TextureWriteCommand{ .texture = .{ .handle = 1, .width = 1, .height = 1, .depth_or_array_layers = 2, .format = model_gpu_types.WGPUTextureFormat_RGBA8Unorm }, .data = &data };
    const layout = try UploadLayout.init(cmd);
    try std.testing.expectEqual(@as(u32, 256), layout.pitch);
    try std.testing.expectEqual(@as(usize, 512), layout.image_stride);
    const packed_bytes = try std.testing.allocator.alloc(u8, layout.size);
    defer std.testing.allocator.free(packed_bytes);
    layout.pack(packed_bytes, &data);
    try std.testing.expectEqualSlices(u8, data[0..4], packed_bytes[0..4]);
    try std.testing.expectEqualSlices(u8, data[4..8], packed_bytes[512..516]);
    try std.testing.expectEqual(@as(u8, 0), packed_bytes[4]);
    var invalid = cmd;
    invalid.data = data[0..7];
    try std.testing.expectError(error.TextureCopyRange, UploadLayout.init(invalid));
    invalid = cmd;
    invalid.texture.mip_level = 32;
    try std.testing.expectError(error.InvalidArgument, UploadLayout.init(invalid));
}

test "D3D12 texture upload honors source offset, row padding and mip volume extent" {
    var bytes = [_]u8{0} ** 64;
    bytes[4] = 11;
    bytes[20] = 22;
    bytes[36] = 33;
    bytes[52] = 44;
    const layout = try UploadLayout.init(.{ .texture = .{ .handle = 1, .width = 4, .height = 4, .depth_or_array_layers = 4, .mip_level = 1, .dimension = model_gpu_types.WGPUTextureDimension_3D, .offset = 4, .bytes_per_row = 16, .rows_per_image = 2 }, .data = &bytes });
    try std.testing.expectEqual(@as(u32, 2), layout.width);
    try std.testing.expectEqual(@as(u32, 2), layout.depth);
    const output = try std.testing.allocator.alloc(u8, layout.size);
    defer std.testing.allocator.free(output);
    layout.pack(output, &bytes);
    try std.testing.expectEqual(@as(u8, 11), output[0]);
    try std.testing.expectEqual(@as(u8, 22), output[256]);
    try std.testing.expectEqual(@as(u8, 33), output[512]);
    try std.testing.expectEqual(@as(u8, 44), output[768]);
}
