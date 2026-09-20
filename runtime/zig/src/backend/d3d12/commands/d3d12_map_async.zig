const std = @import("std");
const model_async_types = @import("../../../contracts/model/model_async_types.zig");
const common_timing = @import("../../common/timing.zig");
const dc = @import("../d3d12_constants.zig");
const bridge = @import("../d3d12_bridge_decls.zig");

pub fn execute_map_async(
    device: ?*anyopaque,
    cmd: model_async_types.MapAsyncCommand,
) !u64 {
    return execute(bridge.c, device, cmd);
}

fn execute(comptime native: type, device: ?*anyopaque, cmd: model_async_types.MapAsyncCommand) !u64 {
    if (device == null) return error.InvalidArgument;
    if (cmd.bytes == 0) return error.InvalidArgument;
    if (cmd.bytes > dc.BASELINE_MAX_BUFFER_SIZE) return error.UnsupportedFeature;

    const encode_start = common_timing.now_ns();

    const heap_type: c_int = switch (cmd.mode) {
        .write => dc.HEAP_TYPE_UPLOAD,
        .read => dc.HEAP_TYPE_READBACK,
    };

    const buffer = native.d3d12_bridge_device_create_buffer(device, cmd.bytes, heap_type) orelse return error.InvalidState;
    defer native.d3d12_bridge_release(buffer);

    const mapped = switch (cmd.mode) {
        .read => native.d3d12_bridge_resource_map_read(buffer, cmd.bytes),
        .write => native.d3d12_bridge_resource_map(buffer),
    } orelse return error.InvalidState;
    defer switch (cmd.mode) {
        .read => native.d3d12_bridge_resource_unmap_read(buffer),
        .write => native.d3d12_bridge_resource_unmap(buffer),
    };
    const bytes: [*]u8 = @ptrCast(mapped);
    switch (cmd.mode) {
        .read => std.mem.doNotOptimizeAway(bytes[0]),
        .write => bytes[0] = 0,
    }

    return common_timing.ns_delta(common_timing.now_ns(), encode_start);
}

const Probe = struct {
    var byte: u8 = 9;
    var live: usize = 0;
    var maps: usize = 0;
    var unmaps: usize = 0;
    var fail_create = false;
    var fail_map = false;
    var heap: c_int = 0;
    fn d3d12_bridge_device_create_buffer(_: ?*anyopaque, _: usize, heap_type: c_int) ?*anyopaque {
        heap = heap_type;
        if (fail_create) return null;
        live += 1;
        return &byte;
    }
    fn d3d12_bridge_release(_: ?*anyopaque) void {
        live -= 1;
    }
    fn d3d12_bridge_resource_map(_: ?*anyopaque) ?*anyopaque {
        std.debug.assert(heap == dc.HEAP_TYPE_UPLOAD);
        maps += 1;
        return if (fail_map) null else &byte;
    }
    fn d3d12_bridge_resource_map_read(_: ?*anyopaque, size: usize) ?*anyopaque {
        std.debug.assert(heap == dc.HEAP_TYPE_READBACK and size == 4);
        maps += 1;
        return if (fail_map) null else &byte;
    }
    fn d3d12_bridge_resource_unmap(_: ?*anyopaque) void {
        std.debug.assert(heap == dc.HEAP_TYPE_UPLOAD);
        unmaps += 1;
    }
    fn d3d12_bridge_resource_unmap_read(_: ?*anyopaque) void {
        std.debug.assert(heap == dc.HEAP_TYPE_READBACK);
        unmaps += 1;
    }
};

test "D3D12 map command admits bounds and releases native storage on every failure" {
    const testing = std.testing;
    const handle = &Probe.byte;
    try testing.expectError(error.InvalidArgument, execute(Probe, null, .{ .bytes = 4 }));
    try testing.expectError(error.InvalidArgument, execute(Probe, handle, .{ .bytes = 0 }));
    try testing.expectError(error.UnsupportedFeature, execute(Probe, handle, .{ .bytes = dc.BASELINE_MAX_BUFFER_SIZE + 1 }));
    for ([_]model_async_types.MapAsyncMode{ .read, .write }) |mode| {
        Probe.maps = 0;
        Probe.unmaps = 0;
        Probe.byte = 9;
        Probe.fail_create = true;
        try testing.expectError(error.InvalidState, execute(Probe, handle, .{ .bytes = 4, .mode = mode }));
        try testing.expectEqual(@as(usize, 0), Probe.maps);
        Probe.fail_create = false;
        Probe.fail_map = true;
        try testing.expectError(error.InvalidState, execute(Probe, handle, .{ .bytes = 4, .mode = mode }));
        try testing.expectEqual(@as(usize, 0), Probe.live);
        try testing.expectEqual(@as(usize, 0), Probe.unmaps);
        Probe.fail_map = false;
        _ = try execute(Probe, handle, .{ .bytes = 4, .mode = mode });
        try testing.expectEqual(@as(usize, 0), Probe.live);
        try testing.expectEqual(@as(usize, 1), Probe.unmaps);
        try testing.expectEqual(@as(u8, if (mode == .read) 9 else 0), Probe.byte);
    }
}
