const std = @import("std");
const base = @import("wgpu_base_types.zig");
const callback_types = @import("wgpu_type_callbacks.zig").definitions(base);

pub const WGPUExtent3D = extern struct {
    width: u32,
    height: u32,
    depthOrArrayLayers: u32,
};

pub const WGPUExtent2D = extern struct {
    width: u32,
    height: u32,
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
    buffer: base.WGPUBuffer,
};

pub const WGPUTexelCopyTextureInfo = extern struct {
    texture: base.WGPUTexture,
    mipLevel: u32,
    origin: WGPUOrigin3D,
    aspect: base.WGPUTextureAspect,
};

pub const WGPUTextureViewDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    format: base.WGPUTextureFormat,
    dimension: base.WGPUTextureViewDimension,
    baseMipLevel: u32,
    mipLevelCount: u32,
    baseArrayLayer: u32,
    arrayLayerCount: u32,
    aspect: base.WGPUTextureAspect,
    usage: base.WGPUTextureUsage,
    swizzleR: base.WGPUTextureComponentSwizzle,
    swizzleG: base.WGPUTextureComponentSwizzle,
    swizzleB: base.WGPUTextureComponentSwizzle,
    swizzleA: base.WGPUTextureComponentSwizzle,
};

pub const WGPUTextureDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    usage: base.WGPUTextureUsage,
    dimension: base.WGPUTextureDimension,
    size: WGPUExtent3D,
    format: base.WGPUTextureFormat,
    mipLevelCount: u32,
    sampleCount: u32,
    viewFormatCount: usize,
    viewFormats: ?[*]const base.WGPUTextureFormat,
};

pub const WGPUBufferBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
    hasDynamicOffset: base.WGPUBool,
    minBindingSize: u64,
};

pub const WGPUSamplerBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
};

pub const WGPUTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    sampleType: u32,
    viewDimension: base.WGPUTextureViewDimension,
    multisampled: base.WGPUBool,
};

pub const WGPUStorageTextureBindingLayout = extern struct {
    nextInChain: ?*anyopaque,
    access: u32,
    format: base.WGPUTextureFormat,
    viewDimension: base.WGPUTextureViewDimension,
};

pub const WGPUBindGroupLayoutEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    visibility: base.WGPUShaderStageFlags,
    bindingArraySize: u32,
    buffer: WGPUBufferBindingLayout,
    sampler: WGPUSamplerBindingLayout,
    texture: WGPUTextureBindingLayout,
    storageTexture: WGPUStorageTextureBindingLayout,
};

pub const WGPUBindGroupEntry = extern struct {
    nextInChain: ?*anyopaque,
    binding: u32,
    buffer: base.WGPUBuffer,
    offset: u64,
    size: u64,
    sampler: base.WGPUSampler,
    textureView: base.WGPUTextureView,
};

pub const WGPUExternalTextureBindingLayout = extern struct {
    chain: WGPUChainedStruct,
};

pub const WGPUExternalTextureBindingEntry = extern struct {
    chain: WGPUChainedStruct,
    externalTexture: base.WGPUExternalTexture,
};

pub const WGPUCopyTextureForBrowserOptions = extern struct {
    nextInChain: ?*WGPUChainedStruct,
    flipY: base.WGPUBool,
    needsColorSpaceConversion: base.WGPUBool,
    srcAlphaMode: base.WGPUAlphaMode,
    srcTransferFunctionParameters: ?[*]const f32,
    conversionMatrix: ?[*]const f32,
    dstTransferFunctionParameters: ?[*]const f32,
    dstAlphaMode: base.WGPUAlphaMode,
    internalUsage: base.WGPUBool,
};

pub const WGPUImageCopyExternalTexture = extern struct {
    nextInChain: ?*WGPUChainedStruct,
    externalTexture: base.WGPUExternalTexture,
    origin: WGPUOrigin3D,
    naturalSize: WGPUExtent2D,
};

pub const WGPUBindGroupLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    entryCount: usize,
    entries: ?[*]const WGPUBindGroupLayoutEntry,
};

pub const WGPUBindGroupDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    layout: base.WGPUBindGroupLayout,
    entryCount: usize,
    entries: [*]const WGPUBindGroupEntry,
};

pub const WGPUPipelineLayoutDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    bindGroupLayoutCount: usize,
    bindGroupLayouts: [*]const base.WGPUBindGroupLayout,
    immediateSize: u32,
};

pub const WGPUCallbackMode = callback_types.WGPUCallbackMode;
pub const WGPUCallbackMode_WaitAnyOnly = callback_types.WGPUCallbackMode_WaitAnyOnly;
pub const WGPUCallbackMode_AllowProcessEvents = callback_types.WGPUCallbackMode_AllowProcessEvents;
pub const WGPUCallbackMode_AllowSpontaneous = callback_types.WGPUCallbackMode_AllowSpontaneous;
pub const WGPUWaitStatus = callback_types.WGPUWaitStatus;
pub const WGPURequestAdapterStatus = callback_types.WGPURequestAdapterStatus;
pub const WGPURequestDeviceStatus = callback_types.WGPURequestDeviceStatus;
pub const WGPUQueueWorkDoneStatus = callback_types.WGPUQueueWorkDoneStatus;
pub const WGPUPowerPreference = callback_types.WGPUPowerPreference;
pub const WGPUFeatureLevel = callback_types.WGPUFeatureLevel;
pub const WGPUBackendType = callback_types.WGPUBackendType;
pub const WGPURequestAdapterCallback = callback_types.WGPURequestAdapterCallback;
pub const WGPURequestDeviceCallback = callback_types.WGPURequestDeviceCallback;
pub const WGPUQueueWorkDoneCallback = callback_types.WGPUQueueWorkDoneCallback;
pub const WGPUDeviceLostReason = callback_types.WGPUDeviceLostReason;
pub const WGPUErrorType = callback_types.WGPUErrorType;
pub const WGPUDeviceLostCallback = callback_types.WGPUDeviceLostCallback;
pub const WGPUUncapturedErrorCallback = callback_types.WGPUUncapturedErrorCallback;
pub const WGPURequestAdapterCallbackInfo = callback_types.WGPURequestAdapterCallbackInfo;
pub const WGPURequestDeviceCallbackInfo = callback_types.WGPURequestDeviceCallbackInfo;
pub const WGPUQueueWorkDoneCallbackInfo = callback_types.WGPUQueueWorkDoneCallbackInfo;
pub const WGPUDeviceLostCallbackInfo = callback_types.WGPUDeviceLostCallbackInfo;
pub const WGPUUncapturedErrorCallbackInfo = callback_types.WGPUUncapturedErrorCallbackInfo;

pub const WGPUChainedStruct = extern struct {
    next: ?*WGPUChainedStruct,
    sType: base.WGPUSType,
};

pub const WGPURequestAdapterOptions = extern struct {
    nextInChain: ?*anyopaque,
    featureLevel: WGPUFeatureLevel,
    powerPreference: WGPUPowerPreference,
    forceFallbackAdapter: base.WGPUBool,
    backendType: WGPUBackendType,
    compatibleSurface: ?*anyopaque,
};

pub const WGPUBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    usage: base.WGPUBufferUsage,
    size: u64,
    mappedAtCreation: base.WGPUBool,
};

pub const WGPUShaderModuleDescriptor = extern struct {
    nextInChain: ?*WGPUChainedStruct,
    label: base.WGPUStringView,
};

pub const WGPUShaderSourceWGSL = extern struct {
    chain: WGPUChainedStruct,
    code: base.WGPUStringView,
};

pub const WGPUShaderSourceMSL = extern struct {
    chain: WGPUChainedStruct,
    code: base.WGPUStringView,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUShaderSourceSPIRV = extern struct {
    chain: WGPUChainedStruct,
    code: [*]const u32,
    code_size: u32,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUShaderSourceHLSL = extern struct {
    chain: WGPUChainedStruct,
    code: base.WGPUStringView,
    workgroup_size_x: u32,
    workgroup_size_y: u32,
    workgroup_size_z: u32,
};

pub const WGPUConstantEntry = extern struct {
    nextInChain: ?*anyopaque,
    key: base.WGPUStringView,
    value: f64,
};

pub const WGPUComputeState = extern struct {
    nextInChain: ?*anyopaque,
    module: base.WGPUShaderModule,
    entryPoint: base.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const WGPUConstantEntry,
};

pub const WGPUComputePipelineDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    layout: ?*anyopaque,
    compute: WGPUComputeState,
};

pub const WGPUComputePassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    timestampWrites: ?*const WGPUPassTimestampWrites,
};

pub const WGPUPassTimestampWrites = extern struct {
    nextInChain: ?*anyopaque,
    querySet: base.WGPUQuerySet,
    beginningOfPassWriteIndex: u32,
    endOfPassWriteIndex: u32,
};

pub const WGPUQuerySetDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    type: base.WGPUQueryType,
    count: u32,
};

pub const WGPUBufferMapCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    mode: WGPUCallbackMode,
    callback: ?WGPUBufferMapCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

pub const WGPUBufferMapCallback = *const fn (
    status: base.WGPUMapAsyncStatus,
    message: base.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void;

pub const WGPUCommandEncoderDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
};

pub const WGPUCommandBufferDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
};

pub const WGPUFutureWaitInfo = extern struct {
    future: base.WGPUFuture,
    completed: base.WGPUBool,
};

pub const WGPUQueueDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
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
    label: base.WGPUStringView,
    requiredFeatureCount: usize,
    requiredFeatures: ?[*]const base.WGPUFeatureName,
    requiredLimits: ?*const WGPULimits,
    defaultQueue: WGPUQueueDescriptor,
    deviceLostCallbackInfo: WGPUDeviceLostCallbackInfo,
    uncapturedErrorCallbackInfo: WGPUUncapturedErrorCallbackInfo,
};

pub const WGPUSamplerDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
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
    view: base.WGPUTextureView,
    depthSlice: u32,
    resolveTarget: base.WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: WGPUColor,
};

pub const WGPURenderPassDepthStencilAttachment = extern struct {
    view: base.WGPUTextureView,
    depthLoadOp: u32,
    depthStoreOp: u32,
    depthClearValue: f32,
    depthReadOnly: base.WGPUBool,
    stencilLoadOp: u32,
    stencilStoreOp: u32,
    stencilClearValue: u32,
    stencilReadOnly: base.WGPUBool,
};

pub const WGPURenderPassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: base.WGPUStringView,
    colorAttachmentCount: usize,
    colorAttachments: ?[*]const WGPURenderPassColorAttachment,
    depthStencilAttachment: ?*const WGPURenderPassDepthStencilAttachment,
    occlusionQuerySet: base.WGPUQuerySet,
    timestampWrites: ?*const WGPUPassTimestampWrites,
    maxDrawCount: u64,
};

pub fn initLimits() WGPULimits {
    var limits = std.mem.zeroes(WGPULimits);
    limits.nextInChain = null;
    return limits;
}
