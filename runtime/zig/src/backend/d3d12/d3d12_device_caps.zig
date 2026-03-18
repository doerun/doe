// d3d12_device_caps.zig — D3D12 device capability queries: feature reporting and limits.
//
// Mirrors doe_device_caps.zig for the D3D12 backend. Limits are conservative
// D3D12 Feature Level 11.0 defaults (the minimum Doe targets). Runtime hardware
// queries are deferred until a Windows host provides evidence.

const builtin = @import("builtin");
const types = @import("../../core/abi/wgpu_types.zig");

// D3D12 is only available on Windows.
const D3D12_AVAILABLE = builtin.os.tag == .windows;

// Feature name constants — match wgpu_types.zig
const FEATURE_DEPTH_CLIP_CONTROL: u32 = types.WGPUFeatureName_DepthClipControl;
const FEATURE_DEPTH32FLOAT_STENCIL8: u32 = types.WGPUFeatureName_Depth32FloatStencil8;
const FEATURE_TEXTURE_COMPRESSION_BC: u32 = types.WGPUFeatureName_TextureCompressionBC;
const FEATURE_BGRA8UNORM_STORAGE: u32 = types.WGPUFeatureName_BGRA8UnormStorage;
const FEATURE_SHADER_F16: u32 = types.WGPUFeatureName_ShaderF16;
const FEATURE_INDIRECT_FIRST_INSTANCE: u32 = types.WGPUFeatureName_IndirectFirstInstance;
const FEATURE_FLOAT32_FILTERABLE: u32 = types.WGPUFeatureName_Float32Filterable;
const FEATURE_FLOAT32_BLENDABLE: u32 = types.WGPUFeatureName_Float32Blendable;

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

// D3D12 feature support. shader-f16 requires SM 6.2+; report true
// optimistically since Doe targets DXC which handles SM 6.x.
// BC texture compression is universally available on D3D12 hardware.
fn is_feature_supported(feature: u32) bool {
    return switch (feature) {
        FEATURE_SHADER_F16 => D3D12_AVAILABLE,
        FEATURE_DEPTH_CLIP_CONTROL,
        FEATURE_DEPTH32FLOAT_STENCIL8,
        FEATURE_TEXTURE_COMPRESSION_BC,
        FEATURE_BGRA8UNORM_STORAGE,
        FEATURE_INDIRECT_FIRST_INSTANCE,
        FEATURE_FLOAT32_FILTERABLE,
        FEATURE_FLOAT32_BLENDABLE,
        => D3D12_AVAILABLE,
        else => false,
    };
}

pub fn d3d12_adapter_has_feature(feature: u32) bool {
    return is_feature_supported(feature);
}

pub fn d3d12_device_has_feature(feature: u32) bool {
    return is_feature_supported(feature);
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
