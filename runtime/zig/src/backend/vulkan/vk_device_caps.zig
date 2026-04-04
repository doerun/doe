// vk_device_caps.zig — Vulkan physical device limits and features querying.
//
// Queries VkPhysicalDeviceProperties and VkPhysicalDeviceFeatures to map
// hardware capabilities to WebGPU limits and feature flags. This replaces
// the static VULKAN_LIMITS_STATIC fallback in doe_device_caps.zig with
// runtime-queried values.

const std = @import("std");
const c = @import("vk_constants.zig");
const abi_callback = @import("../../core/abi/wgpu_callback_descriptor_types.zig");
const abi_feature = @import("../../core/abi/wgpu_feature_base_types.zig");

// WebGPU spec minimum limits — used as floor values to guarantee spec compliance.
const WEBGPU_MIN_MAX_TEXTURE_DIMENSION_1D: u32 = 8192;
const WEBGPU_MIN_MAX_TEXTURE_DIMENSION_2D: u32 = 8192;
const WEBGPU_MIN_MAX_TEXTURE_DIMENSION_3D: u32 = 2048;
const WEBGPU_MIN_MAX_TEXTURE_ARRAY_LAYERS: u32 = 256;
const WEBGPU_MIN_MAX_BIND_GROUPS: u32 = 4;
const WEBGPU_MIN_MAX_BINDINGS_PER_BIND_GROUP: u32 = 1000;
const WEBGPU_MIN_MAX_DYNAMIC_UNIFORM_BUFFERS: u32 = 8;
const WEBGPU_MIN_MAX_DYNAMIC_STORAGE_BUFFERS: u32 = 4;
const WEBGPU_MIN_MAX_SAMPLED_TEXTURES: u32 = 16;
const WEBGPU_MIN_MAX_SAMPLERS: u32 = 16;
const WEBGPU_MIN_MAX_STORAGE_BUFFERS: u32 = 8;
const WEBGPU_MIN_MAX_STORAGE_TEXTURES: u32 = 4;
const WEBGPU_MIN_MAX_UNIFORM_BUFFERS: u32 = 12;
const WEBGPU_MIN_MAX_UNIFORM_BUFFER_BINDING_SIZE: u64 = 65_536;
const WEBGPU_MIN_MAX_STORAGE_BUFFER_BINDING_SIZE: u64 = 134_217_728;
const WEBGPU_MAX_MIN_UNIFORM_BUFFER_OFFSET_ALIGNMENT: u32 = 256;
const WEBGPU_MAX_MIN_STORAGE_BUFFER_OFFSET_ALIGNMENT: u32 = 256;
const WEBGPU_MIN_MAX_VERTEX_BUFFERS: u32 = 8;
const WEBGPU_MIN_MAX_BUFFER_SIZE: u64 = 268_435_456;
const WEBGPU_MIN_MAX_VERTEX_ATTRIBUTES: u32 = 16;
const WEBGPU_MIN_MAX_VERTEX_BUFFER_ARRAY_STRIDE: u32 = 2048;
const WEBGPU_MIN_MAX_INTER_STAGE_SHADER_VARIABLES: u32 = 16;
const WEBGPU_MIN_MAX_COLOR_ATTACHMENTS: u32 = 8;
const WEBGPU_MIN_MAX_COLOR_ATTACHMENT_BYTES_PER_SAMPLE: u32 = 32;
const WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_STORAGE_SIZE: u32 = 16384;
const WEBGPU_MIN_MAX_COMPUTE_INVOCATIONS_PER_WORKGROUP: u32 = 256;
const WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_SIZE_X: u32 = 256;
const WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_SIZE_Y: u32 = 256;
const WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_SIZE_Z: u32 = 64;
const WEBGPU_MIN_MAX_COMPUTE_WORKGROUPS_PER_DIMENSION: u32 = 65535;

// WebGPU feature name constants.
const FEATURE_DEPTH_CLIP_CONTROL: u32 = abi_feature.WGPUFeatureName_DepthClipControl;
const FEATURE_DEPTH32FLOAT_STENCIL8: u32 = abi_feature.WGPUFeatureName_Depth32FloatStencil8;
const FEATURE_TEXTURE_COMPRESSION_BC: u32 = abi_feature.WGPUFeatureName_TextureCompressionBC;
const FEATURE_TEXTURE_COMPRESSION_ETC2: u32 = abi_feature.WGPUFeatureName_TextureCompressionETC2;
const FEATURE_TEXTURE_COMPRESSION_ASTC: u32 = abi_feature.WGPUFeatureName_TextureCompressionASTC;
const FEATURE_INDIRECT_FIRST_INSTANCE: u32 = abi_feature.WGPUFeatureName_IndirectFirstInstance;
const FEATURE_FLOAT32_FILTERABLE: u32 = abi_feature.WGPUFeatureName_Float32Filterable;
const FEATURE_TIMESTAMP_QUERY: u32 = abi_feature.WGPUFeatureName_TimestampQuery;

/// Cached result from querying a Vulkan physical device's limits and features.
pub const VulkanDeviceCaps = struct {
    limits: abi_callback.WGPULimits,
    has_depth_clip_control: bool,
    has_texture_compression_bc: bool,
    has_texture_compression_etc2: bool,
    has_texture_compression_astc: bool,
    has_draw_indirect_first_instance: bool,
    has_float32_filterable: bool,
    has_timestamp_query: bool,
};

/// Query the Vulkan physical device and return WebGPU-mapped limits and features.
/// The timestamp_valid_bits argument comes from queue family selection.
pub fn query_device_caps(
    physical_device: c.VkPhysicalDevice,
    timestamp_valid_bits: u32,
) VulkanDeviceCaps {
    var properties2 = std.mem.zeroes(c.VkPhysicalDeviceProperties2);
    properties2.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;
    properties2.pNext = null;
    c.vkGetPhysicalDeviceProperties2(physical_device, &properties2);

    const vk_limits = properties2.properties.limits;

    var features2 = std.mem.zeroes(c.VkPhysicalDeviceFeatures2);
    features2.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2;
    features2.pNext = null;
    c.vkGetPhysicalDeviceFeatures2(physical_device, &features2);

    const vk_features = features2.features;

    // Check VK_EXT_depth_clip_enable extension availability.
    const depth_clip_available = detect_device_extension(
        physical_device,
        c.VK_EXT_DEPTH_CLIP_ENABLE_EXTENSION_NAME,
    );

    // Check float32 filterability via format properties.
    const float32_filterable = check_float32_filterable(physical_device);

    const wgpu_limits = map_vulkan_to_wgpu_limits(vk_limits);

    return VulkanDeviceCaps{
        .limits = wgpu_limits,
        .has_depth_clip_control = depth_clip_available,
        .has_texture_compression_bc = vk_features.textureCompressionBC == c.VK_TRUE,
        .has_texture_compression_etc2 = vk_features.textureCompressionETC2 == c.VK_TRUE,
        .has_texture_compression_astc = vk_features.textureCompressionASTC_LDR == c.VK_TRUE,
        .has_draw_indirect_first_instance = vk_features.drawIndirectFirstInstance == c.VK_TRUE,
        .has_float32_filterable = float32_filterable,
        .has_timestamp_query = timestamp_valid_bits > 0,
    };
}

/// Map VkPhysicalDeviceLimits to WGPULimits using WebGPU spec minimum guarantees as floor.
fn map_vulkan_to_wgpu_limits(
    vk_limits: c.VkPhysicalDeviceLimits,
) abi_callback.WGPULimits {
    return abi_callback.WGPULimits{
        .nextInChain = null,
        .maxTextureDimension1D = @max(vk_limits.maxImageDimension1D, WEBGPU_MIN_MAX_TEXTURE_DIMENSION_1D),
        .maxTextureDimension2D = @max(vk_limits.maxImageDimension2D, WEBGPU_MIN_MAX_TEXTURE_DIMENSION_2D),
        .maxTextureDimension3D = @max(vk_limits.maxImageDimension3D, WEBGPU_MIN_MAX_TEXTURE_DIMENSION_3D),
        .maxTextureArrayLayers = @max(vk_limits.maxImageArrayLayers, WEBGPU_MIN_MAX_TEXTURE_ARRAY_LAYERS),
        .maxBindGroups = @min(WEBGPU_MIN_MAX_BIND_GROUPS, vk_limits.maxBoundDescriptorSets),
        .maxBindGroupsPlusVertexBuffers = 24,
        .maxBindingsPerBindGroup = WEBGPU_MIN_MAX_BINDINGS_PER_BIND_GROUP,
        .maxDynamicUniformBuffersPerPipelineLayout = WEBGPU_MIN_MAX_DYNAMIC_UNIFORM_BUFFERS,
        .maxDynamicStorageBuffersPerPipelineLayout = WEBGPU_MIN_MAX_DYNAMIC_STORAGE_BUFFERS,
        .maxSampledTexturesPerShaderStage = @max(vk_limits.maxPerStageDescriptorSampledImages, WEBGPU_MIN_MAX_SAMPLED_TEXTURES),
        .maxSamplersPerShaderStage = @max(vk_limits.maxPerStageDescriptorSamplers, WEBGPU_MIN_MAX_SAMPLERS),
        .maxStorageBuffersPerShaderStage = @max(vk_limits.maxPerStageDescriptorStorageBuffers, WEBGPU_MIN_MAX_STORAGE_BUFFERS),
        .maxStorageTexturesPerShaderStage = @max(vk_limits.maxPerStageDescriptorStorageImages, WEBGPU_MIN_MAX_STORAGE_TEXTURES),
        .maxUniformBuffersPerShaderStage = @max(vk_limits.maxPerStageDescriptorUniformBuffers, WEBGPU_MIN_MAX_UNIFORM_BUFFERS),
        .maxUniformBufferBindingSize = @max(vk_limits.maxUniformBufferRange, WEBGPU_MIN_MAX_UNIFORM_BUFFER_BINDING_SIZE),
        .maxStorageBufferBindingSize = @max(vk_limits.maxStorageBufferRange, WEBGPU_MIN_MAX_STORAGE_BUFFER_BINDING_SIZE),
        .minUniformBufferOffsetAlignment = clamp_alignment(@intCast(vk_limits.minUniformBufferOffsetAlignment), WEBGPU_MAX_MIN_UNIFORM_BUFFER_OFFSET_ALIGNMENT),
        .minStorageBufferOffsetAlignment = clamp_alignment(@intCast(vk_limits.minStorageBufferOffsetAlignment), WEBGPU_MAX_MIN_STORAGE_BUFFER_OFFSET_ALIGNMENT),
        .maxVertexBuffers = @min(WEBGPU_MIN_MAX_VERTEX_BUFFERS, vk_limits.maxVertexInputBindings),
        .maxBufferSize = @max(buffer_size_from_storage_range(vk_limits.maxStorageBufferRange), WEBGPU_MIN_MAX_BUFFER_SIZE),
        .maxVertexAttributes = @max(vk_limits.maxVertexInputAttributes, WEBGPU_MIN_MAX_VERTEX_ATTRIBUTES),
        .maxVertexBufferArrayStride = @max(vk_limits.maxVertexInputBindingStride, WEBGPU_MIN_MAX_VERTEX_BUFFER_ARRAY_STRIDE),
        .maxInterStageShaderVariables = WEBGPU_MIN_MAX_INTER_STAGE_SHADER_VARIABLES,
        .maxColorAttachments = @min(WEBGPU_MIN_MAX_COLOR_ATTACHMENTS, vk_limits.maxColorAttachments),
        .maxColorAttachmentBytesPerSample = WEBGPU_MIN_MAX_COLOR_ATTACHMENT_BYTES_PER_SAMPLE,
        .maxComputeWorkgroupStorageSize = @max(vk_limits.maxComputeSharedMemorySize, WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_STORAGE_SIZE),
        .maxComputeInvocationsPerWorkgroup = @max(vk_limits.maxComputeWorkGroupInvocations, WEBGPU_MIN_MAX_COMPUTE_INVOCATIONS_PER_WORKGROUP),
        .maxComputeWorkgroupSizeX = @max(vk_limits.maxComputeWorkGroupSize[0], WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_SIZE_X),
        .maxComputeWorkgroupSizeY = @max(vk_limits.maxComputeWorkGroupSize[1], WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_SIZE_Y),
        .maxComputeWorkgroupSizeZ = @max(vk_limits.maxComputeWorkGroupSize[2], WEBGPU_MIN_MAX_COMPUTE_WORKGROUP_SIZE_Z),
        .maxComputeWorkgroupsPerDimension = @max(vk_limits.maxComputeWorkGroupCount[0], WEBGPU_MIN_MAX_COMPUTE_WORKGROUPS_PER_DIMENSION),
        .maxImmediateSize = 0,
    };
}

/// Derive maxBufferSize from maxStorageBufferRange when no Maintenance3 properties
/// are available. The storage buffer range is a reasonable proxy for maximum
/// buffer allocation on Vulkan 1.0 devices.
fn buffer_size_from_storage_range(max_storage_buffer_range: u32) u64 {
    return @as(u64, max_storage_buffer_range);
}

/// For alignment fields, Vulkan reports the hardware minimum alignment.
/// WebGPU reports the alignment the implementation requires, which must be
/// at most the spec-defined maximum. Use the Vulkan value when it is within
/// spec bounds, otherwise fall back to the WebGPU maximum.
fn clamp_alignment(hw_alignment: u32, spec_max: u32) u32 {
    if (hw_alignment == 0) return spec_max;
    return if (hw_alignment <= spec_max) hw_alignment else spec_max;
}

/// Check whether the device supports linear filtering on R32Float and RG32Float.
/// These are the primary formats for the float32-filterable WebGPU feature.
fn check_float32_filterable(physical_device: c.VkPhysicalDevice) bool {
    const VK_FORMAT_R32_SFLOAT: u32 = 100;
    const VK_FORMAT_R32G32_SFLOAT: u32 = 103;
    const VK_FORMAT_R32G32B32A32_SFLOAT: u32 = 109;
    const VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT: u32 = 0x00001000;

    const formats = [_]u32{
        VK_FORMAT_R32_SFLOAT,
        VK_FORMAT_R32G32_SFLOAT,
        VK_FORMAT_R32G32B32A32_SFLOAT,
    };
    for (formats) |format| {
        var props = std.mem.zeroes(c.VkFormatProperties);
        c.vkGetPhysicalDeviceFormatProperties(physical_device, format, &props);
        if ((props.optimalTilingFeatures & VK_FORMAT_FEATURE_SAMPLED_IMAGE_FILTER_LINEAR_BIT) == 0) {
            return false;
        }
    }
    return true;
}

/// Check whether a physical device advertises a given extension by name.
const MAX_DEVICE_EXTENSIONS: u32 = 512;

fn detect_device_extension(physical_device: c.VkPhysicalDevice, target_name: [*:0]const u8) bool {
    var count: u32 = 0;
    const count_result = c.vkEnumerateDeviceExtensionProperties(physical_device, null, &count, null);
    if (count_result != c.VK_SUCCESS or count == 0) return false;
    if (count > MAX_DEVICE_EXTENSIONS) count = MAX_DEVICE_EXTENSIONS;

    var props: [MAX_DEVICE_EXTENSIONS]c.VkExtensionProperties = undefined;
    const enum_result = c.vkEnumerateDeviceExtensionProperties(physical_device, null, &count, &props);
    if (enum_result != c.VK_SUCCESS) return false;

    const target_len = std.mem.len(target_name);
    var i: u32 = 0;
    while (i < count) : (i += 1) {
        const name_bytes = &props[i].extensionName;
        const ext_len = std.mem.indexOfScalar(u8, name_bytes, 0) orelse name_bytes.len;
        if (ext_len == target_len and std.mem.eql(u8, name_bytes[0..ext_len], target_name[0..target_len])) {
            return true;
        }
    }
    return false;
}

/// Check whether a specific WebGPU feature is supported by queried Vulkan device caps.
pub fn has_feature(caps: VulkanDeviceCaps, feature: u32) bool {
    return switch (feature) {
        FEATURE_DEPTH_CLIP_CONTROL => caps.has_depth_clip_control,
        FEATURE_DEPTH32FLOAT_STENCIL8 => true,
        FEATURE_TEXTURE_COMPRESSION_BC => caps.has_texture_compression_bc,
        FEATURE_TEXTURE_COMPRESSION_ETC2 => caps.has_texture_compression_etc2,
        FEATURE_TEXTURE_COMPRESSION_ASTC => caps.has_texture_compression_astc,
        FEATURE_INDIRECT_FIRST_INSTANCE => caps.has_draw_indirect_first_instance,
        FEATURE_FLOAT32_FILTERABLE => caps.has_float32_filterable,
        FEATURE_TIMESTAMP_QUERY => caps.has_timestamp_query,
        else => false,
    };
}

/// Query device caps using a probe runtime (temporary instance + physical device).
/// Suitable for adapter-time queries before a full device is created.
pub fn probe_device_caps(allocator: std.mem.Allocator) !VulkanDeviceCaps {
    const vk_device = @import("vk_device.zig");
    const NativeVulkanRuntime = @import("native_runtime.zig").NativeVulkanRuntime;

    var probe = NativeVulkanRuntime{ .allocator = allocator, .kernel_root = null };
    try vk_device.create_instance(&probe);
    defer if (probe.has_instance) {
        c.vkDestroyInstance(probe.instance, null);
        probe.instance = null;
        probe.has_instance = false;
        probe.physical_device = null;
    };
    try vk_device.select_physical_device(&probe);
    return query_device_caps(
        probe.physical_device,
        if (probe.timestamp_query_supported_value) 36 else 0,
    );
}
