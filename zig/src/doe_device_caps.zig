// doe_device_caps.zig — Device capability queries: feature reporting and limits.
// Sharded from doe_wgpu_native.zig to stay under 777-line limit.

const types = @import("core/abi/wgpu_types.zig");

const METAL_MAX_TEXTURE_DIMENSION_1D: u32 = 16_384;
const METAL_MAX_TEXTURE_DIMENSION_2D: u32 = 16_384;
const METAL_MAX_TEXTURE_DIMENSION_3D: u32 = 2_048;
const METAL_MAX_TEXTURE_ARRAY_LAYERS: u32 = 2_048;
const METAL_MAX_UNIFORM_BUFFER_BINDING_SIZE: u64 = 64 * 1024;
const METAL_MAX_STORAGE_BUFFER_BINDING_SIZE: u64 = 128 * 1024 * 1024;
const METAL_MAX_BUFFER_SIZE: u64 = 256 * 1024 * 1024;
const METAL_MAX_VERTEX_BUFFER_ARRAY_STRIDE: u32 = 2_048;
const METAL_MAX_COMPUTE_WORKGROUP_STORAGE_SIZE: u32 = 32 * 1024;
const METAL_MAX_COMPUTE_INVOCATIONS_PER_WORKGROUP: u32 = 1_024;
const METAL_MAX_COMPUTE_WORKGROUP_SIZE_X: u32 = 1_024;
const METAL_MAX_COMPUTE_WORKGROUP_SIZE_Y: u32 = 1_024;
const METAL_MAX_COMPUTE_WORKGROUPS_PER_DIMENSION: u32 = 65_535;

pub export fn doeNativeAdapterHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    if (feature == types.WGPUFeatureName_ShaderF16) return 1;
    return 0;
}

pub export fn doeNativeDeviceHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    if (feature == types.WGPUFeatureName_ShaderF16) return 1;
    return 0;
}

// ============================================================
// Device / Adapter limits — Metal defaults for Apple Silicon.
const METAL_LIMITS = types.WGPULimits{
    .nextInChain = null,
    .maxTextureDimension1D = METAL_MAX_TEXTURE_DIMENSION_1D,
    .maxTextureDimension2D = METAL_MAX_TEXTURE_DIMENSION_2D,
    .maxTextureDimension3D = METAL_MAX_TEXTURE_DIMENSION_3D,
    .maxTextureArrayLayers = METAL_MAX_TEXTURE_ARRAY_LAYERS,
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
    .maxUniformBufferBindingSize = METAL_MAX_UNIFORM_BUFFER_BINDING_SIZE,
    .maxStorageBufferBindingSize = METAL_MAX_STORAGE_BUFFER_BINDING_SIZE,
    .minUniformBufferOffsetAlignment = 256,
    .minStorageBufferOffsetAlignment = 32,
    .maxVertexBuffers = 8,
    .maxBufferSize = METAL_MAX_BUFFER_SIZE,
    .maxVertexAttributes = 16,
    .maxVertexBufferArrayStride = METAL_MAX_VERTEX_BUFFER_ARRAY_STRIDE,
    .maxInterStageShaderVariables = 16,
    .maxColorAttachments = 8,
    .maxColorAttachmentBytesPerSample = 32,
    .maxComputeWorkgroupStorageSize = METAL_MAX_COMPUTE_WORKGROUP_STORAGE_SIZE,
    .maxComputeInvocationsPerWorkgroup = METAL_MAX_COMPUTE_INVOCATIONS_PER_WORKGROUP,
    .maxComputeWorkgroupSizeX = METAL_MAX_COMPUTE_WORKGROUP_SIZE_X,
    .maxComputeWorkgroupSizeY = METAL_MAX_COMPUTE_WORKGROUP_SIZE_Y,
    .maxComputeWorkgroupSizeZ = 64,
    .maxComputeWorkgroupsPerDimension = METAL_MAX_COMPUTE_WORKGROUPS_PER_DIMENSION,
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
