const std = @import("std");
const values = @import("model/model_texture_value_types.zig");
const formats = @import("texture_format.zig");
const layout = @import("texture_format_layout.zig");
const texture_contract = @import("texture.zig");

pub const Direction = enum { buffer_to_texture, texture_to_buffer };
pub const Alignment = enum { webgpu, native };
pub const Aspect = enum { color, depth, stencil };
pub const ROW_ALIGNMENT: u32 = 256;
pub const DEPTH_STENCIL_OFFSET_ALIGNMENT: u32 = 4;
pub const STRIDE_UNDEFINED: u32 = std.math.maxInt(u32);
pub const Error = error{ TextureCopyRange, TextureCopyLayout, TextureCopyAspect, TextureCopyUnsupported };

pub const Texture = struct {
    width: u32,
    height: u32,
    layers: u32,
    mip_levels: u32,
    samples: u32,
    dimension: u32,
    format: u32,
};

pub const Copy = struct {
    offset: u64,
    bytes_per_row: u32,
    rows_per_image: u32,
    mip: u32,
    width: u32,
    height: u32,
    depth_or_layers: u32,
    origin: [3]u32 = .{ 0, 0, 0 },
    aspect: u32 = values.WGPUTextureAspect_All,
};

pub const Region = struct {
    aspect: Aspect,
    pitch: u32,
    image_rows: u32,
    row_length: u32,
    image_height: u32,
};

pub fn validate(buffer_size: u64, texture: Texture, copy: Copy, direction: Direction, alignment: Alignment) Error!Region {
    if (copy.mip >= texture.mip_levels or copy.mip >= @bitSizeOf(u32) or texture.samples != 1)
        return error.TextureCopyRange;
    const shift: u5 = @intCast(copy.mip);
    const is_3d = texture.dimension == values.WGPUTextureDimension_3D;
    const block = layout.copy_block_extent(texture.format);
    var extent = [3]u32{ @max(texture.width >> shift, 1), @max(texture.height >> shift, 1), if (is_3d) @max(texture.layers >> shift, 1) else texture.layers };
    const virtual_extent = extent;
    extent[0] = std.math.cast(u32, (std.math.divCeil(u64, extent[0], block[0]) catch unreachable) * block[0]) orelse return error.TextureCopyRange;
    extent[1] = std.math.cast(u32, (std.math.divCeil(u64, extent[1], block[1]) catch unreachable) * block[1]) orelse return error.TextureCopyRange;
    const size = [3]u32{ copy.width, copy.height, copy.depth_or_layers };
    for (copy.origin, size, extent) |origin, count, bound| {
        if (origin > bound or count > bound - origin or origin > std.math.maxInt(i32)) return error.TextureCopyRange;
    }
    const aspect = try resolveAspect(texture.format, copy.aspect, direction);
    const bytes = if (aspect == .stencil) 1 else if (aspect == .depth and texture.format == values.WGPUTextureFormat_Depth32FloatStencil8) 4 else layout.bytes_per_pixel(texture.format) catch return error.TextureCopyUnsupported;
    const depth_stencil = formats.isDepthStencilFormat(texture.format);
    if (depth_stencil and (copy.width != extent[0] or copy.height != extent[1])) return error.TextureCopyRange;
    const offset_alignment = if (depth_stencil) DEPTH_STENCIL_OFFSET_ALIGNMENT else bytes;
    if (copy.origin[0] % block[0] != 0 or copy.origin[1] % block[1] != 0 or
        (copy.width % block[0] != 0 and (alignment == .webgpu or copy.width != virtual_extent[0] -| copy.origin[0])) or
        (copy.height % block[1] != 0 and (alignment == .webgpu or copy.height != virtual_extent[1] -| copy.origin[1])) or
        copy.offset % offset_alignment != 0) return error.TextureCopyLayout;
    const columns = std.math.divCeil(u64, copy.width, block[0]) catch unreachable;
    const rows = std.math.divCeil(u64, copy.height, block[1]) catch unreachable;
    const row_bytes = columns * bytes;
    const pitch_missing = copy.bytes_per_row == STRIDE_UNDEFINED or (alignment == .native and copy.bytes_per_row == 0);
    const image_rows_missing = copy.rows_per_image == STRIDE_UNDEFINED or (alignment == .native and copy.rows_per_image == 0);
    if (alignment == .webgpu) {
        if (pitch_missing and (rows > 1 or copy.depth_or_layers > 1)) return error.TextureCopyLayout;
        if (image_rows_missing and copy.depth_or_layers > 1) return error.TextureCopyLayout;
        if (!pitch_missing and copy.bytes_per_row % ROW_ALIGNMENT != 0) return error.TextureCopyLayout;
    }
    const pitch = if (pitch_missing) row_bytes else copy.bytes_per_row;
    const image_rows = if (image_rows_missing) rows else copy.rows_per_image;
    if (pitch < row_bytes or pitch % bytes != 0 or image_rows < rows) return error.TextureCopyLayout;
    var required: u64 = 0;
    if (copy.depth_or_layers != 0) {
        const image_stride = std.math.mul(u64, pitch, image_rows) catch return error.TextureCopyRange;
        required = std.math.mul(u64, image_stride, copy.depth_or_layers - 1) catch return error.TextureCopyRange;
        if (rows != 0) {
            required = std.math.add(u64, required, std.math.mul(u64, pitch, rows - 1) catch return error.TextureCopyRange) catch return error.TextureCopyRange;
            required = std.math.add(u64, required, row_bytes) catch return error.TextureCopyRange;
        }
    }
    if (copy.offset > buffer_size or required > buffer_size - copy.offset) return error.TextureCopyRange;
    return .{
        .aspect = aspect,
        .pitch = std.math.cast(u32, pitch) orelse return error.TextureCopyRange,
        .image_rows = std.math.cast(u32, image_rows) orelse return error.TextureCopyRange,
        .row_length = std.math.cast(u32, (pitch / bytes) * block[0]) orelse return error.TextureCopyRange,
        .image_height = std.math.cast(u32, image_rows * block[1]) orelse return error.TextureCopyRange,
    };
}

fn resolveAspect(format: u32, requested: u32, direction: Direction) Error!Aspect {
    const aspect = if (requested == values.WGPUTextureAspect_Undefined) values.WGPUTextureAspect_All else requested;
    if (!texture_contract.aspectMatches(format, aspect)) return error.TextureCopyAspect;
    if (!formats.isDepthStencilFormat(format)) return .color;
    const combined = format == values.WGPUTextureFormat_Depth24PlusStencil8 or format == values.WGPUTextureFormat_Depth32FloatStencil8;
    if (combined and aspect == values.WGPUTextureAspect_All) return error.TextureCopyAspect;
    if (aspect == values.WGPUTextureAspect_StencilOnly or format == values.WGPUTextureFormat_Stencil8) return .stencil;
    if (format == values.WGPUTextureFormat_Depth24Plus or format == values.WGPUTextureFormat_Depth24PlusStencil8) return error.TextureCopyUnsupported;
    if (direction == .buffer_to_texture and (format == values.WGPUTextureFormat_Depth32Float or format == values.WGPUTextureFormat_Depth32FloatStencil8)) return error.TextureCopyAspect;
    return .depth;
}

test "copy regions preserve array and volume origins and reject bounds before arithmetic" {
    var texture = Texture{ .width = 8, .height = 8, .layers = 4, .mip_levels = 3, .samples = 1, .dimension = values.WGPUTextureDimension_2D, .format = values.WGPUTextureFormat_RGBA8Unorm };
    var copy = Copy{ .offset = 16, .bytes_per_row = 256, .rows_per_image = 2, .mip = 1, .width = 2, .height = 2, .depth_or_layers = 2, .origin = .{ 2, 1, 2 } };
    const required = 16 + 512 + 256 + 8;
    const region = try validate(required, texture, copy, .buffer_to_texture, .webgpu);
    try std.testing.expectEqual(@as(u32, 64), region.row_length);
    try std.testing.expectError(error.TextureCopyRange, validate(required - 1, texture, copy, .buffer_to_texture, .webgpu));
    texture.dimension = values.WGPUTextureDimension_3D;
    try std.testing.expectError(error.TextureCopyRange, validate(required, texture, copy, .buffer_to_texture, .webgpu));
    copy.origin[2] = 0;
    _ = try validate(required, texture, copy, .texture_to_buffer, .webgpu);
    copy.origin[0] = std.math.maxInt(u32);
    try std.testing.expectError(error.TextureCopyRange, validate(required, texture, copy, .texture_to_buffer, .webgpu));
}

test "depth stencil copies select exactly one legal plane with its own footprint" {
    var texture = Texture{ .width = 4, .height = 1, .layers = 1, .mip_levels = 1, .samples = 1, .dimension = values.WGPUTextureDimension_2D, .format = values.WGPUTextureFormat_Depth32FloatStencil8 };
    var copy = Copy{ .offset = 0, .bytes_per_row = STRIDE_UNDEFINED, .rows_per_image = STRIDE_UNDEFINED, .mip = 0, .width = 4, .height = 1, .depth_or_layers = 1 };
    try std.testing.expectError(error.TextureCopyAspect, validate(16, texture, copy, .texture_to_buffer, .webgpu));
    copy.aspect = values.WGPUTextureAspect_StencilOnly;
    try std.testing.expectEqual(Aspect.stencil, (try validate(4, texture, copy, .buffer_to_texture, .webgpu)).aspect);
    copy.aspect = values.WGPUTextureAspect_DepthOnly;
    try std.testing.expectEqual(@as(u32, 16), (try validate(16, texture, copy, .texture_to_buffer, .webgpu)).pitch);
    try std.testing.expectError(error.TextureCopyAspect, validate(16, texture, copy, .buffer_to_texture, .webgpu));
    texture.format = values.WGPUTextureFormat_RGBA8Unorm;
    try std.testing.expectError(error.TextureCopyAspect, validate(16, texture, copy, .texture_to_buffer, .webgpu));
}

test "strict compressed copies use physical mip bounds and empty copies retain stride validation" {
    var texture = Texture{ .width = 8, .height = 8, .layers = 2, .mip_levels = 4, .samples = 1, .dimension = values.WGPUTextureDimension_2D, .format = values.WGPUTextureFormat_BC1RGBAUnorm };
    var copy = Copy{ .offset = 0, .bytes_per_row = STRIDE_UNDEFINED, .rows_per_image = STRIDE_UNDEFINED, .mip = 2, .width = 4, .height = 4, .depth_or_layers = 1 };
    _ = try validate(8, texture, copy, .texture_to_buffer, .webgpu);
    copy.width = 2;
    try std.testing.expectError(error.TextureCopyLayout, validate(8, texture, copy, .texture_to_buffer, .webgpu));
    copy.width = 4;
    copy.height = 8;
    try std.testing.expectError(error.TextureCopyRange, validate(16, texture, copy, .texture_to_buffer, .webgpu));
    texture.format = values.WGPUTextureFormat_R32Uint;
    copy.mip = 0;
    copy.width = 0;
    copy.height = 2;
    copy.depth_or_layers = 2;
    copy.bytes_per_row = 256;
    copy.rows_per_image = 3;
    try std.testing.expectError(error.TextureCopyRange, validate(1023, texture, copy, .texture_to_buffer, .webgpu));
    _ = try validate(1024, texture, copy, .texture_to_buffer, .webgpu);
    copy.bytes_per_row = 64;
    try std.testing.expectError(error.TextureCopyLayout, validate(1024, texture, copy, .texture_to_buffer, .webgpu));
    copy.bytes_per_row = STRIDE_UNDEFINED;
    try std.testing.expectError(error.TextureCopyLayout, validate(1024, texture, copy, .texture_to_buffer, .webgpu));
}
