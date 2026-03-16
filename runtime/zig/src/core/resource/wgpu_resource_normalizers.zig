const model = @import("../../model.zig");
const types = @import("../abi/wgpu_types.zig");

pub fn normalizeBufferBindingType(value: u32) u32 {
    return switch (value) {
        model.WGPUBufferBindingType_Uniform => types.WGPUBufferBindingType_Uniform,
        model.WGPUBufferBindingType_Storage => types.WGPUBufferBindingType_Storage,
        model.WGPUBufferBindingType_ReadOnlyStorage => types.WGPUBufferBindingType_ReadOnlyStorage,
        else => types.WGPUBufferBindingType_Undefined,
    };
}

pub fn normalizeTextureSampleType(value: u32) u32 {
    return switch (value) {
        model.WGPUTextureSampleType_Float => types.WGPUTextureSampleType_Float,
        model.WGPUTextureSampleType_UnfilterableFloat => types.WGPUTextureSampleType_UnfilterableFloat,
        model.WGPUTextureSampleType_Depth => types.WGPUTextureSampleType_Depth,
        model.WGPUTextureSampleType_Sint => types.WGPUTextureSampleType_Sint,
        model.WGPUTextureSampleType_Uint => types.WGPUTextureSampleType_Uint,
        else => types.WGPUTextureSampleType_Float,
    };
}

pub fn normalizeTextureViewDimension(value: u32) types.WGPUTextureViewDimension {
    return switch (value) {
        model.WGPUTextureViewDimension_1D => types.WGPUTextureViewDimension_1D,
        model.WGPUTextureViewDimension_2D => types.WGPUTextureViewDimension_2D,
        model.WGPUTextureViewDimension_2DArray => types.WGPUTextureViewDimension_2DArray,
        model.WGPUTextureViewDimension_Cube => types.WGPUTextureViewDimension_Cube,
        model.WGPUTextureViewDimension_CubeArray => types.WGPUTextureViewDimension_CubeArray,
        model.WGPUTextureViewDimension_3D => types.WGPUTextureViewDimension_3D,
        else => types.WGPUTextureViewDimension_2D,
    };
}

pub fn normalizeStorageTextureAccess(value: u32) u32 {
    return switch (value) {
        model.WGPUStorageTextureAccess_WriteOnly => types.WGPUStorageTextureAccess_WriteOnly,
        model.WGPUStorageTextureAccess_ReadOnly => types.WGPUStorageTextureAccess_ReadOnly,
        model.WGPUStorageTextureAccess_ReadWrite => types.WGPUStorageTextureAccess_ReadWrite,
        else => types.WGPUStorageTextureAccess_WriteOnly,
    };
}

pub fn normalizeTextureFormat(value: u32) types.WGPUTextureFormat {
    return switch (value) {
        model.WGPUTextureFormat_Undefined => types.WGPUTextureFormat_Undefined,
        model.WGPUTextureFormat_R8Unorm => types.WGPUTextureFormat_R8Unorm,
        model.WGPUTextureFormat_R8Snorm => model.WGPUTextureFormat_R8Snorm,
        model.WGPUTextureFormat_R8Uint => model.WGPUTextureFormat_R8Uint,
        model.WGPUTextureFormat_R8Sint => model.WGPUTextureFormat_R8Sint,
        model.WGPUTextureFormat_R16Unorm => model.WGPUTextureFormat_R16Unorm,
        model.WGPUTextureFormat_R16Snorm => model.WGPUTextureFormat_R16Snorm,
        model.WGPUTextureFormat_R16Uint => model.WGPUTextureFormat_R16Uint,
        model.WGPUTextureFormat_R16Sint => model.WGPUTextureFormat_R16Sint,
        model.WGPUTextureFormat_R16Float => model.WGPUTextureFormat_R16Float,
        model.WGPUTextureFormat_RG8Unorm => model.WGPUTextureFormat_RG8Unorm,
        model.WGPUTextureFormat_RG8Snorm => model.WGPUTextureFormat_RG8Snorm,
        model.WGPUTextureFormat_RG8Uint => model.WGPUTextureFormat_RG8Uint,
        model.WGPUTextureFormat_RG8Sint => model.WGPUTextureFormat_RG8Sint,
        model.WGPUTextureFormat_R32Float => model.WGPUTextureFormat_R32Float,
        model.WGPUTextureFormat_R32Uint => model.WGPUTextureFormat_R32Uint,
        model.WGPUTextureFormat_R32Sint => model.WGPUTextureFormat_R32Sint,
        model.WGPUTextureFormat_RG16Unorm => model.WGPUTextureFormat_RG16Unorm,
        model.WGPUTextureFormat_RG16Snorm => model.WGPUTextureFormat_RG16Snorm,
        model.WGPUTextureFormat_RG16Uint => model.WGPUTextureFormat_RG16Uint,
        model.WGPUTextureFormat_RG16Sint => model.WGPUTextureFormat_RG16Sint,
        model.WGPUTextureFormat_RG16Float => model.WGPUTextureFormat_RG16Float,
        model.WGPUTextureFormat_RGBA8Unorm => model.WGPUTextureFormat_RGBA8Unorm,
        model.WGPUTextureFormat_RGBA8UnormSrgb => model.WGPUTextureFormat_RGBA8UnormSrgb,
        model.WGPUTextureFormat_RGBA8Snorm => model.WGPUTextureFormat_RGBA8Snorm,
        model.WGPUTextureFormat_RGBA8Uint => model.WGPUTextureFormat_RGBA8Uint,
        model.WGPUTextureFormat_RGBA8Sint => model.WGPUTextureFormat_RGBA8Sint,
        model.WGPUTextureFormat_BGRA8Unorm => model.WGPUTextureFormat_BGRA8Unorm,
        model.WGPUTextureFormat_BGRA8UnormSrgb => model.WGPUTextureFormat_BGRA8UnormSrgb,
        model.WGPUTextureFormat_Depth16Unorm => model.WGPUTextureFormat_Depth16Unorm,
        model.WGPUTextureFormat_Depth24Plus => model.WGPUTextureFormat_Depth24Plus,
        model.WGPUTextureFormat_Depth24PlusStencil8 => model.WGPUTextureFormat_Depth24PlusStencil8,
        model.WGPUTextureFormat_Depth32Float => model.WGPUTextureFormat_Depth32Float,
        model.WGPUTextureFormat_Depth32FloatStencil8 => model.WGPUTextureFormat_Depth32FloatStencil8,
        else => types.WGPUTextureFormat_Undefined,
    };
}

pub fn textureFormatBytesPerPixel(format: types.WGPUTextureFormat) ?u32 {
    return switch (format) {
        types.WGPUTextureFormat_R8Unorm,
        model.WGPUTextureFormat_R8Snorm,
        model.WGPUTextureFormat_R8Uint,
        model.WGPUTextureFormat_R8Sint,
        => 1,
        model.WGPUTextureFormat_R16Unorm,
        model.WGPUTextureFormat_R16Snorm,
        model.WGPUTextureFormat_R16Uint,
        model.WGPUTextureFormat_R16Sint,
        model.WGPUTextureFormat_R16Float,
        model.WGPUTextureFormat_RG8Unorm,
        model.WGPUTextureFormat_RG8Snorm,
        model.WGPUTextureFormat_RG8Uint,
        model.WGPUTextureFormat_RG8Sint,
        => 2,
        model.WGPUTextureFormat_R32Float,
        model.WGPUTextureFormat_R32Uint,
        model.WGPUTextureFormat_R32Sint,
        model.WGPUTextureFormat_RG16Unorm,
        model.WGPUTextureFormat_RG16Snorm,
        model.WGPUTextureFormat_RG16Uint,
        model.WGPUTextureFormat_RG16Sint,
        model.WGPUTextureFormat_RG16Float,
        model.WGPUTextureFormat_RGBA8Unorm,
        model.WGPUTextureFormat_RGBA8UnormSrgb,
        model.WGPUTextureFormat_RGBA8Snorm,
        model.WGPUTextureFormat_RGBA8Uint,
        model.WGPUTextureFormat_RGBA8Sint,
        model.WGPUTextureFormat_BGRA8Unorm,
        model.WGPUTextureFormat_BGRA8UnormSrgb,
        model.WGPUTextureFormat_Depth32Float,
        => 4,
        else => null,
    };
}

pub fn inferTextureDimensionFromViewDimension(value: u32) types.WGPUTextureDimension {
    const view_dim = normalizeTextureViewDimension(value);
    return switch (view_dim) {
        types.WGPUTextureViewDimension_Undefined => types.WGPUTextureDimension_Undefined,
        types.WGPUTextureViewDimension_1D => types.WGPUTextureDimension_1D,
        types.WGPUTextureViewDimension_3D => types.WGPUTextureDimension_3D,
        else => types.WGPUTextureDimension_2D,
    };
}

pub fn normalizeTextureViewAspect(value: u32) types.WGPUTextureAspect {
    return switch (value) {
        model.WGPUTextureAspect_DepthOnly => types.WGPUTextureAspect_DepthOnly,
        model.WGPUTextureAspect_StencilOnly => types.WGPUTextureAspect_StencilOnly,
        else => types.WGPUTextureAspect_All,
    };
}

pub fn normalizeTextureBytesPerRow(format: types.WGPUTextureFormat, width: u32, explicit_bytes_per_row: u32) u32 {
    if (explicit_bytes_per_row != 0) return explicit_bytes_per_row;
    const bytes_per_pixel = textureFormatBytesPerPixel(format) orelse return 0;
    return width * bytes_per_pixel;
}

pub fn normalizeTextureRowsPerImage(height: u32, explicit_rows_per_image: u32) u32 {
    if (explicit_rows_per_image != 0) return explicit_rows_per_image;
    return height;
}

const std = @import("std");

test "normalizeBufferBindingType maps Uniform correctly" {
    try std.testing.expectEqual(types.WGPUBufferBindingType_Uniform, normalizeBufferBindingType(model.WGPUBufferBindingType_Uniform));
}

test "normalizeBufferBindingType maps Storage correctly" {
    try std.testing.expectEqual(types.WGPUBufferBindingType_Storage, normalizeBufferBindingType(model.WGPUBufferBindingType_Storage));
}

test "normalizeBufferBindingType maps ReadOnlyStorage correctly" {
    try std.testing.expectEqual(types.WGPUBufferBindingType_ReadOnlyStorage, normalizeBufferBindingType(model.WGPUBufferBindingType_ReadOnlyStorage));
}

test "normalizeBufferBindingType returns Undefined for unknown value" {
    try std.testing.expectEqual(types.WGPUBufferBindingType_Undefined, normalizeBufferBindingType(0xDEAD));
}

test "normalizeTextureSampleType maps Float correctly" {
    try std.testing.expectEqual(types.WGPUTextureSampleType_Float, normalizeTextureSampleType(model.WGPUTextureSampleType_Float));
}

test "normalizeTextureSampleType maps UnfilterableFloat correctly" {
    try std.testing.expectEqual(types.WGPUTextureSampleType_UnfilterableFloat, normalizeTextureSampleType(model.WGPUTextureSampleType_UnfilterableFloat));
}

test "normalizeTextureSampleType maps Depth correctly" {
    try std.testing.expectEqual(types.WGPUTextureSampleType_Depth, normalizeTextureSampleType(model.WGPUTextureSampleType_Depth));
}

test "normalizeTextureSampleType maps Sint correctly" {
    try std.testing.expectEqual(types.WGPUTextureSampleType_Sint, normalizeTextureSampleType(model.WGPUTextureSampleType_Sint));
}

test "normalizeTextureSampleType maps Uint correctly" {
    try std.testing.expectEqual(types.WGPUTextureSampleType_Uint, normalizeTextureSampleType(model.WGPUTextureSampleType_Uint));
}

test "normalizeTextureSampleType defaults to Float for unknown value" {
    try std.testing.expectEqual(types.WGPUTextureSampleType_Float, normalizeTextureSampleType(0xDEAD));
}

test "normalizeTextureViewDimension maps 1D correctly" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_1D, normalizeTextureViewDimension(model.WGPUTextureViewDimension_1D));
}

test "normalizeTextureViewDimension maps 2D correctly" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_2D, normalizeTextureViewDimension(model.WGPUTextureViewDimension_2D));
}

test "normalizeTextureViewDimension maps 2DArray correctly" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_2DArray, normalizeTextureViewDimension(model.WGPUTextureViewDimension_2DArray));
}

test "normalizeTextureViewDimension maps Cube correctly" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_Cube, normalizeTextureViewDimension(model.WGPUTextureViewDimension_Cube));
}

test "normalizeTextureViewDimension maps CubeArray correctly" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_CubeArray, normalizeTextureViewDimension(model.WGPUTextureViewDimension_CubeArray));
}

test "normalizeTextureViewDimension maps 3D correctly" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_3D, normalizeTextureViewDimension(model.WGPUTextureViewDimension_3D));
}

test "normalizeTextureViewDimension defaults to 2D for unknown value" {
    try std.testing.expectEqual(types.WGPUTextureViewDimension_2D, normalizeTextureViewDimension(0xDEAD));
}

test "normalizeStorageTextureAccess maps WriteOnly correctly" {
    try std.testing.expectEqual(types.WGPUStorageTextureAccess_WriteOnly, normalizeStorageTextureAccess(model.WGPUStorageTextureAccess_WriteOnly));
}

test "normalizeStorageTextureAccess maps ReadOnly correctly" {
    try std.testing.expectEqual(types.WGPUStorageTextureAccess_ReadOnly, normalizeStorageTextureAccess(model.WGPUStorageTextureAccess_ReadOnly));
}

test "normalizeStorageTextureAccess maps ReadWrite correctly" {
    try std.testing.expectEqual(types.WGPUStorageTextureAccess_ReadWrite, normalizeStorageTextureAccess(model.WGPUStorageTextureAccess_ReadWrite));
}

test "normalizeStorageTextureAccess defaults to WriteOnly for unknown value" {
    try std.testing.expectEqual(types.WGPUStorageTextureAccess_WriteOnly, normalizeStorageTextureAccess(0xDEAD));
}

test "normalizeTextureFormat maps R8Unorm correctly" {
    try std.testing.expectEqual(types.WGPUTextureFormat_R8Unorm, normalizeTextureFormat(model.WGPUTextureFormat_R8Unorm));
}

test "normalizeTextureFormat maps RGBA8Unorm correctly" {
    try std.testing.expectEqual(model.WGPUTextureFormat_RGBA8Unorm, normalizeTextureFormat(model.WGPUTextureFormat_RGBA8Unorm));
}

test "normalizeTextureFormat maps Depth32Float correctly" {
    try std.testing.expectEqual(model.WGPUTextureFormat_Depth32Float, normalizeTextureFormat(model.WGPUTextureFormat_Depth32Float));
}

test "normalizeTextureFormat returns Undefined for unknown value" {
    try std.testing.expectEqual(types.WGPUTextureFormat_Undefined, normalizeTextureFormat(0xDEAD));
}

test "textureFormatBytesPerPixel returns 1 for R8Unorm" {
    try std.testing.expectEqual(@as(?u32, 1), textureFormatBytesPerPixel(types.WGPUTextureFormat_R8Unorm));
}

test "textureFormatBytesPerPixel returns 2 for RG8Unorm" {
    try std.testing.expectEqual(@as(?u32, 2), textureFormatBytesPerPixel(model.WGPUTextureFormat_RG8Unorm));
}

test "textureFormatBytesPerPixel returns 4 for RGBA8Unorm" {
    try std.testing.expectEqual(@as(?u32, 4), textureFormatBytesPerPixel(model.WGPUTextureFormat_RGBA8Unorm));
}

test "textureFormatBytesPerPixel returns null for unknown format" {
    try std.testing.expectEqual(@as(?u32, null), textureFormatBytesPerPixel(0xDEAD));
}

test "inferTextureDimensionFromViewDimension maps 1D to 1D" {
    try std.testing.expectEqual(types.WGPUTextureDimension_1D, inferTextureDimensionFromViewDimension(model.WGPUTextureViewDimension_1D));
}

test "inferTextureDimensionFromViewDimension maps 2D to 2D" {
    try std.testing.expectEqual(types.WGPUTextureDimension_2D, inferTextureDimensionFromViewDimension(model.WGPUTextureViewDimension_2D));
}

test "inferTextureDimensionFromViewDimension maps 3D to 3D" {
    try std.testing.expectEqual(types.WGPUTextureDimension_3D, inferTextureDimensionFromViewDimension(model.WGPUTextureViewDimension_3D));
}

test "inferTextureDimensionFromViewDimension maps Cube to 2D" {
    try std.testing.expectEqual(types.WGPUTextureDimension_2D, inferTextureDimensionFromViewDimension(model.WGPUTextureViewDimension_Cube));
}

test "normalizeTextureViewAspect maps DepthOnly correctly" {
    try std.testing.expectEqual(types.WGPUTextureAspect_DepthOnly, normalizeTextureViewAspect(model.WGPUTextureAspect_DepthOnly));
}

test "normalizeTextureViewAspect maps StencilOnly correctly" {
    try std.testing.expectEqual(types.WGPUTextureAspect_StencilOnly, normalizeTextureViewAspect(model.WGPUTextureAspect_StencilOnly));
}

test "normalizeTextureViewAspect defaults to All for unknown value" {
    try std.testing.expectEqual(types.WGPUTextureAspect_All, normalizeTextureViewAspect(0xDEAD));
}

test "normalizeTextureBytesPerRow uses explicit value when nonzero" {
    try std.testing.expectEqual(@as(u32, 256), normalizeTextureBytesPerRow(types.WGPUTextureFormat_R8Unorm, 64, 256));
}

test "normalizeTextureBytesPerRow infers from format and width when zero" {
    // R8Unorm = 1 byte per pixel, width = 64, so expected = 64
    try std.testing.expectEqual(@as(u32, 64), normalizeTextureBytesPerRow(types.WGPUTextureFormat_R8Unorm, 64, 0));
}

test "normalizeTextureBytesPerRow returns zero for unknown format when explicit is zero" {
    try std.testing.expectEqual(@as(u32, 0), normalizeTextureBytesPerRow(0xDEAD, 64, 0));
}

test "normalizeTextureRowsPerImage uses explicit value when nonzero" {
    try std.testing.expectEqual(@as(u32, 128), normalizeTextureRowsPerImage(64, 128));
}

test "normalizeTextureRowsPerImage returns height when explicit is zero" {
    try std.testing.expectEqual(@as(u32, 64), normalizeTextureRowsPerImage(64, 0));
}
