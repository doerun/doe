const std = @import("std");
const model_render_types = @import("../../../contracts/model/model_render_types.zig");
const common_timing = @import("../../common/timing.zig");
const bridge = @import("../d3d12_bridge_decls.zig");

const MAX_SAMPLERS: u32 = 256;

pub const SamplerEntry = struct {
    handle: u64,
    address_mode_u: u32,
    address_mode_v: u32,
    address_mode_w: u32,
    mag_filter: u32,
    min_filter: u32,
    mipmap_filter: u32,
    lod_min_clamp: f32,
    lod_max_clamp: f32,
    compare: u32,
    max_anisotropy: u16,
    heap_index: u32,
};

pub const SamplerMap = std.AutoHashMapUnmanaged(u64, SamplerEntry);

pub const SamplerState = struct {
    map: SamplerMap = .{},
    heap: ?*anyopaque = null,
    next_index: u32 = 0,
    free_indices: [MAX_SAMPLERS]u32 = undefined,
    free_count: usize = 0,

    pub fn sampler_create(
        self: *SamplerState,
        device: ?*anyopaque,
        allocator: std.mem.Allocator,
        cmd: model_render_types.SamplerCreateCommand,
    ) !u64 {
        return self.create_with_bridge(device, allocator, cmd, bridge.c);
    }

    fn create_with_bridge(self: *SamplerState, device: ?*anyopaque, allocator: std.mem.Allocator, cmd: model_render_types.SamplerCreateCommand, comptime native: type) !u64 {
        const encode_start = common_timing.now_ns();

        const existing = self.map.get(cmd.handle);
        if (existing == null) try self.map.ensureUnusedCapacity(allocator, 1);
        const index = if (existing) |entry| entry.heap_index else if (self.free_count > 0)
            self.free_indices[self.free_count - 1]
        else if (self.next_index < MAX_SAMPLERS) self.next_index else return error.UnsupportedFeature;
        if (self.heap == null) {
            self.heap = native.d3d12_bridge_device_create_sampler_heap(device, MAX_SAMPLERS) orelse return error.InvalidState;
        }

        const entry = SamplerEntry{
            .handle = cmd.handle,
            .address_mode_u = cmd.address_mode_u,
            .address_mode_v = cmd.address_mode_v,
            .address_mode_w = cmd.address_mode_w,
            .mag_filter = cmd.mag_filter,
            .min_filter = cmd.min_filter,
            .mipmap_filter = cmd.mipmap_filter,
            .lod_min_clamp = cmd.lod_min_clamp,
            .lod_max_clamp = cmd.lod_max_clamp,
            .compare = cmd.compare,
            .max_anisotropy = cmd.max_anisotropy,
            .heap_index = index,
        };
        native.d3d12_bridge_device_create_sampler_in_heap(device, self.heap, index, cmd.min_filter, cmd.mag_filter, cmd.mipmap_filter, cmd.address_mode_u, cmd.address_mode_v, cmd.address_mode_w, cmd.lod_min_clamp, cmd.lod_max_clamp, cmd.compare, cmd.max_anisotropy);
        self.map.putAssumeCapacity(cmd.handle, entry);
        if (existing == null) {
            if (self.free_count > 0) self.free_count -= 1 else self.next_index += 1;
        }

        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn sampler_destroy(
        self: *SamplerState,
        cmd: model_render_types.SamplerDestroyCommand,
    ) !u64 {
        const encode_start = common_timing.now_ns();
        if (self.map.fetchRemove(cmd.handle)) |removed| {
            self.free_indices[self.free_count] = removed.value.heap_index;
            self.free_count += 1;
        }
        return common_timing.ns_delta(common_timing.now_ns(), encode_start);
    }

    pub fn deinit(self: *SamplerState, allocator: std.mem.Allocator) void {
        self.map.deinit(allocator);
        if (self.heap) |h| {
            bridge.c.d3d12_bridge_release(h);
            self.heap = null;
        }
        self.* = .{};
    }
};

test "D3D12 sampler slots survive replacement and are reusable after capacity is reached" {
    const Native = struct {
        var count: usize = 0;
        var last_index: u32 = 0;
        fn d3d12_bridge_device_create_sampler_heap(_: ?*anyopaque, _: u32) ?*anyopaque {
            return @ptrFromInt(1);
        }
        fn d3d12_bridge_device_create_sampler_in_heap(_: ?*anyopaque, _: ?*anyopaque, index: u32, _: u32, _: u32, _: u32, _: u32, _: u32, _: u32, _: f32, _: f32, _: u32, _: u16) void {
            count += 1;
            last_index = index;
        }
    };
    var state: SamplerState = .{};
    defer state.map.deinit(std.testing.allocator);
    for (0..MAX_SAMPLERS) |handle| _ = try state.create_with_bridge(null, std.testing.allocator, .{ .handle = handle }, Native);
    try std.testing.expectError(error.UnsupportedFeature, state.create_with_bridge(null, std.testing.allocator, .{ .handle = MAX_SAMPLERS }, Native));
    _ = try state.create_with_bridge(null, std.testing.allocator, .{ .handle = 5 }, Native);
    try std.testing.expectEqual(@as(u32, 5), Native.last_index);
    _ = try state.sampler_destroy(.{ .handle = 5 });
    _ = try state.sampler_destroy(.{ .handle = 5 });
    _ = try state.create_with_bridge(null, std.testing.allocator, .{ .handle = MAX_SAMPLERS }, Native);
    try std.testing.expectEqual(@as(u32, 5), Native.last_index);
    try std.testing.expectEqual(@as(usize, 0), state.free_count);
    try std.testing.expectEqual(MAX_SAMPLERS, state.map.count());
    try std.testing.expectEqual(@as(usize, MAX_SAMPLERS + 2), Native.count);
}
