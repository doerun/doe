//! Command-owned textures: admitted descriptors, native acquisition and reuse.
const std = @import("std");
const values = @import("../../contracts/model/model_texture_value_types.zig");
const model = @import("../../contracts/model/model_resource_types.zig");
const queries = @import("../../contracts/model/model_texture_types.zig");
const copy = @import("../../contracts/texture_copy.zig");
const formats = @import("../../contracts/texture_format_layout.zig");
const bridge = @import("metal_bridge_decls.zig");

pub const Entry = struct {
    handle: *anyopaque,
    descriptor: Descriptor,
};
pub const Map = std.AutoHashMapUnmanaged(u64, Entry);

pub const Descriptor = struct {
    texture: copy.Texture,
    usage: u32,
    view_dimension: u32,

    pub fn init(resource: model.CopyTextureResource, required_usage: u64) !Descriptor {
        if (resource.width == 0 or resource.height == 0 or resource.depth_or_array_layers == 0 or resource.mip_level >= @bitSizeOf(u32)) return error.InvalidArgument;
        const dimension = if (resource.dimension == values.WGPUTextureDimension_Undefined) values.WGPUTextureDimension_2D else resource.dimension;
        switch (dimension) {
            values.WGPUTextureDimension_1D => if (resource.height != 1 or resource.depth_or_array_layers != 1) return error.InvalidArgument,
            values.WGPUTextureDimension_2D, values.WGPUTextureDimension_3D => {},
            else => return error.UnsupportedFeature,
        }
        const max_dimension = @max(resource.width, @max(resource.height, if (dimension == values.WGPUTextureDimension_3D) resource.depth_or_array_layers else 1));
        if (resource.mip_level > std.math.log2_int(u32, max_dimension)) return error.InvalidArgument;
        if (resource.sample_count != 1) return error.UnsupportedFeature;
        _ = try formats.bytes_per_pixel(resource.format);
        const block = formats.copy_block_extent(resource.format);
        if (resource.width % block[0] != 0 or resource.height % block[1] != 0) return error.InvalidArgument;
        if (block[0] > 1 and dimension != values.WGPUTextureDimension_2D) return error.UnsupportedFeature;
        const usage = if (resource.usage == 0) required_usage else resource.usage;
        const allowed_usage = values.WGPUTextureUsage_CopySrc | values.WGPUTextureUsage_CopyDst | values.WGPUTextureUsage_TextureBinding | values.WGPUTextureUsage_StorageBinding | values.WGPUTextureUsage_RenderAttachment;
        if (usage & ~allowed_usage != 0 or usage & required_usage != required_usage) return error.InvalidArgument;
        const view = switch (dimension) {
            values.WGPUTextureDimension_1D => values.WGPUTextureViewDimension_1D,
            values.WGPUTextureDimension_3D => values.WGPUTextureViewDimension_3D,
            else => if (resource.depth_or_array_layers > 1) values.WGPUTextureViewDimension_2DArray else values.WGPUTextureViewDimension_2D,
        };
        // This command owns a texture, not a separately created cube/reinterpreted view.
        if (resource.view_dimension != values.WGPUTextureViewDimension_Undefined and resource.view_dimension != view) return error.UnsupportedFeature;
        return .{ .texture = .{ .width = resource.width, .height = resource.height, .layers = resource.depth_or_array_layers, .mip_levels = resource.mip_level + 1, .samples = resource.sample_count, .dimension = dimension, .format = resource.format }, .usage = @intCast(usage), .view_dimension = view };
    }

    pub fn region(self: Descriptor, resource: model.CopyTextureResource) copy.Copy {
        const shift: u5 = @intCast(resource.mip_level);
        return .{
            .offset = resource.offset,
            .bytes_per_row = resource.bytes_per_row,
            .rows_per_image = resource.rows_per_image,
            .mip = resource.mip_level,
            .width = @max(self.texture.width >> shift, 1),
            .height = @max(self.texture.height >> shift, 1),
            .depth_or_layers = if (self.texture.dimension == values.WGPUTextureDimension_3D) @max(self.texture.layers >> shift, 1) else self.texture.layers,
            .aspect = resource.aspect,
        };
    }

    fn compatible(self: Descriptor, requested: Descriptor, explicit_usage: bool) bool {
        const a = self.texture;
        const b = requested.texture;
        return a.width == b.width and a.height == b.height and a.layers == b.layers and a.mip_levels >= b.mip_levels and a.samples == b.samples and a.dimension == b.dimension and a.format == b.format and self.view_dimension == requested.view_dimension and
            (if (explicit_usage) self.usage == requested.usage else self.usage & requested.usage == requested.usage);
    }

    pub fn checkQuery(self: Descriptor, query: queries.TextureQueryCommand) !void {
        const texture = self.texture;
        if (query.expected_width) |v| if (texture.width != v) return error.InvalidState;
        if (query.expected_height) |v| if (texture.height != v) return error.InvalidState;
        if (query.expected_depth_or_array_layers) |v| if (texture.layers != v) return error.InvalidState;
        if (query.expected_format) |v| if (texture.format != v) return error.InvalidState;
        if (query.expected_dimension) |v| if (texture.dimension != v) return error.InvalidState;
        if (query.expected_view_dimension) |v| if (self.view_dimension != v) return error.InvalidState;
        if (query.expected_sample_count) |v| if (texture.samples != v) return error.InvalidState;
        if (query.expected_usage) |v| if (self.usage & v != v) return error.InvalidState;
    }
};

/// Validate both new declarations and reused identities before native side effects.
pub fn admit(textures: *const Map, resource: model.CopyTextureResource, required_usage: u64) !Descriptor {
    const requested = try Descriptor.init(resource, required_usage);
    if (textures.get(resource.handle)) |entry| {
        if (!entry.descriptor.compatible(requested, resource.usage != 0)) return error.InvalidArgument;
        return entry.descriptor;
    }
    return requested;
}

/// The map owns the native reference; acquisition failure leaves no published entry.
pub fn ensure(textures: *Map, allocator: std.mem.Allocator, device: ?*anyopaque, id: u64, descriptor: Descriptor) !*anyopaque {
    return ensureWithBridge(textures, allocator, device, id, descriptor, bridge);
}

fn ensureWithBridge(textures: *Map, allocator: std.mem.Allocator, device: ?*anyopaque, id: u64, descriptor: Descriptor, comptime native: type) !*anyopaque {
    if (textures.get(id)) |entry| {
        if (!entry.descriptor.compatible(descriptor, true)) return error.InvalidArgument;
        return entry.handle;
    }
    try textures.ensureUnusedCapacity(allocator, 1);
    const t = descriptor.texture;
    const handle = native.metal_bridge_device_new_texture(device, t.width, t.height, t.layers, t.mip_levels, t.samples, t.format, descriptor.usage, t.dimension) orelse return error.InvalidState;
    textures.putAssumeCapacity(id, .{ .handle = handle, .descriptor = descriptor });
    return handle;
}

test "Metal texture identities reject changed descriptors and queries check exact expectations" {
    var textures: Map = .{};
    defer textures.deinit(std.testing.allocator);
    var token: u8 = 0;
    var resource = model.CopyTextureResource{ .handle = 1, .width = 8, .height = 4, .depth_or_array_layers = 2, .mip_level = 1, .format = values.WGPUTextureFormat_RGBA8Unorm, .usage = values.WGPUTextureUsage_CopySrc | values.WGPUTextureUsage_CopyDst };
    const descriptor = try admit(&textures, resource, values.WGPUTextureUsage_CopyDst);
    try textures.put(std.testing.allocator, resource.handle, .{ .handle = &token, .descriptor = descriptor });
    resource.mip_level = 0;
    _ = try admit(&textures, resource, values.WGPUTextureUsage_CopySrc);
    try descriptor.checkQuery(.{ .handle = 1, .expected_depth_or_array_layers = 2, .expected_view_dimension = values.WGPUTextureViewDimension_2DArray });
    try std.testing.expectError(error.InvalidState, descriptor.checkQuery(.{ .handle = 1, .expected_depth_or_array_layers = 1 }));
    try std.testing.expectError(error.InvalidState, descriptor.checkQuery(.{ .handle = 1, .expected_format = values.WGPUTextureFormat_R8Unorm }));
    try descriptor.checkQuery(.{ .handle = 1, .expected_usage = values.WGPUTextureUsage_CopySrc });
    try std.testing.expectError(error.InvalidState, descriptor.checkQuery(.{ .handle = 1, .expected_usage = values.WGPUTextureUsage_StorageBinding }));
    resource.width = 4;
    try std.testing.expectError(error.InvalidArgument, admit(&textures, resource, values.WGPUTextureUsage_CopySrc));
    resource.width = 8;
    resource.usage = values.WGPUTextureUsage_CopyDst;
    try std.testing.expectError(error.InvalidArgument, admit(&textures, resource, values.WGPUTextureUsage_CopySrc));
    resource.mip_level = 32;
    try std.testing.expectError(error.InvalidArgument, admit(&textures, resource, values.WGPUTextureUsage_CopyDst));
}

test "Metal texture publication reserves ownership before native acquisition" {
    const Probe = struct {
        var acquired: usize = 0;
        var token: u8 = 0;
        var fail_native = false;
        pub fn metal_bridge_device_new_texture(_: ?*anyopaque, _: u32, _: u32, _: u32, _: u32, _: u32, _: u32, _: u32, _: u32) ?*anyopaque {
            acquired += 1;
            return if (fail_native) null else &token;
        }
    };
    Probe.acquired = 0;
    Probe.fail_native = false;
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    var textures: Map = .{};
    defer textures.deinit(std.testing.allocator);
    const descriptor = try Descriptor.init(.{ .handle = 1, .format = values.WGPUTextureFormat_RGBA8Unorm }, values.WGPUTextureUsage_CopyDst);
    try std.testing.expectError(error.OutOfMemory, ensureWithBridge(&textures, failing.allocator(), null, 1, descriptor, Probe));
    try std.testing.expectEqual(@as(usize, 0), Probe.acquired);
    Probe.fail_native = true;
    try std.testing.expectError(error.InvalidState, ensureWithBridge(&textures, std.testing.allocator, null, 1, descriptor, Probe));
    try std.testing.expectEqual(@as(u32, 0), textures.count());
    Probe.fail_native = false;
    _ = try ensureWithBridge(&textures, std.testing.allocator, null, 1, descriptor, Probe);
    _ = try ensureWithBridge(&textures, std.testing.allocator, null, 1, descriptor, Probe);
    try std.testing.expectEqual(@as(usize, 2), Probe.acquired);
}
