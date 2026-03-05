const std = @import("std");
const common_timing = @import("../common/timing.zig");
const webgpu = @import("../../webgpu_ffi.zig");

const MAX_UPLOAD_BYTES: u64 = 64 * 1024 * 1024;
const HEAP_TYPE_DEFAULT: c_int = 1;
const HEAP_TYPE_UPLOAD: c_int = 2;

// D3D12 bridge C functions — symbols provided by d3d12_bridge.c.
extern fn d3d12_bridge_create_device() callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_device_create_command_queue(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_fence(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_copy_buffer(cmd_list: ?*anyopaque, dst: ?*anyopaque, src: ?*anyopaque, size: usize) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;

const PendingUpload = struct {
    cmd_allocator: ?*anyopaque,
    cmd_list: ?*anyopaque,
    src_buffer: ?*anyopaque,
    dst_buffer: ?*anyopaque,
};

pub const NativeD3D12Runtime = struct {
    allocator: std.mem.Allocator,
    device: ?*anyopaque = null,
    queue: ?*anyopaque = null,
    fence: ?*anyopaque = null,
    fence_value: u64 = 0,

    has_device: bool = false,
    pending_uploads: std.ArrayListUnmanaged(PendingUpload) = .{},
    has_deferred_submissions: bool = false,

    pub fn init(allocator: std.mem.Allocator) !NativeD3D12Runtime {
        var self = NativeD3D12Runtime{ .allocator = allocator };
        errdefer self.deinit();
        try self.bootstrap();
        return self;
    }

    pub fn deinit(self: *NativeD3D12Runtime) void {
        _ = self.flush_queue() catch {};
        self.release_pending_uploads();
        self.pending_uploads.deinit(self.allocator);
        if (self.fence) |f| {
            d3d12_bridge_release(f);
            self.fence = null;
        }
        if (self.queue) |q| {
            d3d12_bridge_release(q);
            self.queue = null;
        }
        if (self.device) |d| {
            d3d12_bridge_release(d);
            self.device = null;
            self.has_device = false;
        }
    }

    pub fn upload_bytes(self: *NativeD3D12Runtime, bytes: u64, _mode: webgpu.UploadBufferUsageMode) !void {
        _ = _mode;
        if (bytes == 0) return error.InvalidArgument;
        if (bytes > MAX_UPLOAD_BYTES) return error.UnsupportedFeature;
        const len: usize = @intCast(bytes);

        const cmd_alloc = d3d12_bridge_device_create_command_allocator(self.device) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(cmd_alloc);

        const cmd_list = d3d12_bridge_device_create_command_list(self.device, cmd_alloc) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(cmd_list);

        const src_buf = d3d12_bridge_device_create_buffer(self.device, len, HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(src_buf);

        const dst_buf = d3d12_bridge_device_create_buffer(self.device, len, HEAP_TYPE_DEFAULT) orelse return error.InvalidState;
        errdefer d3d12_bridge_release(dst_buf);

        d3d12_bridge_command_list_copy_buffer(cmd_list, dst_buf, src_buf, len);
        d3d12_bridge_command_list_close(cmd_list);

        try self.pending_uploads.append(self.allocator, .{
            .cmd_allocator = cmd_alloc,
            .cmd_list = cmd_list,
            .src_buffer = src_buf,
            .dst_buffer = dst_buf,
        });
        self.has_deferred_submissions = true;
    }

    pub fn flush_queue(self: *NativeD3D12Runtime) !u64 {
        if (!self.has_device) return 0;
        const start_ns = common_timing.now_ns();

        for (self.pending_uploads.items) |item| {
            d3d12_bridge_queue_execute_command_list(self.queue, item.cmd_list);
        }

        if (self.pending_uploads.items.len > 0 or self.has_deferred_submissions) {
            self.fence_value +|= 1;
            d3d12_bridge_queue_signal(self.queue, self.fence, self.fence_value);
            d3d12_bridge_fence_wait(self.fence, self.fence_value);
            self.has_deferred_submissions = false;
        }

        self.release_pending_uploads();
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn barrier(self: *NativeD3D12Runtime, queue_wait_mode: webgpu.QueueWaitMode) !u64 {
        _ = queue_wait_mode;
        const start_ns = common_timing.now_ns();
        if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
            _ = try self.flush_queue();
        }
        const end_ns = common_timing.now_ns();
        return common_timing.ns_delta(end_ns, start_ns);
    }

    pub fn prewarm_upload_path(self: *NativeD3D12Runtime, max_upload_bytes: u64, mode: webgpu.UploadBufferUsageMode) !void {
        if (max_upload_bytes == 0) return;
        try self.upload_bytes(@min(max_upload_bytes, MAX_UPLOAD_BYTES), mode);
        _ = try self.flush_queue();
    }

    fn bootstrap(self: *NativeD3D12Runtime) !void {
        self.device = d3d12_bridge_create_device() orelse return error.UnsupportedFeature;
        self.queue = d3d12_bridge_device_create_command_queue(self.device) orelse return error.InvalidState;
        self.fence = d3d12_bridge_device_create_fence(self.device) orelse return error.InvalidState;
        self.has_device = true;
    }

    fn release_pending_uploads(self: *NativeD3D12Runtime) void {
        for (self.pending_uploads.items) |item| {
            d3d12_bridge_release(item.cmd_list);
            d3d12_bridge_release(item.cmd_allocator);
            d3d12_bridge_release(item.src_buffer);
            d3d12_bridge_release(item.dst_buffer);
        }
        self.pending_uploads.clearRetainingCapacity();
    }
};
