// doe_device_caps.zig — Device capability queries: feature reporting and limits.
// Sharded from doe_wgpu_native.zig to stay under 777-line limit.
//
// Feature detection uses runtime Metal device queries via metal_bridge_query_device_features()
// instead of compile-time OS-tag heuristics. Each feature is probed against the actual GPU
// hardware (e.g. MTLGPUFamily checks, counter sampling support) and cached on first call.

const builtin = @import("builtin");
const types = @import("core/abi/wgpu_types.zig");

// ============================================================
// Feature bitmask positions — must match METAL_FEATURE_BIT_* in metal_bridge.h

const FEATURE_BIT_SHADER_F16: u32 = 1 << 0;
const FEATURE_BIT_SUBGROUPS: u32 = 1 << 1;
const FEATURE_BIT_TIMESTAMP_QUERY: u32 = 1 << 2;
const FEATURE_BIT_INDIRECT_FIRST_INSTANCE: u32 = 1 << 3;
const FEATURE_BIT_DEPTH_CLIP_CONTROL: u32 = 1 << 4;
const FEATURE_BIT_DEPTH32FLOAT_STENCIL8: u32 = 1 << 5;
const FEATURE_BIT_BGRA8UNORM_STORAGE: u32 = 1 << 6;
const FEATURE_BIT_FLOAT32_FILTERABLE: u32 = 1 << 7;
const FEATURE_BIT_FLOAT32_BLENDABLE: u32 = 1 << 8;
const FEATURE_BIT_TEXTURE_COMPRESSION_ASTC: u32 = 1 << 9;
const FEATURE_BIT_TEXTURE_COMPRESSION_BC: u32 = 1 << 10;
const FEATURE_BIT_TEXTURE_COMPRESSION_BC_SLICED_3D: u32 = 1 << 11;
const FEATURE_BIT_TEXTURE_COMPRESSION_ETC2: u32 = 1 << 12;
const FEATURE_BIT_RG11B10UFLOAT_RENDERABLE: u32 = 1 << 13;
const FEATURE_BIT_SUBGROUPS_F16: u32 = 1 << 14;
const FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D: u32 = 1 << 15;
const FEATURE_BIT_CLIP_DISTANCES: u32 = 1 << 16;
const FEATURE_BIT_DUAL_SOURCE_BLENDING: u32 = 1 << 17;

// ============================================================
// Metal bridge import (runtime query) or no-op stub for non-Metal targets

const IS_METAL: bool = builtin.os.tag == .macos or builtin.os.tag == .ios;

const metal_bridge = if (IS_METAL)
    @import("backend/metal/metal_bridge_decls.zig")
else
    struct {
        pub fn metal_bridge_query_device_features() callconv(.c) u32 {
            return 0;
        }
    };

fn getDeviceFeatures() u32 {
    return metal_bridge.metal_bridge_query_device_features();
}

// ============================================================
// Feature query — maps WGPU feature name to runtime bitmask check

fn queryFeatureSupport(feature: u32) u32 {
    const features = getDeviceFeatures();
    return switch (feature) {
        types.WGPUFeatureName_ShaderF16 => if (features & FEATURE_BIT_SHADER_F16 != 0) 1 else 0,
        types.WGPUFeatureName_Subgroups => if (features & FEATURE_BIT_SUBGROUPS != 0) 1 else 0,
        types.WGPUFeatureName_TimestampQuery => if (features & FEATURE_BIT_TIMESTAMP_QUERY != 0) 1 else 0,
        types.WGPUFeatureName_IndirectFirstInstance => if (features & FEATURE_BIT_INDIRECT_FIRST_INSTANCE != 0) 1 else 0,
        types.WGPUFeatureName_DepthClipControl => if (features & FEATURE_BIT_DEPTH_CLIP_CONTROL != 0) 1 else 0,
        types.WGPUFeatureName_Depth32FloatStencil8 => if (features & FEATURE_BIT_DEPTH32FLOAT_STENCIL8 != 0) 1 else 0,
        types.WGPUFeatureName_BGRA8UnormStorage => if (features & FEATURE_BIT_BGRA8UNORM_STORAGE != 0) 1 else 0,
        types.WGPUFeatureName_Float32Filterable => if (features & FEATURE_BIT_FLOAT32_FILTERABLE != 0) 1 else 0,
        types.WGPUFeatureName_Float32Blendable => if (features & FEATURE_BIT_FLOAT32_BLENDABLE != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionASTC => if (features & FEATURE_BIT_TEXTURE_COMPRESSION_ASTC != 0) 1 else 0,
        types.WGPUFeatureName_RG11B10UfloatRenderable => if (features & FEATURE_BIT_RG11B10UFLOAT_RENDERABLE != 0) 1 else 0,
        types.WGPUFeatureName_SubgroupsF16 => if (features & FEATURE_BIT_SUBGROUPS_F16 != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionASTCSliced3D => if (features & FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionBC => if (features & FEATURE_BIT_TEXTURE_COMPRESSION_BC != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionBCSliced3D => if (features & FEATURE_BIT_TEXTURE_COMPRESSION_BC_SLICED_3D != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionETC2 => if (features & FEATURE_BIT_TEXTURE_COMPRESSION_ETC2 != 0) 1 else 0,
        types.WGPUFeatureName_ClipDistances => if (features & FEATURE_BIT_CLIP_DISTANCES != 0) 1 else 0,
        types.WGPUFeatureName_DualSourceBlending => if (features & FEATURE_BIT_DUAL_SOURCE_BLENDING != 0) 1 else 0,
        else => 0,
    };
}

/// Map a bitmask value to feature support results for testing.
/// Allows unit tests to verify the bitmask-to-feature mapping
/// without depending on actual hardware.
fn queryFeatureFromBitmask(bitmask: u32, feature: u32) u32 {
    return switch (feature) {
        types.WGPUFeatureName_ShaderF16 => if (bitmask & FEATURE_BIT_SHADER_F16 != 0) 1 else 0,
        types.WGPUFeatureName_Subgroups => if (bitmask & FEATURE_BIT_SUBGROUPS != 0) 1 else 0,
        types.WGPUFeatureName_TimestampQuery => if (bitmask & FEATURE_BIT_TIMESTAMP_QUERY != 0) 1 else 0,
        types.WGPUFeatureName_IndirectFirstInstance => if (bitmask & FEATURE_BIT_INDIRECT_FIRST_INSTANCE != 0) 1 else 0,
        types.WGPUFeatureName_DepthClipControl => if (bitmask & FEATURE_BIT_DEPTH_CLIP_CONTROL != 0) 1 else 0,
        types.WGPUFeatureName_Depth32FloatStencil8 => if (bitmask & FEATURE_BIT_DEPTH32FLOAT_STENCIL8 != 0) 1 else 0,
        types.WGPUFeatureName_BGRA8UnormStorage => if (bitmask & FEATURE_BIT_BGRA8UNORM_STORAGE != 0) 1 else 0,
        types.WGPUFeatureName_Float32Filterable => if (bitmask & FEATURE_BIT_FLOAT32_FILTERABLE != 0) 1 else 0,
        types.WGPUFeatureName_Float32Blendable => if (bitmask & FEATURE_BIT_FLOAT32_BLENDABLE != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionASTC => if (bitmask & FEATURE_BIT_TEXTURE_COMPRESSION_ASTC != 0) 1 else 0,
        types.WGPUFeatureName_RG11B10UfloatRenderable => if (bitmask & FEATURE_BIT_RG11B10UFLOAT_RENDERABLE != 0) 1 else 0,
        types.WGPUFeatureName_SubgroupsF16 => if (bitmask & FEATURE_BIT_SUBGROUPS_F16 != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionASTCSliced3D => if (bitmask & FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionBC => if (bitmask & FEATURE_BIT_TEXTURE_COMPRESSION_BC != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionBCSliced3D => if (bitmask & FEATURE_BIT_TEXTURE_COMPRESSION_BC_SLICED_3D != 0) 1 else 0,
        types.WGPUFeatureName_TextureCompressionETC2 => if (bitmask & FEATURE_BIT_TEXTURE_COMPRESSION_ETC2 != 0) 1 else 0,
        types.WGPUFeatureName_ClipDistances => if (bitmask & FEATURE_BIT_CLIP_DISTANCES != 0) 1 else 0,
        types.WGPUFeatureName_DualSourceBlending => if (bitmask & FEATURE_BIT_DUAL_SOURCE_BLENDING != 0) 1 else 0,
        else => 0,
    };
}

pub export fn doeNativeAdapterHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    return queryFeatureSupport(feature);
}

pub export fn doeNativeDeviceHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    return queryFeatureSupport(feature);
}

// ============================================================
// Device / Adapter limits — Metal defaults for Apple Silicon.

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

test "adapter and device feature queries are symmetric" {
    // Both adapter and device must agree on every standardized feature
    const features = [_]u32{
        types.WGPUFeatureName_ShaderF16,
        types.WGPUFeatureName_Subgroups,
        types.WGPUFeatureName_TimestampQuery,
        types.WGPUFeatureName_IndirectFirstInstance,
        types.WGPUFeatureName_DepthClipControl,
        types.WGPUFeatureName_Depth32FloatStencil8,
        types.WGPUFeatureName_BGRA8UnormStorage,
        types.WGPUFeatureName_Float32Filterable,
        types.WGPUFeatureName_Float32Blendable,
        types.WGPUFeatureName_TextureCompressionASTC,
        types.WGPUFeatureName_TextureCompressionBC,
        types.WGPUFeatureName_TextureCompressionBCSliced3D,
        types.WGPUFeatureName_TextureCompressionETC2,
        types.WGPUFeatureName_RG11B10UfloatRenderable,
        types.WGPUFeatureName_SubgroupsF16,
        types.WGPUFeatureName_TextureCompressionASTCSliced3D,
        types.WGPUFeatureName_ClipDistances,
        types.WGPUFeatureName_DualSourceBlending,
    };
    for (features) |f| {
        try testing.expectEqual(doeNativeAdapterHasFeature(null, f), doeNativeDeviceHasFeature(null, f));
    }
}

test "bitmask-to-feature mapping: all bits set" {
    // Verify that every feature bit maps to the correct WGPU feature name
    const all_features: u32 = FEATURE_BIT_SHADER_F16 | FEATURE_BIT_SUBGROUPS |
        FEATURE_BIT_TIMESTAMP_QUERY | FEATURE_BIT_INDIRECT_FIRST_INSTANCE |
        FEATURE_BIT_DEPTH_CLIP_CONTROL | FEATURE_BIT_DEPTH32FLOAT_STENCIL8 |
        FEATURE_BIT_BGRA8UNORM_STORAGE | FEATURE_BIT_FLOAT32_FILTERABLE |
        FEATURE_BIT_FLOAT32_BLENDABLE | FEATURE_BIT_TEXTURE_COMPRESSION_ASTC |
        FEATURE_BIT_TEXTURE_COMPRESSION_BC | FEATURE_BIT_TEXTURE_COMPRESSION_BC_SLICED_3D |
        FEATURE_BIT_TEXTURE_COMPRESSION_ETC2 |
        FEATURE_BIT_RG11B10UFLOAT_RENDERABLE | FEATURE_BIT_SUBGROUPS_F16 |
        FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D |
        FEATURE_BIT_CLIP_DISTANCES | FEATURE_BIT_DUAL_SOURCE_BLENDING;

    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_ShaderF16));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_Subgroups));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_TimestampQuery));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_IndirectFirstInstance));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_DepthClipControl));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_Depth32FloatStencil8));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_BGRA8UnormStorage));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_Float32Filterable));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_Float32Blendable));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_TextureCompressionASTC));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_TextureCompressionBC));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_TextureCompressionBCSliced3D));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_TextureCompressionETC2));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_RG11B10UfloatRenderable));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_SubgroupsF16));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_TextureCompressionASTCSliced3D));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_ClipDistances));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(all_features, types.WGPUFeatureName_DualSourceBlending));
}

test "bitmask-to-feature mapping: no bits set" {
    const no_features: u32 = 0;
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_ShaderF16));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_Subgroups));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_TimestampQuery));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_IndirectFirstInstance));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_DepthClipControl));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_Depth32FloatStencil8));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_BGRA8UnormStorage));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_Float32Filterable));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_Float32Blendable));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_TextureCompressionASTC));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_TextureCompressionBC));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_TextureCompressionBCSliced3D));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_TextureCompressionETC2));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_RG11B10UfloatRenderable));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_SubgroupsF16));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_TextureCompressionASTCSliced3D));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_ClipDistances));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(no_features, types.WGPUFeatureName_DualSourceBlending));
}

test "bitmask-to-feature mapping: individual bits are independent" {
    // Only shader-f16 bit set: only ShaderF16 should report true
    const f16_only: u32 = FEATURE_BIT_SHADER_F16;
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(f16_only, types.WGPUFeatureName_ShaderF16));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(f16_only, types.WGPUFeatureName_Subgroups));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(f16_only, types.WGPUFeatureName_TimestampQuery));

    // Only subgroups bit set: only Subgroups should report true
    const subgroups_only: u32 = FEATURE_BIT_SUBGROUPS;
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(subgroups_only, types.WGPUFeatureName_ShaderF16));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(subgroups_only, types.WGPUFeatureName_Subgroups));

    // Timestamp + ASTC bits: only those two should report true
    const partial: u32 = FEATURE_BIT_TIMESTAMP_QUERY | FEATURE_BIT_TEXTURE_COMPRESSION_ASTC;
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(partial, types.WGPUFeatureName_TimestampQuery));
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(partial, types.WGPUFeatureName_TextureCompressionASTC));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(partial, types.WGPUFeatureName_ShaderF16));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(partial, types.WGPUFeatureName_Float32Blendable));

    // RG11B10 renderable only: only that feature should report true
    const rg11b10_only: u32 = FEATURE_BIT_RG11B10UFLOAT_RENDERABLE;
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(rg11b10_only, types.WGPUFeatureName_RG11B10UfloatRenderable));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(rg11b10_only, types.WGPUFeatureName_SubgroupsF16));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(rg11b10_only, types.WGPUFeatureName_TextureCompressionASTCSliced3D));

    // Subgroups-f16 only: only that feature should report true
    const subgroups_f16_only: u32 = FEATURE_BIT_SUBGROUPS_F16;
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(subgroups_f16_only, types.WGPUFeatureName_SubgroupsF16));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(subgroups_f16_only, types.WGPUFeatureName_Subgroups));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(subgroups_f16_only, types.WGPUFeatureName_ShaderF16));

    // ASTC sliced 3D only
    const astc_3d_only: u32 = FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D;
    try testing.expectEqual(@as(u32, 1), queryFeatureFromBitmask(astc_3d_only, types.WGPUFeatureName_TextureCompressionASTCSliced3D));
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(astc_3d_only, types.WGPUFeatureName_TextureCompressionASTC));
}

test "unsupported features always return false regardless of bitmask" {
    const all_bits: u32 = 0xFFFFFFFF;
    // Unknown feature ID
    try testing.expectEqual(@as(u32, 0), queryFeatureFromBitmask(all_bits, 0xFFFFFFFF));
}

test "feature bit constants are unique powers of two" {
    const bits = [_]u32{
        FEATURE_BIT_SHADER_F16,
        FEATURE_BIT_SUBGROUPS,
        FEATURE_BIT_TIMESTAMP_QUERY,
        FEATURE_BIT_INDIRECT_FIRST_INSTANCE,
        FEATURE_BIT_DEPTH_CLIP_CONTROL,
        FEATURE_BIT_DEPTH32FLOAT_STENCIL8,
        FEATURE_BIT_BGRA8UNORM_STORAGE,
        FEATURE_BIT_FLOAT32_FILTERABLE,
        FEATURE_BIT_FLOAT32_BLENDABLE,
        FEATURE_BIT_TEXTURE_COMPRESSION_ASTC,
        FEATURE_BIT_TEXTURE_COMPRESSION_BC,
        FEATURE_BIT_TEXTURE_COMPRESSION_BC_SLICED_3D,
        FEATURE_BIT_TEXTURE_COMPRESSION_ETC2,
        FEATURE_BIT_RG11B10UFLOAT_RENDERABLE,
        FEATURE_BIT_SUBGROUPS_F16,
        FEATURE_BIT_TEXTURE_COMPRESSION_ASTC_SLICED_3D,
        FEATURE_BIT_CLIP_DISTANCES,
        FEATURE_BIT_DUAL_SOURCE_BLENDING,
    };
    // Each bit is a power of two
    for (bits) |b| {
        try testing.expect(b > 0);
        try testing.expectEqual(@as(u32, 0), b & (b - 1));
    }
    // No two bits overlap: OR of all should have exactly 18 bits set
    var combined: u32 = 0;
    for (bits) |b| combined |= b;
    try testing.expectEqual(@as(u32, 18), @popCount(combined));
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
