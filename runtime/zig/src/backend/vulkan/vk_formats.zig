// WebGPU-to-Vulkan texture format translation.
//
// Maps WGPUTextureFormat values to VkFormat constants and provides
// per-format metadata (bytes per pixel, aspect mask).

const model = @import("../../model.zig");

// --- VkFormat constants (Vulkan 1.0 spec values) ---

// 1-channel 8-bit
pub const VK_FORMAT_R8_UNORM: u32 = 9;
pub const VK_FORMAT_R8_SNORM: u32 = 10;
pub const VK_FORMAT_R8_UINT: u32 = 13;
pub const VK_FORMAT_R8_SINT: u32 = 14;

// 2-channel 8-bit
pub const VK_FORMAT_R8G8_UNORM: u32 = 16;
pub const VK_FORMAT_R8G8_SNORM: u32 = 17;
pub const VK_FORMAT_R8G8_UINT: u32 = 20;
pub const VK_FORMAT_R8G8_SINT: u32 = 21;

// 4-channel 8-bit
pub const VK_FORMAT_R8G8B8A8_UNORM: u32 = 37;
pub const VK_FORMAT_R8G8B8A8_SRGB: u32 = 43;
pub const VK_FORMAT_R8G8B8A8_SNORM: u32 = 38;
pub const VK_FORMAT_R8G8B8A8_UINT: u32 = 41;
pub const VK_FORMAT_R8G8B8A8_SINT: u32 = 42;
pub const VK_FORMAT_B8G8R8A8_UNORM: u32 = 44;
pub const VK_FORMAT_B8G8R8A8_SRGB: u32 = 50;

// Packed 32-bit color
pub const VK_FORMAT_A2B10G10R10_UINT_PACK32: u32 = 68;
pub const VK_FORMAT_A2B10G10R10_UNORM_PACK32: u32 = 64;

// 1-channel 16-bit
pub const VK_FORMAT_R16_UNORM: u32 = 70;
pub const VK_FORMAT_R16_SNORM: u32 = 71;
pub const VK_FORMAT_R16_UINT: u32 = 74;
pub const VK_FORMAT_R16_SINT: u32 = 75;
pub const VK_FORMAT_R16_SFLOAT: u32 = 76;

// 2-channel 16-bit
pub const VK_FORMAT_R16G16_UNORM: u32 = 77;
pub const VK_FORMAT_R16G16_SNORM: u32 = 78;
pub const VK_FORMAT_R16G16_UINT: u32 = 81;
pub const VK_FORMAT_R16G16_SINT: u32 = 82;
pub const VK_FORMAT_R16G16_SFLOAT: u32 = 83;

// 4-channel 16-bit
pub const VK_FORMAT_R16G16B16A16_UINT: u32 = 95;
pub const VK_FORMAT_R16G16B16A16_SINT: u32 = 96;
pub const VK_FORMAT_R16G16B16A16_SFLOAT: u32 = 97;

// 1-channel 32-bit
pub const VK_FORMAT_R32_UINT: u32 = 98;
pub const VK_FORMAT_R32_SINT: u32 = 99;
pub const VK_FORMAT_R32_SFLOAT: u32 = 100;

// 2-channel 32-bit
pub const VK_FORMAT_R32G32_UINT: u32 = 101;
pub const VK_FORMAT_R32G32_SINT: u32 = 102;
pub const VK_FORMAT_R32G32_SFLOAT: u32 = 103;

// 4-channel 32-bit
pub const VK_FORMAT_R32G32B32A32_UINT: u32 = 107;
pub const VK_FORMAT_R32G32B32A32_SINT: u32 = 108;
pub const VK_FORMAT_R32G32B32A32_SFLOAT: u32 = 109;

// Packed float formats
pub const VK_FORMAT_B10G11R11_UFLOAT_PACK32: u32 = 122;
pub const VK_FORMAT_E5B9G9R9_UFLOAT_PACK32: u32 = 123;

// Depth/stencil
pub const VK_FORMAT_D16_UNORM: u32 = 124;
pub const VK_FORMAT_D32_SFLOAT: u32 = 126;
pub const VK_FORMAT_S8_UINT: u32 = 127;
pub const VK_FORMAT_D24_UNORM_S8_UINT: u32 = 129;
pub const VK_FORMAT_D32_SFLOAT_S8_UINT: u32 = 130;

// --- Aspect mask constants ---

pub const VK_IMAGE_ASPECT_COLOR_BIT: u32 = 0x00000001;
pub const VK_IMAGE_ASPECT_DEPTH_BIT: u32 = 0x00000002;
pub const VK_IMAGE_ASPECT_STENCIL_BIT: u32 = 0x00000004;

// --- Format translation ---

pub fn wgpu_format_to_vk_format(format: model.WGPUTextureFormat) !u32 {
    return switch (format) {
        // 1-channel 8-bit
        model.WGPUTextureFormat_R8Unorm => VK_FORMAT_R8_UNORM,
        model.WGPUTextureFormat_R8Snorm => VK_FORMAT_R8_SNORM,
        model.WGPUTextureFormat_R8Uint => VK_FORMAT_R8_UINT,
        model.WGPUTextureFormat_R8Sint => VK_FORMAT_R8_SINT,

        // 2-channel 8-bit
        model.WGPUTextureFormat_RG8Unorm => VK_FORMAT_R8G8_UNORM,
        model.WGPUTextureFormat_RG8Snorm => VK_FORMAT_R8G8_SNORM,
        model.WGPUTextureFormat_RG8Uint => VK_FORMAT_R8G8_UINT,
        model.WGPUTextureFormat_RG8Sint => VK_FORMAT_R8G8_SINT,

        // 4-channel 8-bit
        model.WGPUTextureFormat_RGBA8Unorm => VK_FORMAT_R8G8B8A8_UNORM,
        model.WGPUTextureFormat_RGBA8UnormSrgb => VK_FORMAT_R8G8B8A8_SRGB,
        model.WGPUTextureFormat_RGBA8Snorm => VK_FORMAT_R8G8B8A8_SNORM,
        model.WGPUTextureFormat_RGBA8Uint => VK_FORMAT_R8G8B8A8_UINT,
        model.WGPUTextureFormat_RGBA8Sint => VK_FORMAT_R8G8B8A8_SINT,
        model.WGPUTextureFormat_BGRA8Unorm => VK_FORMAT_B8G8R8A8_UNORM,
        model.WGPUTextureFormat_BGRA8UnormSrgb => VK_FORMAT_B8G8R8A8_SRGB,

        // Packed 32-bit color
        model.WGPUTextureFormat_RGB10A2Uint => VK_FORMAT_A2B10G10R10_UINT_PACK32,
        model.WGPUTextureFormat_RGB10A2Unorm => VK_FORMAT_A2B10G10R10_UNORM_PACK32,
        model.WGPUTextureFormat_RG11B10Ufloat => VK_FORMAT_B10G11R11_UFLOAT_PACK32,
        model.WGPUTextureFormat_RGB9E5Ufloat => VK_FORMAT_E5B9G9R9_UFLOAT_PACK32,

        // 1-channel 16-bit
        model.WGPUTextureFormat_R16Unorm => VK_FORMAT_R16_UNORM,
        model.WGPUTextureFormat_R16Snorm => VK_FORMAT_R16_SNORM,
        model.WGPUTextureFormat_R16Uint => VK_FORMAT_R16_UINT,
        model.WGPUTextureFormat_R16Sint => VK_FORMAT_R16_SINT,
        model.WGPUTextureFormat_R16Float => VK_FORMAT_R16_SFLOAT,

        // 2-channel 16-bit
        model.WGPUTextureFormat_RG16Unorm => VK_FORMAT_R16G16_UNORM,
        model.WGPUTextureFormat_RG16Snorm => VK_FORMAT_R16G16_SNORM,
        model.WGPUTextureFormat_RG16Uint => VK_FORMAT_R16G16_UINT,
        model.WGPUTextureFormat_RG16Sint => VK_FORMAT_R16G16_SINT,
        model.WGPUTextureFormat_RG16Float => VK_FORMAT_R16G16_SFLOAT,

        // 4-channel 16-bit
        model.WGPUTextureFormat_RGBA16Uint => VK_FORMAT_R16G16B16A16_UINT,
        model.WGPUTextureFormat_RGBA16Sint => VK_FORMAT_R16G16B16A16_SINT,
        model.WGPUTextureFormat_RGBA16Float => VK_FORMAT_R16G16B16A16_SFLOAT,

        // 1-channel 32-bit
        model.WGPUTextureFormat_R32Uint => VK_FORMAT_R32_UINT,
        model.WGPUTextureFormat_R32Sint => VK_FORMAT_R32_SINT,
        model.WGPUTextureFormat_R32Float => VK_FORMAT_R32_SFLOAT,

        // 2-channel 32-bit
        model.WGPUTextureFormat_RG32Uint => VK_FORMAT_R32G32_UINT,
        model.WGPUTextureFormat_RG32Sint => VK_FORMAT_R32G32_SINT,
        model.WGPUTextureFormat_RG32Float => VK_FORMAT_R32G32_SFLOAT,

        // 4-channel 32-bit
        model.WGPUTextureFormat_RGBA32Uint => VK_FORMAT_R32G32B32A32_UINT,
        model.WGPUTextureFormat_RGBA32Sint => VK_FORMAT_R32G32B32A32_SINT,
        model.WGPUTextureFormat_RGBA32Float => VK_FORMAT_R32G32B32A32_SFLOAT,

        // Depth/stencil
        model.WGPUTextureFormat_Depth16Unorm => VK_FORMAT_D16_UNORM,
        model.WGPUTextureFormat_Depth32Float => VK_FORMAT_D32_SFLOAT,
        model.WGPUTextureFormat_Stencil8 => VK_FORMAT_S8_UINT,
        model.WGPUTextureFormat_Depth24Plus,
        model.WGPUTextureFormat_Depth24PlusStencil8,
        => VK_FORMAT_D24_UNORM_S8_UINT,
        model.WGPUTextureFormat_Depth32FloatStencil8 => VK_FORMAT_D32_SFLOAT_S8_UINT,

        else => error.UnsupportedFeature,
    };
}

/// Returns the number of bytes per pixel for a given WebGPU texture format.
/// Depth/stencil formats return the total byte footprint per texel.
pub fn bytes_per_pixel(format: model.WGPUTextureFormat) !u32 {
    return switch (format) {
        // 1 byte per pixel
        model.WGPUTextureFormat_R8Unorm,
        model.WGPUTextureFormat_R8Snorm,
        model.WGPUTextureFormat_R8Uint,
        model.WGPUTextureFormat_R8Sint,
        model.WGPUTextureFormat_Stencil8,
        => 1,

        // 2 bytes per pixel
        model.WGPUTextureFormat_R16Unorm,
        model.WGPUTextureFormat_R16Snorm,
        model.WGPUTextureFormat_R16Uint,
        model.WGPUTextureFormat_R16Sint,
        model.WGPUTextureFormat_R16Float,
        model.WGPUTextureFormat_RG8Unorm,
        model.WGPUTextureFormat_RG8Snorm,
        model.WGPUTextureFormat_RG8Uint,
        model.WGPUTextureFormat_RG8Sint,
        model.WGPUTextureFormat_Depth16Unorm,
        => 2,

        // 4 bytes per pixel
        model.WGPUTextureFormat_RGBA8Unorm,
        model.WGPUTextureFormat_RGBA8UnormSrgb,
        model.WGPUTextureFormat_RGBA8Snorm,
        model.WGPUTextureFormat_RGBA8Uint,
        model.WGPUTextureFormat_RGBA8Sint,
        model.WGPUTextureFormat_BGRA8Unorm,
        model.WGPUTextureFormat_BGRA8UnormSrgb,
        model.WGPUTextureFormat_RGB10A2Uint,
        model.WGPUTextureFormat_RGB10A2Unorm,
        model.WGPUTextureFormat_RG11B10Ufloat,
        model.WGPUTextureFormat_RGB9E5Ufloat,
        model.WGPUTextureFormat_RG16Unorm,
        model.WGPUTextureFormat_RG16Snorm,
        model.WGPUTextureFormat_RG16Uint,
        model.WGPUTextureFormat_RG16Sint,
        model.WGPUTextureFormat_RG16Float,
        model.WGPUTextureFormat_R32Uint,
        model.WGPUTextureFormat_R32Sint,
        model.WGPUTextureFormat_R32Float,
        model.WGPUTextureFormat_Depth32Float,
        model.WGPUTextureFormat_Depth24Plus,
        model.WGPUTextureFormat_Depth24PlusStencil8,
        => 4,

        // 8 bytes per pixel
        model.WGPUTextureFormat_RGBA16Uint,
        model.WGPUTextureFormat_RGBA16Sint,
        model.WGPUTextureFormat_RGBA16Float,
        model.WGPUTextureFormat_RG32Uint,
        model.WGPUTextureFormat_RG32Sint,
        model.WGPUTextureFormat_RG32Float,
        model.WGPUTextureFormat_Depth32FloatStencil8,
        => 8,

        // 16 bytes per pixel
        model.WGPUTextureFormat_RGBA32Uint,
        model.WGPUTextureFormat_RGBA32Sint,
        model.WGPUTextureFormat_RGBA32Float,
        => 16,

        else => error.UnsupportedFeature,
    };
}

/// Returns the Vulkan image aspect mask for a WebGPU texture format.
/// Color formats use COLOR_BIT; depth and depth-stencil formats use the
/// appropriate depth/stencil combination.
pub fn aspect_mask_for_format(format: model.WGPUTextureFormat) u32 {
    return switch (format) {
        model.WGPUTextureFormat_Depth16Unorm,
        model.WGPUTextureFormat_Depth32Float,
        model.WGPUTextureFormat_Depth24Plus,
        => VK_IMAGE_ASPECT_DEPTH_BIT,

        model.WGPUTextureFormat_Depth24PlusStencil8,
        model.WGPUTextureFormat_Depth32FloatStencil8,
        => VK_IMAGE_ASPECT_DEPTH_BIT | VK_IMAGE_ASPECT_STENCIL_BIT,

        model.WGPUTextureFormat_Stencil8 => VK_IMAGE_ASPECT_STENCIL_BIT,

        else => VK_IMAGE_ASPECT_COLOR_BIT,
    };
}

/// Returns true if the format is a depth or depth-stencil format.
pub fn is_depth_stencil(format: model.WGPUTextureFormat) bool {
    return switch (format) {
        model.WGPUTextureFormat_Depth16Unorm,
        model.WGPUTextureFormat_Depth24Plus,
        model.WGPUTextureFormat_Depth24PlusStencil8,
        model.WGPUTextureFormat_Depth32Float,
        model.WGPUTextureFormat_Depth32FloatStencil8,
        model.WGPUTextureFormat_Stencil8,
        => true,
        else => false,
    };
}
