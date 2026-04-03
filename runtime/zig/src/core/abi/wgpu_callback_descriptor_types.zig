const std = @import("std");
const base = @import("wgpu_core_base_types.zig");
const feature = @import("wgpu_feature_base_types.zig");
const callback_types = @import("wgpu_type_callbacks.zig").definitions(base);

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
    requiredFeatures: ?[*]const feature.WGPUFeatureName,
    requiredLimits: ?*const WGPULimits,
    defaultQueue: WGPUQueueDescriptor,
    deviceLostCallbackInfo: WGPUDeviceLostCallbackInfo,
    uncapturedErrorCallbackInfo: WGPUUncapturedErrorCallbackInfo,
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

pub const WGPUFutureWaitInfo = extern struct {
    future: base.WGPUFuture,
    completed: base.WGPUBool,
};

pub fn initLimits() WGPULimits {
    var limits = std.mem.zeroes(WGPULimits);
    limits.nextInChain = null;
    return limits;
}
