const facade = @import("native/doe_cache_adapter_native.zig");

pub const doeNativeDeviceCreatePipelineCacheDescriptor = facade.doeNativeDeviceCreatePipelineCacheDescriptor;
pub const doeNativePipelineCacheDescriptorRelease = facade.doeNativePipelineCacheDescriptorRelease;
pub const doeNativeDeviceCreatePipelineCache = facade.doeNativeDeviceCreatePipelineCache;
pub const doeNativePipelineCacheGetData = facade.doeNativePipelineCacheGetData;
pub const doeNativePipelineCacheDataFree = facade.doeNativePipelineCacheDataFree;
pub const doeNativePipelineCacheRelease = facade.doeNativePipelineCacheRelease;
pub const doeNativeInstanceEnumerateAdapters = facade.doeNativeInstanceEnumerateAdapters;
pub const doeNativeAdapterListGetCount = facade.doeNativeAdapterListGetCount;
pub const doeNativeAdapterListGetInfo = facade.doeNativeAdapterListGetInfo;
pub const doeNativeAdapterListRetainDevice = facade.doeNativeAdapterListRetainDevice;
pub const doeNativeAdapterListRelease = facade.doeNativeAdapterListRelease;
pub const doeNativeInstanceSelectAdapter = facade.doeNativeInstanceSelectAdapter;
pub const doeNativeAdapterGetInfoStruct = facade.doeNativeAdapterGetInfoStruct;
pub const doeNativeDeviceRegisterLostCallback = facade.doeNativeDeviceRegisterLostCallback;
pub const doeNativeDeviceNotifyLost = facade.doeNativeDeviceNotifyLost;
