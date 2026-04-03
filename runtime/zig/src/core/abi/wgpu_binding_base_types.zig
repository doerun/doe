const core = @import("wgpu_core_base_types.zig");

pub const WGPUShaderStageFlags = core.WGPUFlags;

pub const WGPUTextureSampleType_BindingNotUsed: u32 = 0x00000000;
pub const WGPUTextureSampleType_Undefined: u32 = 0x00000001;
pub const WGPUTextureSampleType_Float: u32 = 0x00000002;
pub const WGPUTextureSampleType_UnfilterableFloat: u32 = 0x00000003;
pub const WGPUTextureSampleType_Depth: u32 = 0x00000004;
pub const WGPUTextureSampleType_Sint: u32 = 0x00000005;
pub const WGPUTextureSampleType_Uint: u32 = 0x00000006;
pub const WGPUTextureSampleType_UndefinedDefault: u32 = WGPUTextureSampleType_Undefined;

pub const WGPUStorageTextureAccess_BindingNotUsed: u32 = 0x00000000;
pub const WGPUStorageTextureAccess_Undefined: u32 = 0x00000001;
pub const WGPUStorageTextureAccess_WriteOnly: u32 = 0x00000002;
pub const WGPUStorageTextureAccess_ReadOnly: u32 = 0x00000003;
pub const WGPUStorageTextureAccess_ReadWrite: u32 = 0x00000004;

pub const WGPUBufferBindingType_BindingNotUsed: u32 = 0x00000000;
pub const WGPUBufferBindingType_Undefined: u32 = 0x00000001;
pub const WGPUBufferBindingType_Uniform: u32 = 0x00000002;
pub const WGPUBufferBindingType_Storage: u32 = 0x00000003;
pub const WGPUBufferBindingType_ReadOnlyStorage: u32 = 0x00000004;

pub const WGPUShaderStage_None: core.WGPUFlags = 0x0000000000000000;
pub const WGPUShaderStage_Vertex: core.WGPUFlags = 0x0000000000000001;
pub const WGPUShaderStage_Fragment: core.WGPUFlags = 0x0000000000000002;
pub const WGPUShaderStage_Compute: core.WGPUFlags = 0x0000000000000004;

pub const WGPUSamplerBindingType_BindingNotUsed: u32 = 0x00000000;
pub const WGPUSamplerBindingType_Undefined: u32 = 0x00000001;
pub const WGPUSamplerBindingType_Filtering: u32 = 0x00000002;
pub const WGPUSamplerBindingType_NonFiltering: u32 = 0x00000003;
pub const WGPUSamplerBindingType_Comparison: u32 = 0x00000004;
