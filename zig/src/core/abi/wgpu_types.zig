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
pub const WGPUFeatureName_TimestampQuery: WGPUFeatureName = 0x00000009;
pub const WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses: WGPUFeatureName = 0x00050003;
pub const WGPUFeatureName_PixelLocalStorageCoherent: WGPUFeatureName = 0x0005000A;
pub const WGPUFeatureName_PixelLocalStorageNonCoherent: WGPUFeatureName = 0x0005000B;
pub const WGPUFeatureName_MultiDrawIndirect: WGPUFeatureName = 0x00050031;
pub const WGPUFeatureName_ShaderF16: WGPUFeatureName = 0x0000000B;
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
