// metal_upload.zig — Upload path: staging buffer management and upload_bytes.
// Sharded from metal_native_runtime.zig to stay under the line-limit policy.

const std = @import("std");
const webgpu = @import("../../contracts/runtime_types.zig");
const bridge = @import("metal_bridge_decls.zig");
const metal_bridge_begin_blit_encoding = bridge.metal_bridge_begin_blit_encoding;
const metal_bridge_blit_encoder_copy = bridge.metal_bridge_blit_encoder_copy;
const metal_bridge_blit_encoder_copy_region = bridge.metal_bridge_blit_encoder_copy_region;
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;
const metal_bridge_cmd_buf_blit_encoder = bridge.metal_bridge_cmd_buf_blit_encoder;
const metal_bridge_device_new_buffer_private = bridge.metal_bridge_device_new_buffer_private;
const metal_bridge_device_new_buffer_shared = bridge.metal_bridge_device_new_buffer_shared;
const metal_bridge_end_compute_encoding = bridge.metal_bridge_end_compute_encoding;
const metal_bridge_release = bridge.metal_bridge_release;
const metal_bridge_render_encoder_end = bridge.metal_bridge_render_encoder_end;

const metal_buffer_pool = @import("metal_buffer_pool.zig");
const metal_runtime_limits = @import("metal_runtime_limits.zig");

const SMALL_UPLOAD_CAPACITY = metal_runtime_limits.SMALL_UPLOAD_CAPACITY;

pub fn upload_bytes(self: anytype, bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
    if (bytes == 0) return error.InvalidArgument;
    const len: usize = @intCast(bytes);
    const use_small_staging = len <= SMALL_UPLOAD_CAPACITY and
        self.staging_src != null and self.staging_dst != null and self.staging_src_ptr != null;
    const pooled_src = if (use_small_staging) null else metal_buffer_pool.pool_pop(&self.shared_pool, len);
    const src = if (use_small_staging)
        self.staging_src.?
    else
        pooled_src orelse
            (metal_bridge_device_new_buffer_shared(self.device, len) orelse return error.InvalidState);
    errdefer if (!use_small_staging) metal_bridge_release(src);
    if (use_small_staging) {
        if (!self.staging_src_zeroed) {
            @memset(self.staging_src_ptr.?[0..SMALL_UPLOAD_CAPACITY], 0);
            self.staging_src_zeroed = true;
        }
    } else {
        const raw = metal_bridge_buffer_contents(src) orelse return error.InvalidState;
        @memset(@as([*]u8, @ptrCast(raw))[0..len], 0);
    }

    if (mode == .copy_dst_copy_src) {
        if (!use_small_staging) {
            pool_push_or_release(&self.shared_pool, self.allocator, len, src);
        }
        self.streaming_max_upload_bytes = @max(self.streaming_max_upload_bytes, len);
        self.has_deferred_submissions = true;
        return;
    }

    const dst = if (use_small_staging)
        self.staging_dst.?
    else
        metal_buffer_pool.pool_pop(&self.private_pool, len) orelse
            (metal_bridge_device_new_buffer_private(self.device, len) orelse return error.InvalidState);

    errdefer if (!use_small_staging) metal_bridge_release(dst);

    if (self.streaming_compute_encoder) |enc| {
        metal_bridge_end_compute_encoding(enc);
        self.streaming_compute_encoder = null;
    }
    if (self.streaming_render_encoder) |enc| {
        metal_bridge_render_encoder_end(enc);
        metal_bridge_release(enc);
        self.streaming_render_encoder = null;
    }
    if (self.streaming_blit_encoder == null) {
        if (self.streaming_cmd_buf == null) {
            var encoder: ?*anyopaque = null;
            self.streaming_cmd_buf = metal_bridge_begin_blit_encoding(self.queue, &encoder) orelse return error.InvalidState;
            self.streaming_blit_encoder = encoder;
        } else {
            self.streaming_blit_encoder = metal_bridge_cmd_buf_blit_encoder(self.streaming_cmd_buf) orelse return error.InvalidState;
        }
    }
    if (!use_small_staging) {
        try self.streaming_uploads.append(self.allocator, .{
            .src_buffer = src,
            .dst_buffer = dst,
            .byte_count = len,
        });
    }
    metal_bridge_blit_encoder_copy(self.streaming_blit_encoder, src, dst, len);
    self.streaming_max_upload_bytes = @max(self.streaming_max_upload_bytes, len);
    self.has_deferred_submissions = true;
}

pub fn stage_buffer_write_bytes(
    self: anytype,
    dst_buffer: ?*anyopaque,
    dst_offset: u64,
    data_bytes: []const u8,
) !void {
    return stageBufferWriteWithBridge(self, dst_buffer, dst_offset, data_bytes, bridge);
}

fn stageBufferWriteWithBridge(self: anytype, dst_buffer: ?*anyopaque, dst_offset: u64, data_bytes: []const u8, comptime native: type) !void {
    if (data_bytes.len == 0) return error.InvalidArgument;
    const end = std.math.add(u64, dst_offset, data_bytes.len) catch return error.InvalidArgument;
    if (end > native.metal_bridge_buffer_length(dst_buffer)) return error.InvalidArgument;
    const len = data_bytes.len;
    // Every queued write owns immutable bytes until the queue retires it.
    // The prewarmed scratch buffer cannot be shared by outstanding writes.
    try self.streaming_uploads.ensureUnusedCapacity(self.allocator, 1);
    const src = metal_buffer_pool.pool_pop(&self.shared_pool, len) orelse
        (native.metal_bridge_device_new_buffer_shared(self.device, len) orelse return error.InvalidState);
    errdefer native.metal_bridge_release(src);
    const src_ptr = native.metal_bridge_buffer_contents(src) orelse return error.InvalidState;
    @memcpy(src_ptr[0..len], data_bytes);

    if (self.streaming_compute_encoder) |enc| {
        native.metal_bridge_end_compute_encoding(enc);
        self.streaming_compute_encoder = null;
    }
    if (self.streaming_render_encoder) |enc| {
        native.metal_bridge_render_encoder_end(enc);
        native.metal_bridge_release(enc);
        self.streaming_render_encoder = null;
    }
    if (self.streaming_blit_encoder == null) {
        if (self.streaming_cmd_buf == null) {
            self.streaming_cmd_buf = native.metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
        }
        self.streaming_blit_encoder = native.metal_bridge_cmd_buf_blit_encoder(self.streaming_cmd_buf) orelse return error.InvalidState;
    }
    self.streaming_uploads.appendAssumeCapacity(.{
        .src_buffer = src,
        .dst_buffer = null,
        .byte_count = len,
    });
    native.metal_bridge_blit_encoder_copy_region(self.streaming_blit_encoder, src, 0, dst_buffer, dst_offset, len);
    self.streaming_max_upload_bytes = @max(self.streaming_max_upload_bytes, len);
    self.streaming_has_copy = true;
    self.has_deferred_submissions = true;
}

pub fn prewarm_upload_path(self: anytype, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
    if (max_upload_bytes == 0) return;
    if (max_upload_bytes <= SMALL_UPLOAD_CAPACITY and
        (self.staging_src == null or self.staging_dst == null or self.staging_src_ptr == null))
    {
        const src = metal_bridge_device_new_buffer_shared(self.device, SMALL_UPLOAD_CAPACITY) orelse return error.InvalidState;
        errdefer metal_bridge_release(src);
        const dst = metal_bridge_device_new_buffer_private(self.device, SMALL_UPLOAD_CAPACITY) orelse return error.InvalidState;
        errdefer metal_bridge_release(dst);
        const mapped = metal_bridge_buffer_contents(src) orelse return error.InvalidState;
        _ = try self.flush_queue();
        metal_bridge_release(self.staging_src);
        metal_bridge_release(self.staging_dst);
        self.staging_src = src;
        self.staging_dst = dst;
        self.staging_src_ptr = mapped;
        self.staging_src_zeroed = false;
    }
    try upload_bytes(self, max_upload_bytes, mode);
    _ = try self.flush_queue();
}

fn pool_push_or_release(pool: *metal_buffer_pool.BufferPool, allocator: std.mem.Allocator, size: usize, buf: ?*anyopaque) void {
    metal_buffer_pool.pool_push_or_release(pool, allocator, size, buf);
}

test "staged writes retain independent snapshots and roll back failed native acquisition" {
    const Probe = struct {
        const Buffer = struct { bytes: [8]u8 = @splat(0) };
        var buffers: [2]Buffer = .{ .{}, .{} };
        var allocated: usize = 0;
        var released: usize = 0;
        var fail_mapping = false;
        var fail_encoder = false;
        const Copy = struct { source: *Buffer, offset: usize, length: usize };
        var copies: [2]Copy = undefined;
        var copy_count: usize = 0;
        fn metal_bridge_buffer_length(_: ?*anyopaque) usize {
            return 8;
        }
        fn metal_bridge_device_new_buffer_shared(_: ?*anyopaque, _: usize) ?*anyopaque {
            const buffer = &buffers[allocated];
            allocated += 1;
            return buffer;
        }
        fn metal_bridge_buffer_contents(raw: ?*anyopaque) ?[*]u8 {
            if (fail_mapping) return null;
            const buffer: *Buffer = @ptrCast(@alignCast(raw.?));
            return &buffer.bytes;
        }
        fn metal_bridge_release(_: ?*anyopaque) void {
            released += 1;
        }
        fn metal_bridge_end_compute_encoding(_: ?*anyopaque) void {}
        fn metal_bridge_render_encoder_end(_: ?*anyopaque) void {}
        fn metal_bridge_create_command_buffer(_: ?*anyopaque) ?*anyopaque {
            return &buffers;
        }
        fn metal_bridge_cmd_buf_blit_encoder(_: ?*anyopaque) ?*anyopaque {
            return if (fail_encoder) null else &buffers;
        }
        fn metal_bridge_blit_encoder_copy_region(_: ?*anyopaque, source: ?*anyopaque, source_offset: u64, _: ?*anyopaque, offset: u64, length: u64) void {
            std.debug.assert(source_offset == 0);
            copies[copy_count] = .{ .source = @ptrCast(@alignCast(source.?)), .offset = @intCast(offset), .length = @intCast(length) };
            copy_count += 1;
        }
    };
    const Pending = struct { src_buffer: ?*anyopaque, dst_buffer: ?*anyopaque, byte_count: usize };
    const Owner = struct {
        allocator: std.mem.Allocator,
        device: ?*anyopaque = null,
        queue: ?*anyopaque = null,
        shared_pool: metal_buffer_pool.BufferPool = .{},
        streaming_uploads: std.ArrayListUnmanaged(Pending) = .{},
        streaming_compute_encoder: ?*anyopaque = null,
        streaming_render_encoder: ?*anyopaque = null,
        streaming_cmd_buf: ?*anyopaque = null,
        streaming_blit_encoder: ?*anyopaque = null,
        streaming_max_upload_bytes: usize = 0,
        streaming_has_copy: bool = false,
        has_deferred_submissions: bool = false,
    };
    var owner: Owner = .{ .allocator = std.testing.allocator };
    defer owner.streaming_uploads.deinit(owner.allocator);
    Probe.allocated = 0;
    Probe.released = 0;
    Probe.copy_count = 0;
    var first = [_]u8{ 1, 2, 3 };
    try stageBufferWriteWithBridge(&owner, null, 0, &first, Probe);
    @memset(&first, 9);
    try stageBufferWriteWithBridge(&owner, null, 3, &.{ 4, 5, 6 }, Probe);
    try std.testing.expectEqualSlices(u8, &.{ 1, 2, 3 }, Probe.buffers[0].bytes[0..3]);
    try std.testing.expectEqualSlices(u8, &.{ 4, 5, 6 }, Probe.buffers[1].bytes[0..3]);
    try std.testing.expectEqual(@as(usize, 2), owner.streaming_uploads.items.len);
    try std.testing.expect(owner.streaming_uploads.items[0].src_buffer != owner.streaming_uploads.items[1].src_buffer);
    try std.testing.expectEqual(@as(usize, 0), Probe.released);
    // Execute the recorded copies after both host writes, then retire storage.
    var output: [8]u8 = @splat(0);
    for (Probe.copies[0..Probe.copy_count]) |copy| {
        @memcpy(output[copy.offset..][0..copy.length], copy.source.bytes[0..copy.length]);
    }
    try std.testing.expectEqualSlices(u8, &.{ 1, 2, 3, 4, 5, 6, 0, 0 }, &output);
    for (owner.streaming_uploads.items) |item| Probe.metal_bridge_release(item.src_buffer);
    owner.streaming_uploads.clearRetainingCapacity();
    try std.testing.expectEqual(@as(usize, 2), Probe.released);
    Probe.allocated = 0;
    Probe.fail_mapping = true;
    try std.testing.expectError(error.InvalidState, stageBufferWriteWithBridge(&owner, null, 0, &.{1}, Probe));
    Probe.fail_mapping = false;
    owner.streaming_blit_encoder = null;
    Probe.fail_encoder = true;
    try std.testing.expectError(error.InvalidState, stageBufferWriteWithBridge(&owner, null, 0, &.{1}, Probe));
    Probe.fail_encoder = false;
    try std.testing.expectEqual(@as(usize, 4), Probe.released);
    try std.testing.expectEqual(@as(usize, 0), owner.streaming_uploads.items.len);
    try std.testing.expectError(error.InvalidArgument, stageBufferWriteWithBridge(&owner, null, 8, &.{1}, Probe));
    try std.testing.expectError(error.InvalidArgument, stageBufferWriteWithBridge(&owner, null, std.math.maxInt(u64), &.{1}, Probe));
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    var failed_owner: Owner = .{ .allocator = failing.allocator() };
    try std.testing.expectError(error.OutOfMemory, stageBufferWriteWithBridge(&failed_owner, null, 0, &.{1}, Probe));
    try std.testing.expectEqual(@as(usize, 2), Probe.allocated);
}
