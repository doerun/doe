const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");

const HEAP_TYPE_UPLOAD: c_int = 2;
const HEAP_TYPE_READBACK: c_int = 3;
const MAX_MAP_BYTES: usize = 256 * 1024 * 1024;

extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_map(resource: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_unmap(resource: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

pub fn execute_map_async(
    device: ?*anyopaque,
    cmd: model.MapAsyncCommand,
) !u64 {
    if (cmd.bytes == 0) return error.InvalidArgument;
    if (cmd.bytes > MAX_MAP_BYTES) return error.UnsupportedFeature;

    const encode_start = common_timing.now_ns();

    const heap_type: c_int = switch (cmd.mode) {
        .write => HEAP_TYPE_UPLOAD,
        .read => HEAP_TYPE_READBACK,
    };

    const buffer = d3d12_bridge_device_create_buffer(device, cmd.bytes, heap_type) orelse return error.InvalidState;
    defer d3d12_bridge_release(buffer);

    const mapped = d3d12_bridge_resource_map(buffer) orelse return error.InvalidState;
    _ = mapped;
    d3d12_bridge_resource_unmap(buffer);

    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}
