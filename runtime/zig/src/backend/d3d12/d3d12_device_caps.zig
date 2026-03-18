// d3d12_device_caps.zig — D3D12 device capability queries: feature reporting and limits.
//
// Mirrors doe_device_caps.zig for the D3D12 backend. Limits are conservative
// D3D12 Feature Level 11.0 defaults (the minimum Doe targets). Runtime hardware
// queries via bridge functions refine feature detection when a device handle is
// available (ShaderF16, Subgroups, SubgroupsF16, wave lane counts).

const builtin = @import("builtin");
const types = @import("../../core/abi/wgpu_types.zig");

// D3D12 is only available on Windows.
const D3D12_AVAILABLE = builtin.os.tag == .windows;

// Feature name constants — match wgpu_types.zig
const FEATURE_DEPTH_CLIP_CONTROL: u32 = types.WGPUFeatureName_DepthClipControl;
const FEATURE_DEPTH32FLOAT_STENCIL8: u32 = types.WGPUFeatureName_Depth32FloatStencil8;
const FEATURE_TEXTURE_COMPRESSION_BC: u32 = types.WGPUFeatureName_TextureCompressionBC;
const FEATURE_BGRA8UNORM_STORAGE: u32 = types.WGPUFeatureName_BGRA8UnormStorage;
const FEATURE_INDIRECT_FIRST_INSTANCE: u32 = types.WGPUFeatureName_IndirectFirstInstance;
const FEATURE_FLOAT32_FILTERABLE: u32 = types.WGPUFeatureName_Float32Filterable;
const FEATURE_TIMESTAMP_QUERY: u32 = types.WGPUFeatureName_TimestampQuery;
const FEATURE_RG11B10UFLOAT_RENDERABLE: u32 = types.WGPUFeatureName_RG11B10UfloatRenderable;
const FEATURE_CLIP_DISTANCES: u32 = types.WGPUFeatureName_ClipDistances;
const FEATURE_DUAL_SOURCE_BLENDING: u32 = types.WGPUFeatureName_DualSourceBlending;
const FEATURE_SHADER_F16: u32 = types.WGPUFeatureName_ShaderF16;
const FEATURE_SUBGROUPS: u32 = types.WGPUFeatureName_Subgroups;
const FEATURE_SUBGROUPS_F16: u32 = types.WGPUFeatureName_SubgroupsF16;

// Shader model thresholds for feature gating.
const SM_6_0: c_int = 0x60; // Wave intrinsics (subgroups)
const SM_6_2: c_int = 0x62; // Native 16-bit shader ops

// D3D12 Feature Level 11.0 conservative limits.
// These match the WebGPU spec minimum where possible, and D3D12 FL11.0
// hardware guarantees otherwise.
const FALLBACK_MAX_BUFFER_SIZE: u64 = 268_435_456; // 256 MB — spec minimum
const D3D12_MAX_UNIFORM_BUFFER_BINDING_SIZE: u64 = 65_536; // 64 KB (D3D12 constant buffer limit)

const D3D12_LIMITS_STATIC = types.WGPULimits{
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
    .maxSampledTexturesPerShaderStage = 128, // D3D12 SRV limit per stage
    .maxSamplersPerShaderStage = 16,
    .maxStorageBuffersPerShaderStage = 8,
    .maxStorageTexturesPerShaderStage = 8,
    .maxUniformBuffersPerShaderStage = 14, // D3D12 CBV limit
    .maxUniformBufferBindingSize = D3D12_MAX_UNIFORM_BUFFER_BINDING_SIZE,
    .maxStorageBufferBindingSize = FALLBACK_MAX_BUFFER_SIZE,
    .minUniformBufferOffsetAlignment = 256, // D3D12 constant buffer alignment
    .minStorageBufferOffsetAlignment = 32,
    .maxVertexBuffers = 16, // D3D12 input slot count
    .maxBufferSize = FALLBACK_MAX_BUFFER_SIZE,
    .maxVertexAttributes = 32, // D3D12 input element limit
    .maxVertexBufferArrayStride = 2048,
    .maxInterStageShaderVariables = 16,
    .maxColorAttachments = 8, // D3D12 MRT limit
    .maxColorAttachmentBytesPerSample = 32,
    .maxComputeWorkgroupStorageSize = 32768, // D3D12 groupshared memory limit
    .maxComputeInvocationsPerWorkgroup = 1024,
    .maxComputeWorkgroupSizeX = 1024,
    .maxComputeWorkgroupSizeY = 1024,
    .maxComputeWorkgroupSizeZ = 64,
    .maxComputeWorkgroupsPerDimension = 65535,
    .maxImmediateSize = 0,
};

fn build_limits() types.WGPULimits {
    return D3D12_LIMITS_STATIC;
}

// ============================================================
// Bridge extern declarations — resolved by d3d12_bridge.c at link time.
// ============================================================

extern fn d3d12_bridge_device_get_shader_model(device: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_device_get_wave_lane_count_min(device: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_device_get_wave_lane_count_max(device: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_device_supports_native_16bit(device: ?*anyopaque) callconv(.c) c_int;

// ============================================================
// D3D12DeviceCaps — runtime-queried hardware capabilities.
//
// When a device handle is available, query_device_caps calls the bridge
// functions to detect shader model, wave lane counts, and 16-bit support.
// When no device handle is available (null), conservative static defaults
// apply: no ShaderF16, no Subgroups, default wave size.
// ============================================================

pub const D3D12DeviceCaps = struct {
    shader_model: c_int = SM_6_0,
    wave_lane_count_min: u32 = D3D12_DEFAULT_WAVE_SIZE,
    wave_lane_count_max: u32 = D3D12_DEFAULT_WAVE_SIZE,
    supports_native_16bit: bool = false,
    has_subgroups: bool = false,
    has_shader_f16: bool = false,
    has_subgroups_f16: bool = false,
};

// Conservative static defaults when no device handle is available.
const D3D12_CAPS_STATIC = D3D12DeviceCaps{};

pub fn query_device_caps(device: ?*anyopaque) D3D12DeviceCaps {
    if (device == null) return D3D12_CAPS_STATIC;
    if (!D3D12_AVAILABLE) return D3D12_CAPS_STATIC;

    const sm = d3d12_bridge_device_get_shader_model(device);
    const wl_min_raw = d3d12_bridge_device_get_wave_lane_count_min(device);
    const wl_max_raw = d3d12_bridge_device_get_wave_lane_count_max(device);
    const native_16 = d3d12_bridge_device_supports_native_16bit(device);

    const wl_min: u32 = if (wl_min_raw > 0) @intCast(wl_min_raw) else D3D12_DEFAULT_WAVE_SIZE;
    const wl_max: u32 = if (wl_max_raw > 0) @intCast(wl_max_raw) else D3D12_DEFAULT_WAVE_SIZE;

    // Subgroups (wave intrinsics) require SM6.0+.
    const subgroups = sm >= SM_6_0;
    // ShaderF16 requires both SM6.2+ and hardware native 16-bit op support.
    const shader_f16 = sm >= SM_6_2 and native_16 == 1;
    // SubgroupsF16 requires both ShaderF16 and Subgroups.
    const sub_f16 = subgroups and shader_f16;

    return .{
        .shader_model = sm,
        .wave_lane_count_min = wl_min,
        .wave_lane_count_max = wl_max,
        .supports_native_16bit = native_16 == 1,
        .has_subgroups = subgroups,
        .has_shader_f16 = shader_f16,
        .has_subgroups_f16 = sub_f16,
    };
}

// ============================================================
// Feature queries — FL11.0 unconditional + runtime-queried features
// ============================================================

// D3D12 feature support — Feature Level 11.0+ unconditional capabilities.
// Features that need runtime hardware queries (ShaderF16, Subgroups,
// SubgroupsF16, ETC2, ASTC, Float32Blendable) are excluded from the
// static path and checked against the caps struct when available.
fn is_feature_supported_static(feature: u32) bool {
    return switch (feature) {
        FEATURE_DEPTH_CLIP_CONTROL,
        FEATURE_DEPTH32FLOAT_STENCIL8,
        FEATURE_TEXTURE_COMPRESSION_BC,
        FEATURE_BGRA8UNORM_STORAGE,
        FEATURE_INDIRECT_FIRST_INSTANCE,
        FEATURE_FLOAT32_FILTERABLE,
        FEATURE_TIMESTAMP_QUERY,
        FEATURE_RG11B10UFLOAT_RENDERABLE,
        FEATURE_CLIP_DISTANCES,
        FEATURE_DUAL_SOURCE_BLENDING,
        => D3D12_AVAILABLE,
        else => false,
    };
}

fn is_feature_supported_with_caps(feature: u32, caps: D3D12DeviceCaps) bool {
    return switch (feature) {
        FEATURE_SHADER_F16 => D3D12_AVAILABLE and caps.has_shader_f16,
        FEATURE_SUBGROUPS => D3D12_AVAILABLE and caps.has_subgroups,
        FEATURE_SUBGROUPS_F16 => D3D12_AVAILABLE and caps.has_subgroups_f16,
        else => is_feature_supported_static(feature),
    };
}

pub fn d3d12_adapter_has_feature(feature: u32) bool {
    return is_feature_supported_static(feature);
}

pub fn d3d12_device_has_feature(feature: u32) bool {
    return is_feature_supported_static(feature);
}

pub fn d3d12_device_has_feature_with_caps(feature: u32, caps: D3D12DeviceCaps) bool {
    return is_feature_supported_with_caps(feature, caps);
}

pub fn d3d12_device_get_limits(limits: *types.WGPULimits) void {
    limits.* = build_limits();
}

pub fn d3d12_adapter_get_limits(limits: *types.WGPULimits) void {
    limits.* = build_limits();
}

// Subgroup (wave) size. D3D12 wave size is typically 32 (NVIDIA/Intel) or 64 (AMD).
// Report 32 as conservative default; runtime query via
// D3D12_FEATURE_DATA_D3D12_OPTIONS1.WaveLaneCountMin is deferred.
const D3D12_DEFAULT_WAVE_SIZE: u32 = 32;

pub fn d3d12_device_subgroup_size() u32 {
    return if (D3D12_AVAILABLE) D3D12_DEFAULT_WAVE_SIZE else 0;
}

pub fn d3d12_device_subgroup_size_from_caps(caps: D3D12DeviceCaps) u32 {
    if (!D3D12_AVAILABLE) return 0;
    return caps.wave_lane_count_min;
}
