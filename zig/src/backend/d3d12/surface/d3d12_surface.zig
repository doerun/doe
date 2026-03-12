const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");

extern fn d3d12_bridge_create_swap_chain(queue: ?*anyopaque, width: u32, height: u32, format: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_swap_chain_present(swap_chain: ?*anyopaque, sync_interval: u32) callconv(.c) c_int;
extern fn d3d12_bridge_swap_chain_get_buffer(swap_chain: ?*anyopaque, index: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_swap_chain_resize(swap_chain: ?*anyopaque, width: u32, height: u32, format: u32) callconv(.c) c_int;
extern fn d3d12_bridge_device_create_rtv_heap(device: ?*anyopaque, num_descriptors: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_rtv(device: ?*anyopaque, resource: ?*anyopaque, rtv_heap: ?*anyopaque, index: u32, format: u32) callconv(.c) void;
extern fn d3d12_bridge_device_create_texture_2d(device: ?*anyopaque, width: u32, height: u32, mip_levels: u32, format: u32, usage_flags: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

const SurfaceStatus = enum { created, configured, acquired };

pub const SurfaceEntry = struct {
    handle: u64,
    status: SurfaceStatus = .created,
    width: u32 = 0,
    height: u32 = 0,
    format: u32 = model.WGPUTextureFormat_RGBA8Unorm,
    swap_chain: ?*anyopaque = null,
    render_target: ?*anyopaque = null,
    rtv_heap: ?*anyopaque = null,
};

pub const SurfaceMap = std.AutoHashMapUnmanaged(u64, SurfaceEntry);

pub const SurfaceState = struct {
    map: SurfaceMap = .{},

    pub fn create_surface(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model.SurfaceCreateCommand) !u64 {
        const encode_start = common_timing.now_ns();
        self.map.put(allocator, cmd.handle, .{ .handle = cmd.handle }) catch return error.InvalidState;
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn surface_capabilities(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model.SurfaceCapabilitiesCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (!self.map.contains(cmd.handle)) {
            self.map.put(allocator, cmd.handle, .{ .handle = cmd.handle }) catch return error.InvalidState;
        }
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn configure_surface(
        self: *SurfaceState,
        device: ?*anyopaque,
        queue: ?*anyopaque,
        allocator: std.mem.Allocator,
        cmd: model.SurfaceConfigureCommand,
    ) !u64 {
        const encode_start = common_timing.now_ns();

        var entry = self.map.get(cmd.handle) orelse {
            self.map.put(allocator, cmd.handle, .{ .handle = cmd.handle }) catch return error.InvalidState;
            return common_timing.ns_delta(common_timing.now_ns(), encode_start);
        };

        if (entry.render_target) |rt| {
            d3d12_bridge_release(rt);
            entry.render_target = null;
        }

        const usage_render: u32 = @truncate(model.WGPUTextureUsage_RenderAttachment);
        entry.render_target = d3d12_bridge_device_create_texture_2d(device, cmd.width, cmd.height, 1, cmd.format, usage_render) orelse return error.InvalidState;

        if (entry.rtv_heap == null) {
            entry.rtv_heap = d3d12_bridge_device_create_rtv_heap(device, 1) orelse {
                d3d12_bridge_release(entry.render_target);
                entry.render_target = null;
                return error.InvalidState;
            };
        }
        d3d12_bridge_device_create_rtv(device, entry.render_target, entry.rtv_heap, 0, cmd.format);

        if (entry.swap_chain == null) {
            entry.swap_chain = d3d12_bridge_create_swap_chain(queue, cmd.width, cmd.height, cmd.format);
        }

        entry.width = cmd.width;
        entry.height = cmd.height;
        entry.format = cmd.format;
        entry.status = .configured;
        self.map.put(allocator, cmd.handle, entry) catch return error.InvalidState;

        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn acquire_surface(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model.SurfaceAcquireCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.getPtr(cmd.handle)) |entry| {
            entry.status = .acquired;
        } else {
            self.map.put(allocator, cmd.handle, .{ .handle = cmd.handle, .status = .acquired }) catch return error.InvalidState;
        }
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn present_surface(self: *SurfaceState, cmd: model.SurfacePresentCommand) !u64 {
        const submit_start = common_timing.now_ns();
        if (self.map.getPtr(cmd.handle)) |entry| {
            if (entry.swap_chain) |sc| {
                _ = d3d12_bridge_swap_chain_present(sc, 0);
            }
            entry.status = .configured;
        }
        return common_timing.ns_delta(common_timing.now_ns(), submit_start);
    }

    pub fn unconfigure_surface(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model.SurfaceUnconfigureCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.getPtr(cmd.handle)) |entry| {
            if (entry.render_target) |rt| {
                d3d12_bridge_release(rt);
                entry.render_target = null;
            }
            entry.status = .created;
        }
        _ = allocator;
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn release_surface(self: *SurfaceState, cmd: model.SurfaceReleaseCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.fetchRemove(cmd.handle)) |kv| {
            var entry = kv.value;
            if (entry.render_target) |rt| d3d12_bridge_release(rt);
            if (entry.rtv_heap) |h| d3d12_bridge_release(h);
            if (entry.swap_chain) |sc| d3d12_bridge_release(sc);
            entry.render_target = null;
            entry.rtv_heap = null;
            entry.swap_chain = null;
        }
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn deinit(self: *SurfaceState, allocator: std.mem.Allocator) void {
        var it = self.map.valueIterator();
        while (it.next()) |entry| {
            if (entry.render_target) |rt| d3d12_bridge_release(rt);
            if (entry.rtv_heap) |h| d3d12_bridge_release(h);
            if (entry.swap_chain) |sc| d3d12_bridge_release(sc);
        }
        self.map.deinit(allocator);
    }
};
