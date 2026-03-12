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
