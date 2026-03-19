#include "doe_napi_internal.h"

/* ================================================================
 * Instance
 * ================================================================ */

napi_value doe_create_instance(napi_env env, napi_callback_info info) {
    (void)info;
    CHECK_LIB_LOADED(env);
    /* Doe ignores the descriptor — pass NULL for clarity. */
    WGPUInstance inst = pfn_wgpuCreateInstance(NULL);
    if (!inst) NAPI_THROW(env, "wgpuCreateInstance returned NULL");
    return wrap_ptr(env, inst);
}

napi_value doe_instance_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* inst = unwrap_ptr(env, _args[0]);
    if (inst) pfn_wgpuInstanceRelease(inst);
    return NULL;
}

/* ================================================================
 * Adapter (synchronous requestAdapter via callback + processEvents)
 * ================================================================ */

/* Power preference string values match WGPUPowerPreference enum:
 * 0 = undefined, 2 = low-power, 3 = high-performance */
#define WGPU_POWER_PREFERENCE_LOW_POWER      2
#define WGPU_POWER_PREFERENCE_HIGH_PERFORMANCE 3
#define WGPU_FEATURE_LEVEL_COMPATIBILITY 1
#define WGPU_FEATURE_LEVEL_CORE          2
napi_value doe_request_adapter(napi_env env, napi_callback_info info) {
    /* Accept 1 or 2 args: (instance[, options]) */
    size_t actual_argc = 2;
    napi_value args[2];
    if (napi_get_cb_info(env, info, &actual_argc, args, NULL, NULL) != napi_ok)
        NAPI_THROW(env, "napi_get_cb_info failed");
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, args[0]);
    if (!inst) NAPI_THROW(env, "Invalid instance");

    WGPURequestAdapterOptions opts;
    memset(&opts, 0, sizeof(opts));
    const WGPURequestAdapterOptions* opts_ptr = NULL;

    if (actual_argc >= 2) {
        napi_valuetype vt = napi_undefined;
        napi_typeof(env, args[1], &vt);
        if (vt == napi_object) {
            /* featureLevel */
            napi_valuetype feature_level_type = napi_undefined;
            napi_value feature_level_val;
            if (napi_get_named_property(env, args[1], "featureLevel", &feature_level_val) == napi_ok) {
                napi_typeof(env, feature_level_val, &feature_level_type);
            }
            if (feature_level_type == napi_string) {
                char feature_level_str[32];
                size_t feature_level_len = 0;
                napi_get_value_string_utf8(env, feature_level_val, feature_level_str, sizeof(feature_level_str), &feature_level_len);
                if (strcmp(feature_level_str, "compatibility") == 0) {
                    opts.featureLevel = WGPU_FEATURE_LEVEL_COMPATIBILITY;
                } else if (strcmp(feature_level_str, "core") == 0) {
                    opts.featureLevel = WGPU_FEATURE_LEVEL_CORE;
                }
            }
            /* powerPreference */
            napi_valuetype pp_type = napi_undefined;
            napi_value pp_val;
            if (napi_get_named_property(env, args[1], "powerPreference", &pp_val) == napi_ok) {
                napi_typeof(env, pp_val, &pp_type);
            }
            if (pp_type == napi_string) {
                char pp_str[32];
                size_t pp_len = 0;
                napi_get_value_string_utf8(env, pp_val, pp_str, sizeof(pp_str), &pp_len);
                if (strcmp(pp_str, "low-power") == 0) {
                    opts.powerPreference = WGPU_POWER_PREFERENCE_LOW_POWER;
                } else if (strcmp(pp_str, "high-performance") == 0) {
                    opts.powerPreference = WGPU_POWER_PREFERENCE_HIGH_PERFORMANCE;
                }
            }
            /* featureLevel */
            napi_value fl_val;
            napi_valuetype fl_type = napi_undefined;
            if (napi_get_named_property(env, args[1], "featureLevel", &fl_val) == napi_ok) {
                napi_typeof(env, fl_val, &fl_type);
            }
            if (fl_type == napi_string) {
                char fl_str[32];
                size_t fl_len = 0;
                napi_get_value_string_utf8(env, fl_val, fl_str, sizeof(fl_str), &fl_len);
                if (strcmp(fl_str, "compatibility") == 0) {
                    opts.featureLevel = WGPU_FEATURE_LEVEL_COMPATIBILITY;
                } else if (strcmp(fl_str, "core") == 0) {
                    opts.featureLevel = WGPU_FEATURE_LEVEL_CORE;
                }
            }
            /* forceFallbackAdapter */
            napi_value ffa_val;
            napi_valuetype ffa_type = napi_undefined;
            if (napi_get_named_property(env, args[1], "forceFallbackAdapter", &ffa_val) == napi_ok) {
                napi_typeof(env, ffa_val, &ffa_type);
            }
            if (ffa_type == napi_boolean) {
                bool ffa = false;
                napi_get_value_bool(env, ffa_val, &ffa);
                opts.forceFallbackAdapter = ffa ? 1 : 0;
            }
            opts_ptr = &opts;
        }
    }

    AdapterRequestResult result = {0};
    WGPUFuture future;
    if (pfn_doeRequestAdapterFlat) {
        future = pfn_doeRequestAdapterFlat(
            inst, opts_ptr, WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS, adapter_callback, &result, NULL);
    } else {
        const WGPURequestAdapterCallbackInfo callback_info = {
            .nextInChain = NULL,
            .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
            .callback = adapter_callback,
            .userdata1 = &result,
            .userdata2 = NULL,
        };
        future = pfn_wgpuInstanceRequestAdapter(inst, opts_ptr, callback_info);
    }
    if (future.id == 0) NAPI_THROW(env, "requestAdapter future unavailable");
    if (!process_events_until(inst, &result.done, current_timeout_ns()))
        return throw_status_error(env, "DOE_REQUEST_ADAPTER_TIMEOUT", "requestAdapter timed out", result.status, result.message);
    if (result.status != WGPU_REQUEST_STATUS_SUCCESS || !result.adapter)
        return throw_status_error(env, "DOE_REQUEST_ADAPTER_ERROR", "requestAdapter failed", result.status, result.message);

    return wrap_ptr(env, result.adapter);
}

napi_value doe_adapter_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* adapter = unwrap_ptr(env, _args[0]);
    if (adapter) pfn_wgpuAdapterRelease(adapter);
    return NULL;
}

/* ================================================================
 * Device (synchronous requestDevice via callback + processEvents)
 * ================================================================ */

napi_value doe_request_device(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUAdapter adapter = unwrap_ptr(env, _args[1]);
    if (!inst || !adapter) NAPI_THROW(env, "Invalid instance or adapter");

    DeviceRequestResult result = {0};
    const WGPURequestDeviceCallbackInfo callback_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = device_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    WGPUFuture future = pfn_doeNativeAdapterRequestDevice
        ? pfn_doeNativeAdapterRequestDevice(adapter, NULL, callback_info)
        : pfn_wgpuAdapterRequestDevice(adapter, NULL, callback_info);
    if (future.id == 0) NAPI_THROW(env, "requestDevice future unavailable");
    if (!process_events_until(inst, &result.done, current_timeout_ns()))
        return throw_status_error(env, "DOE_REQUEST_DEVICE_TIMEOUT", "requestDevice timed out", result.status, result.message);
    if (result.status != WGPU_REQUEST_STATUS_SUCCESS || !result.device)
        return throw_status_error(env, "DOE_REQUEST_DEVICE_ERROR", "requestDevice failed", result.status, result.message);

    return wrap_ptr(env, result.device);
}

napi_value doe_device_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* device = unwrap_ptr(env, _args[0]);
    if (device) {
        DeviceCallbackBinding* lost = binding_take(&g_lost_bindings, device);
        DeviceCallbackBinding* uncaptured = binding_take(&g_uncaptured_bindings, device);
        if (lost && pfn_doeNativeDeviceRegisterLostCallback) {
            pfn_doeNativeDeviceRegisterLostCallback(device, NULL, NULL);
        }
        if (uncaptured && pfn_doeNativeDeviceSetUncapturedErrorCallback) {
            pfn_doeNativeDeviceSetUncapturedErrorCallback(device, NULL, NULL, NULL);
        }
        if (lost) {
            release_binding(lost);
        }
        if (uncaptured) {
            release_binding(uncaptured);
        }
        pfn_wgpuDeviceRelease(device);
    }
    return NULL;
}

napi_value doe_device_get_queue(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    WGPUQueue queue = pfn_wgpuDeviceGetQueue(device);
    return wrap_ptr(env, queue);
}
