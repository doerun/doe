const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");
const d3d12_texture = @import("../resources/d3d12_texture.zig");

const HEAP_TYPE_DEFAULT: c_int = 1;

extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_copy_buffer(cmd_list: ?*anyopaque, dst: ?*anyopaque, src: ?*anyopaque, size: usize) callconv(.c) void;
extern fn d3d12_bridge_command_list_copy_texture_region(cmd_list: ?*anyopaque, dst: ?*anyopaque, src: ?*anyopaque, src_offset: u64, width: u32, height: u32, bytes_per_row: u32, format: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_resource_barrier_transition(cmd_list: ?*anyopaque, resource: ?*anyopaque, state_before: c_int, state_after: c_int) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_allocator_reset(allocator_h: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_command_list_reset(cmd_list: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

pub const CopyMetrics = struct {
    setup_ns: u64 = 0,
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
};

pub const CopyState = struct {
    cmd_allocator: ?*anyopaque = null,
    cmd_list: ?*anyopaque = null,
    has_cmd: bool = false,

    pub fn execute_copy(
        self: *CopyState,
        device: ?*anyopaque,
        queue: ?*anyopaque,
        texture_map: *d3d12_texture.TextureMap,
        allocator: std.mem.Allocator,
        cmd: model.CopyCommand,
    ) !CopyMetrics {
        if (cmd.bytes == 0) return error.InvalidArgument;

        const setup_start = common_timing.now_ns();

        const src_resource = resolve_resource(device, texture_map, allocator, cmd.src) orelse return error.InvalidState;
        const dst_resource = resolve_resource(device, texture_map, allocator, cmd.dst) orelse return error.InvalidState;

        const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

        const encode_start = common_timing.now_ns();

        try self.ensure_cmd(device);

        if (d3d12_bridge_command_allocator_reset(self.cmd_allocator) != 0) return error.InvalidState;
        if (d3d12_bridge_command_list_reset(self.cmd_list, self.cmd_allocator) != 0) return error.InvalidState;

        switch (cmd.direction) {
            .buffer_to_buffer => {
                d3d12_bridge_command_list_copy_buffer(self.cmd_list, dst_resource, src_resource, cmd.bytes);
            },
            .buffer_to_texture => {
                const width = if (cmd.dst.width > 0) cmd.dst.width else 1;
                const height = if (cmd.dst.height > 0) cmd.dst.height else 1;
                const bpr = if (cmd.dst.bytes_per_row > 0) cmd.dst.bytes_per_row else @as(u32, @intCast(cmd.bytes / height));
                const format: u32 = if (cmd.dst.format != model.WGPUTextureFormat_Undefined) cmd.dst.format else model.WGPUTextureFormat_RGBA8Unorm;
                d3d12_bridge_command_list_copy_texture_region(self.cmd_list, dst_resource, src_resource, cmd.src.offset, width, height, bpr, format);
            },
            .texture_to_buffer, .texture_to_texture => {
                d3d12_bridge_command_list_copy_buffer(self.cmd_list, dst_resource, src_resource, cmd.bytes);
            },
        }

        d3d12_bridge_command_list_close(self.cmd_list);

        const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

        const submit_start = common_timing.now_ns();
        d3d12_bridge_queue_execute_command_list(queue, self.cmd_list);
        const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start);

        return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns };
    }

    fn ensure_cmd(self: *CopyState, device: ?*anyopaque) !void {
        if (self.has_cmd) return;
        self.cmd_allocator = d3d12_bridge_device_create_command_allocator(device) orelse return error.InvalidState;
        self.cmd_list = d3d12_bridge_device_create_command_list(device, self.cmd_allocator) orelse {
            d3d12_bridge_release(self.cmd_allocator);
            self.cmd_allocator = null;
            return error.InvalidState;
        };
        d3d12_bridge_command_list_close(self.cmd_list);
        self.has_cmd = true;
    }

    pub fn deinit(self: *CopyState) void {
        if (self.has_cmd) {
            d3d12_bridge_release(self.cmd_list);
            d3d12_bridge_release(self.cmd_allocator);
            self.has_cmd = false;
        }
        self.* = .{};
    }
};

fn resolve_resource(
    device: ?*anyopaque,
    texture_map: *d3d12_texture.TextureMap,
    allocator: std.mem.Allocator,
    res: model.CopyTextureResource,
) ?*anyopaque {
    if (res.kind == .texture) {
        if (texture_map.get(res.handle)) |entry| return entry.resource;
        const width = if (res.width > 0) res.width else 1;
        const height = if (res.height > 0) res.height else 1;
        const format: u32 = if (res.format != model.WGPUTextureFormat_Undefined) res.format else model.WGPUTextureFormat_RGBA8Unorm;
        _ = @as(u32, @truncate(res.usage));
        const tex = d3d12_bridge_device_create_buffer(device, @as(usize, width) * @as(usize, height) * 4, HEAP_TYPE_DEFAULT) orelse return null;
        texture_map.put(allocator, res.handle, .{
            .handle = res.handle,
            .resource = tex,
            .width = width,
            .height = height,
            .format = format,
            .usage = res.usage,
        }) catch {
            d3d12_bridge_release(tex);
            return null;
        };
        return tex;
    }
    return d3d12_bridge_device_create_buffer(device, if (res.offset > 0) @intCast(res.offset) else 256, HEAP_TYPE_DEFAULT);
}
