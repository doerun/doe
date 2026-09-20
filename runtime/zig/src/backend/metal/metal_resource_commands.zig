//! Command sampler lifecycle and validated host texture uploads.

const std = @import("std");
const copy_contract = @import("../../contracts/texture_copy.zig");
const formats = @import("../../contracts/texture_format.zig");
const values = @import("../../contracts/model/model_texture_value_types.zig");
const textures = @import("metal_texture_resources.zig");
const model_render_types = @import("../../contracts/model/model_render_types.zig");
const model_texture_types = @import("../../contracts/model/model_texture_types.zig");
const bridge = @import("metal_bridge_decls.zig");

const model = struct {
    pub const SamplerCreateCommand = model_render_types.SamplerCreateCommand;
    pub const SamplerDestroyCommand = model_render_types.SamplerDestroyCommand;
    pub const TextureDestroyCommand = model_texture_types.TextureDestroyCommand;
    pub const TextureQueryCommand = model_texture_types.TextureQueryCommand;
    pub const TextureWriteCommand = model_texture_types.TextureWriteCommand;
};

pub fn sampler_create(self: anytype, cmd: model.SamplerCreateCommand) !void {
    _ = try self.flush_queue();
    const h = try self.sampler_cache.acquire(self.device, cmd);
    errdefer if (!self.sampler_cache.release(h)) bridge.metal_bridge_release(h);
    const gop = try self.samplers.getOrPut(self.allocator, cmd.handle);
    if (gop.found_existing) {
        // Release old sampler — try cache first, fall back to deferred pool.
        const old = gop.value_ptr.*;
        if (!self.sampler_cache.release(old)) {
            self.deferred_pool.enqueue(old);
        }
    }
    gop.value_ptr.* = h;
}

pub fn sampler_destroy(self: anytype, cmd: model.SamplerDestroyCommand) !void {
    _ = try self.flush_queue();
    if (self.samplers.fetchRemove(cmd.handle)) |e| {
        // Try returning to sampler cache first (decrements ref count).
        // If not cache-managed, enqueue for batch release at next flush.
        if (!self.sampler_cache.release(e.value)) {
            self.deferred_pool.enqueue(e.value);
        }
    }
}

const Write = struct {
    descriptor: textures.Descriptor,
    copy: copy_contract.Copy,
    layout: ?copy_contract.Region,

    fn init(map: *const textures.Map, cmd: model.TextureWriteCommand) !Write {
        const descriptor = try textures.admit(map, cmd.texture, values.WGPUTextureUsage_CopyDst);
        const region = descriptor.region(cmd.texture);
        // Empty payload is the existing declaration-only command, not a zero-byte upload.
        if (cmd.data.len == 0) {
            if (cmd.texture.offset != 0) return error.TextureCopyRange;
            return .{ .descriptor = descriptor, .copy = region, .layout = null };
        }
        // replaceRegion cannot upload separately selected depth/stencil planes.
        if (formats.isDepthStencilFormat(descriptor.texture.format)) return error.UnsupportedFeature;
        return .{ .descriptor = descriptor, .copy = region, .layout = try copy_contract.validate(cmd.data.len, descriptor.texture, region, .buffer_to_texture, .native) };
    }
};

pub fn texture_write(self: anytype, cmd: model.TextureWriteCommand) !void {
    return writeWithBridge(self, cmd, bridge);
}

fn writeWithBridge(self: anytype, cmd: model.TextureWriteCommand, comptime native: type) !void {
    const write = try Write.init(&self.textures, cmd);
    // CPU replacement must not overtake earlier queued GPU reads or writes.
    if (write.layout != null) _ = try self.flush_queue();
    const texture = try textures.ensure(&self.textures, self.allocator, self.device, cmd.texture.handle, write.descriptor);
    const layout = write.layout orelse return;
    const copy = write.copy;
    const volume = write.descriptor.texture.dimension == values.WGPUTextureDimension_3D;
    const image_stride = @as(u64, layout.pitch) * layout.image_rows;
    const image_count = if (volume) 1 else copy.depth_or_layers;
    for (0..image_count) |layer| {
        const source_offset: usize = @intCast(copy.offset + image_stride * layer);
        if (native.metal_bridge_texture_write_region(texture, cmd.data[source_offset..].ptr, layout.pitch, layout.image_rows, 0, 0, 0, copy.mip, @intCast(layer), copy.width, copy.height, if (volume) copy.depth_or_layers else 1) == 0) return error.InvalidState;
    }
}

pub fn texture_query(self: anytype, cmd: model.TextureQueryCommand) !void {
    const texture = self.textures.get(cmd.handle) orelse return error.InvalidState;
    try texture.descriptor.checkQuery(cmd);
}

pub fn texture_destroy(self: anytype, cmd: model.TextureDestroyCommand) !void {
    _ = try self.flush_queue();
    if (self.textures.fetchRemove(cmd.handle)) |e| {
        self.deferred_pool.enqueue(e.value.handle);
    }
}

test "Metal texture writes validate last byte, array padding and volume mip extents" {
    const map: textures.Map = .{};
    var bytes: [156]u8 = undefined;
    var cmd = model.TextureWriteCommand{ .texture = .{ .handle = 1, .width = 4, .height = 4, .depth_or_array_layers = 2, .mip_level = 1, .format = values.WGPUTextureFormat_RGBA8Unorm, .bytes_per_row = 32, .rows_per_image = 3, .offset = 20 }, .data = &bytes };
    const write = try Write.init(&map, cmd);
    try std.testing.expectEqual(@as(u64, 136), write.layout.?.required_bytes);
    cmd.data = bytes[0..155];
    try std.testing.expectError(error.TextureCopyRange, Write.init(&map, cmd));
    cmd.data = &bytes;
    cmd.texture.dimension = values.WGPUTextureDimension_3D;
    const volume = try Write.init(&map, cmd);
    try std.testing.expectEqual(@as(u32, 1), volume.copy.depth_or_layers);
    cmd.texture.mip_level = 32;
    try std.testing.expectError(error.InvalidArgument, Write.init(&map, cmd));
    cmd.texture.mip_level = 1;
    cmd.texture.bytes_per_row = 4;
    try std.testing.expectError(error.TextureCopyLayout, Write.init(&map, cmd));
    cmd.texture.bytes_per_row = 32;
    cmd.texture.rows_per_image = 1;
    try std.testing.expectError(error.TextureCopyLayout, Write.init(&map, cmd));
}

test "Metal texture writes reject before side effects and retire before writing each array layer" {
    const Probe = struct {
        var retired = false;
        var writes: usize = 0;
        var fail_write = false;
        var output: [32]u8 = undefined;
        pub fn metal_bridge_texture_write_region(_: ?*anyopaque, source: *const anyopaque, pitch: u32, _: u32, _: u32, _: u32, _: u32, _: u32, layer: u32, width: u32, height: u32, depth: u32) c_int {
            std.testing.expect(retired and width == 2 and height == 2 and depth == 1) catch return 0;
            if (fail_write) return 0;
            const bytes: [*]const u8 = @ptrCast(source);
            for (0..2) |row| @memcpy(output[layer * 16 + row * 8 ..][0..8], bytes[row * pitch ..][0..8]);
            writes += 1;
            return 1;
        }
    };
    const Owner = struct {
        textures: textures.Map = .{},
        allocator: std.mem.Allocator = std.testing.allocator,
        device: ?*anyopaque = null,
        fail_wait: bool = false,
        pub fn flush_queue(self: *@This()) !u64 {
            if (self.fail_wait) return error.DeviceLost;
            Probe.retired = true;
            return 0;
        }
    };
    Probe.retired = false;
    Probe.writes = 0;
    Probe.fail_write = false;
    @memset(&Probe.output, 0);
    var owner = Owner{};
    defer owner.textures.deinit(owner.allocator);
    var token: u8 = 0;
    var bytes = [_]u8{255} ** 60;
    @memset(bytes[4..12], 17);
    @memset(bytes[16..24], 18);
    @memset(bytes[40..48], 83);
    @memset(bytes[52..60], 84);
    var cmd = model.TextureWriteCommand{ .texture = .{ .handle = 1, .width = 2, .height = 2, .depth_or_array_layers = 2, .format = values.WGPUTextureFormat_RGBA8Unorm, .offset = 4, .bytes_per_row = 12, .rows_per_image = 3 }, .data = bytes[0..59] };
    const descriptor = try textures.Descriptor.init(cmd.texture, values.WGPUTextureUsage_CopyDst);
    try owner.textures.put(owner.allocator, 1, .{ .handle = &token, .descriptor = descriptor });
    try std.testing.expectError(error.TextureCopyRange, writeWithBridge(&owner, cmd, Probe));
    try std.testing.expect(!Probe.retired and Probe.writes == 0);
    cmd.data = &bytes;
    owner.fail_wait = true;
    try std.testing.expectError(error.DeviceLost, writeWithBridge(&owner, cmd, Probe));
    try std.testing.expect(!Probe.retired and Probe.writes == 0);
    owner.fail_wait = false;
    try writeWithBridge(&owner, cmd, Probe);
    const expected = [_]u8{17} ** 8 ++ [_]u8{18} ** 8 ++ [_]u8{83} ** 8 ++ [_]u8{84} ** 8;
    try std.testing.expectEqualSlices(u8, &expected, &Probe.output);
    try std.testing.expectEqual(@as(usize, 2), Probe.writes);
    Probe.fail_write = true;
    try std.testing.expectError(error.InvalidState, writeWithBridge(&owner, cmd, Probe));
}
