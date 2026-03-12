const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");
const common_errors = @import("../../common/errors.zig");

const HEAP_TYPE_UPLOAD: c_int = 2;
const RESOURCE_STATE_COPY_DEST: c_int = 0x00000800;
const RESOURCE_STATE_GENERIC_READ: c_int = 0x00000001 | 0x00000002 | 0x00000040 | 0x00000080 | 0x00000200 | 0x00000800;
const RESOURCE_STATE_PIXEL_SHADER_RESOURCE: c_int = 0x00000080;
const MAX_TEXTURE_WRITE_BYTES: usize = 64 * 1024 * 1024;

extern fn d3d12_bridge_device_create_texture_2d(device: ?*anyopaque, width: u32, height: u32, mip_levels: u32, format: u32, usage_flags: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_copy_texture_region(cmd_list: ?*anyopaque, dst: ?*anyopaque, src: ?*anyopaque, src_offset: u64, width: u32, height: u32, bytes_per_row: u32, format: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_resource_barrier_transition(cmd_list: ?*anyopaque, resource: ?*anyopaque, state_before: c_int, state_after: c_int) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

pub const TextureEntry = struct {
    handle: u64,
    resource: ?*anyopaque,
    width: u32,
    height: u32,
    depth_or_array_layers: u32 = 1,
    format: u32,
    usage: u64 = 0,
    dimension: u32 = model.WGPUTextureDimension_2D,
    sample_count: u32 = 1,
    mip_levels: u32 = 1,
};

pub const TextureMap = std.AutoHashMapUnmanaged(u64, TextureEntry);

pub fn texture_write(
    device: ?*anyopaque,
    queue: ?*anyopaque,
    texture_map: *TextureMap,
    allocator: std.mem.Allocator,
    cmd: model.TextureWriteCommand,
) !u64 {
    const tex_res = &cmd.texture;
    const data = cmd.data;
    if (data.len == 0) return error.InvalidArgument;
    if (data.len > MAX_TEXTURE_WRITE_BYTES) return error.UnsupportedFeature;

    const width = if (tex_res.width > 0) tex_res.width else 1;
    const height = if (tex_res.height > 0) tex_res.height else 1;
    const format: u32 = if (tex_res.format != model.WGPUTextureFormat_Undefined) tex_res.format else model.WGPUTextureFormat_RGBA8Unorm;
    const usage: u32 = @truncate(tex_res.usage);

    const encode_start = common_timing.now_ns();

    var entry = texture_map.get(tex_res.handle);
    if (entry == null) {
        const tex_handle = d3d12_bridge_device_create_texture_2d(device, width, height, 1, format, usage) orelse return error.InvalidState;
        const new_entry = TextureEntry{
            .handle = tex_res.handle,
            .resource = tex_handle,
            .width = width,
            .height = height,
            .format = format,
            .usage = tex_res.usage,
        };
        texture_map.put(allocator, tex_res.handle, new_entry) catch {
            d3d12_bridge_release(tex_handle);
            return error.InvalidState;
        };
        entry = new_entry;
    }

    const staging = d3d12_bridge_device_create_buffer(device, data.len, HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
    defer d3d12_bridge_release(staging);

    const cmd_alloc = d3d12_bridge_device_create_command_allocator(device) orelse return error.InvalidState;
    defer d3d12_bridge_release(cmd_alloc);

    const cmd_list = d3d12_bridge_device_create_command_list(device, cmd_alloc) orelse return error.InvalidState;
    defer d3d12_bridge_release(cmd_list);

    const bytes_per_row = if (tex_res.bytes_per_row > 0) tex_res.bytes_per_row else @as(u32, @intCast(data.len / height));

    d3d12_bridge_command_list_copy_texture_region(cmd_list, entry.?.resource, staging, 0, width, height, bytes_per_row, format);
    d3d12_bridge_command_list_resource_barrier_transition(cmd_list, entry.?.resource, RESOURCE_STATE_COPY_DEST, RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
    d3d12_bridge_command_list_close(cmd_list);
    d3d12_bridge_queue_execute_command_list(queue, cmd_list);

    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}

pub fn texture_query(
    texture_map: *const TextureMap,
    cmd: model.TextureQueryCommand,
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
    cmd: model.TextureDestroyCommand,
) !u64 {
    const encode_start = common_timing.now_ns();

    if (texture_map.fetchRemove(cmd.handle)) |kv| {
        if (kv.value.resource) |res| {
            d3d12_bridge_release(res);
        }
    }

    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}

pub fn release_all(texture_map: *TextureMap) void {
    var it = texture_map.valueIterator();
    while (it.next()) |entry| {
        if (entry.resource) |res| d3d12_bridge_release(res);
    }
    texture_map.clearAndFree(std.heap.page_allocator);
}
