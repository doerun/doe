const std = @import("std");
const abi_base = @import("../../core/abi/wgpu_base_types.zig");
const c = @import("vk_constants.zig");

const FEATURE_SHADER_F16: u32 = abi_base.WGPUFeatureName_ShaderF16;
const FEATURE_FLOAT32_BLENDABLE: u32 = abi_base.WGPUFeatureName_Float32Blendable;
const FEATURE_SUBGROUPS: u32 = abi_base.WGPUFeatureName_Subgroups;
const FEATURE_DUAL_SOURCE_BLENDING: u32 = abi_base.WGPUFeatureName_DualSourceBlending;
const FEATURE_TEXTURE_FORMATS_TIER1: u32 = abi_base.WGPUFeatureName_TextureFormatsTier1;
const FEATURE_TEXTURE_FORMATS_TIER2: u32 = abi_base.WGPUFeatureName_TextureFormatsTier2;

const VK_FORMAT_FEATURE_STORAGE_IMAGE_BIT: u32 = 0x00000002;
const VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT: u32 = 0x00000080;
const VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT: u32 = 0x00000100;
const VK_SUBGROUP_REQUIRED_OPERATIONS: u32 =
    c.VK_SUBGROUP_FEATURE_BASIC_BIT |
    c.VK_SUBGROUP_FEATURE_VOTE_BIT |
    c.VK_SUBGROUP_FEATURE_ARITHMETIC_BIT |
    c.VK_SUBGROUP_FEATURE_BALLOT_BIT |
    c.VK_SUBGROUP_FEATURE_SHUFFLE_BIT |
    c.VK_SUBGROUP_FEATURE_SHUFFLE_RELATIVE_BIT;

const VK_FORMAT_R8_UNORM: u32 = 9;
const VK_FORMAT_R8_SNORM: u32 = 10;
const VK_FORMAT_R8_UINT: u32 = 13;
const VK_FORMAT_R8_SINT: u32 = 14;
const VK_FORMAT_R8G8_UNORM: u32 = 16;
const VK_FORMAT_R8G8_SNORM: u32 = 17;
const VK_FORMAT_R8G8_UINT: u32 = 20;
const VK_FORMAT_R8G8_SINT: u32 = 21;
const VK_FORMAT_R8G8B8A8_UNORM: u32 = 37;
const VK_FORMAT_R8G8B8A8_UINT: u32 = 41;
const VK_FORMAT_R8G8B8A8_SINT: u32 = 42;
const VK_FORMAT_A2B10G10R10_UNORM_PACK32: u32 = 64;
const VK_FORMAT_A2B10G10R10_UINT_PACK32: u32 = 68;
const VK_FORMAT_R16_UNORM: u32 = 70;
const VK_FORMAT_R16_SNORM: u32 = 71;
const VK_FORMAT_R16_UINT: u32 = 74;
const VK_FORMAT_R16_SINT: u32 = 75;
const VK_FORMAT_R16_SFLOAT: u32 = 76;
const VK_FORMAT_R16G16_UNORM: u32 = 77;
const VK_FORMAT_R16G16_SNORM: u32 = 78;
const VK_FORMAT_R16G16_UINT: u32 = 81;
const VK_FORMAT_R16G16_SINT: u32 = 82;
const VK_FORMAT_R16G16_SFLOAT: u32 = 83;
const VK_FORMAT_R16G16B16A16_UNORM: u32 = 91;
const VK_FORMAT_R16G16B16A16_SNORM: u32 = 92;
const VK_FORMAT_R16G16B16A16_UINT: u32 = 95;
const VK_FORMAT_R16G16B16A16_SINT: u32 = 96;
const VK_FORMAT_R16G16B16A16_SFLOAT: u32 = 97;
const VK_FORMAT_R32_UINT: u32 = 98;
const VK_FORMAT_R32_SINT: u32 = 99;
const VK_FORMAT_R32_SFLOAT: u32 = 100;
const VK_FORMAT_R32G32_UINT: u32 = 101;
const VK_FORMAT_R32G32_SINT: u32 = 102;
const VK_FORMAT_R32G32_SFLOAT: u32 = 103;
const VK_FORMAT_R32G32B32A32_UINT: u32 = 107;
const VK_FORMAT_R32G32B32A32_SINT: u32 = 108;
const VK_FORMAT_R32G32B32A32_SFLOAT: u32 = 109;
const VK_FORMAT_B10G11R11_UFLOAT_PACK32: u32 = 122;

const TIER1_STORAGE_FORMATS = [_]u32{
    VK_FORMAT_R8_UNORM,
    VK_FORMAT_R8_SNORM,
    VK_FORMAT_R8_UINT,
    VK_FORMAT_R8_SINT,
    VK_FORMAT_R16_UNORM,
    VK_FORMAT_R16_SNORM,
    VK_FORMAT_R16_UINT,
    VK_FORMAT_R16_SINT,
    VK_FORMAT_R16_SFLOAT,
    VK_FORMAT_R8G8_UNORM,
    VK_FORMAT_R8G8_SNORM,
    VK_FORMAT_R8G8_UINT,
    VK_FORMAT_R8G8_SINT,
    VK_FORMAT_R16G16_UNORM,
    VK_FORMAT_R16G16_SNORM,
    VK_FORMAT_R16G16_UINT,
    VK_FORMAT_R16G16_SINT,
    VK_FORMAT_R16G16_SFLOAT,
    VK_FORMAT_R16G16B16A16_UNORM,
    VK_FORMAT_R16G16B16A16_SNORM,
    VK_FORMAT_A2B10G10R10_UINT_PACK32,
    VK_FORMAT_A2B10G10R10_UNORM_PACK32,
    VK_FORMAT_B10G11R11_UFLOAT_PACK32,
};

const TIER2_READ_WRITE_FORMATS = [_]u32{
    VK_FORMAT_R8_UNORM,
    VK_FORMAT_R8_UINT,
    VK_FORMAT_R8_SINT,
    VK_FORMAT_R8G8B8A8_UNORM,
    VK_FORMAT_R8G8B8A8_UINT,
    VK_FORMAT_R8G8B8A8_SINT,
    VK_FORMAT_R16_UINT,
    VK_FORMAT_R16_SINT,
    VK_FORMAT_R16_SFLOAT,
    VK_FORMAT_R16G16B16A16_UINT,
    VK_FORMAT_R16G16B16A16_SINT,
    VK_FORMAT_R16G16B16A16_SFLOAT,
    VK_FORMAT_R32G32B32A32_UINT,
    VK_FORMAT_R32G32B32A32_SINT,
    VK_FORMAT_R32G32B32A32_SFLOAT,
};

const FLOAT32_BLENDABLE_FORMATS = [_]u32{
    VK_FORMAT_R32_SFLOAT,
    VK_FORMAT_R32G32_SFLOAT,
    VK_FORMAT_R32G32B32A32_SFLOAT,
};

pub const VulkanFeatureCaps = struct {
    shader_f16: bool = false,
    float32_blendable: bool = false,
    dual_source_blending: bool = false,
    subgroups: bool = false,
    texture_formats_tier1: bool = false,
    texture_formats_tier2: bool = false,
};

pub const VulkanFeatureQuery = struct {
    caps: VulkanFeatureCaps = .{},
    enabled_features: c.VkPhysicalDeviceFeatures = std.mem.zeroes(c.VkPhysicalDeviceFeatures),
    enabled_vulkan12_features: c.VkPhysicalDeviceVulkan12Features = init_enabled_vulkan12_features(),
};

fn init_enabled_vulkan12_features() c.VkPhysicalDeviceVulkan12Features {
    var features = std.mem.zeroes(c.VkPhysicalDeviceVulkan12Features);
    features.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES;
    features.pNext = null;
    return features;
}

pub fn query(physical_device: c.VkPhysicalDevice) VulkanFeatureQuery {
    var raw_vulkan12_features = init_enabled_vulkan12_features();
    var raw_features2 = std.mem.zeroes(c.VkPhysicalDeviceFeatures2);
    raw_features2.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
    raw_features2.pNext = @ptrCast(&raw_vulkan12_features);
    c.vkGetPhysicalDeviceFeatures2(physical_device, &raw_features2);

    var subgroup_properties = std.mem.zeroes(c.VkPhysicalDeviceSubgroupProperties);
    subgroup_properties.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES;
    subgroup_properties.pNext = null;
    var properties2 = std.mem.zeroes(c.VkPhysicalDeviceProperties2);
    properties2.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;
    properties2.pNext = @ptrCast(&subgroup_properties);
    c.vkGetPhysicalDeviceProperties2(physical_device, &properties2);

    const caps = VulkanFeatureCaps{
        .shader_f16 = raw_vulkan12_features.shaderFloat16 == c.VK_TRUE,
        .float32_blendable = supports_all_formats(physical_device, &FLOAT32_BLENDABLE_FORMATS, supports_color_attachment_blend),
        .dual_source_blending = raw_features2.features.dualSrcBlend == c.VK_TRUE,
        .subgroups = subgroup_properties.subgroupSize > 0 and
            (subgroup_properties.supportedStages & c.VK_SHADER_STAGE_COMPUTE_BIT) != 0 and
            (subgroup_properties.supportedOperations & VK_SUBGROUP_REQUIRED_OPERATIONS) == VK_SUBGROUP_REQUIRED_OPERATIONS and
            raw_vulkan12_features.subgroupBroadcastDynamicId == c.VK_TRUE,
        .texture_formats_tier1 = supports_all_formats(physical_device, &TIER1_STORAGE_FORMATS, supports_storage_image),
        .texture_formats_tier2 = false,
    };

    var resolved_caps = caps;
    resolved_caps.texture_formats_tier2 = resolved_caps.texture_formats_tier1 and
        supports_all_formats(physical_device, &TIER2_READ_WRITE_FORMATS, supports_storage_image) and
        supports_color_attachment(physical_device, VK_FORMAT_B10G11R11_UFLOAT_PACK32);

    var query_result = VulkanFeatureQuery{ .caps = resolved_caps };
    query_result.enabled_features.drawIndirectFirstInstance = raw_features2.features.drawIndirectFirstInstance;
    query_result.enabled_features.textureCompressionETC2 = raw_features2.features.textureCompressionETC2;
    query_result.enabled_features.textureCompressionASTC_LDR = raw_features2.features.textureCompressionASTC_LDR;
    query_result.enabled_features.textureCompressionBC = raw_features2.features.textureCompressionBC;
    query_result.enabled_features.shaderClipDistance = raw_features2.features.shaderClipDistance;
    if (resolved_caps.dual_source_blending) {
        query_result.enabled_features.dualSrcBlend = c.VK_TRUE;
    }
    if (resolved_caps.shader_f16) {
        query_result.enabled_vulkan12_features.shaderFloat16 = c.VK_TRUE;
    }
    if (resolved_caps.subgroups) {
        query_result.enabled_vulkan12_features.subgroupBroadcastDynamicId = c.VK_TRUE;
    }
    return query_result;
}

pub fn dynamic_feature_supported(feature: u32, caps: VulkanFeatureCaps) bool {
    return switch (feature) {
        FEATURE_SHADER_F16 => caps.shader_f16,
        FEATURE_FLOAT32_BLENDABLE => caps.float32_blendable,
        FEATURE_SUBGROUPS => caps.subgroups,
        FEATURE_DUAL_SOURCE_BLENDING => caps.dual_source_blending,
        FEATURE_TEXTURE_FORMATS_TIER1 => caps.texture_formats_tier1,
        FEATURE_TEXTURE_FORMATS_TIER2 => caps.texture_formats_tier2,
        else => false,
    };
}

fn supports_all_formats(
    physical_device: c.VkPhysicalDevice,
    formats: []const u32,
    comptime predicate: fn (c.VkPhysicalDevice, u32) bool,
) bool {
    for (formats) |format| {
        if (!predicate(physical_device, format)) return false;
    }
    return true;
}

fn format_properties(physical_device: c.VkPhysicalDevice, format: u32) c.VkFormatProperties {
    var properties = std.mem.zeroes(c.VkFormatProperties);
    c.vkGetPhysicalDeviceFormatProperties(physical_device, format, &properties);
    return properties;
}

fn supports_storage_image(physical_device: c.VkPhysicalDevice, format: u32) bool {
    const properties = format_properties(physical_device, format);
    return (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_STORAGE_IMAGE_BIT) != 0;
}

fn supports_color_attachment(physical_device: c.VkPhysicalDevice, format: u32) bool {
    const properties = format_properties(physical_device, format);
    return (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT) != 0;
}

fn supports_color_attachment_blend(physical_device: c.VkPhysicalDevice, format: u32) bool {
    const properties = format_properties(physical_device, format);
    return (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BLEND_BIT) != 0;
}
