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

napi_value doe_request_adapter(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    if (!inst) NAPI_THROW(env, "Invalid instance");

    AdapterRequestResult result = {0};
    WGPUFuture future;
    if (pfn_doeRequestAdapterFlat) {
        future = pfn_doeRequestAdapterFlat(
            inst, NULL, WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS, adapter_callback, &result, NULL);
    } else {
        const WGPURequestAdapterCallbackInfo callback_info = {
            .nextInChain = NULL,
            .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
            .callback = adapter_callback,
            .userdata1 = &result,
            .userdata2 = NULL,
        };
        future = pfn_wgpuInstanceRequestAdapter(inst, NULL, callback_info);
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
