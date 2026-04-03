const std = @import("std");
const model = @import("../../model_gpu_types.zig");
const execution_types = @import("wgpu_execution_types.zig");
const compressed_formats = @import("wgpu_type_texture_formats.zig");

pub const NativeExecutionStatus = execution_types.NativeExecutionStatus;
pub const NativeExecutionResult = execution_types.NativeExecutionResult;

pub const WGPUInstance = ?*anyopaque;
pub const WGPUAdapter = ?*anyopaque;
pub const WGPUDevice = ?*anyopaque;
pub const WGPUQueue = ?*anyopaque;
pub const WGPUBuffer = ?*anyopaque;
pub const WGPUTexture = ?*anyopaque;
pub const WGPUTextureView = ?*anyopaque;
pub const WGPUExternalTexture = ?*anyopaque;
pub const WGPUShaderModule = ?*anyopaque;
pub const WGPUSampler = ?*anyopaque;
pub const WGPUComputePipeline = ?*anyopaque;
pub const WGPURenderPipeline = ?*anyopaque;
pub const WGPUComputePassEncoder = ?*anyopaque;
pub const WGPURenderPassEncoder = ?*anyopaque;
pub const WGPUBindGroupLayout = ?*anyopaque;
pub const WGPUBindGroup = ?*anyopaque;
pub const WGPUPipelineLayout = ?*anyopaque;
pub const WGPUCommandEncoder = ?*anyopaque;
pub const WGPUCommandBuffer = ?*anyopaque;
pub const WGPUQuerySet = ?*anyopaque;

pub const WGPUFuture = extern struct {
    id: u64,
};

pub const WGPUStringView = extern struct {
    data: ?[*]const u8,
    length: usize,
};

pub const WGPUFlags = u64;
pub const WGPUBufferUsage = WGPUFlags;
pub const WGPUTextureUsage = WGPUFlags;
pub const WGPUTextureFormat = u32;
pub const WGPUShaderStageFlags = WGPUFlags;
pub const WGPUTextureDimension = u32;
pub const WGPUTextureAspect = u32;
pub const WGPUTextureComponentSwizzle = u32;
pub const WGPUTextureViewDimension = u32;
pub const WGPUAlphaMode = u32;
pub const WGPUBool = u32;
pub const WGPUSType = u32;

pub const WGPUSType_ShaderSourceWGSL: WGPUSType = 0x00000002;
pub const WGPUSType_ShaderSourceMSL: WGPUSType = 0x00000003;
pub const WGPUSType_ShaderSourceSPIRV: WGPUSType = 0x00000004;
pub const WGPUSType_ShaderSourceHLSL: WGPUSType = 0x00000005;
pub const WGPUSType_ExternalTextureBindingLayout: WGPUSType = 0x0000000D;
pub const WGPUSType_ExternalTextureBindingEntry: WGPUSType = 0x0000000E;

pub const WGPU_STRLEN = std.math.maxInt(usize);
pub const WGPU_FALSE: WGPUBool = 0;
pub const WGPU_TRUE: WGPUBool = 1;
pub const WGPU_COPY_STRIDE_UNDEFINED: u32 = model.WGPUCopyStrideUndefined;
pub const WGPU_WHOLE_SIZE: u64 = model.WGPUWholeSize;
pub const WGPU_MIP_LEVEL_COUNT_UNDEFINED: u32 = 0xFFFFFFFF;
pub const WGPU_ARRAY_LAYER_COUNT_UNDEFINED: u32 = 0xFFFFFFFF;

pub const WGPUBufferUsage_None: WGPUBufferUsage = 0;
pub const WGPUBufferUsage_MapWrite: WGPUBufferUsage = 0x0000000000000002;
pub const WGPUBufferUsage_CopySrc: WGPUBufferUsage = 0x0000000000000004;
pub const WGPUBufferUsage_CopyDst: WGPUBufferUsage = 0x0000000000000008;
pub const WGPUBufferUsage_Index: WGPUBufferUsage = 0x0000000000000010;
pub const WGPUBufferUsage_Vertex: WGPUBufferUsage = 0x0000000000000020;
pub const WGPUBufferUsage_Uniform: WGPUBufferUsage = 0x0000000000000040;
pub const WGPUBufferUsage_Storage: WGPUBufferUsage = 0x0000000000000080;
pub const WGPUBufferUsage_MapRead: WGPUBufferUsage = 0x0000000000000001;
pub const WGPUBufferUsage_QueryResolve: WGPUBufferUsage = 0x0000000000000200;

pub const WGPUFeatureName = u32;
pub const WGPUFeatureName_DepthClipControl: WGPUFeatureName = 0x00000001;
pub const WGPUFeatureName_Depth32FloatStencil8: WGPUFeatureName = 0x00000002;
pub const WGPUFeatureName_TextureCompressionBC: WGPUFeatureName = 0x00000003;
pub const WGPUFeatureName_TextureCompressionBCSliced3D: WGPUFeatureName = 0x00000004;
pub const WGPUFeatureName_TextureCompressionETC2: WGPUFeatureName = 0x00000005;
pub const WGPUFeatureName_TextureCompressionASTC: WGPUFeatureName = 0x00000006;
pub const WGPUFeatureName_TextureCompressionASTCSliced3D: WGPUFeatureName = 0x00000007;
pub const WGPUFeatureName_RG11B10UfloatRenderable: WGPUFeatureName = 0x00000008;
pub const WGPUFeatureName_TimestampQuery: WGPUFeatureName = 0x00000009;
pub const WGPUFeatureName_BGRA8UnormStorage: WGPUFeatureName = 0x0000000A;
pub const WGPUFeatureName_ShaderF16: WGPUFeatureName = 0x0000000B;
pub const WGPUFeatureName_IndirectFirstInstance: WGPUFeatureName = 0x0000000C;
pub const WGPUFeatureName_Float32Filterable: WGPUFeatureName = 0x0000000D;
pub const WGPUFeatureName_Subgroups: WGPUFeatureName = 0x0000000E;
pub const WGPUFeatureName_SubgroupsF16: WGPUFeatureName = 0x0000000F;
pub const WGPUFeatureName_Float32Blendable: WGPUFeatureName = 0x00000010;
pub const WGPUFeatureName_ClipDistances: WGPUFeatureName = 0x00000011;
pub const WGPUFeatureName_DualSourceBlending: WGPUFeatureName = 0x00000012;
pub const WGPUFeatureName_CoreFeaturesAndLimits: WGPUFeatureName = 0x00000013;
pub const WGPUFeatureName_TextureFormatsTier1: WGPUFeatureName = 0x00000014;
pub const WGPUFeatureName_TextureFormatsTier2: WGPUFeatureName = 0x00000015;
pub const WGPUFeatureName_PrimitiveIndex: WGPUFeatureName = 0x00000016;
pub const WGPUFeatureName_TextureComponentSwizzle: WGPUFeatureName = 0x00000017;
pub const WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses: WGPUFeatureName = 0x00050003;
pub const WGPUFeatureName_PixelLocalStorageCoherent: WGPUFeatureName = 0x0005000A;
pub const WGPUFeatureName_PixelLocalStorageNonCoherent: WGPUFeatureName = 0x0005000B;
pub const WGPUFeatureName_MultiDrawIndirect: WGPUFeatureName = 0x00050031;
pub const WGPUFeatureName_ChromiumExperimentalSamplingResourceTable: WGPUFeatureName = 0x0005003A;

pub const WGPUQueryType = u32;
pub const WGPUQueryType_Timestamp: WGPUQueryType = 0x00000002;

pub const WGPUMapMode = WGPUFlags;
pub const WGPUMapMode_Read: WGPUMapMode = 0x0000000000000001;
pub const WGPUMapMode_Write: WGPUMapMode = 0x0000000000000002;

pub const WGPUMapAsyncStatus = u32;
pub const WGPUMapAsyncStatus_Success: WGPUMapAsyncStatus = 1;
pub const WGPUBufferMapAsyncStatus = WGPUMapAsyncStatus;
pub const WGPUBufferMapAsyncStatus_Success = WGPUMapAsyncStatus_Success;

pub const WGPUStatus = u32;
pub const WGPUStatus_Success: WGPUStatus = 1;
pub const TIMESTAMP_BUFFER_SIZE: u64 = 16;

pub const WGPUTextureUsage_None: WGPUTextureUsage = 0;
pub const WGPUTextureUsage_CopySrc: WGPUTextureUsage = 0x0000000000000001;
pub const WGPUTextureUsage_CopyDst: WGPUTextureUsage = 0x0000000000000002;
pub const WGPUTextureUsage_TextureBinding: WGPUTextureUsage = 0x0000000000000004;
pub const WGPUTextureUsage_StorageBinding: WGPUTextureUsage = 0x0000000000000008;
pub const WGPUTextureUsage_RenderAttachment: WGPUTextureUsage = 0x0000000000000010;
pub const WGPUTextureUsage_TransientAttachment: WGPUTextureUsage = 0x0000000000000020;
pub const WGPUTextureUsage_StorageAttachment: WGPUTextureUsage = 0x0000000000000040;

pub const WGPUTextureFormat_Undefined: WGPUTextureFormat = 0;
pub const WGPUTextureFormat_R8Unorm: WGPUTextureFormat = 0x00000001;
pub const WGPUTextureFormat_R8Snorm: WGPUTextureFormat = 0x00000002;
pub const WGPUTextureFormat_R8Uint: WGPUTextureFormat = 0x00000003;
pub const WGPUTextureFormat_R8Sint: WGPUTextureFormat = 0x00000004;
pub const WGPUTextureFormat_R16Uint: WGPUTextureFormat = 0x00000007;
pub const WGPUTextureFormat_R16Sint: WGPUTextureFormat = 0x00000008;
pub const WGPUTextureFormat_R16Float: WGPUTextureFormat = 0x00000009;
pub const WGPUTextureFormat_RG8Unorm: WGPUTextureFormat = 0x0000000A;
pub const WGPUTextureFormat_RG8Snorm: WGPUTextureFormat = 0x0000000B;
pub const WGPUTextureFormat_RG8Uint: WGPUTextureFormat = 0x0000000C;
pub const WGPUTextureFormat_RG8Sint: WGPUTextureFormat = 0x0000000D;
pub const WGPUTextureFormat_R32Float: WGPUTextureFormat = 0x0000000E;
pub const WGPUTextureFormat_R32Uint: WGPUTextureFormat = 0x0000000F;
pub const WGPUTextureFormat_R32Sint: WGPUTextureFormat = 0x00000010;
pub const WGPUTextureFormat_RG16Uint: WGPUTextureFormat = 0x00000013;
pub const WGPUTextureFormat_RG16Sint: WGPUTextureFormat = 0x00000014;
pub const WGPUTextureFormat_RG16Float: WGPUTextureFormat = 0x00000015;
pub const WGPUTextureFormat_RGBA8Unorm: WGPUTextureFormat = 0x00000016;
pub const WGPUTextureFormat_RGBA8UnormSrgb: WGPUTextureFormat = 0x00000017;
pub const WGPUTextureFormat_RGBA8Snorm: WGPUTextureFormat = 0x00000018;
pub const WGPUTextureFormat_RGBA8Uint: WGPUTextureFormat = 0x00000019;
pub const WGPUTextureFormat_RGBA8Sint: WGPUTextureFormat = 0x0000001A;
pub const WGPUTextureFormat_BGRA8Unorm: WGPUTextureFormat = 0x0000001B;
pub const WGPUTextureFormat_BGRA8UnormSrgb: WGPUTextureFormat = 0x0000001C;
pub const WGPUTextureFormat_RGB10A2Uint: WGPUTextureFormat = 0x0000001D;
pub const WGPUTextureFormat_RGB10A2Unorm: WGPUTextureFormat = 0x0000001E;
pub const WGPUTextureFormat_RG11B10Ufloat: WGPUTextureFormat = 0x0000001F;
pub const WGPUTextureFormat_RGB9E5Ufloat: WGPUTextureFormat = 0x00000020;
pub const WGPUTextureFormat_RG32Float: WGPUTextureFormat = 0x00000021;
pub const WGPUTextureFormat_RG32Uint: WGPUTextureFormat = 0x00000022;
pub const WGPUTextureFormat_RG32Sint: WGPUTextureFormat = 0x00000023;
pub const WGPUTextureFormat_RGBA16Uint: WGPUTextureFormat = 0x00000024;
pub const WGPUTextureFormat_RGBA16Sint: WGPUTextureFormat = 0x00000025;
pub const WGPUTextureFormat_RGBA16Float: WGPUTextureFormat = 0x00000026;
pub const WGPUTextureFormat_RGBA32Float: WGPUTextureFormat = 0x00000027;
pub const WGPUTextureFormat_RGBA32Uint: WGPUTextureFormat = 0x00000028;
pub const WGPUTextureFormat_RGBA32Sint: WGPUTextureFormat = 0x00000029;
pub const WGPUTextureFormat_Stencil8: WGPUTextureFormat = 0x0000002C;
pub const WGPUTextureFormat_Depth16Unorm: WGPUTextureFormat = 0x0000002D;
pub const WGPUTextureFormat_Depth24Plus: WGPUTextureFormat = 0x0000002E;
pub const WGPUTextureFormat_Depth24PlusStencil8: WGPUTextureFormat = 0x0000002F;
pub const WGPUTextureFormat_Depth32Float: WGPUTextureFormat = 0x00000030;
pub const WGPUTextureFormat_Depth32FloatStencil8: WGPUTextureFormat = 0x00000031;

pub const WGPUTextureFormat_BC1RGBAUnorm = compressed_formats.WGPUTextureFormat_BC1RGBAUnorm;
pub const WGPUTextureFormat_BC1RGBAUnormSrgb = compressed_formats.WGPUTextureFormat_BC1RGBAUnormSrgb;
pub const WGPUTextureFormat_BC2RGBAUnorm = compressed_formats.WGPUTextureFormat_BC2RGBAUnorm;
pub const WGPUTextureFormat_BC2RGBAUnormSrgb = compressed_formats.WGPUTextureFormat_BC2RGBAUnormSrgb;
pub const WGPUTextureFormat_BC3RGBAUnorm = compressed_formats.WGPUTextureFormat_BC3RGBAUnorm;
pub const WGPUTextureFormat_BC3RGBAUnormSrgb = compressed_formats.WGPUTextureFormat_BC3RGBAUnormSrgb;
pub const WGPUTextureFormat_BC4RUnorm = compressed_formats.WGPUTextureFormat_BC4RUnorm;
pub const WGPUTextureFormat_BC4RSnorm = compressed_formats.WGPUTextureFormat_BC4RSnorm;
pub const WGPUTextureFormat_BC5RGUnorm = compressed_formats.WGPUTextureFormat_BC5RGUnorm;
pub const WGPUTextureFormat_BC5RGSnorm = compressed_formats.WGPUTextureFormat_BC5RGSnorm;
pub const WGPUTextureFormat_BC6HRGBUfloat = compressed_formats.WGPUTextureFormat_BC6HRGBUfloat;
pub const WGPUTextureFormat_BC6HRGBFloat = compressed_formats.WGPUTextureFormat_BC6HRGBFloat;
pub const WGPUTextureFormat_BC7RGBAUnorm = compressed_formats.WGPUTextureFormat_BC7RGBAUnorm;
pub const WGPUTextureFormat_BC7RGBAUnormSrgb = compressed_formats.WGPUTextureFormat_BC7RGBAUnormSrgb;
pub const BC_FORMAT_FIRST = compressed_formats.BC_FORMAT_FIRST;
pub const BC_FORMAT_LAST = compressed_formats.BC_FORMAT_LAST;
pub const isBCFormat = compressed_formats.isBCFormat;

pub const WGPUTextureFormat_ETC2RGB8Unorm = compressed_formats.WGPUTextureFormat_ETC2RGB8Unorm;
pub const WGPUTextureFormat_ETC2RGB8UnormSrgb = compressed_formats.WGPUTextureFormat_ETC2RGB8UnormSrgb;
pub const WGPUTextureFormat_ETC2RGB8A1Unorm = compressed_formats.WGPUTextureFormat_ETC2RGB8A1Unorm;
pub const WGPUTextureFormat_ETC2RGB8A1UnormSrgb = compressed_formats.WGPUTextureFormat_ETC2RGB8A1UnormSrgb;
pub const WGPUTextureFormat_ETC2RGBA8Unorm = compressed_formats.WGPUTextureFormat_ETC2RGBA8Unorm;
pub const WGPUTextureFormat_ETC2RGBA8UnormSrgb = compressed_formats.WGPUTextureFormat_ETC2RGBA8UnormSrgb;
pub const WGPUTextureFormat_EACR11Unorm = compressed_formats.WGPUTextureFormat_EACR11Unorm;
pub const WGPUTextureFormat_EACR11Snorm = compressed_formats.WGPUTextureFormat_EACR11Snorm;
pub const WGPUTextureFormat_EACRG11Unorm = compressed_formats.WGPUTextureFormat_EACRG11Unorm;
pub const WGPUTextureFormat_EACRG11Snorm = compressed_formats.WGPUTextureFormat_EACRG11Snorm;
pub const ETC2_FORMAT_FIRST = compressed_formats.ETC2_FORMAT_FIRST;
pub const ETC2_FORMAT_LAST = compressed_formats.ETC2_FORMAT_LAST;
pub const isETC2Format = compressed_formats.isETC2Format;

pub const WGPUTextureFormat_ASTC4x4Unorm = compressed_formats.WGPUTextureFormat_ASTC4x4Unorm;
pub const WGPUTextureFormat_ASTC4x4UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC4x4UnormSrgb;
pub const WGPUTextureFormat_ASTC5x4Unorm = compressed_formats.WGPUTextureFormat_ASTC5x4Unorm;
pub const WGPUTextureFormat_ASTC5x4UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC5x4UnormSrgb;
pub const WGPUTextureFormat_ASTC5x5Unorm = compressed_formats.WGPUTextureFormat_ASTC5x5Unorm;
pub const WGPUTextureFormat_ASTC5x5UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC5x5UnormSrgb;
pub const WGPUTextureFormat_ASTC6x5Unorm = compressed_formats.WGPUTextureFormat_ASTC6x5Unorm;
pub const WGPUTextureFormat_ASTC6x5UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC6x5UnormSrgb;
pub const WGPUTextureFormat_ASTC6x6Unorm = compressed_formats.WGPUTextureFormat_ASTC6x6Unorm;
pub const WGPUTextureFormat_ASTC6x6UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC6x6UnormSrgb;
pub const WGPUTextureFormat_ASTC8x5Unorm = compressed_formats.WGPUTextureFormat_ASTC8x5Unorm;
pub const WGPUTextureFormat_ASTC8x5UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC8x5UnormSrgb;
pub const WGPUTextureFormat_ASTC8x6Unorm = compressed_formats.WGPUTextureFormat_ASTC8x6Unorm;
pub const WGPUTextureFormat_ASTC8x6UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC8x6UnormSrgb;
pub const WGPUTextureFormat_ASTC8x8Unorm = compressed_formats.WGPUTextureFormat_ASTC8x8Unorm;
pub const WGPUTextureFormat_ASTC8x8UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC8x8UnormSrgb;
pub const WGPUTextureFormat_ASTC10x5Unorm = compressed_formats.WGPUTextureFormat_ASTC10x5Unorm;
pub const WGPUTextureFormat_ASTC10x5UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC10x5UnormSrgb;
pub const WGPUTextureFormat_ASTC10x6Unorm = compressed_formats.WGPUTextureFormat_ASTC10x6Unorm;
pub const WGPUTextureFormat_ASTC10x6UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC10x6UnormSrgb;
pub const WGPUTextureFormat_ASTC10x8Unorm = compressed_formats.WGPUTextureFormat_ASTC10x8Unorm;
pub const WGPUTextureFormat_ASTC10x8UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC10x8UnormSrgb;
pub const WGPUTextureFormat_ASTC10x10Unorm = compressed_formats.WGPUTextureFormat_ASTC10x10Unorm;
pub const WGPUTextureFormat_ASTC10x10UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC10x10UnormSrgb;
pub const WGPUTextureFormat_ASTC12x10Unorm = compressed_formats.WGPUTextureFormat_ASTC12x10Unorm;
pub const WGPUTextureFormat_ASTC12x10UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC12x10UnormSrgb;
pub const WGPUTextureFormat_ASTC12x12Unorm = compressed_formats.WGPUTextureFormat_ASTC12x12Unorm;
pub const WGPUTextureFormat_ASTC12x12UnormSrgb = compressed_formats.WGPUTextureFormat_ASTC12x12UnormSrgb;
pub const ASTC_FORMAT_FIRST = compressed_formats.ASTC_FORMAT_FIRST;
pub const ASTC_FORMAT_LAST = compressed_formats.ASTC_FORMAT_LAST;
pub const isASTCFormat = compressed_formats.isASTCFormat;
pub const isDepthStencilFormat = compressed_formats.isDepthStencilFormat;
pub const hasStencilAspect = compressed_formats.hasStencilAspect;
pub const isFloat32Format = compressed_formats.isFloat32Format;
pub const isBaseStorageTextureFormat = compressed_formats.isBaseStorageTextureFormat;
pub const isStorageTextureFormat = compressed_formats.isStorageTextureFormat;

pub const WGPUTextureSampleType_BindingNotUsed: u32 = 0x00000000;
pub const WGPUTextureSampleType_Undefined: u32 = 0x00000001;
pub const WGPUTextureSampleType_Float: u32 = 0x00000002;
pub const WGPUTextureSampleType_UnfilterableFloat: u32 = 0x00000003;
pub const WGPUTextureSampleType_Depth: u32 = 0x00000004;
pub const WGPUTextureSampleType_Sint: u32 = 0x00000005;
pub const WGPUTextureSampleType_Uint: u32 = 0x00000006;
pub const WGPUTextureSampleType_UndefinedDefault: u32 = WGPUTextureSampleType_Undefined;

pub const WGPUTextureAspect_Undefined: u32 = 0;
pub const WGPUTextureAspect_All: u32 = 1;
pub const WGPUTextureAspect_StencilOnly: u32 = 2;
pub const WGPUTextureAspect_DepthOnly: u32 = 3;

pub const WGPUTextureComponentSwizzle_Undefined: u32 = 0;
pub const WGPUTextureComponentSwizzle_Zero: u32 = 1;
pub const WGPUTextureComponentSwizzle_One: u32 = 2;
pub const WGPUTextureComponentSwizzle_Red: u32 = 3;
pub const WGPUTextureComponentSwizzle_Green: u32 = 4;
pub const WGPUTextureComponentSwizzle_Blue: u32 = 5;
pub const WGPUTextureComponentSwizzle_Alpha: u32 = 6;

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

pub const WGPUTextureViewDimension_Undefined: u32 = 0x00000000;
pub const WGPUTextureViewDimension_1D: u32 = 0x00000001;
pub const WGPUTextureViewDimension_2D: u32 = 0x00000002;
pub const WGPUTextureViewDimension_2DArray: u32 = 0x00000003;
pub const WGPUTextureViewDimension_Cube: u32 = 0x00000004;
pub const WGPUTextureViewDimension_CubeArray: u32 = 0x00000005;
pub const WGPUTextureViewDimension_3D: u32 = 0x00000006;
pub const WGPUTextureViewDimension_2DDepth: u32 = 0x00000007;
pub const WGPUTextureViewDimension_2DArrayDepth: u32 = 0x00000008;

pub const WGPUTextureDimension_Undefined: u32 = 0;
pub const WGPUTextureDimension_1D: u32 = 1;
pub const WGPUTextureDimension_2D: u32 = 2;
pub const WGPUTextureDimension_3D: u32 = 3;

pub const WGPUShaderStage_None: WGPUFlags = 0x0000000000000000;
pub const WGPUShaderStage_Vertex: WGPUFlags = 0x0000000000000001;
pub const WGPUShaderStage_Fragment: WGPUFlags = 0x0000000000000002;
pub const WGPUShaderStage_Compute: WGPUFlags = 0x0000000000000004;

pub const WGPUSamplerBindingType_BindingNotUsed: u32 = 0x00000000;
pub const WGPUSamplerBindingType_Undefined: u32 = 0x00000001;
pub const WGPUSamplerBindingType_Filtering: u32 = 0x00000002;
pub const WGPUSamplerBindingType_NonFiltering: u32 = 0x00000003;
pub const WGPUSamplerBindingType_Comparison: u32 = 0x00000004;
