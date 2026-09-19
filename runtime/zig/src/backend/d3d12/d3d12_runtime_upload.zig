const std = @import("std");
const common_timing = @import("../common/timing.zig");
const dc = @import("d3d12_constants.zig");
const bridge = @import("d3d12_bridge_decls.zig");

pub const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;

pub const PendingUpload = struct {
    cmd_allocator: ?*anyopaque,
    cmd_list: ?*anyopaque,
    src_buffer: ?*anyopaque,
    dst_buffer: ?*anyopaque,
    byte_count: usize,
};

pub const PoolEntry = struct {
    buffer: ?*anyopaque,
};

pub const D3D12Pool = std.AutoHashMapUnmanaged(usize, std.ArrayListUnmanaged(PoolEntry));

pub fn uploadBytes(self: anytype, bytes: u64, max_upload_bytes: u64, default_heap_type: c_int) !void {
    if (self.device_lost) return error.DeviceLost;
    if (bytes == 0) return error.InvalidArgument;
    if (bytes > max_upload_bytes) return error.UnsupportedFeature;
    const len: usize = @intCast(bytes);

    const cmd_alloc = bridge.c.d3d12_bridge_device_create_command_allocator(self.device) orelse return error.InvalidState;
    errdefer bridge.c.d3d12_bridge_release(cmd_alloc);

    const cmd_list = bridge.c.d3d12_bridge_device_create_command_list(self.device, cmd_alloc) orelse return error.InvalidState;
    errdefer bridge.c.d3d12_bridge_release(cmd_list);

    const src_buf = d3d12PoolPop(&self.upload_pool, len) orelse
        (bridge.c.d3d12_bridge_device_create_buffer(self.device, len, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState);
    errdefer d3d12PoolPushOrRelease(&self.upload_pool, self.allocator, len, src_buf);

    const dst_buf = d3d12PoolPop(&self.default_pool, len) orelse
        (bridge.c.d3d12_bridge_device_create_buffer(self.device, len, default_heap_type) orelse return error.InvalidState);
    errdefer d3d12PoolPushOrRelease(&self.default_pool, self.allocator, len, dst_buf);

    bridge.c.d3d12_bridge_command_list_copy_buffer(cmd_list, dst_buf, src_buf, len);
    if (bridge.c.d3d12_bridge_command_list_close_checked(cmd_list) != 0) return error.InvalidState;

    try self.pending_uploads.append(self.allocator, .{
        .cmd_allocator = cmd_alloc,
        .cmd_list = cmd_list,
        .src_buffer = src_buf,
        .dst_buffer = dst_buf,
        .byte_count = len,
    });
    self.has_deferred_submissions = true;
}

pub fn flushQueue(self: anytype) !u64 {
    return flushWithBridge(self, bridge.c);
}

fn flushWithBridge(self: anytype, comptime native: type) !u64 {
    if (!self.has_device) return 0;
    if (self.device_lost) return error.DeviceLost;
    const start_ns = common_timing.now_ns();
    if (self.streaming_copy_state.has_pending()) {
        _ = self.streaming_copy_state.flush(self.queue, self.fence, &self.fence_value) catch |err| {
            if (err == error.DeviceLost) self.device_lost = true;
            return err;
        };
        self.noteCompletedFenceWait();
        if (self.device_lost) return error.DeviceLost;
    }
    const has_work = self.pending_uploads.items.len > 0 or self.has_deferred_submissions or self.pending_submit_batches.items.len > 0;
    if (!has_work) return common_timing.ns_delta(common_timing.now_ns(), start_ns);
    if (self.fence_value >= std.math.maxInt(u64) - 1) return error.InvalidState;
    self.fence_value += 1;
    for (self.pending_uploads.items[self.submitted_upload_count..]) |item| {
        native.d3d12_bridge_queue_execute_command_list(self.queue, item.cmd_list);
        self.submitted_upload_count += 1;
    }
    bridge.check_signal(native.d3d12_bridge_queue_signal_checked(self.queue, self.fence, self.fence_value)) catch |err| {
        if (err == error.DeviceLost) self.device_lost = true;
        return err;
    };
    bridge.check_wait(native.d3d12_bridge_fence_wait_checked(self.fence, self.fence_value)) catch |err| {
        if (err == error.DeviceLost) self.device_lost = true;
        return err;
    };
    self.noteCompletedFenceWait();
    if (self.device_lost) return error.DeviceLost;
    self.has_deferred_submissions = false;
    self.releaseCompletedUploads();
    return common_timing.ns_delta(common_timing.now_ns(), start_ns);
}

pub fn barrier(self: anytype) !u64 {
    const start_ns = common_timing.now_ns();
    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0 or self.pending_submit_batches.items.len > 0) {
        _ = try flushQueue(self);
    }
    const end_ns = common_timing.now_ns();
    return common_timing.ns_delta(end_ns, start_ns);
}

pub fn releasePendingUploads(self: anytype) void {
    for (self.pending_uploads.items) |item| {
        bridge.c.d3d12_bridge_release(item.cmd_list);
        bridge.c.d3d12_bridge_release(item.cmd_allocator);
        d3d12PoolPushOrRelease(&self.upload_pool, self.allocator, item.byte_count, item.src_buffer);
        d3d12PoolPushOrRelease(&self.default_pool, self.allocator, item.byte_count, item.dst_buffer);
    }
    self.pending_uploads.clearRetainingCapacity();
    self.submitted_upload_count = 0;
}

pub fn d3d12PoolPop(pool: *D3D12Pool, size: usize) ?*anyopaque {
    if (pool.getPtr(size)) |list| {
        if (list.items.len > 0) {
            const entry = list.pop() orelse return null;
            return entry.buffer;
        }
    }
    return null;
}

pub fn d3d12PoolPushOrRelease(pool: *D3D12Pool, allocator: std.mem.Allocator, size: usize, buf: ?*anyopaque) void {
    const gop = pool.getOrPut(allocator, size) catch {
        bridge.c.d3d12_bridge_release(buf);
        return;
    };
    if (!gop.found_existing) gop.value_ptr.* = .{};
    if (gop.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        bridge.c.d3d12_bridge_release(buf);
        return;
    }
    gop.value_ptr.append(allocator, .{ .buffer = buf }) catch {
        bridge.c.d3d12_bridge_release(buf);
    };
}

pub fn d3d12ReleasePool(pool: *D3D12Pool, allocator: std.mem.Allocator) void {
    var it = pool.valueIterator();
    while (it.next()) |list| {
        for (list.items) |entry| bridge.c.d3d12_bridge_release(entry.buffer);
        var m = list.*;
        m.deinit(allocator);
    }
    pool.deinit(allocator);
}

test "D3D12 failed flush preserves uploads and retry never executes them twice" {
    const Probe = struct {
        has_device: bool = true,
        device_lost: bool = false,
        queue: ?*anyopaque = null,
        fence: ?*anyopaque = null,
        fence_value: u64 = 0,
        has_deferred_submissions: bool = true,
        submitted_upload_count: usize = 0,
        pending_uploads: struct { items: []const PendingUpload },
        pending_submit_batches: struct { items: []const u8 } = .{ .items = &.{} },
        streaming_copy_state: struct {
            fn has_pending(_: @This()) bool {
                return false;
            }
            fn flush(_: *@This(), _: ?*anyopaque, _: ?*anyopaque, _: *u64) !u64 {
                return 0;
            }
        } = .{},
        completions: usize = 0,
        releases: usize = 0,
        fn noteCompletedFenceWait(self: *@This()) void {
            self.completions += 1;
        }
        fn releaseCompletedUploads(self: *@This()) void {
            self.releases += self.pending_uploads.items.len;
            self.pending_uploads.items = &.{};
            self.submitted_upload_count = 0;
        }
        var submissions: usize = 0;
        var signal_result: c_int = 0;
        var wait_result: c_int = 0;
        fn d3d12_bridge_queue_execute_command_list(_: ?*anyopaque, _: ?*anyopaque) void {
            submissions += 1;
        }
        fn d3d12_bridge_queue_signal_checked(_: ?*anyopaque, _: ?*anyopaque, _: u64) c_int {
            return signal_result;
        }
        fn d3d12_bridge_fence_wait_checked(_: ?*anyopaque, _: u64) c_int {
            return wait_result;
        }
    };
    const uploads = [_]PendingUpload{.{ .cmd_allocator = null, .cmd_list = null, .src_buffer = null, .dst_buffer = null, .byte_count = 4 }};
    for ([_]bool{ false, true }) |fail_signal| {
        Probe.submissions = 0;
        Probe.signal_result = if (fail_signal) bridge.c.D3D12_SYNC_FAILED else bridge.c.D3D12_SYNC_OK;
        Probe.wait_result = if (fail_signal) bridge.c.D3D12_SYNC_OK else bridge.c.D3D12_SYNC_FAILED;
        var state = Probe{ .pending_uploads = .{ .items = &uploads } };
        try std.testing.expectError(if (fail_signal) error.QueueSignalFailed else error.FenceWaitFailed, flushWithBridge(&state, Probe));
        try std.testing.expectEqual(@as(usize, 0), state.completions);
        try std.testing.expectEqual(@as(usize, 0), state.releases);
        try std.testing.expectEqual(@as(usize, 1), Probe.submissions);
        Probe.signal_result = bridge.c.D3D12_SYNC_OK;
        Probe.wait_result = bridge.c.D3D12_SYNC_OK;
        _ = try flushWithBridge(&state, Probe);
        try std.testing.expectEqual(@as(usize, 1), Probe.submissions);
        try std.testing.expectEqual(@as(usize, 1), state.completions);
        try std.testing.expectEqual(@as(usize, 1), state.releases);
        try std.testing.expect(!state.has_deferred_submissions);
    }
    Probe.submissions = 0;
    Probe.signal_result = bridge.c.D3D12_SYNC_DEVICE_LOST;
    Probe.wait_result = bridge.c.D3D12_SYNC_OK;
    var lost = Probe{ .pending_uploads = .{ .items = &uploads } };
    try std.testing.expectError(error.DeviceLost, flushWithBridge(&lost, Probe));
    try std.testing.expect(lost.device_lost);
    try std.testing.expectEqual(@as(usize, 0), lost.completions);
    try std.testing.expectEqual(@as(usize, 0), lost.releases);
    try std.testing.expectError(error.DeviceLost, flushWithBridge(&lost, Probe));
    try std.testing.expectEqual(@as(usize, 1), Probe.submissions);
}
