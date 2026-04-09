const std = @import("std");
const common_timing = @import("../common/timing.zig");
const dc = @import("d3d12_constants.zig");

pub const MAX_POOL_ENTRIES_PER_SIZE: usize = 8;

extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_copy_buffer(cmd_list: ?*anyopaque, dst: ?*anyopaque, src: ?*anyopaque, size: usize) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;

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
    if (bytes == 0) return error.InvalidArgument;
    if (bytes > max_upload_bytes) return error.UnsupportedFeature;
    const len: usize = @intCast(bytes);

    const cmd_alloc = d3d12_bridge_device_create_command_allocator(self.device) orelse return error.InvalidState;
    errdefer d3d12_bridge_release(cmd_alloc);

    const cmd_list = d3d12_bridge_device_create_command_list(self.device, cmd_alloc) orelse return error.InvalidState;
    errdefer d3d12_bridge_release(cmd_list);

    const src_buf = d3d12PoolPop(&self.upload_pool, len) orelse
        (d3d12_bridge_device_create_buffer(self.device, len, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState);
    errdefer d3d12PoolPushOrRelease(&self.upload_pool, self.allocator, len, src_buf);

    const dst_buf = d3d12PoolPop(&self.default_pool, len) orelse
        (d3d12_bridge_device_create_buffer(self.device, len, default_heap_type) orelse return error.InvalidState);
    errdefer d3d12PoolPushOrRelease(&self.default_pool, self.allocator, len, dst_buf);

    d3d12_bridge_command_list_copy_buffer(cmd_list, dst_buf, src_buf, len);
    d3d12_bridge_command_list_close(cmd_list);

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
    if (!self.has_device) return 0;
    const start_ns = common_timing.now_ns();

    if (self.streaming_copy_state.has_pending()) {
        _ = try self.streaming_copy_state.flush(self.queue, self.fence, &self.fence_value);
        self.noteCompletedFenceWait();
    }

    for (self.pending_uploads.items) |item| {
        d3d12_bridge_queue_execute_command_list(self.queue, item.cmd_list);
    }

    const has_new_submissions = self.pending_uploads.items.len > 0 or self.has_deferred_submissions;
    const has_outstanding_submissions = self.pending_submit_batches.items.len > 0;
    if (has_new_submissions) {
        self.fence_value +|= 1;
        d3d12_bridge_queue_signal(self.queue, self.fence, self.fence_value);
    }
    if (has_new_submissions or has_outstanding_submissions) {
        d3d12_bridge_fence_wait(self.fence, self.fence_value);
        self.noteCompletedFenceWait();
    }
    self.has_deferred_submissions = false;

    releasePendingUploads(self);
    const end_ns = common_timing.now_ns();
    return common_timing.ns_delta(end_ns, start_ns);
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
        d3d12_bridge_release(item.cmd_list);
        d3d12_bridge_release(item.cmd_allocator);
        d3d12PoolPushOrRelease(&self.upload_pool, self.allocator, item.byte_count, item.src_buffer);
        d3d12PoolPushOrRelease(&self.default_pool, self.allocator, item.byte_count, item.dst_buffer);
    }
    self.pending_uploads.clearRetainingCapacity();
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
        d3d12_bridge_release(buf);
        return;
    };
    if (!gop.found_existing) gop.value_ptr.* = .{};
    if (gop.value_ptr.items.len >= MAX_POOL_ENTRIES_PER_SIZE) {
        d3d12_bridge_release(buf);
        return;
    }
    gop.value_ptr.append(allocator, .{ .buffer = buf }) catch {
        d3d12_bridge_release(buf);
    };
}

pub fn d3d12ReleasePool(pool: *D3D12Pool, allocator: std.mem.Allocator) void {
    var it = pool.valueIterator();
    while (it.next()) |list| {
        for (list.items) |entry| d3d12_bridge_release(entry.buffer);
        var m = list.*;
        m.deinit(allocator);
    }
    pool.deinit(allocator);
}
