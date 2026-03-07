/*
 * doe_napi.c — N-API binding for libwebgpu_doe (Doe WebGPU runtime).
 *
 * Loads the Doe shared library at runtime via dlopen and exposes the core
 * WebGPU compute surface to JavaScript through Node.js N-API.
 *
 * All WGPUInstance/Adapter/Device/Buffer/etc. handles are wrapped as
 * napi_external values. Struct descriptors are marshaled from JS objects.
 * Async operations (requestAdapter, requestDevice, bufferMapAsync, queue flush)
 * are bridged into synchronous Node calls by pumping wgpuInstanceProcessEvents
 * with a bounded timeout.
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
#include <time.h>
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
typedef void* WGPURenderPassEncoder;
typedef uint64_t WGPUFlags;
typedef uint32_t WGPUBool;

#define WGPU_STRLEN SIZE_MAX
#define WGPU_WHOLE_SIZE UINT64_MAX
#define WGPU_STYPE_SHADER_SOURCE_WGSL 0x00000002
#define WGPU_WAIT_STATUS_SUCCESS 1
#define WGPU_MAP_ASYNC_STATUS_SUCCESS 1
#define WGPU_REQUEST_STATUS_SUCCESS 1
#define WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS 2
#define DOE_DEFAULT_TIMEOUT_NS 2000000000ULL
#define DOE_WAIT_SLICE_NS 1000ULL

typedef struct { uint64_t id; } WGPUFuture;
typedef struct { const char* data; size_t length; } WGPUStringView;
typedef struct { WGPUFuture future; WGPUBool completed; } WGPUFutureWaitInfo;

typedef struct { void* next; uint32_t sType; } WGPUChainedStruct;

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

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t depthOrArrayLayers;
} WGPUExtent3D;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    uint64_t usage;
    uint32_t dimension;
    WGPUExtent3D size;
    uint32_t format;
    uint32_t mipLevelCount;
    uint32_t sampleCount;
    size_t viewFormatCount;
    const uint32_t* viewFormats;
} WGPUTextureDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    uint32_t format;
    uint32_t dimension;
    uint32_t baseMipLevel;
    uint32_t mipLevelCount;
    uint32_t baseArrayLayer;
    uint32_t arrayLayerCount;
    uint32_t aspect;
    uint64_t usage;
} WGPUTextureViewDescriptor;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    uint32_t addressModeU;
    uint32_t addressModeV;
    uint32_t addressModeW;
    uint32_t magFilter;
    uint32_t minFilter;
    uint32_t mipmapFilter;
    float lodMinClamp;
    float lodMaxClamp;
    uint32_t compare;
    uint16_t maxAnisotropy;
} WGPUSamplerDescriptor;

typedef struct { double r; double g; double b; double a; } WGPUColor;

typedef struct {
    void* nextInChain;
    WGPUTextureView view;
    uint32_t depthSlice;
    WGPUTextureView resolveTarget;
    uint32_t loadOp;
    uint32_t storeOp;
    WGPUColor clearValue;
} WGPURenderPassColorAttachment;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    size_t colorAttachmentCount;
    const WGPURenderPassColorAttachment* colorAttachments;
    void* depthStencilAttachment;
    WGPUQuerySet occlusionQuerySet;
    void* timestampWrites;
} WGPURenderPassDescriptor;

typedef struct {
    void*    nextInChain;
    uint32_t maxTextureDimension1D;
    uint32_t maxTextureDimension2D;
    uint32_t maxTextureDimension3D;
    uint32_t maxTextureArrayLayers;
    uint32_t maxBindGroups;
    uint32_t maxBindGroupsPlusVertexBuffers;
    uint32_t maxBindingsPerBindGroup;
    uint32_t maxDynamicUniformBuffersPerPipelineLayout;
    uint32_t maxDynamicStorageBuffersPerPipelineLayout;
    uint32_t maxSampledTexturesPerShaderStage;
    uint32_t maxSamplersPerShaderStage;
    uint32_t maxStorageBuffersPerShaderStage;
    uint32_t maxStorageTexturesPerShaderStage;
    uint32_t maxUniformBuffersPerShaderStage;
    uint64_t maxUniformBufferBindingSize;
    uint64_t maxStorageBufferBindingSize;
    uint32_t minUniformBufferOffsetAlignment;
    uint32_t minStorageBufferOffsetAlignment;
    uint32_t maxVertexBuffers;
    uint64_t maxBufferSize;
    uint32_t maxVertexAttributes;
    uint32_t maxVertexBufferArrayStride;
    uint32_t maxInterStageShaderVariables;
    uint32_t maxColorAttachments;
    uint32_t maxColorAttachmentBytesPerSample;
    uint32_t maxComputeWorkgroupStorageSize;
    uint32_t maxComputeInvocationsPerWorkgroup;
    uint32_t maxComputeWorkgroupSizeX;
    uint32_t maxComputeWorkgroupSizeY;
    uint32_t maxComputeWorkgroupSizeZ;
    uint32_t maxComputeWorkgroupsPerDimension;
    uint32_t maxImmediateSize;
} WGPULimits;

#define WGPU_FEATURE_SHADER_F16 0x0000000B

/* Callback types */
typedef void (*WGPURequestAdapterCallback)(
    uint32_t status, WGPUAdapter adapter, WGPUStringView message,
    void* userdata1, void* userdata2);

typedef void (*WGPURequestDeviceCallback)(
    uint32_t status, WGPUDevice device, WGPUStringView message,
    void* userdata1, void* userdata2);

typedef struct {
    void* nextInChain;
    uint32_t mode;
    WGPURequestAdapterCallback callback;
    void* userdata1;
    void* userdata2;
} WGPURequestAdapterCallbackInfo;

typedef struct {
    void* nextInChain;
    uint32_t mode;
    WGPURequestDeviceCallback callback;
    void* userdata1;
    void* userdata2;
} WGPURequestDeviceCallbackInfo;

typedef void (*WGPUBufferMapCallback)(
    uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2);

typedef void (*WGPUQueueWorkDoneCallback)(
    uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2);

typedef struct {
    void* nextInChain;
    uint32_t mode;
    WGPUQueueWorkDoneCallback callback;
    void* userdata1;
    void* userdata2;
} WGPUQueueWorkDoneCallbackInfo;

#define WGPU_CALLBACK_MODE_WAIT_ANY_ONLY 1
#define WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS 1

/* ================================================================
 * Function pointer types and global storage
 * ================================================================ */

#define DECL_PFN(ret, name, params) typedef ret (*PFN_##name) params; static PFN_##name pfn_##name = NULL

DECL_PFN(WGPUInstance, wgpuCreateInstance, (const void*));
DECL_PFN(void, wgpuInstanceRelease, (WGPUInstance));
DECL_PFN(WGPUFuture, wgpuInstanceRequestAdapter, (WGPUInstance, const void*, WGPURequestAdapterCallbackInfo));
DECL_PFN(uint32_t, wgpuInstanceWaitAny, (WGPUInstance, size_t, WGPUFutureWaitInfo*, uint64_t));
DECL_PFN(void, wgpuInstanceProcessEvents, (WGPUInstance));
DECL_PFN(void, wgpuAdapterRelease, (WGPUAdapter));
DECL_PFN(WGPUBool, wgpuAdapterHasFeature, (WGPUAdapter, uint32_t));
DECL_PFN(WGPUFuture, wgpuAdapterRequestDevice, (WGPUAdapter, const void*, WGPURequestDeviceCallbackInfo));
DECL_PFN(void, wgpuDeviceRelease, (WGPUDevice));
DECL_PFN(WGPUBool, wgpuDeviceHasFeature, (WGPUDevice, uint32_t));
DECL_PFN(WGPUQueue, wgpuDeviceGetQueue, (WGPUDevice));
DECL_PFN(WGPUBuffer, wgpuDeviceCreateBuffer, (WGPUDevice, const WGPUBufferDescriptor*));
DECL_PFN(WGPUShaderModule, wgpuDeviceCreateShaderModule, (WGPUDevice, const WGPUShaderModuleDescriptor*));
DECL_PFN(void, wgpuShaderModuleRelease, (WGPUShaderModule));
DECL_PFN(WGPUComputePipeline, wgpuDeviceCreateComputePipeline, (WGPUDevice, const WGPUComputePipelineDescriptor*));
DECL_PFN(void, wgpuComputePipelineRelease, (WGPUComputePipeline));
DECL_PFN(WGPUBindGroupLayout, wgpuComputePipelineGetBindGroupLayout, (WGPUComputePipeline, uint32_t));
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
DECL_PFN(void, wgpuComputePassEncoderDispatchWorkgroupsIndirect, (WGPUComputePassEncoder, WGPUBuffer, uint64_t));
DECL_PFN(void, wgpuComputePassEncoderEnd, (WGPUComputePassEncoder));
DECL_PFN(void, wgpuComputePassEncoderRelease, (WGPUComputePassEncoder));
DECL_PFN(void, wgpuQueueSubmit, (WGPUQueue, size_t, const WGPUCommandBuffer*));
DECL_PFN(void, wgpuQueueWriteBuffer, (WGPUQueue, WGPUBuffer, uint64_t, const void*, size_t));
DECL_PFN(WGPUFuture, wgpuQueueOnSubmittedWorkDone, (WGPUQueue, WGPUQueueWorkDoneCallbackInfo));
DECL_PFN(void, wgpuQueueRelease, (WGPUQueue));
DECL_PFN(void, wgpuBufferRelease, (WGPUBuffer));
DECL_PFN(void, wgpuBufferUnmap, (WGPUBuffer));
DECL_PFN(const void*, wgpuBufferGetConstMappedRange, (WGPUBuffer, size_t, size_t));
DECL_PFN(void*, wgpuBufferGetMappedRange, (WGPUBuffer, size_t, size_t));
DECL_PFN(void, wgpuCommandBufferRelease, (WGPUCommandBuffer));
DECL_PFN(WGPUTexture, wgpuDeviceCreateTexture, (WGPUDevice, const WGPUTextureDescriptor*));
DECL_PFN(WGPUTextureView, wgpuTextureCreateView, (WGPUTexture, const WGPUTextureViewDescriptor*));
DECL_PFN(void, wgpuTextureRelease, (WGPUTexture));
DECL_PFN(void, wgpuTextureViewRelease, (WGPUTextureView));
DECL_PFN(WGPUSampler, wgpuDeviceCreateSampler, (WGPUDevice, const WGPUSamplerDescriptor*));
DECL_PFN(void, wgpuSamplerRelease, (WGPUSampler));
DECL_PFN(WGPURenderPipeline, wgpuDeviceCreateRenderPipeline, (WGPUDevice, const void*));
DECL_PFN(void, wgpuRenderPipelineRelease, (WGPURenderPipeline));
DECL_PFN(WGPURenderPassEncoder, wgpuCommandEncoderBeginRenderPass, (WGPUCommandEncoder, const WGPURenderPassDescriptor*));
DECL_PFN(void, wgpuRenderPassEncoderSetPipeline, (WGPURenderPassEncoder, WGPURenderPipeline));
DECL_PFN(void, wgpuRenderPassEncoderDraw, (WGPURenderPassEncoder, uint32_t, uint32_t, uint32_t, uint32_t));
DECL_PFN(void, wgpuRenderPassEncoderEnd, (WGPURenderPassEncoder));
DECL_PFN(void, wgpuRenderPassEncoderRelease, (WGPURenderPassEncoder));
DECL_PFN(uint32_t, wgpuDeviceGetLimits, (WGPUDevice, void*));

/* Flat helpers are optional. When absent, the addon assembles the callback-info
 * structs directly and calls the standard WebGPU request entrypoints. */
DECL_PFN(WGPUFuture, doeRequestAdapterFlat, (WGPUInstance, const void*, uint32_t, WGPURequestAdapterCallback, void*, void*));
DECL_PFN(WGPUFuture, doeRequestDeviceFlat, (WGPUAdapter, const void*, uint32_t, WGPURequestDeviceCallback, void*, void*));
DECL_PFN(void, doeNativeQueueFlush, (void*));
DECL_PFN(void, doeNativeComputeDispatchFlush, (void*, void*, void**, uint32_t, uint32_t, uint32_t, uint32_t, void*, uint64_t, void*, uint64_t, uint64_t));
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

static uint64_t monotonic_now_ns(void) {
#ifdef _WIN32
    static LARGE_INTEGER frequency = {0};
    LARGE_INTEGER counter;
    if (frequency.QuadPart == 0) QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&counter);
    return (uint64_t)((counter.QuadPart * 1000000000ULL) / frequency.QuadPart);
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((uint64_t)ts.tv_sec * 1000000000ULL) + (uint64_t)ts.tv_nsec;
#endif
}

static void wait_slice(void) {
#ifdef _WIN32
    Sleep(0);
#else
    struct timespec req = {0};
    req.tv_nsec = DOE_WAIT_SLICE_NS;
    nanosleep(&req, NULL);
#endif
}

static int process_events_until(WGPUInstance inst, volatile uint32_t* done, uint64_t timeout_ns) {
    uint64_t start_ns = monotonic_now_ns();
    uint32_t spins = 0;
    while (!*done) {
        pfn_wgpuInstanceProcessEvents(inst);
        if (monotonic_now_ns() - start_ns >= timeout_ns) return 0;
        spins += 1;
        if (spins > 1000) wait_slice();
    }
    return 1;
}

/* ================================================================
 * N-API utility helpers
 * ================================================================ */

#define NAPI_THROW(env, msg) do { napi_throw_error(env, NULL, msg); return NULL; } while(0)
#define MAX_NAPI_ARGS 8
#define NAPI_ASSERT_ARGC(env, info, n) \
    size_t _argc = (n); napi_value _args[MAX_NAPI_ARGS]; \
    if ((n) > MAX_NAPI_ARGS) NAPI_THROW(env, "too many args"); \
    if (napi_get_cb_info(env, info, &_argc, _args, NULL, NULL) != napi_ok) NAPI_THROW(env, "napi_get_cb_info failed")
#define CHECK_LIB_LOADED(env) do { if (!g_lib) NAPI_THROW(env, "Library not loaded"); } while(0)

static void* unwrap_ptr(napi_env env, napi_value val) {
    void* ptr = NULL;
    napi_get_value_external(env, val, &ptr);
    return ptr;
}

/* Release callback for GC'd externals. Logs but cannot release because we
 * don't know the handle type. Prevents silent leaks in long-lived processes. */
static void handle_Release_hint(napi_env env, void* data, void* hint) {
    (void)env; (void)hint;
    /* If data is non-null, the JS side forgot to call release().
     * We cannot safely call the typed release here without knowing the type,
     * so this is intentionally a no-op — but the destructor being non-NULL
     * means napi will not leak the ref-tracking entry. */
    (void)data;
}

static napi_value wrap_ptr(napi_env env, void* ptr) {
    napi_value result;
    if (napi_create_external(env, ptr, handle_Release_hint, NULL, &result) != napi_ok) return NULL;
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
    if (!g_lib) NAPI_THROW(env, "Failed to load libwebgpu_doe");

    LOAD_SYM(wgpuCreateInstance);
    LOAD_SYM(wgpuInstanceRelease);
    LOAD_SYM(wgpuInstanceRequestAdapter);
    LOAD_SYM(wgpuInstanceWaitAny);
    LOAD_SYM(wgpuInstanceProcessEvents);
    LOAD_SYM(wgpuAdapterRelease);
    LOAD_SYM(wgpuAdapterHasFeature);
    LOAD_SYM(wgpuAdapterRequestDevice);
    LOAD_SYM(wgpuDeviceRelease);
    LOAD_SYM(wgpuDeviceHasFeature);
    LOAD_SYM(wgpuDeviceGetQueue);
    LOAD_SYM(wgpuDeviceCreateBuffer);
    LOAD_SYM(wgpuDeviceCreateShaderModule);
    LOAD_SYM(wgpuShaderModuleRelease);
    LOAD_SYM(wgpuDeviceCreateComputePipeline);
    LOAD_SYM(wgpuComputePipelineRelease);
    LOAD_SYM(wgpuComputePipelineGetBindGroupLayout);
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
    LOAD_SYM(wgpuComputePassEncoderDispatchWorkgroupsIndirect);
    LOAD_SYM(wgpuComputePassEncoderEnd);
    LOAD_SYM(wgpuComputePassEncoderRelease);
    LOAD_SYM(wgpuQueueSubmit);
    LOAD_SYM(wgpuQueueWriteBuffer);
    LOAD_SYM(wgpuQueueOnSubmittedWorkDone);
    LOAD_SYM(wgpuQueueRelease);
    LOAD_SYM(wgpuBufferRelease);
    LOAD_SYM(wgpuBufferUnmap);
    LOAD_SYM(wgpuBufferGetConstMappedRange);
    LOAD_SYM(wgpuBufferGetMappedRange);
    LOAD_SYM(wgpuCommandBufferRelease);
    LOAD_SYM(wgpuDeviceCreateTexture);
    LOAD_SYM(wgpuTextureCreateView);
    LOAD_SYM(wgpuTextureRelease);
    LOAD_SYM(wgpuTextureViewRelease);
    LOAD_SYM(wgpuDeviceCreateSampler);
    LOAD_SYM(wgpuSamplerRelease);
    LOAD_SYM(wgpuDeviceCreateRenderPipeline);
    LOAD_SYM(wgpuRenderPipelineRelease);
    LOAD_SYM(wgpuCommandEncoderBeginRenderPass);
    LOAD_SYM(wgpuRenderPassEncoderSetPipeline);
    LOAD_SYM(wgpuRenderPassEncoderDraw);
    LOAD_SYM(wgpuRenderPassEncoderEnd);
    LOAD_SYM(wgpuRenderPassEncoderRelease);
    LOAD_SYM(wgpuDeviceGetLimits);
    pfn_doeRequestAdapterFlat = (PFN_doeRequestAdapterFlat)LIB_SYM(g_lib, "doeRequestAdapterFlat");
    pfn_doeRequestDeviceFlat = (PFN_doeRequestDeviceFlat)LIB_SYM(g_lib, "doeRequestDeviceFlat");
    pfn_wgpuBufferMapAsync2 = (PFN_wgpuBufferMapAsync2)LIB_SYM(g_lib, "wgpuBufferMapAsync");
    pfn_doeNativeQueueFlush = (PFN_doeNativeQueueFlush)LIB_SYM(g_lib, "doeNativeQueueFlush");
    pfn_doeNativeComputeDispatchFlush = (PFN_doeNativeComputeDispatchFlush)LIB_SYM(g_lib, "doeNativeComputeDispatchFlush");

    /* Validate all critical function pointers were resolved. */
    if (!pfn_wgpuCreateInstance || !pfn_wgpuInstanceRelease || !pfn_wgpuInstanceRequestAdapter ||
        !pfn_wgpuInstanceWaitAny || !pfn_wgpuInstanceProcessEvents ||
        !pfn_wgpuAdapterRequestDevice ||
        !pfn_wgpuDeviceGetQueue || !pfn_wgpuDeviceCreateBuffer ||
        !pfn_wgpuDeviceCreateShaderModule || !pfn_wgpuDeviceCreateComputePipeline ||
        !pfn_wgpuDeviceCreateCommandEncoder || !pfn_wgpuCommandEncoderBeginComputePass ||
        !pfn_wgpuCommandEncoderFinish || !pfn_wgpuQueueSubmit ||
        !pfn_wgpuQueueOnSubmittedWorkDone ||
        !pfn_wgpuBufferMapAsync2) {
        LIB_CLOSE(g_lib);
        g_lib = NULL;
        NAPI_THROW(env, "Failed to resolve required symbols from libwebgpu_doe");
    }

    napi_value result;
    napi_get_boolean(env, true, &result);
    return result;
}

/* ================================================================
 * Instance
 * ================================================================ */

static napi_value doe_create_instance(napi_env env, napi_callback_info info) {
    (void)info;
    CHECK_LIB_LOADED(env);
    /* Doe ignores the descriptor — pass NULL for clarity. */
    WGPUInstance inst = pfn_wgpuCreateInstance(NULL);
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
 * Adapter (synchronous requestAdapter via callback + processEvents)
 * ================================================================ */

typedef struct {
    uint32_t status;
    WGPUAdapter adapter;
    uint32_t done;
} AdapterRequestResult;

static void adapter_callback(uint32_t status, WGPUAdapter adapter,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)message; (void)userdata2;
    AdapterRequestResult* r = (AdapterRequestResult*)userdata1;
    r->status = status;
    r->adapter = adapter;
    r->done = 1;
}

static napi_value doe_request_adapter(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    if (!inst) NAPI_THROW(env, "Invalid instance");

    AdapterRequestResult result = {0, NULL, 0};
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
    if (!process_events_until(inst, &result.done, DOE_DEFAULT_TIMEOUT_NS) ||
        result.status != WGPU_REQUEST_STATUS_SUCCESS || !result.adapter)
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
 * Device (synchronous requestDevice via callback + processEvents)
 * ================================================================ */

typedef struct {
    uint32_t status;
    WGPUDevice device;
    uint32_t done;
} DeviceRequestResult;

static void device_callback(uint32_t status, WGPUDevice device,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)message; (void)userdata2;
    DeviceRequestResult* r = (DeviceRequestResult*)userdata1;
    r->status = status;
    r->device = device;
    r->done = 1;
}

static napi_value doe_request_device(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUAdapter adapter = unwrap_ptr(env, _args[1]);
    if (!inst || !adapter) NAPI_THROW(env, "Invalid instance or adapter");

    DeviceRequestResult result = {0, NULL, 0};
    WGPUFuture future;
    if (pfn_doeRequestDeviceFlat) {
        future = pfn_doeRequestDeviceFlat(
            adapter, NULL, WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS, device_callback, &result, NULL);
    } else {
        const WGPURequestDeviceCallbackInfo callback_info = {
            .nextInChain = NULL,
            .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
            .callback = device_callback,
            .userdata1 = &result,
            .userdata2 = NULL,
        };
        future = pfn_wgpuAdapterRequestDevice(adapter, NULL, callback_info);
    }
    if (future.id == 0) NAPI_THROW(env, "requestDevice future unavailable");
    if (!process_events_until(inst, &result.done, DOE_DEFAULT_TIMEOUT_NS) ||
        result.status != WGPU_REQUEST_STATUS_SUCCESS || !result.device)
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
    uint32_t done;
} BufferMapResult;

static void buffer_map_callback(uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2) {
    (void)message; (void)userdata2;
    BufferMapResult* r = (BufferMapResult*)userdata1;
    r->status = status;
    r->done = 1;
}

/* bufferMapSync(instance, buffer, mode, offset, size) */
static napi_value doe_buffer_map_sync(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUBuffer buf = unwrap_ptr(env, _args[1]);
    uint32_t mode;
    napi_get_value_uint32(env, _args[2], &mode);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[3], &offset_i);
    napi_get_value_int64(env, _args[4], &size_i);

    BufferMapResult result = {0, 0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode,
        (size_t)offset_i, (size_t)size_i, cb_info);
    if (future.id == 0) NAPI_THROW(env, "bufferMapAsync future unavailable");
    if (!process_events_until(inst, &result.done, DOE_DEFAULT_TIMEOUT_NS) ||
        result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
        NAPI_THROW(env, "bufferMapAsync failed");

    napi_value ok;
    napi_get_boolean(env, true, &ok);
    return ok;
}

/* bufferGetMappedRange(buffer, offset, size) → ArrayBuffer */
static napi_value doe_buffer_get_mapped_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    /* _args[1] is the WGSL source code string */
    size_t code_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &code_len);
    char* code = (char*)malloc(code_len + 1);
    napi_get_value_string_utf8(env, _args[1], code, code_len + 1, &code_len);

    WGPUShaderSourceWGSL wgsl_source = {
        .chain = { .next = NULL, .sType = WGPU_STYPE_SHADER_SOURCE_WGSL },
        .code = { .data = code, .length = code_len },
    };
    WGPUShaderModuleDescriptor desc = {
        .nextInChain = (void*)&wgsl_source,
        .label = { .data = NULL, .length = 0 },
    };

    WGPUShaderModule mod = pfn_wgpuDeviceCreateShaderModule(device, &desc);
    free(code);
    if (!mod) NAPI_THROW(env, "createShaderModule failed (WGSL translation or compilation error — check stderr for details)");
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
    CHECK_LIB_LOADED(env);
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
    if (!pipeline) NAPI_THROW(env, "createComputePipeline failed (shader module invalid or entry point not found — check stderr for details)");
    return wrap_ptr(env, pipeline);
}

static napi_value doe_compute_pipeline_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuComputePipelineRelease(p);
    return NULL;
}

/* computePipelineGetBindGroupLayout(pipeline, groupIndex) → bindGroupLayout */
static napi_value doe_compute_pipeline_get_bind_group_layout(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUComputePipeline pipeline = unwrap_ptr(env, _args[0]);
    if (!pipeline) NAPI_THROW(env, "Invalid pipeline");
    uint32_t index;
    napi_get_value_uint32(env, _args[1], &index);
    WGPUBindGroupLayout layout = pfn_wgpuComputePipelineGetBindGroupLayout(pipeline, index);
    if (!layout) NAPI_THROW(env, "getBindGroupLayout failed");
    return wrap_ptr(env, layout);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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

/* computePassDispatchWorkgroupsIndirect(pass, buffer, offset) */
static napi_value doe_compute_pass_dispatch_indirect(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPUComputePassEncoder pass = unwrap_ptr(env, _args[0]);
    WGPUBuffer buffer = unwrap_ptr(env, _args[1]);
    int64_t offset;
    napi_get_value_int64(env, _args[2], &offset);
    pfn_wgpuComputePassEncoderDispatchWorkgroupsIndirect(pass, buffer, (uint64_t)offset);
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
    CHECK_LIB_LOADED(env);
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
    CHECK_LIB_LOADED(env);
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
        /* Use typed array element count * element size for correct byte length. */
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int8_array: case napi_uint8_array: case napi_uint8_clamped_array: elem_size = 1; break;
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        byte_length = ta_length * elem_size;
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

/* queueFlush(queue) — wait for all pending GPU work to complete.
 * Calls doeNativeQueueFlush directly (semaphore wait on pending command buffer)
 * instead of routing through wgpuQueueOnSubmittedWorkDone (immediate no-op in Doe). */
static napi_value doe_queue_flush(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUQueue queue = unwrap_ptr(env, _args[0]);
    if (!queue) NAPI_THROW(env, "queueFlush requires queue");
    if (!pfn_doeNativeQueueFlush) NAPI_THROW(env, "queueFlush: doeNativeQueueFlush not available");
    pfn_doeNativeQueueFlush(queue);
    return NULL;
}

/* submitBatched(device, queue, commandsArray)
 * Fast path: single dispatch + optional copy → doeNativeComputeDispatchFlush (direct Metal, no Zig command recording).
 * Fallback: standard wgpu path for multi-dispatch or unsupported patterns. */
#define BATCH_MAX_BIND_GROUPS 4
static napi_value doe_submit_batched(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    WGPUQueue queue = unwrap_ptr(env, _args[1]);
    napi_value commands = _args[2];
    if (!device || !queue) NAPI_THROW(env, "submitBatched requires device and queue");

    uint32_t cmd_count = 0;
    napi_get_array_length(env, commands, &cmd_count);
    if (cmd_count == 0) return NULL;

    /* Fast path: exactly 1 dispatch + 0-1 copy, and direct dispatch function available. */
    if (pfn_doeNativeComputeDispatchFlush && cmd_count >= 1 && cmd_count <= 2) {
        napi_value cmd0;
        napi_get_element(env, commands, 0, &cmd0);
        uint32_t t0 = get_uint32_prop(env, cmd0, "t");
        if (t0 == 0) {
            void* pipeline = unwrap_ptr(env, get_prop(env, cmd0, "p"));
            napi_value bgs = get_prop(env, cmd0, "bg");
            uint32_t bg_count = 0;
            napi_get_array_length(env, bgs, &bg_count);
            if (bg_count > BATCH_MAX_BIND_GROUPS) bg_count = BATCH_MAX_BIND_GROUPS;
            void* bg_ptrs[BATCH_MAX_BIND_GROUPS] = {NULL};
            for (uint32_t j = 0; j < bg_count; j++) {
                napi_value bg_val;
                napi_get_element(env, bgs, j, &bg_val);
                bg_ptrs[j] = unwrap_ptr(env, bg_val);
            }
            uint32_t dx = get_uint32_prop(env, cmd0, "x");
            uint32_t dy = get_uint32_prop(env, cmd0, "y");
            uint32_t dz = get_uint32_prop(env, cmd0, "z");

            void* copy_src = NULL; uint64_t copy_src_off = 0;
            void* copy_dst = NULL; uint64_t copy_dst_off = 0;
            uint64_t copy_size = 0;
            if (cmd_count == 2) {
                napi_value cmd1;
                napi_get_element(env, commands, 1, &cmd1);
                if (get_uint32_prop(env, cmd1, "t") == 1) {
                    copy_src = unwrap_ptr(env, get_prop(env, cmd1, "s"));
                    copy_src_off = (uint64_t)get_int64_prop(env, cmd1, "so");
                    copy_dst = unwrap_ptr(env, get_prop(env, cmd1, "d"));
                    copy_dst_off = (uint64_t)get_int64_prop(env, cmd1, "do");
                    copy_size = (uint64_t)get_int64_prop(env, cmd1, "sz");
                }
            }
            pfn_doeNativeComputeDispatchFlush(
                queue, pipeline, (void**)bg_ptrs, bg_count,
                dx, dy, dz,
                copy_src, copy_src_off, copy_dst, copy_dst_off, copy_size);
            return NULL;
        }
    }

    /* Fallback: standard wgpu path. */
    WGPUCommandEncoder encoder = pfn_wgpuDeviceCreateCommandEncoder(device, NULL);
    if (!encoder) NAPI_THROW(env, "submitBatched: createCommandEncoder failed");
    for (uint32_t i = 0; i < cmd_count; i++) {
        napi_value cmd;
        napi_get_element(env, commands, i, &cmd);
        uint32_t type = get_uint32_prop(env, cmd, "t");
        if (type == 0) {
            WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(encoder, NULL);
            void* pipeline = unwrap_ptr(env, get_prop(env, cmd, "p"));
            pfn_wgpuComputePassEncoderSetPipeline(pass, pipeline);
            napi_value bgs = get_prop(env, cmd, "bg");
            uint32_t bg_count = 0;
            napi_get_array_length(env, bgs, &bg_count);
            if (bg_count > BATCH_MAX_BIND_GROUPS) bg_count = BATCH_MAX_BIND_GROUPS;
            for (uint32_t j = 0; j < bg_count; j++) {
                napi_value bg_val;
                napi_get_element(env, bgs, j, &bg_val);
                void* bg = unwrap_ptr(env, bg_val);
                if (bg) pfn_wgpuComputePassEncoderSetBindGroup(pass, j, bg, 0, NULL);
            }
            pfn_wgpuComputePassEncoderDispatchWorkgroups(pass,
                get_uint32_prop(env, cmd, "x"), get_uint32_prop(env, cmd, "y"), get_uint32_prop(env, cmd, "z"));
            pfn_wgpuComputePassEncoderEnd(pass);
            pfn_wgpuComputePassEncoderRelease(pass);
        } else if (type == 1) {
            void* src = unwrap_ptr(env, get_prop(env, cmd, "s"));
            void* dst = unwrap_ptr(env, get_prop(env, cmd, "d"));
            pfn_wgpuCommandEncoderCopyBufferToBuffer(encoder, src,
                (uint64_t)get_int64_prop(env, cmd, "so"), dst,
                (uint64_t)get_int64_prop(env, cmd, "do"),
                (uint64_t)get_int64_prop(env, cmd, "sz"));
        }
    }
    WGPUCommandBuffer cmd_buf = pfn_wgpuCommandEncoderFinish(encoder, NULL);
    pfn_wgpuQueueSubmit(queue, 1, &cmd_buf);
    pfn_wgpuCommandBufferRelease(cmd_buf);
    pfn_wgpuCommandEncoderRelease(encoder);
    return NULL;
}

/* flushAndMapSync(instance, queue, buffer, mode, offset, size) — flush + map in one N-API call. */
static napi_value doe_flush_and_map_sync(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUQueue queue = unwrap_ptr(env, _args[1]);
    WGPUBuffer buf = unwrap_ptr(env, _args[2]);
    uint32_t mode;
    napi_get_value_uint32(env, _args[3], &mode);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[4], &offset_i);
    napi_get_value_int64(env, _args[5], &size_i);

    if (!queue || !buf) NAPI_THROW(env, "flushAndMapSync requires queue and buffer");

    /* Flush pending GPU work. */
    if (pfn_doeNativeQueueFlush) {
        pfn_doeNativeQueueFlush(queue);
    }

    /* Map the buffer synchronously via processEvents polling. */
    BufferMapResult result = {0, 0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode,
        (size_t)offset_i, (size_t)size_i, cb_info);
    if (future.id == 0) NAPI_THROW(env, "flushAndMapSync: bufferMapAsync future unavailable");
    if (!process_events_until(inst, &result.done, DOE_DEFAULT_TIMEOUT_NS) ||
        result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
        NAPI_THROW(env, "flushAndMapSync: bufferMapAsync failed");

    napi_value ok;
    napi_get_boolean(env, true, &ok);
    return ok;
}

static napi_value doe_queue_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuQueueRelease(p);
    return NULL;
}

/* ================================================================
 * Texture
 * createTexture(device, { format, width, height, usage, mipLevelCount?, dimension? })
 * ================================================================ */

/* WebGPU texture format string → numeric value mapping. */
static uint32_t texture_format_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    if (vt != napi_string) return 0x00000016; /* rgba8unorm */
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "rgba8unorm") == 0)      return 0x00000016;
    if (strcmp(buf, "rgba8unorm-srgb") == 0) return 0x00000017;
    if (strcmp(buf, "bgra8unorm") == 0)      return 0x0000001B;
    if (strcmp(buf, "bgra8unorm-srgb") == 0) return 0x0000001C;
    if (strcmp(buf, "depth32float") == 0)    return 0x00000030;
    return 0x00000016;
}

static napi_value doe_create_texture(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    WGPUTextureDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.format = texture_format_from_string(env, get_prop(env, _args[1], "format"));
    desc.size.width = get_uint32_prop(env, _args[1], "width");
    desc.size.height = get_uint32_prop(env, _args[1], "height");
    desc.size.depthOrArrayLayers = 1;
    if (has_prop(env, _args[1], "depthOrArrayLayers"))
        desc.size.depthOrArrayLayers = get_uint32_prop(env, _args[1], "depthOrArrayLayers");
    desc.usage = (uint64_t)get_int64_prop(env, _args[1], "usage");
    desc.mipLevelCount = 1;
    if (has_prop(env, _args[1], "mipLevelCount"))
        desc.mipLevelCount = get_uint32_prop(env, _args[1], "mipLevelCount");
    desc.sampleCount = 1;
    desc.dimension = 1; /* 2D */

    WGPUTexture tex = pfn_wgpuDeviceCreateTexture(device, &desc);
    if (!tex) NAPI_THROW(env, "createTexture failed");
    return wrap_ptr(env, tex);
}

static napi_value doe_texture_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuTextureRelease(p);
    return NULL;
}

/* textureCreateView(texture) */
static napi_value doe_texture_create_view(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUTexture tex = unwrap_ptr(env, _args[0]);
    if (!tex) NAPI_THROW(env, "Invalid texture");
    WGPUTextureView view = pfn_wgpuTextureCreateView(tex, NULL);
    if (!view) NAPI_THROW(env, "textureCreateView failed");
    return wrap_ptr(env, view);
}

static napi_value doe_texture_view_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuTextureViewRelease(p);
    return NULL;
}

/* ================================================================
 * Sampler
 * createSampler(device, { magFilter?, minFilter?, mipmapFilter?,
 *   addressModeU?, addressModeV?, addressModeW?, lodMinClamp?, lodMaxClamp?, maxAnisotropy? })
 * ================================================================ */

static uint32_t filter_mode_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0; /* nearest */
    char buf[16] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "linear") == 0) return 1;
    return 0; /* nearest */
}

static uint32_t address_mode_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 1; /* clamp-to-edge */
    char buf[24] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "repeat") == 0) return 2;
    if (strcmp(buf, "mirror-repeat") == 0) return 3;
    return 1; /* clamp-to-edge */
}

static napi_value doe_create_sampler(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    WGPUSamplerDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.lodMaxClamp = 32.0f;
    desc.maxAnisotropy = 1;

    napi_valuetype desc_type;
    napi_typeof(env, _args[1], &desc_type);
    if (desc_type == napi_object) {
        if (has_prop(env, _args[1], "magFilter"))
            desc.magFilter = filter_mode_from_string(env, get_prop(env, _args[1], "magFilter"));
        if (has_prop(env, _args[1], "minFilter"))
            desc.minFilter = filter_mode_from_string(env, get_prop(env, _args[1], "minFilter"));
        if (has_prop(env, _args[1], "mipmapFilter"))
            desc.mipmapFilter = filter_mode_from_string(env, get_prop(env, _args[1], "mipmapFilter"));
        if (has_prop(env, _args[1], "addressModeU"))
            desc.addressModeU = address_mode_from_string(env, get_prop(env, _args[1], "addressModeU"));
        if (has_prop(env, _args[1], "addressModeV"))
            desc.addressModeV = address_mode_from_string(env, get_prop(env, _args[1], "addressModeV"));
        if (has_prop(env, _args[1], "addressModeW"))
            desc.addressModeW = address_mode_from_string(env, get_prop(env, _args[1], "addressModeW"));
        if (has_prop(env, _args[1], "maxAnisotropy"))
            desc.maxAnisotropy = (uint16_t)get_uint32_prop(env, _args[1], "maxAnisotropy");
    }

    WGPUSampler sampler = pfn_wgpuDeviceCreateSampler(device, &desc);
    if (!sampler) NAPI_THROW(env, "createSampler failed");
    return wrap_ptr(env, sampler);
}

static napi_value doe_sampler_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuSamplerRelease(p);
    return NULL;
}

/* ================================================================
 * Render Pipeline (noop stub — uses built-in Metal shaders)
 * createRenderPipeline(device)
 * ================================================================ */

static napi_value doe_create_render_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    WGPURenderPipeline rp = pfn_wgpuDeviceCreateRenderPipeline(device, NULL);
    if (!rp) NAPI_THROW(env, "createRenderPipeline failed");
    return wrap_ptr(env, rp);
}

static napi_value doe_render_pipeline_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuRenderPipelineRelease(p);
    return NULL;
}

/* ================================================================
 * Render Pass
 * beginRenderPass(encoder, colorAttachments[])
 * ================================================================ */

static napi_value doe_begin_render_pass(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");

    /* _args[1] is array of color attachments */
    uint32_t att_count = 0;
    napi_get_array_length(env, _args[1], &att_count);
    if (att_count == 0) NAPI_THROW(env, "beginRenderPass: need at least one color attachment");

    WGPURenderPassColorAttachment* atts = (WGPURenderPassColorAttachment*)calloc(
        att_count, sizeof(WGPURenderPassColorAttachment));
    for (uint32_t i = 0; i < att_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[1], i, &elem);
        atts[i].view = unwrap_ptr(env, get_prop(env, elem, "view"));
        atts[i].loadOp = 1; /* clear */
        atts[i].storeOp = 1; /* store */
        if (has_prop(env, elem, "clearValue") && prop_type(env, elem, "clearValue") == napi_object) {
            napi_value cv = get_prop(env, elem, "clearValue");
            double r = 0, g = 0, b = 0, a = 1;
            napi_value tmp;
            if (napi_get_named_property(env, cv, "r", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &r);
            if (napi_get_named_property(env, cv, "g", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &g);
            if (napi_get_named_property(env, cv, "b", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &b);
            if (napi_get_named_property(env, cv, "a", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &a);
            atts[i].clearValue = (WGPUColor){ r, g, b, a };
        }
    }

    WGPURenderPassDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.colorAttachmentCount = att_count;
    desc.colorAttachments = atts;

    WGPURenderPassEncoder pass = pfn_wgpuCommandEncoderBeginRenderPass(enc, &desc);
    free(atts);
    if (!pass) NAPI_THROW(env, "beginRenderPass failed");
    return wrap_ptr(env, pass);
}

static napi_value doe_render_pass_set_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    pfn_wgpuRenderPassEncoderSetPipeline(
        unwrap_ptr(env, _args[0]), unwrap_ptr(env, _args[1]));
    return NULL;
}

/* renderPassDraw(pass, vertexCount, instanceCount, firstVertex, firstInstance) */
static napi_value doe_render_pass_draw(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t vc, ic, fv, fi;
    napi_get_value_uint32(env, _args[1], &vc);
    napi_get_value_uint32(env, _args[2], &ic);
    napi_get_value_uint32(env, _args[3], &fv);
    napi_get_value_uint32(env, _args[4], &fi);
    pfn_wgpuRenderPassEncoderDraw(pass, vc, ic, fv, fi);
    return NULL;
}

static napi_value doe_render_pass_end(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    pfn_wgpuRenderPassEncoderEnd(unwrap_ptr(env, _args[0]));
    return NULL;
}

static napi_value doe_render_pass_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuRenderPassEncoderRelease(p);
    return NULL;
}

/* ================================================================
 * Device capabilities: limits, features
 * ================================================================ */

static napi_value doe_device_get_limits(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "deviceGetLimits: null device");

    WGPULimits limits;
    memset(&limits, 0, sizeof(limits));
    pfn_wgpuDeviceGetLimits(device, &limits);

    napi_value obj;
    napi_create_object(env, &obj);

#define SET_U32(name) do { napi_value v; napi_create_uint32(env, limits.name, &v); napi_set_named_property(env, obj, #name, v); } while(0)
#define SET_U64(name) do { napi_value v; napi_create_double(env, (double)limits.name, &v); napi_set_named_property(env, obj, #name, v); } while(0)

    SET_U32(maxTextureDimension1D);
    SET_U32(maxTextureDimension2D);
    SET_U32(maxTextureDimension3D);
    SET_U32(maxTextureArrayLayers);
    SET_U32(maxBindGroups);
    SET_U32(maxBindGroupsPlusVertexBuffers);
    SET_U32(maxBindingsPerBindGroup);
    SET_U32(maxDynamicUniformBuffersPerPipelineLayout);
    SET_U32(maxDynamicStorageBuffersPerPipelineLayout);
    SET_U32(maxSampledTexturesPerShaderStage);
    SET_U32(maxSamplersPerShaderStage);
    SET_U32(maxStorageBuffersPerShaderStage);
    SET_U32(maxStorageTexturesPerShaderStage);
    SET_U32(maxUniformBuffersPerShaderStage);
    SET_U64(maxUniformBufferBindingSize);
    SET_U64(maxStorageBufferBindingSize);
    SET_U32(minUniformBufferOffsetAlignment);
    SET_U32(minStorageBufferOffsetAlignment);
    SET_U32(maxVertexBuffers);
    SET_U64(maxBufferSize);
    SET_U32(maxVertexAttributes);
    SET_U32(maxVertexBufferArrayStride);
    SET_U32(maxInterStageShaderVariables);
    SET_U32(maxColorAttachments);
    SET_U32(maxColorAttachmentBytesPerSample);
    SET_U32(maxComputeWorkgroupStorageSize);
    SET_U32(maxComputeInvocationsPerWorkgroup);
    SET_U32(maxComputeWorkgroupSizeX);
    SET_U32(maxComputeWorkgroupSizeY);
    SET_U32(maxComputeWorkgroupSizeZ);
    SET_U32(maxComputeWorkgroupsPerDimension);

#undef SET_U32
#undef SET_U64

    return obj;
}

static napi_value doe_device_has_feature(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    uint32_t feature;
    napi_get_value_uint32(env, _args[1], &feature);
    uint32_t result = pfn_wgpuDeviceHasFeature(device, feature);
    napi_value ret;
    napi_get_boolean(env, result != 0, &ret);
    return ret;
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
        EXPORT_FN("computePipelineGetBindGroupLayout", doe_compute_pipeline_get_bind_group_layout),
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
        EXPORT_FN("computePassDispatchWorkgroupsIndirect", doe_compute_pass_dispatch_indirect),
        EXPORT_FN("computePassEnd", doe_compute_pass_end),
        EXPORT_FN("computePassRelease", doe_compute_pass_release),
        EXPORT_FN("queueSubmit", doe_queue_submit),
        EXPORT_FN("queueWriteBuffer", doe_queue_write_buffer),
        EXPORT_FN("queueFlush", doe_queue_flush),
        EXPORT_FN("submitBatched", doe_submit_batched),
        EXPORT_FN("flushAndMapSync", doe_flush_and_map_sync),
        EXPORT_FN("queueRelease", doe_queue_release),
        EXPORT_FN("createTexture", doe_create_texture),
        EXPORT_FN("textureRelease", doe_texture_release),
        EXPORT_FN("textureCreateView", doe_texture_create_view),
        EXPORT_FN("textureViewRelease", doe_texture_view_release),
        EXPORT_FN("createSampler", doe_create_sampler),
        EXPORT_FN("samplerRelease", doe_sampler_release),
        EXPORT_FN("createRenderPipeline", doe_create_render_pipeline),
        EXPORT_FN("renderPipelineRelease", doe_render_pipeline_release),
        EXPORT_FN("beginRenderPass", doe_begin_render_pass),
        EXPORT_FN("renderPassSetPipeline", doe_render_pass_set_pipeline),
        EXPORT_FN("renderPassDraw", doe_render_pass_draw),
        EXPORT_FN("renderPassEnd", doe_render_pass_end),
        EXPORT_FN("renderPassRelease", doe_render_pass_release),
        EXPORT_FN("deviceGetLimits", doe_device_get_limits),
        EXPORT_FN("deviceHasFeature", doe_device_has_feature),
    };

    size_t count = sizeof(descriptors) / sizeof(descriptors[0]);
    napi_define_properties(env, exports, count, descriptors);
    return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, doe_module_init)
