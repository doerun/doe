const std = @import("std");
const model = @import("model.zig");

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

pub const WGPUQueryType = u32;
pub const WGPUQueryType_Timestamp: WGPUQueryType = 0x00000002;

pub const WGPUMapMode = WGPUFlags;
pub const WGPUMapMode_Read: WGPUMapMode = 0x0000000000000001;

pub const WGPUMapAsyncStatus = u32;
pub const WGPUMapAsyncStatus_Success: WGPUMapAsyncStatus = 1;

pub const WGPUStatus = u32;
pub const WGPUStatus_Success: WGPUStatus = 1;

pub const TIMESTAMP_BUFFER_SIZE: u64 = 16;

pub const WGPUTextureUsage_None: WGPUTextureUsage = 0;
pub const WGPUTextureUsage_CopySrc: WGPUTextureUsage = 0x0000000000000001;
pub const WGPUTextureUsage_CopyDst: WGPUTextureUsage = 0x0000000000000002;
pub const WGPUTextureUsage_TextureBinding: WGPUTextureUsage = 0x0000000000000004;
pub const WGPUTextureUsage_StorageBinding: WGPUTextureUsage = 0x0000000000000008;
pub const WGPUTextureUsage_RenderAttachment: WGPUTextureUsage = 0x0000000000000010;
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

pub const WGPUDeviceDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: WGPUStringView,
    requiredFeatureCount: usize,
    requiredFeatures: ?[*]const WGPUFeatureName,
    requiredLimits: ?*anyopaque,
    defaultQueue: WGPUQueueDescriptor,
    deviceLostCallbackInfo: WGPUDeviceLostCallbackInfo,
    uncapturedErrorCallbackInfo: WGPUUncapturedErrorCallbackInfo,
};

pub const FnWgpuCreateInstance = *const fn (?*anyopaque) callconv(.c) WGPUInstance;
pub const FnWgpuInstanceRequestAdapter = *const fn (WGPUInstance, ?*const WGPURequestAdapterOptions, WGPURequestAdapterCallbackInfo) callconv(.c) WGPUFuture;
pub const FnWgpuInstanceWaitAny = *const fn (WGPUInstance, usize, [*]WGPUFutureWaitInfo, u64) callconv(.c) WGPUWaitStatus;
pub const FnWgpuInstanceProcessEvents = *const fn (WGPUInstance) callconv(.c) void;
pub const FnWgpuAdapterRequestDevice = *const fn (WGPUAdapter, ?*const WGPUDeviceDescriptor, WGPURequestDeviceCallbackInfo) callconv(.c) WGPUFuture;
pub const FnWgpuDeviceCreateBuffer = *const fn (WGPUDevice, ?*const WGPUBufferDescriptor) callconv(.c) WGPUBuffer;
pub const FnWgpuDeviceCreateShaderModule = *const fn (WGPUDevice, ?*const WGPUShaderModuleDescriptor) callconv(.c) WGPUShaderModule;
pub const FnWgpuShaderModuleRelease = *const fn (WGPUShaderModule) callconv(.c) void;
pub const FnWgpuDeviceCreateComputePipeline = *const fn (WGPUDevice, ?*const WGPUComputePipelineDescriptor) callconv(.c) WGPUComputePipeline;
pub const FnWgpuComputePipelineRelease = *const fn (WGPUComputePipeline) callconv(.c) void;
pub const FnWgpuRenderPipelineRelease = *const fn (WGPURenderPipeline) callconv(.c) void;
pub const FnWgpuDeviceCreateCommandEncoder = *const fn (WGPUDevice, ?*const WGPUCommandEncoderDescriptor) callconv(.c) WGPUCommandEncoder;
pub const FnWgpuCommandEncoderBeginComputePass = *const fn (WGPUCommandEncoder, ?*const WGPUComputePassDescriptor) callconv(.c) WGPUComputePassEncoder;
pub const FnWgpuDeviceCreateRenderPipeline = *const fn (WGPUDevice, *const anyopaque) callconv(.c) WGPURenderPipeline;
pub const FnWgpuCommandEncoderBeginRenderPass = *const fn (WGPUCommandEncoder, *const anyopaque) callconv(.c) WGPURenderPassEncoder;
pub const FnWgpuCommandEncoderWriteTimestamp = *const fn (WGPUCommandEncoder, WGPUQuerySet, u32) callconv(.c) void;
pub const FnWgpuCommandEncoderCopyBufferToBuffer = *const fn (WGPUCommandEncoder, WGPUBuffer, u64, WGPUBuffer, u64, u64) callconv(.c) void;
pub const FnWgpuCommandEncoderCopyBufferToTexture = *const fn (WGPUCommandEncoder, *const WGPUTexelCopyBufferInfo, *const WGPUTexelCopyTextureInfo, WGPUExtent3D) callconv(.c) void;
pub const FnWgpuCommandEncoderCopyTextureToBuffer = *const fn (WGPUCommandEncoder, *const WGPUTexelCopyTextureInfo, *const WGPUTexelCopyBufferInfo, WGPUExtent3D) callconv(.c) void;
pub const FnWgpuCommandEncoderCopyTextureToTexture = *const fn (WGPUCommandEncoder, *const WGPUTexelCopyTextureInfo, *const WGPUTexelCopyTextureInfo, WGPUExtent3D) callconv(.c) void;
pub const FnWgpuComputePassEncoderSetPipeline = *const fn (WGPUComputePassEncoder, WGPUComputePipeline) callconv(.c) void;
pub const FnWgpuComputePassEncoderSetBindGroup = *const fn (WGPUComputePassEncoder, u32, WGPUBindGroup, usize, ?[*]const u32) callconv(.c) void;
pub const FnWgpuComputePassEncoderDispatchWorkgroups = *const fn (WGPUComputePassEncoder, u32, u32, u32) callconv(.c) void;
pub const FnWgpuComputePassEncoderEnd = *const fn (WGPUComputePassEncoder) callconv(.c) void;
pub const FnWgpuComputePassEncoderRelease = *const fn (WGPUComputePassEncoder) callconv(.c) void;
pub const FnWgpuRenderPassEncoderSetPipeline = *const fn (WGPURenderPassEncoder, WGPURenderPipeline) callconv(.c) void;
pub const FnWgpuRenderPassEncoderSetVertexBuffer = *const fn (WGPURenderPassEncoder, u32, WGPUBuffer, u64, u64) callconv(.c) void;
pub const FnWgpuRenderPassEncoderSetIndexBuffer = *const fn (WGPURenderPassEncoder, WGPUBuffer, u32, u64, u64) callconv(.c) void;
pub const FnWgpuRenderPassEncoderSetBindGroup = *const fn (WGPURenderPassEncoder, u32, WGPUBindGroup, usize, ?[*]const u32) callconv(.c) void;
pub const FnWgpuRenderPassEncoderDraw = *const fn (WGPURenderPassEncoder, u32, u32, u32, u32) callconv(.c) void;
pub const FnWgpuRenderPassEncoderDrawIndexed = *const fn (WGPURenderPassEncoder, u32, u32, u32, i32, u32) callconv(.c) void;
pub const FnWgpuRenderPassEncoderDrawIndirect = *const fn (WGPURenderPassEncoder, WGPUBuffer, u64) callconv(.c) void;
pub const FnWgpuRenderPassEncoderDrawIndexedIndirect = *const fn (WGPURenderPassEncoder, WGPUBuffer, u64) callconv(.c) void;
pub const FnWgpuRenderPassEncoderEnd = *const fn (WGPURenderPassEncoder) callconv(.c) void;
pub const FnWgpuRenderPassEncoderRelease = *const fn (WGPURenderPassEncoder) callconv(.c) void;
pub const FnWgpuCommandEncoderFinish = *const fn (WGPUCommandEncoder, ?*const WGPUCommandBufferDescriptor) callconv(.c) WGPUCommandBuffer;
pub const FnWgpuDeviceGetQueue = *const fn (WGPUDevice) callconv(.c) WGPUQueue;
pub const FnWgpuQueueSubmit = *const fn (WGPUQueue, usize, [*c]WGPUCommandBuffer) callconv(.c) void;
pub const FnWgpuQueueOnSubmittedWorkDone = *const fn (WGPUQueue, WGPUQueueWorkDoneCallbackInfo) callconv(.c) WGPUFuture;
pub const FnWgpuQueueWriteBuffer = *const fn (WGPUQueue, WGPUBuffer, u64, ?*const anyopaque, usize) callconv(.c) void;
pub const FnWgpuDeviceCreateTexture = *const fn (WGPUDevice, ?*const WGPUTextureDescriptor) callconv(.c) WGPUTexture;
pub const FnWgpuTextureCreateView = *const fn (WGPUTexture, ?*const WGPUTextureViewDescriptor) callconv(.c) WGPUTextureView;
pub const FnWgpuDeviceCreateBindGroupLayout = *const fn (WGPUDevice, ?*const WGPUBindGroupLayoutDescriptor) callconv(.c) WGPUBindGroupLayout;
pub const FnWgpuBindGroupLayoutRelease = *const fn (WGPUBindGroupLayout) callconv(.c) void;
pub const FnWgpuDeviceCreateBindGroup = *const fn (WGPUDevice, ?*const WGPUBindGroupDescriptor) callconv(.c) WGPUBindGroup;
pub const FnWgpuBindGroupRelease = *const fn (WGPUBindGroup) callconv(.c) void;
pub const FnWgpuDeviceCreatePipelineLayout = *const fn (WGPUDevice, *const WGPUPipelineLayoutDescriptor) callconv(.c) WGPUPipelineLayout;
pub const FnWgpuPipelineLayoutRelease = *const fn (WGPUPipelineLayout) callconv(.c) void;
pub const FnWgpuTextureRelease = *const fn (WGPUTexture) callconv(.c) void;
pub const FnWgpuTextureViewRelease = *const fn (WGPUTextureView) callconv(.c) void;
pub const FnWgpuInstanceRelease = *const fn (WGPUInstance) callconv(.c) void;
pub const FnWgpuAdapterRelease = *const fn (WGPUAdapter) callconv(.c) void;
pub const FnWgpuDeviceRelease = *const fn (WGPUDevice) callconv(.c) void;
pub const FnWgpuQueueRelease = *const fn (WGPUQueue) callconv(.c) void;
pub const FnWgpuCommandEncoderRelease = *const fn (WGPUCommandEncoder) callconv(.c) void;
pub const FnWgpuCommandBufferRelease = *const fn (WGPUCommandBuffer) callconv(.c) void;
pub const FnWgpuBufferRelease = *const fn (WGPUBuffer) callconv(.c) void;
pub const FnWgpuAdapterHasFeature = *const fn (WGPUAdapter, WGPUFeatureName) callconv(.c) WGPUBool;
pub const FnWgpuDeviceHasFeature = *const fn (WGPUDevice, WGPUFeatureName) callconv(.c) WGPUBool;
pub const FnWgpuDeviceCreateQuerySet = *const fn (WGPUDevice, *const WGPUQuerySetDescriptor) callconv(.c) WGPUQuerySet;
pub const FnWgpuCommandEncoderResolveQuerySet = *const fn (WGPUCommandEncoder, WGPUQuerySet, u32, u32, WGPUBuffer, u64) callconv(.c) void;
pub const FnWgpuQuerySetRelease = *const fn (WGPUQuerySet) callconv(.c) void;
pub const FnWgpuBufferMapAsync = *const fn (WGPUBuffer, WGPUMapMode, usize, usize, WGPUBufferMapCallbackInfo) callconv(.c) WGPUFuture;
pub const FnWgpuBufferGetConstMappedRange = *const fn (WGPUBuffer, usize, usize) callconv(.c) ?*const anyopaque;
pub const FnWgpuBufferUnmap = *const fn (WGPUBuffer) callconv(.c) void;

pub const Procs = struct {
    wgpuCreateInstance: FnWgpuCreateInstance,
    wgpuInstanceRequestAdapter: FnWgpuInstanceRequestAdapter,
    wgpuInstanceWaitAny: FnWgpuInstanceWaitAny,
    wgpuInstanceProcessEvents: FnWgpuInstanceProcessEvents,
    wgpuAdapterRequestDevice: FnWgpuAdapterRequestDevice,
    wgpuDeviceCreateBuffer: FnWgpuDeviceCreateBuffer,
    wgpuDeviceCreateShaderModule: FnWgpuDeviceCreateShaderModule,
    wgpuShaderModuleRelease: FnWgpuShaderModuleRelease,
    wgpuDeviceCreateComputePipeline: FnWgpuDeviceCreateComputePipeline,
    wgpuComputePipelineRelease: FnWgpuComputePipelineRelease,
    wgpuRenderPipelineRelease: ?FnWgpuRenderPipelineRelease,
    wgpuDeviceCreateCommandEncoder: FnWgpuDeviceCreateCommandEncoder,
    wgpuCommandEncoderBeginComputePass: FnWgpuCommandEncoderBeginComputePass,
    wgpuDeviceCreateRenderPipeline: ?FnWgpuDeviceCreateRenderPipeline,
    wgpuCommandEncoderBeginRenderPass: ?FnWgpuCommandEncoderBeginRenderPass,
    wgpuCommandEncoderWriteTimestamp: ?FnWgpuCommandEncoderWriteTimestamp,
    wgpuCommandEncoderCopyBufferToBuffer: FnWgpuCommandEncoderCopyBufferToBuffer,
    wgpuCommandEncoderCopyBufferToTexture: FnWgpuCommandEncoderCopyBufferToTexture,
    wgpuCommandEncoderCopyTextureToBuffer: FnWgpuCommandEncoderCopyTextureToBuffer,
    wgpuCommandEncoderCopyTextureToTexture: FnWgpuCommandEncoderCopyTextureToTexture,
    wgpuComputePassEncoderSetBindGroup: FnWgpuComputePassEncoderSetBindGroup,
    wgpuComputePassEncoderSetPipeline: FnWgpuComputePassEncoderSetPipeline,
    wgpuComputePassEncoderDispatchWorkgroups: FnWgpuComputePassEncoderDispatchWorkgroups,
    wgpuComputePassEncoderEnd: FnWgpuComputePassEncoderEnd,
    wgpuComputePassEncoderRelease: FnWgpuComputePassEncoderRelease,
    wgpuRenderPassEncoderSetPipeline: ?FnWgpuRenderPassEncoderSetPipeline,
    wgpuRenderPassEncoderSetVertexBuffer: ?FnWgpuRenderPassEncoderSetVertexBuffer,
    wgpuRenderPassEncoderSetIndexBuffer: ?FnWgpuRenderPassEncoderSetIndexBuffer,
    wgpuRenderPassEncoderSetBindGroup: ?FnWgpuRenderPassEncoderSetBindGroup,
    wgpuRenderPassEncoderDraw: ?FnWgpuRenderPassEncoderDraw,
    wgpuRenderPassEncoderDrawIndexed: ?FnWgpuRenderPassEncoderDrawIndexed,
    wgpuRenderPassEncoderDrawIndirect: ?FnWgpuRenderPassEncoderDrawIndirect,
    wgpuRenderPassEncoderDrawIndexedIndirect: ?FnWgpuRenderPassEncoderDrawIndexedIndirect,
    wgpuRenderPassEncoderEnd: ?FnWgpuRenderPassEncoderEnd,
    wgpuRenderPassEncoderRelease: ?FnWgpuRenderPassEncoderRelease,
    wgpuDeviceCreateTexture: FnWgpuDeviceCreateTexture,
    wgpuTextureCreateView: FnWgpuTextureCreateView,
    wgpuDeviceCreateBindGroupLayout: FnWgpuDeviceCreateBindGroupLayout,
    wgpuBindGroupLayoutRelease: FnWgpuBindGroupLayoutRelease,
    wgpuDeviceCreateBindGroup: FnWgpuDeviceCreateBindGroup,
    wgpuBindGroupRelease: FnWgpuBindGroupRelease,
    wgpuDeviceCreatePipelineLayout: FnWgpuDeviceCreatePipelineLayout,
    wgpuPipelineLayoutRelease: FnWgpuPipelineLayoutRelease,
    wgpuTextureRelease: FnWgpuTextureRelease,
    wgpuTextureViewRelease: FnWgpuTextureViewRelease,
    wgpuCommandEncoderFinish: FnWgpuCommandEncoderFinish,
    wgpuDeviceGetQueue: FnWgpuDeviceGetQueue,
    wgpuQueueSubmit: FnWgpuQueueSubmit,
    wgpuQueueOnSubmittedWorkDone: FnWgpuQueueOnSubmittedWorkDone,
    wgpuQueueWriteBuffer: FnWgpuQueueWriteBuffer,
    wgpuInstanceRelease: FnWgpuInstanceRelease,
    wgpuAdapterRelease: FnWgpuAdapterRelease,
    wgpuDeviceRelease: FnWgpuDeviceRelease,
    wgpuQueueRelease: FnWgpuQueueRelease,
    wgpuCommandEncoderRelease: FnWgpuCommandEncoderRelease,
    wgpuCommandBufferRelease: FnWgpuCommandBufferRelease,
    wgpuBufferRelease: FnWgpuBufferRelease,
    wgpuAdapterHasFeature: FnWgpuAdapterHasFeature,
    wgpuDeviceHasFeature: ?FnWgpuDeviceHasFeature,
    wgpuDeviceCreateQuerySet: FnWgpuDeviceCreateQuerySet,
    wgpuCommandEncoderResolveQuerySet: FnWgpuCommandEncoderResolveQuerySet,
    wgpuQuerySetRelease: FnWgpuQuerySetRelease,
    wgpuBufferMapAsync: FnWgpuBufferMapAsync,
    wgpuBufferGetConstMappedRange: FnWgpuBufferGetConstMappedRange,
    wgpuBufferUnmap: FnWgpuBufferUnmap,
};

pub const BufferRecord = struct {
    buffer: WGPUBuffer,
    size: u64,
    usage: WGPUBufferUsage,
};

pub const TextureRecord = struct {
    texture: WGPUTexture,
    width: u32,
    height: u32,
    depth_or_array_layers: u32,
    format: WGPUTextureFormat,
    usage: WGPUTextureUsage,
    dimension: WGPUTextureDimension,
    sample_count: u32,
};

pub const DispatchPassArtifacts = struct {
    pass_bind_groups: []?WGPUBindGroup,
    group_layouts: []WGPUBindGroupLayout,
    texture_views: []WGPUTextureView,
};

pub const RenderPipelineCacheEntry = struct {
    shader_module: WGPUShaderModule,
    pipeline: WGPURenderPipeline,
};

pub const RenderTextureViewCacheEntry = struct {
    texture: WGPUTexture,
    view: WGPUTextureView,
    width: u32,
    height: u32,
    format: WGPUTextureFormat,
};

pub const DispatchPassGroup = struct {
    layout_entries: std.array_list.Managed(WGPUBindGroupLayoutEntry),
    bind_entries: std.array_list.Managed(WGPUBindGroupEntry),
};

pub const RequestState = struct {
    done: bool = false,
    status: WGPURequestAdapterStatus = .@"error",
    adapter: WGPUAdapter = null,
    status_message: []const u8 = "",
};

pub const DeviceRequestState = struct {
    done: bool = false,
    status: WGPURequestDeviceStatus = .@"error",
    device: WGPUDevice = null,
    status_message: []const u8 = "",
};

pub const QueueSubmitState = struct {
    done: bool = false,
    status: WGPUQueueWorkDoneStatus = .@"error",
    status_message: []const u8 = "",
};

pub const BufferMapState = struct {
    done: bool = false,
    status: WGPUMapAsyncStatus = 0,
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
