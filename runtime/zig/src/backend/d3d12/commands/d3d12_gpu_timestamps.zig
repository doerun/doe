const std = @import("std");
const common_timing = @import("../../common/timing.zig");

const HEAP_TYPE_READBACK: c_int = 3;
const TIMESTAMP_QUERY_COUNT: u32 = 2;
const NS_PER_SECOND: u64 = 1_000_000_000;

extern fn d3d12_bridge_device_create_timestamp_query_heap(device: ?*anyopaque, count: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_end_query(cmd_list: ?*anyopaque, query_heap: ?*anyopaque, index: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_resolve_query_data(cmd_list: ?*anyopaque, query_heap: ?*anyopaque, start_index: u32, count: u32, dst_buffer: ?*anyopaque, dst_offset: u64) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_queue_get_timestamp_frequency(queue: ?*anyopaque) callconv(.c) u64;
extern fn d3d12_bridge_resource_map(resource: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_unmap(resource: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

pub const TimestampState = struct {
    query_heap: ?*anyopaque = null,
    readback_buffer: ?*anyopaque = null,
    cmd_allocator: ?*anyopaque = null,
    cmd_list: ?*anyopaque = null,
    has_cmd: bool = false,
    frequency: u64 = 0,

    pub fn init_resources(self: *TimestampState, device: ?*anyopaque, queue: ?*anyopaque) !void {
        if (self.query_heap != null) return;

        self.query_heap = d3d12_bridge_device_create_timestamp_query_heap(device, TIMESTAMP_QUERY_COUNT) orelse return error.UnsupportedFeature;
        self.readback_buffer = d3d12_bridge_device_create_buffer(device, TIMESTAMP_QUERY_COUNT * @sizeOf(u64), HEAP_TYPE_READBACK) orelse return error.InvalidState;
        self.frequency = d3d12_bridge_queue_get_timestamp_frequency(queue);
        if (self.frequency == 0) self.frequency = 1;

        self.cmd_allocator = d3d12_bridge_device_create_command_allocator(device) orelse return error.InvalidState;
        self.cmd_list = d3d12_bridge_device_create_command_list(device, self.cmd_allocator) orelse return error.InvalidState;
        d3d12_bridge_command_list_close(self.cmd_list);
        self.has_cmd = true;
    }

    pub fn record_begin_timestamp(self: *TimestampState, cmd_list: ?*anyopaque) void {
        if (self.query_heap == null) return;
        d3d12_bridge_command_list_end_query(cmd_list, self.query_heap, 0);
    }

    pub fn record_end_timestamp(self: *TimestampState, cmd_list: ?*anyopaque) void {
        if (self.query_heap == null) return;
        d3d12_bridge_command_list_end_query(cmd_list, self.query_heap, 1);
        d3d12_bridge_command_list_resolve_query_data(cmd_list, self.query_heap, 0, TIMESTAMP_QUERY_COUNT, self.readback_buffer, 0);
    }

    pub fn read_gpu_timestamp_ns(self: *TimestampState) u64 {
        if (self.readback_buffer == null or self.frequency == 0) return 0;
        const mapped = d3d12_bridge_resource_map(self.readback_buffer) orelse return 0;
        const timestamps: *const [2]u64 = @ptrCast(@alignCast(mapped));
        const begin_ticks = timestamps[0];
        const end_ticks = timestamps[1];
        d3d12_bridge_resource_unmap(self.readback_buffer);

        if (end_ticks <= begin_ticks) return 0;
        const delta_ticks = end_ticks - begin_ticks;
        return delta_ticks * NS_PER_SECOND / self.frequency;
    }

    pub fn deinit(self: *TimestampState) void {
        if (self.has_cmd) {
            d3d12_bridge_release(self.cmd_list);
            d3d12_bridge_release(self.cmd_allocator);
        }
        if (self.readback_buffer) |b| d3d12_bridge_release(b);
        if (self.query_heap) |h| d3d12_bridge_release(h);
        self.* = .{};
    }
};
