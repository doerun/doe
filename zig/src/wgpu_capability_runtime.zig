const loader = @import("wgpu_loader.zig");
const types = @import("wgpu_types.zig");
const p1_capability_procs_mod = @import("wgpu_p1_capability_procs.zig");
const p2_lifecycle_procs_mod = @import("wgpu_p2_lifecycle_procs.zig");

pub const AdapterProbeResult = struct {
    adapter_has_timestamp_query: bool,
    has_timestamp_inside_passes: bool,
    adapter_has_multi_draw_indirect: bool,
    adapter_has_pixel_local_storage_coherent: bool,
    adapter_has_pixel_local_storage_non_coherent: bool,
};

pub const DeviceProbeResult = struct {
    has_timestamp_query: bool,
    has_multi_draw_indirect: bool,
    has_pixel_local_storage_coherent: bool,
    has_pixel_local_storage_non_coherent: bool,
};

pub fn probeInstanceCapabilities(
    capability_procs: ?p1_capability_procs_mod.CapabilityProcs,
    instance: types.WGPUInstance,
) !void {
    const cap = capability_procs orelse return;
    if (instance == null) return;

    if (cap.get_instance_features) |get_instance_features| {
        var features = p1_capability_procs_mod.initSupportedInstanceFeatures();
        get_instance_features(&features);
        _ = p1_capability_procs_mod.hasInstanceFeatureInList(
            features,
            p1_capability_procs_mod.WGPUInstanceFeatureName_TimedWaitAny,
        );
        if (cap.supported_instance_features_free_members) |free_members| free_members(features);
    }
    if (cap.get_instance_limits) |get_instance_limits| {
        var limits = p1_capability_procs_mod.initInstanceLimits();
        if (get_instance_limits(&limits) != types.WGPUStatus_Success) return error.InstanceLimitsQueryFailed;
    }
    if (cap.has_instance_feature) |has_instance_feature| {
        _ = has_instance_feature(p1_capability_procs_mod.WGPUInstanceFeatureName_TimedWaitAny);
    }
    if (cap.get_proc_address) |get_proc_address| {
        const proc_name = loader.stringView("wgpuAdapterGetInfo");
        if (get_proc_address(proc_name) == null) return error.GetProcAddressFailed;
    }
    if (cap.instance_get_wgsl_language_features) |get_wgsl_features| {
        var features = p1_capability_procs_mod.initSupportedWGSLLanguageFeatures();
        get_wgsl_features(instance, &features);
        _ = p1_capability_procs_mod.hasWGSLLanguageFeatureInList(
            features,
            p1_capability_procs_mod.WGPUWGSLLanguageFeatureName_ReadonlyAndReadwriteStorageTextures,
        );
        if (cap.supported_wgsl_language_features_free_members) |free_members| free_members(features);
    }
    if (cap.instance_has_wgsl_language_feature) |has_wgsl_feature| {
        _ = has_wgsl_feature(
            instance,
            p1_capability_procs_mod.WGPUWGSLLanguageFeatureName_ReadonlyAndReadwriteStorageTextures,
        );
    }
}

pub fn probeAdapterCapabilities(
    capability_procs: ?p1_capability_procs_mod.CapabilityProcs,
    adapter: types.WGPUAdapter,
    instance: types.WGPUInstance,
    defaults: AdapterProbeResult,
) !AdapterProbeResult {
    const cap = capability_procs orelse return defaults;
    const active_adapter = adapter orelse return defaults;
    var result = defaults;
    var has_adapter_properties_memory_heaps = false;
    var has_subgroup_matrix_configs = false;
    var has_drm_format_capabilities = false;

    if (cap.adapter_get_features) |get_features| {
        var features = p1_capability_procs_mod.initSupportedFeatures();
        get_features(active_adapter, &features);
        result.adapter_has_timestamp_query = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_TimestampQuery,
        );
        result.has_timestamp_inside_passes = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses,
        );
        result.adapter_has_multi_draw_indirect = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_MultiDrawIndirect,
        );
        result.adapter_has_pixel_local_storage_coherent = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_PixelLocalStorageCoherent,
        );
        result.adapter_has_pixel_local_storage_non_coherent = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_PixelLocalStorageNonCoherent,
        );
        has_adapter_properties_memory_heaps = p1_capability_procs_mod.hasFeature(
            features,
            p1_capability_procs_mod.WGPUFeatureName_AdapterPropertiesMemoryHeaps,
        );
        has_subgroup_matrix_configs = p1_capability_procs_mod.hasFeature(
            features,
            p1_capability_procs_mod.WGPUFeatureName_ChromiumExperimentalSubgroupMatrix,
        );
        has_drm_format_capabilities = p1_capability_procs_mod.hasFeature(
            features,
            p1_capability_procs_mod.WGPUFeatureName_DawnDrmFormatCapabilities,
        );
        if (cap.supported_features_free_members) |free_members| free_members(features);
    }
    if (cap.adapter_get_format_capabilities) |get_format_capabilities| {
        var drm_caps = p1_capability_procs_mod.initDawnDrmFormatCapabilities();
        var format_caps = p1_capability_procs_mod.initDawnFormatCapabilities(
            if (has_drm_format_capabilities) @ptrCast(&drm_caps.chain) else null,
        );
        if (get_format_capabilities(active_adapter, types.WGPUTextureFormat_R8Unorm, &format_caps) != types.WGPUStatus_Success) {
            return error.AdapterFormatCapabilitiesQueryFailed;
        }
        if (has_drm_format_capabilities) {
            if (cap.dawn_drm_format_capabilities_free_members) |free_members| {
                free_members(drm_caps);
            }
        }
    }
    if (cap.adapter_get_info) |get_info| {
        var heaps = p1_capability_procs_mod.initAdapterPropertiesMemoryHeaps();
        var subgroup_configs = p1_capability_procs_mod.initAdapterPropertiesSubgroupMatrixConfigs();
        var info_chain: ?*anyopaque = null;
        if (has_adapter_properties_memory_heaps) {
            info_chain = @ptrCast(&heaps.chain);
        }
        if (has_subgroup_matrix_configs) {
            if (has_adapter_properties_memory_heaps) {
                heaps.chain.next = @ptrCast(&subgroup_configs.chain);
            } else {
                info_chain = @ptrCast(&subgroup_configs.chain);
            }
        }
        var info = p1_capability_procs_mod.initAdapterInfo(info_chain);
        if (get_info(active_adapter, &info) != types.WGPUStatus_Success) return error.AdapterInfoQueryFailed;
        if (cap.adapter_info_free_members) |free_members| free_members(info);
        if (has_adapter_properties_memory_heaps) {
            if (cap.adapter_properties_memory_heaps_free_members) |free_members| {
                free_members(heaps);
            }
        }
        if (has_subgroup_matrix_configs) {
            if (cap.adapter_properties_subgroup_matrix_configs_free_members) |free_members| {
                free_members(subgroup_configs);
            }
        }
    }
    if (cap.adapter_get_instance) |get_instance| {
        const adapter_instance = get_instance(active_adapter);
        if (adapter_instance == null or adapter_instance != instance) return error.AdapterInstanceMismatch;
    }
    if (cap.adapter_get_limits) |get_limits| {
        var limits = p1_capability_procs_mod.initLimits();
        if (get_limits(active_adapter, &limits) != types.WGPUStatus_Success) return error.AdapterLimitsQueryFailed;
    }

    return result;
}

pub fn probeDeviceCapabilities(
    capability_procs: ?p1_capability_procs_mod.CapabilityProcs,
    device: types.WGPUDevice,
    adapter: types.WGPUAdapter,
    defaults: DeviceProbeResult,
) !DeviceProbeResult {
    const cap = capability_procs orelse return defaults;
    const active_device = device orelse return defaults;
    var result = defaults;
    var has_adapter_properties_memory_heaps = false;
    var has_subgroup_matrix_configs = false;

    if (cap.device_get_adapter) |get_adapter| {
        const device_adapter = get_adapter(active_device);
        if (device_adapter == null or device_adapter != adapter) return error.DeviceAdapterMismatch;
    }
    if (cap.device_get_features) |get_features| {
        var features = p1_capability_procs_mod.initSupportedFeatures();
        get_features(active_device, &features);
        result.has_timestamp_query = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_TimestampQuery,
        );
        result.has_multi_draw_indirect = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_MultiDrawIndirect,
        );
        result.has_pixel_local_storage_coherent = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_PixelLocalStorageCoherent,
        );
        result.has_pixel_local_storage_non_coherent = p1_capability_procs_mod.hasFeature(
            features,
            types.WGPUFeatureName_PixelLocalStorageNonCoherent,
        );
        has_adapter_properties_memory_heaps = p1_capability_procs_mod.hasFeature(
            features,
            p1_capability_procs_mod.WGPUFeatureName_AdapterPropertiesMemoryHeaps,
        );
        has_subgroup_matrix_configs = p1_capability_procs_mod.hasFeature(
            features,
            p1_capability_procs_mod.WGPUFeatureName_ChromiumExperimentalSubgroupMatrix,
        );
        if (cap.supported_features_free_members) |free_members| free_members(features);
    }
    if (cap.device_get_adapter_info) |get_adapter_info| {
        var heaps = p1_capability_procs_mod.initAdapterPropertiesMemoryHeaps();
        var subgroup_configs = p1_capability_procs_mod.initAdapterPropertiesSubgroupMatrixConfigs();
        var info_chain: ?*anyopaque = null;
        if (has_adapter_properties_memory_heaps) {
            info_chain = @ptrCast(&heaps.chain);
        }
        if (has_subgroup_matrix_configs) {
            if (has_adapter_properties_memory_heaps) {
                heaps.chain.next = @ptrCast(&subgroup_configs.chain);
            } else {
                info_chain = @ptrCast(&subgroup_configs.chain);
            }
        }
        var info = p1_capability_procs_mod.initAdapterInfo(info_chain);
        if (get_adapter_info(active_device, &info) != types.WGPUStatus_Success) return error.DeviceAdapterInfoQueryFailed;
        if (cap.adapter_info_free_members) |free_members| free_members(info);
        if (has_adapter_properties_memory_heaps) {
            if (cap.adapter_properties_memory_heaps_free_members) |free_members| {
                free_members(heaps);
            }
        }
        if (has_subgroup_matrix_configs) {
            if (cap.adapter_properties_subgroup_matrix_configs_free_members) |free_members| {
                free_members(subgroup_configs);
            }
        }
    }
    if (cap.device_get_limits) |get_limits| {
        var limits = p1_capability_procs_mod.initLimits();
        if (get_limits(active_device, &limits) != types.WGPUStatus_Success) return error.DeviceLimitsQueryFailed;
    }

    return result;
}

pub fn touchPrimaryObjectRefs(
    lifecycle_procs: ?p2_lifecycle_procs_mod.LifecycleProcs,
    procs: types.Procs,
    instance: types.WGPUInstance,
    adapter: types.WGPUAdapter,
    device: types.WGPUDevice,
    queue: types.WGPUQueue,
) void {
    const life = lifecycle_procs orelse return;
    if (instance) |active_instance| {
        p2_lifecycle_procs_mod.addRefIfPresent(types.WGPUInstance, life.instance_add_ref, active_instance);
        procs.wgpuInstanceRelease(active_instance);
    }
    if (adapter) |active_adapter| {
        p2_lifecycle_procs_mod.addRefIfPresent(types.WGPUAdapter, life.adapter_add_ref, active_adapter);
        procs.wgpuAdapterRelease(active_adapter);
    }
    if (device) |active_device| {
        p2_lifecycle_procs_mod.addRefIfPresent(types.WGPUDevice, life.device_add_ref, active_device);
        procs.wgpuDeviceRelease(active_device);
    }
    if (queue) |active_queue| {
        p2_lifecycle_procs_mod.addRefIfPresent(types.WGPUQueue, life.queue_add_ref, active_queue);
        procs.wgpuQueueRelease(active_queue);
    }
}
