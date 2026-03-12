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

// ============================================================
// Inline tests
const std = @import("std");
const testing = std.testing;

test "METAL_LIMITS texture dimensions are positive" {
    try testing.expect(METAL_LIMITS.maxTextureDimension1D > 0);
    try testing.expect(METAL_LIMITS.maxTextureDimension2D > 0);
    try testing.expect(METAL_LIMITS.maxTextureDimension3D > 0);
    try testing.expect(METAL_LIMITS.maxTextureArrayLayers > 0);
}

test "METAL_LIMITS compute workgroup sizes are positive" {
    try testing.expect(METAL_LIMITS.maxComputeWorkgroupSizeX > 0);
    try testing.expect(METAL_LIMITS.maxComputeWorkgroupSizeY > 0);
    try testing.expect(METAL_LIMITS.maxComputeWorkgroupSizeZ > 0);
    try testing.expect(METAL_LIMITS.maxComputeInvocationsPerWorkgroup > 0);
    try testing.expect(METAL_LIMITS.maxComputeWorkgroupsPerDimension > 0);
    try testing.expect(METAL_LIMITS.maxComputeWorkgroupStorageSize > 0);
}

test "METAL_LIMITS buffer sizes respect hierarchy" {
    // maxBufferSize >= maxStorageBufferBindingSize >= maxUniformBufferBindingSize
    try testing.expect(METAL_LIMITS.maxBufferSize >= METAL_LIMITS.maxStorageBufferBindingSize);
    try testing.expect(METAL_LIMITS.maxStorageBufferBindingSize >= METAL_LIMITS.maxUniformBufferBindingSize);
}

test "METAL_LIMITS alignment values are powers of two" {
    try testing.expect(METAL_LIMITS.minUniformBufferOffsetAlignment > 0);
    try testing.expect(METAL_LIMITS.minStorageBufferOffsetAlignment > 0);
    // Power-of-two check: n & (n - 1) == 0 for n > 0
    try testing.expectEqual(@as(u32, 0), METAL_LIMITS.minUniformBufferOffsetAlignment & (METAL_LIMITS.minUniformBufferOffsetAlignment - 1));
    try testing.expectEqual(@as(u32, 0), METAL_LIMITS.minStorageBufferOffsetAlignment & (METAL_LIMITS.minStorageBufferOffsetAlignment - 1));
}

test "METAL_LIMITS named constants match struct fields" {
    try testing.expectEqual(METAL_MAX_TEXTURE_DIMENSION_1D, METAL_LIMITS.maxTextureDimension1D);
    try testing.expectEqual(METAL_MAX_TEXTURE_DIMENSION_2D, METAL_LIMITS.maxTextureDimension2D);
    try testing.expectEqual(METAL_MAX_TEXTURE_DIMENSION_3D, METAL_LIMITS.maxTextureDimension3D);
    try testing.expectEqual(METAL_MAX_TEXTURE_ARRAY_LAYERS, METAL_LIMITS.maxTextureArrayLayers);
    try testing.expectEqual(METAL_MAX_UNIFORM_BUFFER_BINDING_SIZE, METAL_LIMITS.maxUniformBufferBindingSize);
    try testing.expectEqual(METAL_MAX_STORAGE_BUFFER_BINDING_SIZE, METAL_LIMITS.maxStorageBufferBindingSize);
    try testing.expectEqual(METAL_MAX_BUFFER_SIZE, METAL_LIMITS.maxBufferSize);
    try testing.expectEqual(METAL_MAX_VERTEX_BUFFER_ARRAY_STRIDE, METAL_LIMITS.maxVertexBufferArrayStride);
    try testing.expectEqual(METAL_MAX_COMPUTE_WORKGROUP_STORAGE_SIZE, METAL_LIMITS.maxComputeWorkgroupStorageSize);
    try testing.expectEqual(METAL_MAX_COMPUTE_INVOCATIONS_PER_WORKGROUP, METAL_LIMITS.maxComputeInvocationsPerWorkgroup);
    try testing.expectEqual(METAL_MAX_COMPUTE_WORKGROUP_SIZE_X, METAL_LIMITS.maxComputeWorkgroupSizeX);
    try testing.expectEqual(METAL_MAX_COMPUTE_WORKGROUP_SIZE_Y, METAL_LIMITS.maxComputeWorkgroupSizeY);
    try testing.expectEqual(METAL_MAX_COMPUTE_WORKGROUPS_PER_DIMENSION, METAL_LIMITS.maxComputeWorkgroupsPerDimension);
}

test "adapter and device feature query returns true for ShaderF16" {
    try testing.expectEqual(@as(u32, 1), doeNativeAdapterHasFeature(null, types.WGPUFeatureName_ShaderF16));
    try testing.expectEqual(@as(u32, 1), doeNativeDeviceHasFeature(null, types.WGPUFeatureName_ShaderF16));
}

test "adapter and device feature query returns false for unsupported features" {
    // TimestampQuery is not reported as supported
    try testing.expectEqual(@as(u32, 0), doeNativeAdapterHasFeature(null, types.WGPUFeatureName_TimestampQuery));
    try testing.expectEqual(@as(u32, 0), doeNativeDeviceHasFeature(null, types.WGPUFeatureName_TimestampQuery));
    // Unknown feature ID
    try testing.expectEqual(@as(u32, 0), doeNativeAdapterHasFeature(null, 0xFFFFFFFF));
    try testing.expectEqual(@as(u32, 0), doeNativeDeviceHasFeature(null, 0xFFFFFFFF));
}

test "device and adapter GetLimits populates limits struct" {
    var limits: types.WGPULimits = undefined;
    const device_status = doeNativeDeviceGetLimits(null, &limits);
    try testing.expectEqual(types.WGPUStatus_Success, device_status);
    try testing.expectEqual(METAL_LIMITS.maxTextureDimension2D, limits.maxTextureDimension2D);
    try testing.expectEqual(METAL_LIMITS.maxComputeWorkgroupSizeX, limits.maxComputeWorkgroupSizeX);
    try testing.expectEqual(METAL_LIMITS.maxBufferSize, limits.maxBufferSize);

    var adapter_limits: types.WGPULimits = undefined;
    const adapter_status = doeNativeAdapterGetLimits(null, &adapter_limits);
    try testing.expectEqual(types.WGPUStatus_Success, adapter_status);
    try testing.expectEqual(METAL_LIMITS.maxTextureDimension2D, adapter_limits.maxTextureDimension2D);
}
