const gpu = @import("model_gpu_types.zig");

pub const DispatchCommand = struct {
    x: u32,
    y: u32,
    z: u32,
};

pub const DispatchIndirectCommand = DispatchCommand;

pub const KernelBindingResourceKind = enum(u8) {
    buffer,
    texture,
    storage_texture,
    sampler,
};

pub const KernelBinding = struct {
    binding: u32,
    group: u32 = 0,
    resource_kind: KernelBindingResourceKind,
    resource_handle: u64,
    visibility: gpu.WGPUFlags = gpu.WGPUShaderStage_Compute,
    buffer_offset: u64 = 0,
    buffer_size: u64 = gpu.WGPUWholeSize,
    buffer_type: u32 = gpu.WGPUBufferBindingType_Undefined,
    texture_sample_type: u32 = gpu.WGPUTextureSampleType_Undefined,
    texture_view_dimension: u32 = gpu.WGPUTextureViewDimension_Undefined,
    storage_texture_access: u32 = gpu.WGPUStorageTextureAccess_Undefined,
    texture_aspect: u32 = gpu.WGPUTextureAspect_Undefined,
    texture_format: gpu.WGPUTextureFormat = gpu.WGPUTextureFormat_Undefined,
    texture_multisampled: bool = false,
};

pub const KernelDispatchCommand = struct {
    kernel: []const u8,
    entry_point: ?[]const u8 = null,
    x: u32,
    y: u32,
    z: u32,
    repeat: u32 = 1,
    warmup_dispatch_count: u32 = 0,
    initialize_buffers_on_create: bool = false,
    bindings: ?[]const KernelBinding = null,
};
