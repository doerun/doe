const std = @import("std");
const bridge = @import("../d3d12_bridge_decls.zig");
const dc = @import("../d3d12_constants.zig");
const configuration = @import("../../../contracts/runtime_configuration.zig");

const QUERY_COUNT: u32 = 2;
const READBACK_BYTES = QUERY_COUNT * @sizeOf(u64);

pub fn should_measure(mode: configuration.GpuTimestampMode, sync_mode: configuration.QueueSyncMode) !bool {
    if (mode == .off) return false;
    if (sync_mode == .deferred) {
        if (mode == .require) return error.TimingPolicyMismatch;
        return false;
    }
    return true;
}

pub fn elapsed_ns(begin: u64, end: u64, frequency: u64) !u64 {
    if (frequency == 0) return error.SyncUnavailable;
    if (end < begin) return error.InvalidTimestamp;
    const result = @as(u128, end - begin) * std.time.ns_per_s / frequency;
    if (result > std.math.maxInt(u64)) return error.TimestampOverflow;
    return @intCast(result);
}

pub const TimestampState = State(bridge.c);

// The dispatch adapter instantiates this same owner with its native bridge.
pub fn State(comptime native: type) type {
    return struct {
        const Self = @This();
        const Pending = struct {
            command_list: *anyopaque,
            fence: *anyopaque,
            value: u64,
            resolved: bool = false,
        };

        query_heap: ?*anyopaque = null,
        readback_buffer: ?*anyopaque = null,
        device: ?*anyopaque = null,
        queue: ?*anyopaque = null,
        frequency: u64 = 0,
        pending: ?Pending = null,

        pub fn prepare(self: *Self, mode: configuration.GpuTimestampMode, sync_mode: configuration.QueueSyncMode, device: ?*anyopaque, queue: ?*anyopaque) !bool {
            if (!try should_measure(mode, sync_mode)) return false;
            self.init_resources(device, queue) catch |err| {
                if (mode == .auto and err == error.SyncUnavailable) return false;
                return err;
            };
            return true;
        }

        pub fn init_resources(self: *Self, device: ?*anyopaque, queue: ?*anyopaque) !void {
            if (device == null or queue == null) return error.InvalidArgument;
            if (self.query_heap != null) {
                if (self.device != device or self.queue != queue) return error.InvalidState;
                return;
            }
            var frequency: u64 = 0;
            const result = native.d3d12_bridge_queue_get_timestamp_frequency_checked(queue, &frequency);
            if (result == bridge.c.D3D12_SYNC_DEVICE_LOST) return error.DeviceLost;
            if (result != bridge.c.D3D12_SYNC_OK or frequency == 0) return error.SyncUnavailable;
            const heap = native.d3d12_bridge_device_create_timestamp_query_heap(device, QUERY_COUNT) orelse return error.InvalidState;
            errdefer native.d3d12_bridge_release(heap);
            const buffer = native.d3d12_bridge_device_create_buffer(device, READBACK_BYTES, dc.HEAP_TYPE_READBACK) orelse return error.InvalidState;
            self.* = .{ .query_heap = heap, .readback_buffer = buffer, .device = device, .queue = queue, .frequency = frequency };
        }

        pub fn begin(self: *Self, command_list: ?*anyopaque, fence: ?*anyopaque, value: u64) !void {
            if (self.query_heap == null or command_list == null or fence == null or value == 0 or value == std.math.maxInt(u64)) return error.InvalidState;
            if (self.pending) |pending| try ensure_complete(pending);
            const completed = native.d3d12_bridge_fence_completed_value(fence);
            if (completed == std.math.maxInt(u64)) return error.DeviceLost;
            if (completed >= value) return error.InvalidState;
            self.pending = .{ .command_list = command_list.?, .fence = fence.?, .value = value };
            native.d3d12_bridge_command_list_end_query(command_list, self.query_heap, 0);
        }

        pub fn end(self: *Self, command_list: ?*anyopaque) !void {
            const pending = if (self.pending) |*pending| pending else return error.InvalidState;
            if (pending.command_list != command_list or pending.resolved) return error.InvalidState;
            native.d3d12_bridge_command_list_end_query(command_list, self.query_heap, 1);
            native.d3d12_bridge_command_list_resolve_query_data(command_list, self.query_heap, 0, QUERY_COUNT, self.readback_buffer, 0);
            pending.resolved = true;
        }

        // Only the recording owner, before ExecuteCommandLists, may cancel.
        pub fn cancel_unsubmitted(self: *Self) void {
            self.pending = null;
        }

        pub fn read_gpu_timestamp_ns(self: *Self) !u64 {
            const pending = self.pending orelse return error.InvalidState;
            if (!pending.resolved) return error.InvalidState;
            try ensure_complete(pending);
            const mapped = native.d3d12_bridge_resource_map_read(self.readback_buffer, READBACK_BYTES) orelse return error.TimestampReadbackFailed;
            defer native.d3d12_bridge_resource_unmap_read(self.readback_buffer);
            const bytes: [*]const u8 = @ptrCast(mapped);
            const begin_ticks = std.mem.readInt(u64, bytes[0..8], .little);
            const end_ticks = std.mem.readInt(u64, bytes[8..16], .little);
            self.pending = null;
            return elapsed_ns(begin_ticks, end_ticks, self.frequency);
        }

        fn ensure_complete(pending: Pending) !void {
            const completed = native.d3d12_bridge_fence_completed_value(pending.fence);
            if (completed == std.math.maxInt(u64)) return error.DeviceLost;
            if (completed < pending.value) return error.TimestampPending;
        }

        // The runtime's completion or terminal-loss barrier precedes destruction.
        pub fn deinit(self: *Self) void {
            if (self.readback_buffer) |buffer| native.d3d12_bridge_release(buffer);
            if (self.query_heap) |heap| native.d3d12_bridge_release(heap);
            self.* = .{};
        }
    };
}

const Probe = struct {
    var external: u8 = 0;
    var handles: [2]u8 = .{ 0, 0 };
    var live: usize = 0;
    var fail_create: usize = 0;
    var creations: usize = 0;
    var clock_result: c_int = 0;
    var frequency: u64 = 1000;
    var completed: u64 = 0;
    var map_fails: bool = false;
    var maps: usize = 0;
    var unmaps: usize = 0;
    var data: [16]u8 = @splat(0);
    var query_calls: usize = 0;
    var resolve_calls: usize = 0;

    fn reset() void {
        live = 0;
        creations = 0;
        fail_create = 0;
        clock_result = 0;
        frequency = 1000;
        completed = 0;
        map_fails = false;
        maps = 0;
        unmaps = 0;
        query_calls = 0;
        resolve_calls = 0;
        std.mem.writeInt(u64, data[0..8], 100, .little);
        std.mem.writeInt(u64, data[8..16], 130, .little);
    }
    fn create() ?*anyopaque {
        creations += 1;
        if (creations == fail_create) return null;
        live += 1;
        return &handles[live - 1];
    }
    fn d3d12_bridge_release(_: ?*anyopaque) void {
        std.debug.assert(live > 0);
        live -= 1;
    }
    fn d3d12_bridge_queue_get_timestamp_frequency_checked(_: ?*anyopaque, result: *u64) c_int {
        result.* = frequency;
        return clock_result;
    }
    fn d3d12_bridge_device_create_timestamp_query_heap(_: ?*anyopaque, count: u32) ?*anyopaque {
        std.debug.assert(count == QUERY_COUNT);
        return create();
    }
    fn d3d12_bridge_device_create_buffer(_: ?*anyopaque, size: usize, heap: c_int) ?*anyopaque {
        std.debug.assert(size == READBACK_BYTES and heap == dc.HEAP_TYPE_READBACK);
        return create();
    }
    fn d3d12_bridge_fence_completed_value(_: ?*anyopaque) u64 {
        return completed;
    }
    fn d3d12_bridge_command_list_end_query(_: ?*anyopaque, _: ?*anyopaque, _: u32) void {
        query_calls += 1;
    }
    fn d3d12_bridge_command_list_resolve_query_data(_: ?*anyopaque, _: ?*anyopaque, _: u32, count: u32, _: ?*anyopaque, offset: u64) void {
        std.debug.assert(count == QUERY_COUNT and offset == 0);
        resolve_calls += 1;
    }
    fn d3d12_bridge_resource_map_read(_: ?*anyopaque, size: usize) ?*anyopaque {
        std.debug.assert(size == READBACK_BYTES);
        maps += 1;
        return if (map_fails) null else &data;
    }
    fn d3d12_bridge_resource_unmap_read(_: ?*anyopaque) void {
        unmaps += 1;
    }
};

test "D3D12 timestamp policy never measures off or deferred work" {
    Probe.reset();
    var state: State(Probe) = .{};
    try std.testing.expect(!try state.prepare(.off, .per_command, null, null));
    try std.testing.expect(!try state.prepare(.auto, .deferred, null, null));
    try std.testing.expectError(error.TimingPolicyMismatch, state.prepare(.require, .deferred, null, null));
    try std.testing.expectEqual(@as(usize, 0), Probe.creations);
}

test "D3D12 timestamp initialization is transactional and unavailable frequency stays unavailable" {
    for (1..3) |failure| {
        Probe.reset();
        Probe.fail_create = failure;
        var state: State(Probe) = .{};
        try std.testing.expectError(error.InvalidState, state.init_resources(&Probe.external, &Probe.external));
        try std.testing.expectEqual(@as(usize, 0), Probe.live);
        try std.testing.expect(state.query_heap == null and state.readback_buffer == null and state.frequency == 0);
        Probe.fail_create = 0;
        try state.init_resources(&Probe.external, &Probe.external);
        state.deinit();
        try std.testing.expectEqual(@as(usize, 0), Probe.live);
    }
    Probe.reset();
    Probe.frequency = 0;
    var state: State(Probe) = .{};
    try std.testing.expect(!try state.prepare(.auto, .per_command, &Probe.external, &Probe.external));
    try std.testing.expectError(error.SyncUnavailable, state.prepare(.require, .per_command, &Probe.external, &Probe.external));
    try std.testing.expectEqual(@as(usize, 0), Probe.creations);
    Probe.frequency = 1000;
    Probe.clock_result = bridge.c.D3D12_SYNC_FAILED;
    try std.testing.expectError(error.SyncUnavailable, state.init_resources(&Probe.external, &Probe.external));
    Probe.clock_result = bridge.c.D3D12_SYNC_DEVICE_LOST;
    try std.testing.expectError(error.DeviceLost, state.prepare(.auto, .per_command, &Probe.external, &Probe.external));
}

test "D3D12 timestamp readback waits for its fence and balances mapping on failure" {
    Probe.reset();
    var state: State(Probe) = .{};
    defer state.deinit();
    const handle = &Probe.external;
    try state.init_resources(handle, handle);
    try std.testing.expectError(error.InvalidState, state.read_gpu_timestamp_ns());
    try state.begin(handle, handle, 1);
    try std.testing.expectError(error.InvalidState, state.read_gpu_timestamp_ns());
    try state.end(handle);
    try std.testing.expectError(error.TimestampPending, state.read_gpu_timestamp_ns());
    try std.testing.expectError(error.TimestampPending, state.begin(handle, handle, 2));
    try std.testing.expectEqual(@as(usize, 0), Probe.maps);
    Probe.completed = std.math.maxInt(u64);
    try std.testing.expectError(error.DeviceLost, state.read_gpu_timestamp_ns());
    try std.testing.expectEqual(@as(usize, 0), Probe.maps);
    Probe.completed = 1;
    Probe.map_fails = true;
    try std.testing.expectError(error.TimestampReadbackFailed, state.read_gpu_timestamp_ns());
    try std.testing.expectEqual(@as(usize, 0), Probe.unmaps);
    Probe.map_fails = false;
    try std.testing.expectEqual(@as(u64, 30_000_000), try state.read_gpu_timestamp_ns());
    try std.testing.expectEqual(@as(usize, 1), Probe.unmaps);
    try std.testing.expectError(error.InvalidState, state.read_gpu_timestamp_ns());
    try state.begin(handle, handle, 2);
    try state.end(handle);
    Probe.completed = 2;
    std.mem.writeInt(u64, Probe.data[8..16], 99, .little);
    try std.testing.expectError(error.InvalidTimestamp, state.read_gpu_timestamp_ns());
    try std.testing.expectEqual(@as(usize, 2), Probe.unmaps);
}

test "D3D12 timestamps bind recording to one command list and device" {
    Probe.reset();
    var state: State(Probe) = .{};
    defer state.deinit();
    var other: u8 = 0;
    const handle = &Probe.external;
    try state.init_resources(handle, handle);
    try std.testing.expectError(error.InvalidState, state.init_resources(&other, handle));
    try std.testing.expectError(error.InvalidState, state.end(handle));
    try state.begin(handle, handle, 1);
    try std.testing.expectError(error.InvalidState, state.end(&other));
    try state.end(handle);
    try std.testing.expectError(error.InvalidState, state.end(handle));
    try std.testing.expectEqual(@as(usize, 2), Probe.query_calls);
    try std.testing.expectEqual(@as(usize, 1), Probe.resolve_calls);
    state.cancel_unsubmitted();
    try state.begin(handle, handle, 1);
    state.cancel_unsubmitted();
}

test "D3D12 timestamp arithmetic preserves zero duration and rejects overflow" {
    const testing = std.testing;
    try testing.expectEqual(@as(u64, 0), try elapsed_ns(10, 10, 1000));
    try testing.expectEqual(@as(u64, 333_333_333), try elapsed_ns(0, 1, 3));
    try testing.expectEqual(@as(u64, std.math.maxInt(u64)), try elapsed_ns(0, std.math.maxInt(u64), std.time.ns_per_s));
    try testing.expectError(error.TimestampOverflow, elapsed_ns(0, std.math.maxInt(u64), 1));
    try testing.expectError(error.InvalidTimestamp, elapsed_ns(100, 99, 1000));
    try testing.expectError(error.SyncUnavailable, elapsed_ns(0, 10, 0));
}
