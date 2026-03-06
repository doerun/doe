/*
 * doe_napi.c — N-API binding for libdoe_webgpu (Doe WebGPU runtime).
 *
 * Loads the Doe shared library at runtime via dlopen and exposes the core
 * WebGPU compute surface to JavaScript through Node.js N-API.
 *
 * All WGPUInstance/Adapter/Device/Buffer/etc. handles are wrapped as
 * napi_external values. Struct descriptors are marshaled from JS objects.
 * Async operations (requestAdapter, requestDevice, bufferMapAsync) use
 * synchronous WaitAny blocking — acceptable for headless compute.
 */

#include <node_api.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#ifdef _WIN32
#include <windows.h>
#define LIB_OPEN(p)      LoadLibraryA(p)
#define LIB_SYM(h, n)    ((void*)GetProcAddress((HMODULE)(h), n))
#define LIB_CLOSE(h)     FreeLibrary((HMODULE)(h))
#else
#include <dlfcn.h>
#define LIB_OPEN(p)      dlopen(p, RTLD_NOW | RTLD_LOCAL)
#define LIB_SYM(h, n)    dlsym(h, n)
#define LIB_CLOSE(h)     dlclose(h)
#endif

/* ================================================================
 * WebGPU C ABI type definitions (matching wgpu_types.zig)
 * ================================================================ */

typedef void* WGPUInstance;
typedef void* WGPUAdapter;
typedef void* WGPUDevice;
typedef void* WGPUQueue;
typedef void* WGPUBuffer;
typedef void* WGPUShaderModule;
typedef void* WGPUComputePipeline;
typedef void* WGPURenderPipeline;
typedef void* WGPUBindGroupLayout;
typedef void* WGPUBindGroup;
typedef void* WGPUPipelineLayout;
typedef void* WGPUCommandEncoder;
typedef void* WGPUCommandBuffer;
typedef void* WGPUComputePassEncoder;
typedef void* WGPUQuerySet;
typedef void* WGPUTexture;
typedef void* WGPUTextureView;
typedef void* WGPUSampler;
typedef uint64_t WGPUFlags;
typedef uint32_t WGPUBool;

#define WGPU_STRLEN SIZE_MAX
#define WGPU_WHOLE_SIZE UINT64_MAX

typedef struct { uint64_t id; } WGPUFuture;
typedef struct { const char* data; size_t length; } WGPUStringView;
typedef struct { WGPUFuture future; WGPUBool completed; } WGPUFutureWaitInfo;

typedef struct { void* next; uint32_t sType; } WGPUChainedStruct;

typedef enum {
    WGPUInstanceFeatureName_TimedWaitAny = 0x00000001,
} WGPUInstanceFeatureName;

typedef struct {
    WGPUChainedStruct* nextInChain;
    size_t timedWaitAnyMaxCount;
} WGPUInstanceLimits;

typedef struct {
    WGPUChainedStruct* nextInChain;
    size_t requiredFeatureCount;
    const WGPUInstanceFeatureName* requiredFeatures;
    const WGPUInstanceLimits* requiredLimits;
} WGPUInstanceDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    uint64_t usage;
    uint64_t size;
    WGPUBool mappedAtCreation;
} WGPUBufferDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
} WGPUCommandEncoderDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
} WGPUCommandBufferDescriptor;

typedef struct {
    WGPUChainedStruct chain;
    WGPUStringView code;
} WGPUShaderSourceWGSL;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
} WGPUShaderModuleDescriptor;

typedef struct {
    void* nextInChain;
    WGPUShaderModule module;
    WGPUStringView entryPoint;
    size_t constantCount;
    void* constants;
} WGPUComputeState;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    void* layout;
    WGPUComputeState compute;
} WGPUComputePipelineDescriptor;

typedef struct {
    void* nextInChain;
    uint32_t type;
    WGPUBool hasDynamicOffset;
    uint64_t minBindingSize;
} WGPUBufferBindingLayout;

typedef struct {
    void* nextInChain;
    uint32_t type;
} WGPUSamplerBindingLayout;

typedef struct {
    void* nextInChain;
    uint32_t sampleType;
    uint32_t viewDimension;
    WGPUBool multisampled;
} WGPUTextureBindingLayout;

typedef struct {
    void* nextInChain;
    uint32_t access;
    uint32_t format;
    uint32_t viewDimension;
} WGPUStorageTextureBindingLayout;

typedef struct {
    void* nextInChain;
    uint32_t binding;
    uint64_t visibility;
    uint32_t bindingArraySize;
    WGPUBufferBindingLayout buffer;
    WGPUSamplerBindingLayout sampler;
    WGPUTextureBindingLayout texture;
    WGPUStorageTextureBindingLayout storageTexture;
} WGPUBindGroupLayoutEntry;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    size_t entryCount;
    const WGPUBindGroupLayoutEntry* entries;
} WGPUBindGroupLayoutDescriptor;

typedef struct {
    void* nextInChain;
    uint32_t binding;
    WGPUBuffer buffer;
    uint64_t offset;
    uint64_t size;
    WGPUSampler sampler;
    WGPUTextureView textureView;
} WGPUBindGroupEntry;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    WGPUBindGroupLayout layout;
    size_t entryCount;
    const WGPUBindGroupEntry* entries;
} WGPUBindGroupDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    size_t bindGroupLayoutCount;
    const WGPUBindGroupLayout* bindGroupLayouts;
    uint32_t immediateSize;
} WGPUPipelineLayoutDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    void* timestampWrites;
} WGPUComputePassDescriptor;

/* Callback types */
typedef void (*WGPURequestAdapterCallback)(
    uint32_t status, WGPUAdapter adapter, WGPUStringView message,
    void* userdata1, void* userdata2);

typedef void (*WGPURequestDeviceCallback)(
    uint32_t status, WGPUDevice device, WGPUStringView message,
    void* userdata1, void* userdata2);

typedef void (*WGPUBufferMapCallback)(
    uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2);

/* ================================================================
 * Function pointer types and global storage
 * ================================================================ */

#define DECL_PFN(ret, name, params) typedef ret (*PFN_##name) params; static PFN_##name pfn_##name = NULL

DECL_PFN(WGPUInstance, wgpuCreateInstance, (const void*));
DECL_PFN(void, wgpuInstanceRelease, (WGPUInstance));
DECL_PFN(uint32_t, wgpuInstanceWaitAny, (WGPUInstance, size_t, WGPUFutureWaitInfo*, uint64_t));
DECL_PFN(void, wgpuInstanceProcessEvents, (WGPUInstance));
DECL_PFN(void, wgpuAdapterRelease, (WGPUAdapter));
DECL_PFN(WGPUBool, wgpuAdapterHasFeature, (WGPUAdapter, uint32_t));
DECL_PFN(void, wgpuDeviceRelease, (WGPUDevice));
DECL_PFN(WGPUBool, wgpuDeviceHasFeature, (WGPUDevice, uint32_t));
DECL_PFN(WGPUQueue, wgpuDeviceGetQueue, (WGPUDevice));
DECL_PFN(WGPUBuffer, wgpuDeviceCreateBuffer, (WGPUDevice, const WGPUBufferDescriptor*));
DECL_PFN(WGPUShaderModule, wgpuDeviceCreateShaderModule, (WGPUDevice, const WGPUShaderModuleDescriptor*));
DECL_PFN(void, wgpuShaderModuleRelease, (WGPUShaderModule));
DECL_PFN(WGPUComputePipeline, wgpuDeviceCreateComputePipeline, (WGPUDevice, const WGPUComputePipelineDescriptor*));
DECL_PFN(void, wgpuComputePipelineRelease, (WGPUComputePipeline));
DECL_PFN(WGPUBindGroupLayout, wgpuDeviceCreateBindGroupLayout, (WGPUDevice, const WGPUBindGroupLayoutDescriptor*));
DECL_PFN(void, wgpuBindGroupLayoutRelease, (WGPUBindGroupLayout));
DECL_PFN(WGPUBindGroup, wgpuDeviceCreateBindGroup, (WGPUDevice, const WGPUBindGroupDescriptor*));
DECL_PFN(void, wgpuBindGroupRelease, (WGPUBindGroup));
DECL_PFN(WGPUPipelineLayout, wgpuDeviceCreatePipelineLayout, (WGPUDevice, const WGPUPipelineLayoutDescriptor*));
DECL_PFN(void, wgpuPipelineLayoutRelease, (WGPUPipelineLayout));
DECL_PFN(WGPUCommandEncoder, wgpuDeviceCreateCommandEncoder, (WGPUDevice, const WGPUCommandEncoderDescriptor*));
DECL_PFN(void, wgpuCommandEncoderRelease, (WGPUCommandEncoder));
DECL_PFN(WGPUComputePassEncoder, wgpuCommandEncoderBeginComputePass, (WGPUCommandEncoder, const WGPUComputePassDescriptor*));
DECL_PFN(void, wgpuCommandEncoderCopyBufferToBuffer, (WGPUCommandEncoder, WGPUBuffer, uint64_t, WGPUBuffer, uint64_t, uint64_t));
DECL_PFN(WGPUCommandBuffer, wgpuCommandEncoderFinish, (WGPUCommandEncoder, const WGPUCommandBufferDescriptor*));
DECL_PFN(void, wgpuComputePassEncoderSetPipeline, (WGPUComputePassEncoder, WGPUComputePipeline));
DECL_PFN(void, wgpuComputePassEncoderSetBindGroup, (WGPUComputePassEncoder, uint32_t, WGPUBindGroup, size_t, const uint32_t*));
DECL_PFN(void, wgpuComputePassEncoderDispatchWorkgroups, (WGPUComputePassEncoder, uint32_t, uint32_t, uint32_t));
DECL_PFN(void, wgpuComputePassEncoderEnd, (WGPUComputePassEncoder));
DECL_PFN(void, wgpuComputePassEncoderRelease, (WGPUComputePassEncoder));
DECL_PFN(void, wgpuQueueSubmit, (WGPUQueue, size_t, const WGPUCommandBuffer*));
DECL_PFN(void, wgpuQueueWriteBuffer, (WGPUQueue, WGPUBuffer, uint64_t, const void*, size_t));
DECL_PFN(void, wgpuQueueRelease, (WGPUQueue));
DECL_PFN(void, wgpuBufferRelease, (WGPUBuffer));
DECL_PFN(void, wgpuBufferUnmap, (WGPUBuffer));
DECL_PFN(const void*, wgpuBufferGetConstMappedRange, (WGPUBuffer, size_t, size_t));
DECL_PFN(void*, wgpuBufferGetMappedRange, (WGPUBuffer, size_t, size_t));
DECL_PFN(void, wgpuCommandBufferRelease, (WGPUCommandBuffer));

/* Flat helpers for FFI-friendly adapter/device request */
DECL_PFN(WGPUFuture, doeRequestAdapterFlat, (WGPUInstance, const void*, uint32_t, WGPURequestAdapterCallback, void*, void*));
DECL_PFN(WGPUFuture, doeRequestDeviceFlat, (WGPUAdapter, const void*, uint32_t, WGPURequestDeviceCallback, void*, void*));
typedef struct {
    void* nextInChain;
    uint32_t mode;
    WGPUBufferMapCallback callback;
    void* userdata1;
    void* userdata2;
} WGPUBufferMapCallbackInfo;

typedef WGPUFuture (*PFN_wgpuBufferMapAsync2)(WGPUBuffer, uint64_t, size_t, size_t, WGPUBufferMapCallbackInfo);
static PFN_wgpuBufferMapAsync2 pfn_wgpuBufferMapAsync2 = NULL;

static void* g_lib = NULL;

/* ================================================================
 * N-API utility helpers
 * ================================================================ */

#define NAPI_THROW(env, msg) do { napi_throw_error(env, NULL, msg); return NULL; } while(0)
#define NAPI_ASSERT_ARGC(env, info, n) \
    size_t _argc = n; napi_value _args[n]; \
    if (napi_get_cb_info(env, info, &_argc, _args, NULL, NULL) != napi_ok) NAPI_THROW(env, "napi_get_cb_info failed")

static void* unwrap_ptr(napi_env env, napi_value val) {
    void* ptr = NULL;
    napi_get_value_external(env, val, &ptr);
    return ptr;
}

static napi_value wrap_ptr(napi_env env, void* ptr) {
    napi_value result;
    if (napi_create_external(env, ptr, NULL, NULL, &result) != napi_ok) return NULL;
    return result;
}

static uint32_t get_uint32_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    uint32_t out = 0;
    napi_get_value_uint32(env, val, &out);
    return out;
}

static int64_t get_int64_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    int64_t out = 0;
    napi_get_value_int64(env, val, &out);
    return out;
}

static bool get_bool_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_boolean) return false;
    bool out = false;
    napi_get_value_bool(env, val, &out);
    return out;
}

static bool has_prop(napi_env env, napi_value obj, const char* key) {
    bool result = false;
    napi_has_named_property(env, obj, key, &result);
    return result;
}

static napi_value get_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    return val;
}

static napi_valuetype prop_type(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    return vt;
}

/* ================================================================
 * Library loading
 * ================================================================ */

#define LOAD_SYM(name) pfn_##name = (PFN_##name)LIB_SYM(g_lib, #name)

static napi_value doe_load_library(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    size_t path_len = 0;
    napi_get_value_string_utf8(env, _args[0], NULL, 0, &path_len);
    char* path = (char*)malloc(path_len + 1);
    napi_get_value_string_utf8(env, _args[0], path, path_len + 1, &path_len);

    if (g_lib) { LIB_CLOSE(g_lib); g_lib = NULL; }
    g_lib = LIB_OPEN(path);
    free(path);
    if (!g_lib) NAPI_THROW(env, "Failed to load libdoe_webgpu");

    LOAD_SYM(wgpuCreateInstance);
    LOAD_SYM(wgpuInstanceRelease);
    LOAD_SYM(wgpuInstanceWaitAny);
    LOAD_SYM(wgpuInstanceProcessEvents);
    LOAD_SYM(wgpuAdapterRelease);
    LOAD_SYM(wgpuAdapterHasFeature);
    LOAD_SYM(wgpuDeviceRelease);
    LOAD_SYM(wgpuDeviceHasFeature);
    LOAD_SYM(wgpuDeviceGetQueue);
    LOAD_SYM(wgpuDeviceCreateBuffer);
    LOAD_SYM(wgpuDeviceCreateShaderModule);
    LOAD_SYM(wgpuShaderModuleRelease);
    LOAD_SYM(wgpuDeviceCreateComputePipeline);
    LOAD_SYM(wgpuComputePipelineRelease);
    LOAD_SYM(wgpuDeviceCreateBindGroupLayout);
    LOAD_SYM(wgpuBindGroupLayoutRelease);
    LOAD_SYM(wgpuDeviceCreateBindGroup);
    LOAD_SYM(wgpuBindGroupRelease);
    LOAD_SYM(wgpuDeviceCreatePipelineLayout);
    LOAD_SYM(wgpuPipelineLayoutRelease);
    LOAD_SYM(wgpuDeviceCreateCommandEncoder);
    LOAD_SYM(wgpuCommandEncoderRelease);
    LOAD_SYM(wgpuCommandEncoderBeginComputePass);
    LOAD_SYM(wgpuCommandEncoderCopyBufferToBuffer);
    LOAD_SYM(wgpuCommandEncoderFinish);
    LOAD_SYM(wgpuComputePassEncoderSetPipeline);
    LOAD_SYM(wgpuComputePassEncoderSetBindGroup);
    LOAD_SYM(wgpuComputePassEncoderDispatchWorkgroups);
    LOAD_SYM(wgpuComputePassEncoderEnd);
    LOAD_SYM(wgpuComputePassEncoderRelease);
    LOAD_SYM(wgpuQueueSubmit);
    LOAD_SYM(wgpuQueueWriteBuffer);
    LOAD_SYM(wgpuQueueRelease);
    LOAD_SYM(wgpuBufferRelease);
    LOAD_SYM(wgpuBufferUnmap);
    LOAD_SYM(wgpuBufferGetConstMappedRange);
    LOAD_SYM(wgpuBufferGetMappedRange);
    LOAD_SYM(wgpuCommandBufferRelease);
    LOAD_SYM(doeRequestAdapterFlat);
    LOAD_SYM(doeRequestDeviceFlat);
    pfn_wgpuBufferMapAsync2 = (PFN_wgpuBufferMapAsync2)LIB_SYM(g_lib, "wgpuBufferMapAsync");

    napi_value result;
    napi_get_boolean(env, true, &result);
    return result;
}

/* ================================================================
 * Instance
 * ================================================================ */

static napi_value doe_create_instance(napi_env env, napi_callback_info info) {
    (void)info;
    if (!pfn_wgpuCreateInstance) NAPI_THROW(env, "Library not loaded");

    WGPUInstanceFeatureName features[] = { WGPUInstanceFeatureName_TimedWaitAny };
    WGPUInstanceLimits limits = { .nextInChain = NULL, .timedWaitAnyMaxCount = 64 };
    WGPUInstanceDescriptor desc = {
        .nextInChain = NULL,
        .requiredFeatureCount = 1,
        .requiredFeatures = features,
        .requiredLimits = &limits,
    };
    WGPUInstance inst = pfn_wgpuCreateInstance(&desc);
    if (!inst) NAPI_THROW(env, "wgpuCreateInstance returned NULL");
    return wrap_ptr(env, inst);
}

static napi_value doe_instance_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* inst = unwrap_ptr(env, _args[0]);
    if (inst) pfn_wgpuInstanceRelease(inst);
    return NULL;
}

/* ================================================================
 * Adapter (synchronous requestAdapter via WaitAny)
 * ================================================================ */

typedef struct {
    uint32_t status;
    WGPUAdapter adapter;
} AdapterRequestResult;

static void adapter_callback(uint32_t status, WGPUAdapter adapter,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)message; (void)userdata2;
    AdapterRequestResult* r = (AdapterRequestResult*)userdata1;
    r->status = status;
    r->adapter = adapter;
}

static napi_value doe_request_adapter(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    if (!inst) NAPI_THROW(env, "Invalid instance");

    AdapterRequestResult result = {0, NULL};
    WGPUFuture future = pfn_doeRequestAdapterFlat(
        inst, NULL, 1 /* WaitAnyOnly */, adapter_callback, &result, NULL);

    WGPUFutureWaitInfo wait_info = { .future = future, .completed = 0 };
    uint32_t wait_status = pfn_wgpuInstanceWaitAny(
        inst, 1, &wait_info, (uint64_t)5000000000ULL);

    if (wait_status != 1 || result.status != 1 || !result.adapter)
        NAPI_THROW(env, "requestAdapter failed");

    return wrap_ptr(env, result.adapter);
}

static napi_value doe_adapter_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* adapter = unwrap_ptr(env, _args[0]);
    if (adapter) pfn_wgpuAdapterRelease(adapter);
    return NULL;
}

/* ================================================================
 * Device (synchronous requestDevice via WaitAny)
 * ================================================================ */

typedef struct {
    uint32_t status;
    WGPUDevice device;
} DeviceRequestResult;

static void device_callback(uint32_t status, WGPUDevice device,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)message; (void)userdata2;
    DeviceRequestResult* r = (DeviceRequestResult*)userdata1;
    r->status = status;
    r->device = device;
}

static napi_value doe_request_device(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUAdapter adapter = unwrap_ptr(env, _args[1]);
    if (!inst || !adapter) NAPI_THROW(env, "Invalid instance or adapter");

    DeviceRequestResult result = {0, NULL};
    WGPUFuture future = pfn_doeRequestDeviceFlat(
        adapter, NULL, 1 /* WaitAnyOnly */, device_callback, &result, NULL);

    WGPUFutureWaitInfo wait_info = { .future = future, .completed = 0 };
    uint32_t wait_status = pfn_wgpuInstanceWaitAny(
        inst, 1, &wait_info, (uint64_t)5000000000ULL);

    if (wait_status != 1 || result.status != 1 || !result.device)
        NAPI_THROW(env, "requestDevice failed");

    return wrap_ptr(env, result.device);
}

static napi_value doe_device_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* device = unwrap_ptr(env, _args[0]);
    if (device) pfn_wgpuDeviceRelease(device);
    return NULL;
}

static napi_value doe_device_get_queue(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    WGPUQueue queue = pfn_wgpuDeviceGetQueue(device);
    return wrap_ptr(env, queue);
}

/* ================================================================
 * Buffer
 * ================================================================ */

static napi_value doe_create_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    WGPUBufferDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.usage = (uint64_t)get_int64_prop(env, _args[1], "usage");
    desc.size = (uint64_t)get_int64_prop(env, _args[1], "size");
    desc.mappedAtCreation = get_bool_prop(env, _args[1], "mappedAtCreation") ? 1 : 0;

    WGPUBuffer buf = pfn_wgpuDeviceCreateBuffer(device, &desc);
    if (!buf) NAPI_THROW(env, "createBuffer failed");
    return wrap_ptr(env, buf);
}

static napi_value doe_buffer_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* buf = unwrap_ptr(env, _args[0]);
    if (buf) pfn_wgpuBufferRelease(buf);
    return NULL;
}

static napi_value doe_buffer_unmap(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    if (buf) pfn_wgpuBufferUnmap(buf);
    return NULL;
}

typedef struct {
    uint32_t status;
} BufferMapResult;

static void buffer_map_callback(uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2) {
    (void)message; (void)userdata2;
    BufferMapResult* r = (BufferMapResult*)userdata1;
    r->status = status;
}

/* bufferMapSync(instance, buffer, mode, offset, size) */
static napi_value doe_buffer_map_sync(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUBuffer buf = unwrap_ptr(env, _args[1]);
    uint32_t mode;
    napi_get_value_uint32(env, _args[2], &mode);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[3], &offset_i);
    napi_get_value_int64(env, _args[4], &size_i);

    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = 1, /* WaitAnyOnly */
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode,
        (size_t)offset_i, (size_t)size_i, cb_info);

    WGPUFutureWaitInfo wait_info = { .future = future, .completed = 0 };
    uint32_t wait_status = pfn_wgpuInstanceWaitAny(
        inst, 1, &wait_info, (uint64_t)5000000000ULL);

    if (wait_status != 1 || result.status != 1)
        NAPI_THROW(env, "bufferMapAsync failed");

    napi_value ok;
    napi_get_boolean(env, true, &ok);
    return ok;
}

/* bufferGetMappedRange(buffer, offset, size) → ArrayBuffer */
static napi_value doe_buffer_get_mapped_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[1], &offset_i);
    napi_get_value_int64(env, _args[2], &size_i);

    const void* data = pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!data) NAPI_THROW(env, "getMappedRange returned NULL");

    /* Copy native data into a JS ArrayBuffer */
    void* ab_data = NULL;
    napi_value ab;
    napi_create_arraybuffer(env, (size_t)size_i, &ab_data, &ab);
    memcpy(ab_data, data, (size_t)size_i);
    return ab;
}

/* ================================================================
 * Shader Module
 * ================================================================ */

static napi_value doe_create_shader_module(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    /* _args[1] is the WGSL source code string */
    size_t code_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &code_len);
    char* code = (char*)malloc(code_len + 1);
    napi_get_value_string_utf8(env, _args[1], code, code_len + 1, &code_len);

    WGPUShaderSourceWGSL wgsl_source = {
        .chain = { .next = NULL, .sType = 0x00000002 /* ShaderSourceWGSL */ },
        .code = { .data = code, .length = code_len },
    };
    WGPUShaderModuleDescriptor desc = {
        .nextInChain = (void*)&wgsl_source,
        .label = { .data = NULL, .length = 0 },
    };

    WGPUShaderModule mod = pfn_wgpuDeviceCreateShaderModule(device, &desc);
    free(code);
    if (!mod) NAPI_THROW(env, "createShaderModule failed");
    return wrap_ptr(env, mod);
}

static napi_value doe_shader_module_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* mod = unwrap_ptr(env, _args[0]);
    if (mod) pfn_wgpuShaderModuleRelease(mod);
    return NULL;
}

/* ================================================================
 * Compute Pipeline
 * createComputePipeline(device, shaderModule, entryPoint, pipelineLayout?)
 * ================================================================ */

static napi_value doe_create_compute_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    WGPUShaderModule shader = unwrap_ptr(env, _args[1]);
    if (!device || !shader) NAPI_THROW(env, "Invalid device or shader");

    size_t ep_len = 0;
    napi_get_value_string_utf8(env, _args[2], NULL, 0, &ep_len);
    char* ep = (char*)malloc(ep_len + 1);
    napi_get_value_string_utf8(env, _args[2], ep, ep_len + 1, &ep_len);

    /* pipelineLayout can be null (auto layout) */
    napi_valuetype layout_type;
    napi_typeof(env, _args[3], &layout_type);
    void* layout = NULL;
    if (layout_type == napi_external) layout = unwrap_ptr(env, _args[3]);

    WGPUComputePipelineDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.layout = layout;
    desc.compute.module = shader;
    desc.compute.entryPoint.data = ep;
    desc.compute.entryPoint.length = ep_len;

    WGPUComputePipeline pipeline = pfn_wgpuDeviceCreateComputePipeline(device, &desc);
    free(ep);
    if (!pipeline) NAPI_THROW(env, "createComputePipeline failed");
    return wrap_ptr(env, pipeline);
}

static napi_value doe_compute_pipeline_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuComputePipelineRelease(p);
    return NULL;
}

/* ================================================================
 * Bind Group Layout
 * createBindGroupLayout(device, entries[])
 * Each entry: { binding, visibility, buffer?: { type }, storageTexture?: { ... } }
 * ================================================================ */

static uint32_t buffer_binding_type_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0x00000001; /* Undefined */
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "uniform") == 0) return 0x00000002;
    if (strcmp(buf, "storage") == 0) return 0x00000003;
    if (strcmp(buf, "read-only-storage") == 0) return 0x00000004;
    return 0x00000001;
}

static napi_value doe_create_bind_group_layout(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    uint32_t entry_count = 0;
    napi_get_array_length(env, _args[1], &entry_count);

    WGPUBindGroupLayoutEntry* entries = (WGPUBindGroupLayoutEntry*)calloc(
        entry_count, sizeof(WGPUBindGroupLayoutEntry));

    for (uint32_t i = 0; i < entry_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[1], i, &elem);

        entries[i].binding = get_uint32_prop(env, elem, "binding");
        entries[i].visibility = (uint64_t)get_int64_prop(env, elem, "visibility");

        if (has_prop(env, elem, "buffer") && prop_type(env, elem, "buffer") == napi_object) {
            napi_value buf_obj = get_prop(env, elem, "buffer");
            entries[i].buffer.type = buffer_binding_type_from_string(
                env, get_prop(env, buf_obj, "type"));
            if (has_prop(env, buf_obj, "hasDynamicOffset"))
                entries[i].buffer.hasDynamicOffset = get_bool_prop(env, buf_obj, "hasDynamicOffset") ? 1 : 0;
            if (has_prop(env, buf_obj, "minBindingSize"))
                entries[i].buffer.minBindingSize = (uint64_t)get_int64_prop(env, buf_obj, "minBindingSize");
        }

        if (has_prop(env, elem, "storageTexture") && prop_type(env, elem, "storageTexture") == napi_object) {
            napi_value st_obj = get_prop(env, elem, "storageTexture");
            entries[i].storageTexture.access = get_uint32_prop(env, st_obj, "access");
            entries[i].storageTexture.format = get_uint32_prop(env, st_obj, "format");
            entries[i].storageTexture.viewDimension = get_uint32_prop(env, st_obj, "viewDimension");
        }
    }

    WGPUBindGroupLayoutDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
        .entryCount = entry_count,
        .entries = entries,
    };

    WGPUBindGroupLayout layout = pfn_wgpuDeviceCreateBindGroupLayout(device, &desc);
    free(entries);
    if (!layout) NAPI_THROW(env, "createBindGroupLayout failed");
    return wrap_ptr(env, layout);
}

static napi_value doe_bind_group_layout_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuBindGroupLayoutRelease(p);
    return NULL;
}

/* ================================================================
 * Bind Group
 * createBindGroup(device, layout, entries[])
 * Each entry: { binding, buffer, offset?, size? }
 * ================================================================ */

static napi_value doe_create_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    WGPUBindGroupLayout layout = unwrap_ptr(env, _args[1]);
    if (!device || !layout) NAPI_THROW(env, "Invalid device or layout");

    uint32_t entry_count = 0;
    napi_get_array_length(env, _args[2], &entry_count);

    WGPUBindGroupEntry* entries = (WGPUBindGroupEntry*)calloc(
        entry_count, sizeof(WGPUBindGroupEntry));

    for (uint32_t i = 0; i < entry_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[2], i, &elem);

        entries[i].binding = get_uint32_prop(env, elem, "binding");

        if (has_prop(env, elem, "buffer") && prop_type(env, elem, "buffer") == napi_external)
            entries[i].buffer = unwrap_ptr(env, get_prop(env, elem, "buffer"));

        if (has_prop(env, elem, "offset"))
            entries[i].offset = (uint64_t)get_int64_prop(env, elem, "offset");

        entries[i].size = WGPU_WHOLE_SIZE;
        if (has_prop(env, elem, "size"))
            entries[i].size = (uint64_t)get_int64_prop(env, elem, "size");
    }

    WGPUBindGroupDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
        .layout = layout,
        .entryCount = entry_count,
        .entries = entries,
    };

    WGPUBindGroup group = pfn_wgpuDeviceCreateBindGroup(device, &desc);
    free(entries);
    if (!group) NAPI_THROW(env, "createBindGroup failed");
    return wrap_ptr(env, group);
}

static napi_value doe_bind_group_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuBindGroupRelease(p);
    return NULL;
}

/* ================================================================
 * Pipeline Layout
 * createPipelineLayout(device, bindGroupLayouts[])
 * ================================================================ */

static napi_value doe_create_pipeline_layout(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    uint32_t layout_count = 0;
    napi_get_array_length(env, _args[1], &layout_count);

    WGPUBindGroupLayout* layouts = (WGPUBindGroupLayout*)calloc(
        layout_count, sizeof(WGPUBindGroupLayout));
    for (uint32_t i = 0; i < layout_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[1], i, &elem);
        layouts[i] = unwrap_ptr(env, elem);
    }

    WGPUPipelineLayoutDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
        .bindGroupLayoutCount = layout_count,
        .bindGroupLayouts = layouts,
        .immediateSize = 0,
    };

    WGPUPipelineLayout pl = pfn_wgpuDeviceCreatePipelineLayout(device, &desc);
    free(layouts);
    if (!pl) NAPI_THROW(env, "createPipelineLayout failed");
    return wrap_ptr(env, pl);
}

static napi_value doe_pipeline_layout_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuPipelineLayoutRelease(p);
    return NULL;
}

/* ================================================================
 * Command Encoder
 * ================================================================ */

static napi_value doe_create_command_encoder(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    WGPUCommandEncoderDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
    };
    WGPUCommandEncoder enc = pfn_wgpuDeviceCreateCommandEncoder(device, &desc);
    if (!enc) NAPI_THROW(env, "createCommandEncoder failed");
    return wrap_ptr(env, enc);
}

static napi_value doe_command_encoder_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuCommandEncoderRelease(p);
    return NULL;
}

static napi_value doe_command_encoder_copy_buffer_to_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUBuffer src = unwrap_ptr(env, _args[1]);
    int64_t src_offset; napi_get_value_int64(env, _args[2], &src_offset);
    WGPUBuffer dst = unwrap_ptr(env, _args[3]);
    int64_t dst_offset; napi_get_value_int64(env, _args[4], &dst_offset);
    int64_t size; napi_get_value_int64(env, _args[5], &size);

    pfn_wgpuCommandEncoderCopyBufferToBuffer(enc, src, (uint64_t)src_offset,
        dst, (uint64_t)dst_offset, (uint64_t)size);
    return NULL;
}

static napi_value doe_command_encoder_finish(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");

    WGPUCommandBufferDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
    };
    WGPUCommandBuffer cmd = pfn_wgpuCommandEncoderFinish(enc, &desc);
    if (!cmd) NAPI_THROW(env, "commandEncoderFinish failed");
    return wrap_ptr(env, cmd);
}

static napi_value doe_command_buffer_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuCommandBufferRelease(p);
    return NULL;
}

/* ================================================================
 * Compute Pass
 * ================================================================ */

static napi_value doe_begin_compute_pass(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");

    WGPUComputePassDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
        .timestampWrites = NULL,
    };
    WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(enc, &desc);
    if (!pass) NAPI_THROW(env, "beginComputePass failed");
    return wrap_ptr(env, pass);
}

static napi_value doe_compute_pass_set_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    pfn_wgpuComputePassEncoderSetPipeline(
        unwrap_ptr(env, _args[0]), unwrap_ptr(env, _args[1]));
    return NULL;
}

static napi_value doe_compute_pass_set_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPUComputePassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t index; napi_get_value_uint32(env, _args[1], &index);
    WGPUBindGroup group = unwrap_ptr(env, _args[2]);
    pfn_wgpuComputePassEncoderSetBindGroup(pass, index, group, 0, NULL);
    return NULL;
}

static napi_value doe_compute_pass_dispatch(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    WGPUComputePassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t x, y, z;
    napi_get_value_uint32(env, _args[1], &x);
    napi_get_value_uint32(env, _args[2], &y);
    napi_get_value_uint32(env, _args[3], &z);
    pfn_wgpuComputePassEncoderDispatchWorkgroups(pass, x, y, z);
    return NULL;
}

static napi_value doe_compute_pass_end(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    pfn_wgpuComputePassEncoderEnd(unwrap_ptr(env, _args[0]));
    return NULL;
}

static napi_value doe_compute_pass_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuComputePassEncoderRelease(p);
    return NULL;
}

/* ================================================================
 * Queue
 * ================================================================ */

static napi_value doe_queue_submit(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    WGPUQueue queue = unwrap_ptr(env, _args[0]);
    if (!queue) NAPI_THROW(env, "Invalid queue");

    uint32_t cmd_count = 0;
    napi_get_array_length(env, _args[1], &cmd_count);

    WGPUCommandBuffer* cmds = (WGPUCommandBuffer*)calloc(
        cmd_count, sizeof(WGPUCommandBuffer));
    for (uint32_t i = 0; i < cmd_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[1], i, &elem);
        cmds[i] = unwrap_ptr(env, elem);
    }

    pfn_wgpuQueueSubmit(queue, cmd_count, cmds);
    free(cmds);
    return NULL;
}

/* queueWriteBuffer(queue, buffer, offset, typedArray) */
static napi_value doe_queue_write_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    WGPUQueue queue = unwrap_ptr(env, _args[0]);
    WGPUBuffer buf = unwrap_ptr(env, _args[1]);
    int64_t offset; napi_get_value_int64(env, _args[2], &offset);

    void* data = NULL;
    size_t byte_length = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, _args[3], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length;
        napi_value ab;
        size_t byte_offset;
        napi_get_typedarray_info(env, _args[3], &ta_type, &ta_length, &data, &ab, &byte_offset);
        /* Get byte length from the arraybuffer */
        napi_get_arraybuffer_info(env, ab, NULL, &byte_length);
        byte_length = byte_length - byte_offset;
        data = (char*)data;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, _args[3], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, _args[3], &data, &byte_length);
        } else {
            bool is_buffer = false;
            napi_is_buffer(env, _args[3], &is_buffer);
            if (is_buffer) {
                napi_get_buffer_info(env, _args[3], &data, &byte_length);
            } else {
                NAPI_THROW(env, "queueWriteBuffer: data must be TypedArray, ArrayBuffer, or Buffer");
            }
        }
    }

    pfn_wgpuQueueWriteBuffer(queue, buf, (uint64_t)offset, data, byte_length);
    return NULL;
}

static napi_value doe_queue_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuQueueRelease(p);
    return NULL;
}

/* ================================================================
 * Module initialization
 * ================================================================ */

#define EXPORT_FN(name, fn) { name, 0, fn, 0, 0, 0, napi_default, 0 }

static napi_value doe_module_init(napi_env env, napi_value exports) {
    napi_property_descriptor descriptors[] = {
        EXPORT_FN("loadLibrary", doe_load_library),
        EXPORT_FN("createInstance", doe_create_instance),
        EXPORT_FN("instanceRelease", doe_instance_release),
        EXPORT_FN("requestAdapter", doe_request_adapter),
        EXPORT_FN("adapterRelease", doe_adapter_release),
        EXPORT_FN("requestDevice", doe_request_device),
        EXPORT_FN("deviceRelease", doe_device_release),
        EXPORT_FN("deviceGetQueue", doe_device_get_queue),
        EXPORT_FN("createBuffer", doe_create_buffer),
        EXPORT_FN("bufferRelease", doe_buffer_release),
        EXPORT_FN("bufferUnmap", doe_buffer_unmap),
        EXPORT_FN("bufferMapSync", doe_buffer_map_sync),
        EXPORT_FN("bufferGetMappedRange", doe_buffer_get_mapped_range),
        EXPORT_FN("createShaderModule", doe_create_shader_module),
        EXPORT_FN("shaderModuleRelease", doe_shader_module_release),
        EXPORT_FN("createComputePipeline", doe_create_compute_pipeline),
        EXPORT_FN("computePipelineRelease", doe_compute_pipeline_release),
        EXPORT_FN("createBindGroupLayout", doe_create_bind_group_layout),
        EXPORT_FN("bindGroupLayoutRelease", doe_bind_group_layout_release),
        EXPORT_FN("createBindGroup", doe_create_bind_group),
        EXPORT_FN("bindGroupRelease", doe_bind_group_release),
        EXPORT_FN("createPipelineLayout", doe_create_pipeline_layout),
        EXPORT_FN("pipelineLayoutRelease", doe_pipeline_layout_release),
        EXPORT_FN("createCommandEncoder", doe_create_command_encoder),
        EXPORT_FN("commandEncoderRelease", doe_command_encoder_release),
        EXPORT_FN("commandEncoderCopyBufferToBuffer", doe_command_encoder_copy_buffer_to_buffer),
        EXPORT_FN("commandEncoderFinish", doe_command_encoder_finish),
        EXPORT_FN("commandBufferRelease", doe_command_buffer_release),
        EXPORT_FN("beginComputePass", doe_begin_compute_pass),
        EXPORT_FN("computePassSetPipeline", doe_compute_pass_set_pipeline),
        EXPORT_FN("computePassSetBindGroup", doe_compute_pass_set_bind_group),
        EXPORT_FN("computePassDispatchWorkgroups", doe_compute_pass_dispatch),
        EXPORT_FN("computePassEnd", doe_compute_pass_end),
        EXPORT_FN("computePassRelease", doe_compute_pass_release),
        EXPORT_FN("queueSubmit", doe_queue_submit),
        EXPORT_FN("queueWriteBuffer", doe_queue_write_buffer),
        EXPORT_FN("queueRelease", doe_queue_release),
    };

    size_t count = sizeof(descriptors) / sizeof(descriptors[0]);
    napi_define_properties(env, exports, count, descriptors);
    return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, doe_module_init)
