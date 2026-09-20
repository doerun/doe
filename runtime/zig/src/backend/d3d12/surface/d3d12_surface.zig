const std = @import("std");
const model_gpu_types = @import("../../../contracts/model/model_texture_value_types.zig");
const model_surface_control_types = @import("../../../contracts/model/model_surface_control_types.zig");
const common_timing = @import("../../common/timing.zig");
const bridge = @import("../d3d12_bridge_decls.zig");

const SurfaceStatus = enum { created, configured, acquired };

pub const SurfaceEntry = struct {
    handle: u64,
    status: SurfaceStatus = .created,
    width: u32 = 0,
    height: u32 = 0,
    format: u32 = model_gpu_types.WGPUTextureFormat_RGBA8Unorm,
    alpha_mode: u32 = 0x00000001,
    tone_mapping_mode: u32 = model_surface_control_types.WGPUCanvasToneMappingMode_Standard,
    swap_chain: ?*anyopaque = null,
    render_target: ?*anyopaque = null,
    rtv_heap: ?*anyopaque = null,
};

pub const SurfaceMap = std.AutoHashMapUnmanaged(u64, SurfaceEntry);

pub const SurfaceState = struct {
    map: SurfaceMap = .{},

    pub fn create_surface(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model_surface_control_types.SurfaceCreateCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.contains(cmd.handle)) return error.InvalidArgument;
        try self.map.put(allocator, cmd.handle, .{ .handle = cmd.handle });
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn surface_capabilities(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model_surface_control_types.SurfaceCapabilitiesCommand) !u64 {
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
        cmd: model_surface_control_types.SurfaceConfigureCommand,
    ) !u64 {
        _ = allocator;
        return self.configure_with_bridge(device, queue, cmd, bridge.c);
    }

    fn configure_with_bridge(self: *SurfaceState, device: ?*anyopaque, queue: ?*anyopaque, cmd: model_surface_control_types.SurfaceConfigureCommand, comptime native: type) !u64 {
        const encode_start = common_timing.now_ns();
        if (cmd.width == 0 or cmd.height == 0) return error.InvalidArgument;
        const entry = self.map.getPtr(cmd.handle) orelse return error.InvalidState;
        if (entry.status == .acquired) return error.InvalidState;
        const render_target = native.d3d12_bridge_device_create_texture_2d(device, cmd.width, cmd.height, 1, cmd.format, @intCast(model_gpu_types.WGPUTextureUsage_RenderAttachment)) orelse return error.InvalidState;
        errdefer native.d3d12_bridge_release(render_target);
        const rtv_heap = native.d3d12_bridge_device_create_rtv_heap(device, 1) orelse return error.InvalidState;
        errdefer native.d3d12_bridge_release(rtv_heap);
        const swap_chain = native.d3d12_bridge_create_swap_chain(queue, cmd.width, cmd.height, cmd.format, cmd.alpha_mode, cmd.tone_mapping_mode) orelse return error.InvalidState;
        errdefer native.d3d12_bridge_release(swap_chain);
        native.d3d12_bridge_device_create_rtv(device, render_target, rtv_heap, 0, cmd.format);
        if (entry.render_target) |handle| native.d3d12_bridge_release(handle);
        if (entry.rtv_heap) |handle| native.d3d12_bridge_release(handle);
        if (entry.swap_chain) |handle| native.d3d12_bridge_release(handle);
        entry.* = .{ .handle = cmd.handle, .width = cmd.width, .height = cmd.height, .format = cmd.format, .alpha_mode = cmd.alpha_mode, .tone_mapping_mode = cmd.tone_mapping_mode, .status = .configured, .render_target = render_target, .rtv_heap = rtv_heap, .swap_chain = swap_chain };
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn acquire_surface(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model_surface_control_types.SurfaceAcquireCommand) !u64 {
        const encode_start = common_timing.now_ns();
        _ = allocator;
        const entry = self.map.getPtr(cmd.handle) orelse return error.InvalidState;
        if (entry.status != .configured) return error.InvalidState;
        entry.status = .acquired;
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn present_surface(self: *SurfaceState, cmd: model_surface_control_types.SurfacePresentCommand) !u64 {
        const submit_start = common_timing.now_ns();
        const entry = self.map.getPtr(cmd.handle) orelse return error.InvalidState;
        if (entry.status != .acquired) return error.InvalidState;
        if (entry.swap_chain) |sc| {
            if (bridge.c.d3d12_bridge_swap_chain_present(sc, 0) != 0) return error.InvalidState;
        } else {
            return error.InvalidState;
        }
        entry.status = .configured;
        return common_timing.ns_delta(common_timing.now_ns(), submit_start);
    }

    pub fn unconfigure_surface(self: *SurfaceState, allocator: std.mem.Allocator, cmd: model_surface_control_types.SurfaceUnconfigureCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.getPtr(cmd.handle)) |entry| {
            if (entry.render_target) |rt| {
                bridge.c.d3d12_bridge_release(rt);
                entry.render_target = null;
            }
            if (entry.swap_chain) |sc| {
                bridge.c.d3d12_bridge_release(sc);
                entry.swap_chain = null;
            }
            if (entry.rtv_heap) |heap| {
                bridge.c.d3d12_bridge_release(heap);
                entry.rtv_heap = null;
            }
            entry.status = .created;
        }
        _ = allocator;
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn release_surface(self: *SurfaceState, cmd: model_surface_control_types.SurfaceReleaseCommand) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.fetchRemove(cmd.handle)) |kv| {
            var entry = kv.value;
            if (entry.render_target) |rt| bridge.c.d3d12_bridge_release(rt);
            if (entry.rtv_heap) |h| bridge.c.d3d12_bridge_release(h);
            if (entry.swap_chain) |sc| bridge.c.d3d12_bridge_release(sc);
            entry.render_target = null;
            entry.rtv_heap = null;
            entry.swap_chain = null;
        }
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn deinit(self: *SurfaceState, allocator: std.mem.Allocator) void {
        var it = self.map.valueIterator();
        while (it.next()) |entry| {
            if (entry.render_target) |rt| bridge.c.d3d12_bridge_release(rt);
            if (entry.rtv_heap) |h| bridge.c.d3d12_bridge_release(h);
            if (entry.swap_chain) |sc| bridge.c.d3d12_bridge_release(sc);
        }
        self.map.deinit(allocator);
        self.* = .{};
    }
};

test "D3D12 surface reconfiguration preserves old ownership on every native failure" {
    const Native = struct {
        var stage: usize = 0;
        var fail_at: usize = 0;
        var released: usize = 0;
        var old_released: usize = 0;
        fn acquire() ?*anyopaque {
            stage += 1;
            return if (stage == fail_at) null else @ptrFromInt(16 + stage);
        }
        fn d3d12_bridge_device_create_texture_2d(_: ?*anyopaque, _: u32, _: u32, _: u32, _: u32, _: u32) ?*anyopaque {
            return acquire();
        }
        fn d3d12_bridge_device_create_rtv_heap(_: ?*anyopaque, _: u32) ?*anyopaque {
            return acquire();
        }
        fn d3d12_bridge_create_swap_chain(_: ?*anyopaque, _: u32, _: u32, _: u32, _: u32, _: u32) ?*anyopaque {
            return acquire();
        }
        fn d3d12_bridge_device_create_rtv(_: ?*anyopaque, _: ?*anyopaque, _: ?*anyopaque, _: u32, _: u32) void {}
        fn d3d12_bridge_release(handle: ?*anyopaque) void {
            if (@intFromPtr(handle) < 16) old_released += 1 else released += 1;
        }
    };
    var state: SurfaceState = .{};
    defer state.map.deinit(std.testing.allocator);
    try state.map.put(std.testing.allocator, 1, .{ .handle = 1, .status = .configured, .width = 4, .height = 4, .render_target = @ptrFromInt(1), .rtv_heap = @ptrFromInt(2), .swap_chain = @ptrFromInt(3) });
    try std.testing.expectError(error.InvalidArgument, state.create_surface(std.testing.allocator, .{ .handle = 1 }));
    for (1..4) |failure| {
        Native.stage = 0;
        Native.fail_at = failure;
        Native.released = 0;
        try std.testing.expectError(error.InvalidState, state.configure_with_bridge(null, null, .{ .handle = 1, .width = 8, .height = 8 }, Native));
        try std.testing.expectEqual(failure - 1, Native.released);
        try std.testing.expectEqual(@as(usize, 0), Native.old_released);
        try std.testing.expectEqual(@as(u32, 4), state.map.get(1).?.width);
    }
    Native.stage = 0;
    Native.fail_at = 0;
    _ = try state.configure_with_bridge(null, null, .{ .handle = 1, .width = 8, .height = 8 }, Native);
    try std.testing.expectEqual(@as(usize, 3), Native.old_released);
    try std.testing.expectEqual(@as(u32, 8), state.map.get(1).?.width);
    try std.testing.expectError(error.InvalidState, state.configure_with_bridge(null, null, .{ .handle = 2, .width = 8, .height = 8 }, Native));
    _ = try state.acquire_surface(std.testing.allocator, .{ .handle = 1 });
    try std.testing.expectError(error.InvalidState, state.configure_with_bridge(null, null, .{ .handle = 1, .width = 8, .height = 8 }, Native));
}
