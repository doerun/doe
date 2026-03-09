// doe_device_caps.zig — Device capability queries: feature reporting and limits.
// Sharded from doe_wgpu_native.zig to stay under 777-line limit.

const types = @import("core/abi/wgpu_types.zig");

// ============================================================
// Feature queries — report shader-f16 as supported (Metal natively supports half).
const FEATURE_SHADER_F16 = types.WGPUFeatureName_ShaderF16;

pub export fn doeNativeAdapterHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    if (feature == FEATURE_SHADER_F16) return 1;
    return 0;
}

pub export fn doeNativeDeviceHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    if (feature == FEATURE_SHADER_F16) return 1;
    return 0;
}

// ============================================================
// Device / Adapter limits — Metal defaults for Apple Silicon.
const METAL_LIMITS = types.WGPULimits{
    .nextInChain = null,
    .maxTextureDimension1D = 16384,
    .maxTextureDimension2D = 16384,
    .maxTextureDimension3D = 2048,
    .maxTextureArrayLayers = 2048,
    .maxBindGroups = 4,
    .maxBindGroupsPlusVertexBuffers = 24,
    .maxBindingsPerBindGroup = 1000,
    .maxDynamicUniformBuffersPerPipelineLayout = 8,
    .maxDynamicStorageBuffersPerPipelineLayout = 4,
    .maxSampledTexturesPerShaderStage = 16,
    .maxSamplersPerShaderStage = 16,
    .maxStorageBuffersPerShaderStage = 8,
    .maxStorageTexturesPerShaderStage = 4,
    .maxUniformBuffersPerShaderStage = 12,
    .maxUniformBufferBindingSize = 65536,
    .maxStorageBufferBindingSize = 134217728, // 128 MB
    .minUniformBufferOffsetAlignment = 256,
    .minStorageBufferOffsetAlignment = 32,
    .maxVertexBuffers = 8,
    .maxBufferSize = 268435456, // 256 MB
    .maxVertexAttributes = 16,
    .maxVertexBufferArrayStride = 2048,
    .maxInterStageShaderVariables = 16,
    .maxColorAttachments = 8,
    .maxColorAttachmentBytesPerSample = 32,
    .maxComputeWorkgroupStorageSize = 32768,
    .maxComputeInvocationsPerWorkgroup = 1024,
    .maxComputeWorkgroupSizeX = 1024,
    .maxComputeWorkgroupSizeY = 1024,
    .maxComputeWorkgroupSizeZ = 64,
    .maxComputeWorkgroupsPerDimension = 65535,
    .maxImmediateSize = 0,
};

pub export fn doeNativeDeviceGetLimits(raw: ?*anyopaque, limits: ?*types.WGPULimits) callconv(.c) types.WGPUStatus {
    _ = raw;
    if (limits) |l| l.* = METAL_LIMITS;
    return types.WGPUStatus_Success;
}

pub export fn doeNativeAdapterGetLimits(raw: ?*anyopaque, limits: ?*types.WGPULimits) callconv(.c) types.WGPUStatus {
    _ = raw;
    if (limits) |l| l.* = METAL_LIMITS;
    return types.WGPUStatus_Success;
}
