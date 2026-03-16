const std = @import("std");
const model = @import("../../model.zig");

pub const NativeExecutionStatus = enum {
    ok,
    unsupported,
    @"error",
};

pub const NativeExecutionResult = struct {
    status: NativeExecutionStatus,
    status_message: []const u8,
    setup_ns: u64 = 0,
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    dispatch_count: u32 = 0,
    gpu_timestamp_ns: u64 = 0,
    gpu_timestamp_attempted: bool = false,
    gpu_timestamp_valid: bool = false,
};

pub const WGPUInstance = ?*anyopaque;
pub const WGPUAdapter = ?*anyopaque;
pub const WGPUDevice = ?*anyopaque;
pub const WGPUQueue = ?*anyopaque;
pub const WGPUBuffer = ?*anyopaque;
pub const WGPUTexture = ?*anyopaque;
pub const WGPUTextureView = ?*anyopaque;
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
pub const WGPUTextureViewDimension = u32;

pub const WGPUBool = u32;
pub const WGPUSType = u32;
pub const WGPUSType_ShaderSourceWGSL: WGPUSType = 0x00000002;
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
// Standardized WebGPU features (webgpu.h enum order)
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
// Chromium-specific extension features
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

const compressed_formats = @import("wgpu_type_texture_formats.zig");
// BC compressed texture formats
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
// ETC2/EAC compressed texture formats
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
// ASTC compressed texture formats
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

pub const WGPUExtent3D = extern struct {
    width: u32,
    height: u32,
    depthOrArrayLayers: u32,
};

pub const WGPUOrigin3D = extern struct {
    x: u32,
    y: u32,
    z: u32,
};

pub const WGPUTexelCopyBufferLayout = extern struct {
    offset: u64,
    bytesPerRow: u32,
    rowsPerImage: u32,
};

pub const WGPUTexelCopyBufferInfo = extern struct {
    layout: WGPUTexelCopyBufferLayout,
    buffer: WGPUBuffer,
};

pub const WGPUTexelCopyTextureInfo = extern struct {
    texture: WGPUTexture,
    mipLevel: u32,
    origin: WGPUOrigin3D,
    aspect: WGPUTextureAspect,
};

pub const WGPUTextureViewDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    format: WGPUTextureFormat,
    dimension: WGPUTextureViewDimension,
    baseMipLevel: u32,
    mipLevelCount: u32,
    baseArrayLayer: u32,
    arrayLayerCount: u32,
    aspect: WGPUTextureAspect,
    usage: WGPUTextureUsage,
};

pub const WGPUTextureDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    usage: WGPUTextureUsage,
    dimension: WGPUTextureDimension,
    size: WGPUExtent3D,
    format: WGPUTextureFormat,
    mipLevelCount: u32,
    sampleCount: u32,
    viewFormatCount: usize,
    viewFormats: ?[*]const WGPUTextureFormat,
};

pub const WGPUBufferBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
    hasDynamicOffset: WGPUBool,
    minBindingSize: u64,
};

pub const WGPUSamplerBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
};

pub const WGPUTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    sampleType: u32,
    viewDimension: WGPUTextureViewDimension,
    multisampled: WGPUBool,
};

pub const WGPUStorageTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    access: u32,
    format: WGPUTextureFormat,
    viewDimension: WGPUTextureViewDimension,
};

pub const WGPUBindGroupLayoutEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    visibility: WGPUShaderStageFlags,
    bindingArraySize: u32,
    buffer: WGPUBufferBindingLayout,
    sampler: WGPUSamplerBindingLayout,
    texture: WGPUTextureBindingLayout,
    storageTexture: WGPUStorageTextureBindingLayout,
};

pub const WGPUBindGroupEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    buffer: WGPUBuffer,
    offset: u64,
    size: u64,
    sampler: WGPUSampler,
    textureView: WGPUTextureView,
};

pub const WGPUBindGroupLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    entryCount: usize,
    entries: ?[*]const WGPUBindGroupLayoutEntry,
};

pub const WGPUBindGroupDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    layout: WGPUBindGroupLayout,
    entryCount: usize,
    entries: [*]const WGPUBindGroupEntry,
};

pub const WGPUPipelineLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    bindGroupLayoutCount: usize,
    bindGroupLayouts: [*]const WGPUBindGroupLayout,
    immediateSize: u32,
};

pub const WGPUCallbackMode = u32;
pub const WGPUCallbackMode_WaitAnyOnly: WGPUCallbackMode = 0x00000001;
pub const WGPUCallbackMode_AllowProcessEvents: WGPUCallbackMode = 0x00000002;
pub const WGPUCallbackMode_AllowSpontaneous: WGPUCallbackMode = 0x00000003;

pub const WGPUWaitStatus = enum(u32) {
    success = 1,
    timedOut = 2,
    @"error" = 3,
    _,
};

pub const WGPURequestAdapterStatus = enum(u32) {
    success = 1,
    callbackCancelled = 2,
    unavailable = 3,
    @"error" = 4,
    _,
};

pub const WGPURequestDeviceStatus = enum(u32) {
    success = 1,
    callbackCancelled = 2,
    @"error" = 3,
    _,
};

pub const WGPUQueueWorkDoneStatus = enum(u32) {
    success = 1,
    callbackCancelled = 2,
    @"error" = 3,
    _,
};

pub const WGPUPowerPreference = enum(u32) { undefined = 0, lowPower = 1, highPerformance = 2, _ };
pub const WGPUFeatureLevel = enum(u32) { undefined = 0, compatibility = 1, core = 2, _ };
pub const WGPUBackendType = enum(u32) {
    undefined = 0,
    nullBackend = 1,
    webgpu = 2,
    d3d11 = 3,
    d3d12 = 4,
    metal = 5,
    vulkan = 6,
    openGl = 7,
    openGLES = 8,
    _,
};

pub const WGPURequestAdapterCallback = *const fn (
    status: WGPURequestAdapterStatus,
    adapter: WGPUAdapter,
    message: WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPURequestDeviceCallback = *const fn (
    status: WGPURequestDeviceStatus,
    device: WGPUDevice,
    message: WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPUQueueWorkDoneCallback = *const fn (
    status: WGPUQueueWorkDoneStatus,
    message: WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPUDeviceLostReason = enum(u32) {
    unknown = 1,
    destroyed = 2,
    callbackCancelled = 3,
    failedCreation = 4,
    _,
};

pub const WGPUErrorType = enum(u32) {
    noError = 1,
    validation = 2,
    outOfMemory = 3,
    internal = 4,
    unknown = 5,
    _,
};

pub const WGPUDeviceLostCallback = *const fn (
    device: ?*const anyopaque,
    reason: WGPUDeviceLostReason,
    message: WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPUUncapturedErrorCallback = *const fn (
    device: ?*const anyopaque,
    @"type": WGPUErrorType,
    message: WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPURequestAdapterCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: WGPUCallbackMode,
    callback: WGPURequestAdapterCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPURequestDeviceCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: WGPUCallbackMode,
    callback: WGPURequestDeviceCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPUQueueWorkDoneCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: WGPUCallbackMode,
    callback: WGPUQueueWorkDoneCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPUDeviceLostCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: WGPUCallbackMode,
    callback: ?WGPUDeviceLostCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPUUncapturedErrorCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    callback: ?WGPUUncapturedErrorCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPUChainedStruct = extern struct {
    next: ?*anyopaque,
    sType: WGPUSType,
};

pub const WGPURequestAdapterOptions = extern struct {
    nextInChain: ?*anyopaque,
    featureLevel: WGPUFeatureLevel,
    powerPreference: WGPUPowerPreference,
    forceFallbackAdapter: WGPUBool,
    backendType: WGPUBackendType,
    compatibleSurface: ?*anyopaque,
};

pub const WGPUBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    usage: WGPUBufferUsage,
    size: u64,
    mappedAtCreation: WGPUBool,
};

pub const WGPUShaderModuleDescriptor = extern struct {
    nextInChain: ?*WGPUChainedStruct,
    label: WGPUStringView,
};

pub const WGPUShaderSourceWGSL = extern struct {
    chain: WGPUChainedStruct,
    code: WGPUStringView,
};

pub const WGPUComputeState = extern struct {
    nextInChain: ?*anyopaque,
    module: WGPUShaderModule,
    entryPoint: WGPUStringView,
    constantCount: usize,
    constants: ?*anyopaque,
};

pub const WGPUComputePipelineDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    layout: ?*anyopaque,
    compute: WGPUComputeState,
};

pub const WGPUComputePassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    timestampWrites: ?*const WGPUPassTimestampWrites,
};

pub const WGPUPassTimestampWrites = extern struct {
    nextInChain: ?*anyopaque,
    querySet: WGPUQuerySet,
    beginningOfPassWriteIndex: u32,
    endOfPassWriteIndex: u32,
};

pub const WGPUQuerySetDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    type: WGPUQueryType,
    count: u32,
};

pub const WGPUBufferMapCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: WGPUCallbackMode,
    callback: WGPUBufferMapCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPUBufferMapCallback = *const fn (
    status: WGPUMapAsyncStatus,
    message: WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPUCommandEncoderDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
};

pub const WGPUCommandBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
};

pub const WGPUFutureWaitInfo = extern struct {
    future: WGPUFuture,
    completed: WGPUBool,
};

pub const WGPUQueueDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
};

pub const WGPULimits = extern struct {
    nextInChain: ?*anyopaque,
    maxTextureDimension1D: u32,
    maxTextureDimension2D: u32,
    maxTextureDimension3D: u32,
    maxTextureArrayLayers: u32,
    maxBindGroups: u32,
    maxBindGroupsPlusVertexBuffers: u32,
    maxBindingsPerBindGroup: u32,
    maxDynamicUniformBuffersPerPipelineLayout: u32,
    maxDynamicStorageBuffersPerPipelineLayout: u32,
    maxSampledTexturesPerShaderStage: u32,
    maxSamplersPerShaderStage: u32,
    maxStorageBuffersPerShaderStage: u32,
    maxStorageTexturesPerShaderStage: u32,
    maxUniformBuffersPerShaderStage: u32,
    maxUniformBufferBindingSize: u64,
    maxStorageBufferBindingSize: u64,
    minUniformBufferOffsetAlignment: u32,
    minStorageBufferOffsetAlignment: u32,
    maxVertexBuffers: u32,
    maxBufferSize: u64,
    maxVertexAttributes: u32,
    maxVertexBufferArrayStride: u32,
    maxInterStageShaderVariables: u32,
    maxColorAttachments: u32,
    maxColorAttachmentBytesPerSample: u32,
    maxComputeWorkgroupStorageSize: u32,
    maxComputeInvocationsPerWorkgroup: u32,
    maxComputeWorkgroupSizeX: u32,
    maxComputeWorkgroupSizeY: u32,
    maxComputeWorkgroupSizeZ: u32,
    maxComputeWorkgroupsPerDimension: u32,
    maxImmediateSize: u32,
};

pub const WGPUDeviceDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    requiredFeatureCount: usize,
    requiredFeatures: ?[*]const WGPUFeatureName,
    requiredLimits: ?*const WGPULimits,
    defaultQueue: WGPUQueueDescriptor,
    deviceLostCallbackInfo: WGPUDeviceLostCallbackInfo,
    uncapturedErrorCallbackInfo: WGPUUncapturedErrorCallbackInfo,
};

pub const WGPUSamplerDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    addressModeU: u32,
    addressModeV: u32,
    addressModeW: u32,
    magFilter: u32,
    minFilter: u32,
    mipmapFilter: u32,
    lodMinClamp: f32,
    lodMaxClamp: f32,
    compare: u32,
    maxAnisotropy: u16,
};

pub const WGPUColor = extern struct {
    r: f64,
    g: f64,
    b: f64,
    a: f64,
};

pub const WGPURenderPassColorAttachment = extern struct {
    nextInChain: ?*anyopaque,
    view: WGPUTextureView,
    depthSlice: u32,
    resolveTarget: WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: WGPUColor,
};

pub const WGPURenderPassDepthStencilAttachment = extern struct {
    view: WGPUTextureView,
    depthLoadOp: u32,
    depthStoreOp: u32,
    depthClearValue: f32,
    depthReadOnly: WGPUBool,
    stencilLoadOp: u32,
    stencilStoreOp: u32,
    stencilClearValue: u32,
    stencilReadOnly: WGPUBool,
};

pub const WGPURenderPassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    colorAttachmentCount: usize,
    colorAttachments: ?[*]const WGPURenderPassColorAttachment,
    depthStencilAttachment: ?*const WGPURenderPassDepthStencilAttachment,
    occlusionQuerySet: WGPUQuerySet,
    timestampWrites: ?*const WGPUPassTimestampWrites,
};

pub fn initLimits() WGPULimits {
    var limits = std.mem.zeroes(WGPULimits);
    limits.nextInChain = null;
    return limits;
}

const proc_aliases = @import("wgpu_type_proc_aliases.zig");
const records = @import("wgpu_type_records.zig").definitions(@This());

pub const FnWgpuCreateInstance = proc_aliases.FnWgpuCreateInstance;
pub const FnWgpuInstanceRequestAdapter = proc_aliases.FnWgpuInstanceRequestAdapter;
pub const FnWgpuInstanceWaitAny = proc_aliases.FnWgpuInstanceWaitAny;
pub const FnWgpuInstanceProcessEvents = proc_aliases.FnWgpuInstanceProcessEvents;
pub const FnWgpuAdapterRequestDevice = proc_aliases.FnWgpuAdapterRequestDevice;
pub const FnWgpuDeviceCreateBuffer = proc_aliases.FnWgpuDeviceCreateBuffer;
pub const FnWgpuDeviceCreateShaderModule = proc_aliases.FnWgpuDeviceCreateShaderModule;
pub const FnWgpuShaderModuleRelease = proc_aliases.FnWgpuShaderModuleRelease;
pub const FnWgpuDeviceCreateComputePipeline = proc_aliases.FnWgpuDeviceCreateComputePipeline;
pub const FnWgpuComputePipelineRelease = proc_aliases.FnWgpuComputePipelineRelease;
pub const FnWgpuRenderPipelineRelease = proc_aliases.FnWgpuRenderPipelineRelease;
pub const FnWgpuDeviceCreateCommandEncoder = proc_aliases.FnWgpuDeviceCreateCommandEncoder;
pub const FnWgpuCommandEncoderBeginComputePass = proc_aliases.FnWgpuCommandEncoderBeginComputePass;
pub const FnWgpuDeviceCreateRenderPipeline = proc_aliases.FnWgpuDeviceCreateRenderPipeline;
pub const FnWgpuCommandEncoderBeginRenderPass = proc_aliases.FnWgpuCommandEncoderBeginRenderPass;
pub const FnWgpuCommandEncoderWriteTimestamp = proc_aliases.FnWgpuCommandEncoderWriteTimestamp;
pub const FnWgpuCommandEncoderCopyBufferToBuffer = proc_aliases.FnWgpuCommandEncoderCopyBufferToBuffer;
pub const FnWgpuCommandEncoderCopyBufferToTexture = proc_aliases.FnWgpuCommandEncoderCopyBufferToTexture;
pub const FnWgpuCommandEncoderCopyTextureToBuffer = proc_aliases.FnWgpuCommandEncoderCopyTextureToBuffer;
pub const FnWgpuCommandEncoderCopyTextureToTexture = proc_aliases.FnWgpuCommandEncoderCopyTextureToTexture;
pub const FnWgpuComputePassEncoderSetPipeline = proc_aliases.FnWgpuComputePassEncoderSetPipeline;
pub const FnWgpuComputePassEncoderSetBindGroup = proc_aliases.FnWgpuComputePassEncoderSetBindGroup;
pub const FnWgpuComputePassEncoderDispatchWorkgroups = proc_aliases.FnWgpuComputePassEncoderDispatchWorkgroups;
pub const FnWgpuComputePassEncoderEnd = proc_aliases.FnWgpuComputePassEncoderEnd;
pub const FnWgpuComputePassEncoderRelease = proc_aliases.FnWgpuComputePassEncoderRelease;
pub const FnWgpuRenderPassEncoderSetPipeline = proc_aliases.FnWgpuRenderPassEncoderSetPipeline;
pub const FnWgpuRenderPassEncoderSetVertexBuffer = proc_aliases.FnWgpuRenderPassEncoderSetVertexBuffer;
pub const FnWgpuRenderPassEncoderSetIndexBuffer = proc_aliases.FnWgpuRenderPassEncoderSetIndexBuffer;
pub const FnWgpuRenderPassEncoderSetBindGroup = proc_aliases.FnWgpuRenderPassEncoderSetBindGroup;
pub const FnWgpuRenderPassEncoderDraw = proc_aliases.FnWgpuRenderPassEncoderDraw;
pub const FnWgpuRenderPassEncoderDrawIndexed = proc_aliases.FnWgpuRenderPassEncoderDrawIndexed;
pub const FnWgpuRenderPassEncoderDrawIndirect = proc_aliases.FnWgpuRenderPassEncoderDrawIndirect;
pub const FnWgpuRenderPassEncoderDrawIndexedIndirect = proc_aliases.FnWgpuRenderPassEncoderDrawIndexedIndirect;
pub const FnWgpuRenderPassEncoderEnd = proc_aliases.FnWgpuRenderPassEncoderEnd;
pub const FnWgpuRenderPassEncoderRelease = proc_aliases.FnWgpuRenderPassEncoderRelease;
pub const FnWgpuCommandEncoderFinish = proc_aliases.FnWgpuCommandEncoderFinish;
pub const FnWgpuDeviceGetQueue = proc_aliases.FnWgpuDeviceGetQueue;
pub const FnWgpuQueueSubmit = proc_aliases.FnWgpuQueueSubmit;
pub const FnWgpuQueueOnSubmittedWorkDone = proc_aliases.FnWgpuQueueOnSubmittedWorkDone;
pub const FnWgpuQueueWriteBuffer = proc_aliases.FnWgpuQueueWriteBuffer;
pub const FnWgpuDeviceCreateTexture = proc_aliases.FnWgpuDeviceCreateTexture;
pub const FnWgpuTextureCreateView = proc_aliases.FnWgpuTextureCreateView;
pub const FnWgpuDeviceCreateBindGroupLayout = proc_aliases.FnWgpuDeviceCreateBindGroupLayout;
pub const FnWgpuBindGroupLayoutRelease = proc_aliases.FnWgpuBindGroupLayoutRelease;
pub const FnWgpuDeviceCreateBindGroup = proc_aliases.FnWgpuDeviceCreateBindGroup;
pub const FnWgpuBindGroupRelease = proc_aliases.FnWgpuBindGroupRelease;
pub const FnWgpuDeviceCreatePipelineLayout = proc_aliases.FnWgpuDeviceCreatePipelineLayout;
pub const FnWgpuPipelineLayoutRelease = proc_aliases.FnWgpuPipelineLayoutRelease;
pub const FnWgpuTextureRelease = proc_aliases.FnWgpuTextureRelease;
pub const FnWgpuTextureViewRelease = proc_aliases.FnWgpuTextureViewRelease;
pub const FnWgpuInstanceRelease = proc_aliases.FnWgpuInstanceRelease;
pub const FnWgpuAdapterRelease = proc_aliases.FnWgpuAdapterRelease;
pub const FnWgpuDeviceRelease = proc_aliases.FnWgpuDeviceRelease;
pub const FnWgpuQueueRelease = proc_aliases.FnWgpuQueueRelease;
pub const FnWgpuCommandEncoderRelease = proc_aliases.FnWgpuCommandEncoderRelease;
pub const FnWgpuCommandBufferRelease = proc_aliases.FnWgpuCommandBufferRelease;
pub const FnWgpuBufferRelease = proc_aliases.FnWgpuBufferRelease;
pub const FnWgpuAdapterHasFeature = proc_aliases.FnWgpuAdapterHasFeature;
pub const FnWgpuDeviceHasFeature = proc_aliases.FnWgpuDeviceHasFeature;
pub const FnWgpuDeviceCreateQuerySet = proc_aliases.FnWgpuDeviceCreateQuerySet;
pub const FnWgpuCommandEncoderResolveQuerySet = proc_aliases.FnWgpuCommandEncoderResolveQuerySet;
pub const FnWgpuQuerySetRelease = proc_aliases.FnWgpuQuerySetRelease;
pub const FnWgpuBufferMapAsync = proc_aliases.FnWgpuBufferMapAsync;
pub const FnWgpuBufferGetConstMappedRange = proc_aliases.FnWgpuBufferGetConstMappedRange;
pub const FnWgpuBufferGetMappedRange = proc_aliases.FnWgpuBufferGetMappedRange;
pub const FnWgpuBufferUnmap = proc_aliases.FnWgpuBufferUnmap;
pub const FnWgpuDeviceCreateSampler = proc_aliases.FnWgpuDeviceCreateSampler;
pub const FnWgpuSamplerRelease = proc_aliases.FnWgpuSamplerRelease;
pub const Procs = proc_aliases.Procs;

pub const BufferRecord = records.BufferRecord;
pub const TextureRecord = records.TextureRecord;
pub const DispatchPassArtifacts = records.DispatchPassArtifacts;
pub const RenderPipelineCacheEntry = records.RenderPipelineCacheEntry;
pub const RenderTextureViewCacheEntry = records.RenderTextureViewCacheEntry;
pub const DispatchPassGroup = records.DispatchPassGroup;
pub const RequestState = records.RequestState;
pub const DeviceRequestState = records.DeviceRequestState;

pub const QueueSubmitState = struct {
    done: bool = false,
    status: WGPUQueueWorkDoneStatus = .@"error",
    status_message: []const u8 = "",
};

pub const BufferMapState = struct {
    done: bool = false,
    status: WGPUMapAsyncStatus = 0,
};

pub const UncapturedErrorState = struct {
    pending: std.atomic.Value(u32) = std.atomic.Value(u32).init(0),
    error_type: std.atomic.Value(u32) = std.atomic.Value(u32).init(@intFromEnum(WGPUErrorType.noError)),
};

pub const KernelSource = struct {
    source: []const u8,
    owned: bool,
    mode: KernelLookupResult,
};

pub const KernelLookupResult = enum {
    fallback,
    builtin,
    file,
};

pub const PipelineCacheEntry = struct {
    shader_module: WGPUShaderModule,
    pipeline: WGPUComputePipeline,
};
