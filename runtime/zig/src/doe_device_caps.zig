// doe_device_caps.zig — Device capability queries: feature reporting and limits.
// Sharded from doe_wgpu_native.zig to stay under 777-line limit.
//
// Limits are queried from the hardware at runtime where possible, then cached.
// Static fallbacks apply on non-Metal targets or when hardware query fails.

const builtin = @import("builtin");
const types = @import("core/abi/wgpu_types.zig");

// Metal bridge — only linked on macOS; guarded by comptime platform check.
const BRIDGE_AVAILABLE = builtin.os.tag == .macos;

// ============================================================
// Feature name constants
// ============================================================

const FEATURE_SHADER_F16: u32 = types.WGPUFeatureName_ShaderF16;

// Extended feature constants not yet in wgpu_types.zig.
// Values follow the WebGPU spec extension namespace.
pub const FEATURE_SUBGROUPS: u32 = 0x0000000F;
pub const FEATURE_SUBGROUP_UNIFORMITY: u32 = 0x00000010;
pub const FEATURE_RW_STORAGE_TEXTURE: u32 = 0x00000014;
pub const FEATURE_LARGE_BUFFER: u32 = 0x00000015;

// ============================================================
// Limits: Apple Silicon hardware-specific defaults.
//
// maxBufferSize and maxStorageBufferBindingSize are queried from the
// device at runtime (via metal_bridge_device_max_buffer_length) when a
// device handle is available.  The constants below are conservative
// fallbacks for static/headless contexts.
// ============================================================

// Apple Silicon GPUs support buffers up to ~32 GB.
// The spec minimum is 256 MB; report the true hardware limit when possible.
const FALLBACK_MAX_BUFFER_SIZE: u64 = 268_435_456; // 256 MB — spec minimum

// Metal uniform buffer binding size limit (hardware-imposed, not tunable).
const METAL_MAX_UNIFORM_BUFFER_BINDING_SIZE: u64 = 65_536; // 64 KB

// Metal subgroup (SIMD-group) size on Apple Silicon (all known variants).
pub const METAL_SIMD_GROUP_SIZE: u32 = 32;

// Default Metal limits (used when no device handle is available).
const METAL_LIMITS_STATIC = types.WGPULimits{
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
    .maxUniformBufferBindingSize = METAL_MAX_UNIFORM_BUFFER_BINDING_SIZE,
    .maxStorageBufferBindingSize = FALLBACK_MAX_BUFFER_SIZE,
    .minUniformBufferOffsetAlignment = 256,
    .minStorageBufferOffsetAlignment = 32,
    .maxVertexBuffers = 8,
    .maxBufferSize = FALLBACK_MAX_BUFFER_SIZE,
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

// Resolved by metal_bridge.m at link time. This file is only compiled on
// macOS (doe_wgpu_native.zig — its only importer — is platform-guarded).
extern fn metal_bridge_device_max_buffer_length(device: ?*anyopaque) callconv(.c) u64;

// Query the actual device max buffer length from a raw MTLDevice handle.
// The `raw` argument here must be an MTLDevice (not a DoeDevice wrapper).
// Falls back to the static conservative value when unavailable.
fn query_max_buffer_length(mtl_device: ?*anyopaque) u64 {
    if (mtl_device == null) return FALLBACK_MAX_BUFFER_SIZE;
    const hw_limit = metal_bridge_device_max_buffer_length(mtl_device);
    return if (hw_limit > 0) hw_limit else FALLBACK_MAX_BUFFER_SIZE;
}

// Build a WGPULimits struct with runtime-queried buffer sizes.
// mtl_device may be null — in that case static fallback values apply.
fn build_limits(mtl_device: ?*anyopaque) types.WGPULimits {
    const buf_limit = query_max_buffer_length(mtl_device);
    var limits = METAL_LIMITS_STATIC;
    limits.maxBufferSize = buf_limit;
    // Storage buffer binding size is capped at the buffer allocation limit.
    limits.maxStorageBufferBindingSize = buf_limit;
    return limits;
}

// ============================================================
// Feature queries
// ============================================================

fn is_feature_supported(feature: u32) bool {
    return switch (feature) {
        FEATURE_SHADER_F16 => true,
        FEATURE_SUBGROUPS => BRIDGE_AVAILABLE,
        FEATURE_SUBGROUP_UNIFORMITY => BRIDGE_AVAILABLE,
        FEATURE_RW_STORAGE_TEXTURE => BRIDGE_AVAILABLE,
        FEATURE_LARGE_BUFFER => BRIDGE_AVAILABLE,
        else => false,
    };
}

pub export fn doeNativeAdapterHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    return if (is_feature_supported(feature)) 1 else 0;
}

pub export fn doeNativeDeviceHasFeature(raw: ?*anyopaque, feature: u32) callconv(.c) u32 {
    _ = raw;
    return if (is_feature_supported(feature)) 1 else 0;
}

// ============================================================
// Device / Adapter limits — runtime queries
// ============================================================

// doeNativeDeviceGetLimits — called with a DoeDevice* opaque pointer.
// Reports static conservative values; for runtime-accurate large-buffer
// limits, callers should use doeNativeDeviceGetLimitsFromMtl with the
// underlying MTLDevice pointer.
pub export fn doeNativeDeviceGetLimits(raw: ?*anyopaque, limits: ?*types.WGPULimits) callconv(.c) types.WGPUStatus {
    _ = raw;
    if (limits) |l| l.* = build_limits(null);
    return types.WGPUStatus_Success;
}

pub export fn doeNativeAdapterGetLimits(raw: ?*anyopaque, limits: ?*types.WGPULimits) callconv(.c) types.WGPUStatus {
    _ = raw;
    if (limits) |l| l.* = build_limits(null);
    return types.WGPUStatus_Success;
}

// doeNativeDeviceGetLimitsFromMtl — accepts a raw MTLDevice pointer and
// queries maxBufferLength at runtime for accurate large-buffer reporting.
pub export fn doeNativeDeviceGetLimitsFromMtl(mtl_device: ?*anyopaque, limits: ?*types.WGPULimits) callconv(.c) types.WGPUStatus {
    if (limits) |l| l.* = build_limits(mtl_device);
    return types.WGPUStatus_Success;
}

// ============================================================
// Subgroup size query
// ============================================================

pub export fn doeNativeDeviceSubgroupSize(raw: ?*anyopaque) callconv(.c) u32 {
    _ = raw;
    // Metal SIMD-group size is 32 on all Apple Silicon variants known at time
    // of writing.  Report 0 when Metal is unavailable (non-macOS).
    return if (BRIDGE_AVAILABLE) METAL_SIMD_GROUP_SIZE else 0;
}
