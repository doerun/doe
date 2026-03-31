/**
 * C-linkage shim for WebKit's WebGPU.framework.
 *
 * Bridges five ABI gaps between the Zig plan executor (compiled against
 * Dawn's webgpu.h) and WebKit's C++ WebGPU implementation:
 *
 * 1. NAME MANGLING: WebKit's wgpu* symbols have C++ linkage. This shim
 *    re-exports with C linkage via asm("_wgpuFoo") labels.
 *
 * 2. STRUCT LAYOUT: Dawn and WebKit have completely different struct layouts
 *    (nextInChain presence, WGPUStringView vs char-ptr/WTF-String, uint64_t vs
 *    uint32_t flags, different field ordering). Each function reads Dawn layout
 *    and constructs WebKit layout.
 *
 * 3. ENUM VALUES: WGPUFeatureName numbering differs. Status enums differ
 *    (Dawn Success=1, WebKit Success=0).
 *
 * 4. C++ TYPE SIGNATURES: WebKit uses std::span, std::optional<Vector>,
 *    and WTF::String in some function signatures.
 *
 * 5. CALLBACK PATTERNS: Dawn uses CallbackInfo structs (dual userdata,
 *    WGPUFuture return). WebKit uses old-style (fn + void-ptr, returns void).
 */

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <string>

// Pull in WebKit's WebGPU.h (C++ linkage, WebKit struct layouts).
// The framework header is in PrivateHeaders/WebGPU.h, included via -I.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wnullability-completeness"
namespace WTF { class String; }
#include "WebGPU.h"
#pragma clang diagnostic pop

// ═══════════════════════════════════════════════════════════════════
// Dawn ABI types — match the binary layout the Zig executor produces
// when compiled against Dawn's webgpu.h.
// ═══════════════════════════════════════════════════════════════════

typedef uint64_t DawnFlags;

struct DawnStringView {
    char const* data;
    size_t length;
};

struct DawnChainedStruct {
    DawnChainedStruct* next;
    uint32_t sType;
};

struct DawnFuture {
    uint64_t id;
};

// ── Dawn callback types ─────────────────────────────────────────────
// Status param is uint32_t (raw enum) because Dawn and WebKit use
// different enum values — we translate in the callback wrappers.

typedef void (*DawnRequestAdapterCB)(
    uint32_t status, WGPUAdapter adapter, DawnStringView msg, void* ud1, void* ud2);
typedef void (*DawnRequestDeviceCB)(
    uint32_t status, WGPUDevice device, DawnStringView msg, void* ud1, void* ud2);
typedef void (*DawnQueueWorkDoneCB)(
    uint32_t status, DawnStringView msg, void* ud1, void* ud2);

struct DawnRequestAdapterCBInfo {
    void*                  nextInChain;
    uint32_t               mode;
    DawnRequestAdapterCB   callback;
    void*                  userdata1;
    void*                  userdata2;
};

struct DawnRequestDeviceCBInfo {
    void*                  nextInChain;
    uint32_t               mode;
    DawnRequestDeviceCB    callback;
    void*                  userdata1;
    void*                  userdata2;
};

struct DawnQueueWorkDoneCBInfo {
    void*                  nextInChain;
    uint32_t               mode;
    DawnQueueWorkDoneCB    callback;
    void*                  userdata1;
    void*                  userdata2;
};

// ── Dawn descriptor struct layouts ──────────────────────────────────

struct DawnInstanceDescriptor {
    DawnChainedStruct* nextInChain;
    size_t requiredFeatureCount;
    uint32_t const* requiredFeatures;
    void const* requiredLimits;
};

struct DawnRequestAdapterOptions {
    DawnChainedStruct* nextInChain;
    uint32_t featureLevel;
    uint32_t powerPreference;
    uint32_t forceFallbackAdapter;
    uint32_t backendType;
    void* compatibleSurface;
};

struct DawnDeviceDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    size_t requiredFeatureCount;
    uint32_t const* requiredFeatures;
    void const* requiredLimits;
    // WGPUQueueDescriptor + callback infos follow; executor zero-inits them
};

struct DawnBufferDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    DawnFlags usage;        // uint64_t in Dawn, uint32_t in WebKit
    uint64_t size;
    uint32_t mappedAtCreation;
};

struct DawnShaderSourceWGSL {
    DawnChainedStruct chain;
    DawnStringView code;
};

struct DawnShaderModuleDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
};

struct DawnBufferBindingLayout {
    DawnChainedStruct* nextInChain;
    uint32_t type;
    uint32_t hasDynamicOffset;
    uint64_t minBindingSize;
};

struct DawnSamplerBindingLayout {
    DawnChainedStruct* nextInChain;
    uint32_t type;
};

struct DawnTextureBindingLayout {
    DawnChainedStruct* nextInChain;
    uint32_t sampleType;
    uint32_t viewDimension;
    uint32_t multisampled;
};

struct DawnStorageTextureBindingLayout {
    DawnChainedStruct* nextInChain;
    uint32_t access;
    uint32_t format;
    uint32_t viewDimension;
};

struct DawnBindGroupLayoutEntry {
    DawnChainedStruct* nextInChain;
    uint32_t binding;
    // compiler inserts 4 bytes padding here (uint64_t alignment)
    DawnFlags visibility;               // uint64_t
    uint32_t bindingArraySize;
    // compiler inserts 4 bytes padding here (pointer alignment)
    DawnBufferBindingLayout buffer;
    DawnSamplerBindingLayout sampler;
    DawnTextureBindingLayout texture;
    DawnStorageTextureBindingLayout storageTexture;
};

struct DawnBindGroupLayoutDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    size_t entryCount;
    DawnBindGroupLayoutEntry const* entries;
};

struct DawnPipelineLayoutDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    size_t bindGroupLayoutCount;
    WGPUBindGroupLayout const* bindGroupLayouts;
    uint32_t immediateSize;
};

struct DawnComputeState {
    DawnChainedStruct* nextInChain;
    WGPUShaderModule module;
    DawnStringView entryPoint;
    size_t constantCount;
    void const* constants;
};

struct DawnComputePipelineDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    WGPUPipelineLayout layout;
    DawnComputeState compute;
};

struct DawnBindGroupEntry {
    DawnChainedStruct* nextInChain;
    uint32_t binding;
    // compiler inserts 4 bytes padding (pointer alignment)
    WGPUBuffer buffer;
    uint64_t offset;
    uint64_t size;
    WGPUSampler sampler;
    WGPUTextureView textureView;
};

struct DawnBindGroupDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    WGPUBindGroupLayout layout;
    size_t entryCount;
    DawnBindGroupEntry const* entries;
};

struct DawnCommandEncoderDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
};

struct DawnComputePassDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    void const* timestampWrites;
};

struct DawnCommandBufferDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
};

// ═══════════════════════════════════════════════════════════════════
// Enum translation — Dawn and WebKit assign different values.
// ═══════════════════════════════════════════════════════════════════

// Dawn inserted CoreFeaturesAndLimits at 0x01, shifting DepthClipControl+
// by one relative to WebKit. Values 0x04–0x08 happen to match.
static WGPUFeatureName translateFeatureName(uint32_t dawn_val) {
    switch (dawn_val) {
        case 0x02: return WGPUFeatureName_DepthClipControl;         // Dawn 0x02 → WebKit 0x01
        case 0x03: return WGPUFeatureName_Depth32FloatStencil8;     // Dawn 0x03 → WebKit 0x02
        case 0x09: return WGPUFeatureName_TimestampQuery;           // Dawn 0x09 → WebKit 0x03
        case 0x0A: return WGPUFeatureName_IndirectFirstInstance;    // Dawn 0x0A → WebKit 0x09
        case 0x0B: return WGPUFeatureName_ShaderF16;                // Dawn 0x0B → WebKit 0x0A
        case 0x0C: return WGPUFeatureName_RG11B10UfloatRenderable;  // Dawn 0x0C → WebKit 0x0B
        case 0x0D: return WGPUFeatureName_BGRA8UnormStorage;        // Dawn 0x0D → WebKit 0x0C
        case 0x0E: return WGPUFeatureName_Float32Filterable;        // Dawn 0x0E → WebKit 0x0D
        case 0x0F: return WGPUFeatureName_Float32Blendable;         // Dawn 0x0F → WebKit 0x0E
        case 0x10: return WGPUFeatureName_ClipDistances;            // Dawn 0x10 → WebKit 0x0F
        case 0x11: return WGPUFeatureName_DualSourceBlending;       // Dawn 0x11 → WebKit 0x10
        default:   return (WGPUFeatureName)dawn_val;                // 0x04–0x08 match
    }
}

// Dawn:  Success=1, Unavailable=3, Error=4
// WebKit: Success=0, Unavailable=1, Error=2
static uint32_t webkitAdapterStatusToDawn(WGPURequestAdapterStatus ws) {
    switch (ws) {
        case WGPURequestAdapterStatus_Success:     return 1;
        case WGPURequestAdapterStatus_Unavailable: return 3;
        case WGPURequestAdapterStatus_Error:       return 4;
        default:                                    return 4;
    }
}

// Dawn:  Success=1, Error=3
// WebKit: Success=0, Error=1
static uint32_t webkitDeviceStatusToDawn(WGPURequestDeviceStatus ws) {
    switch (ws) {
        case WGPURequestDeviceStatus_Success: return 1;
        case WGPURequestDeviceStatus_Error:   return 3;
        default:                               return 3;
    }
}

// Dawn:  Success=1, Error=3
// WebKit: Success=0, Error=1
static uint32_t webkitQueueStatusToDawn(WGPUQueueWorkDoneStatus ws) {
    switch (ws) {
        case WGPUQueueWorkDoneStatus_Success: return 1;
        case WGPUQueueWorkDoneStatus_Error:   return 3;
        default:                               return 3;
    }
}

// ═══════════════════════════════════════════════════════════════════
// Callback adapters — bridge Dawn's dual-userdata + WGPUFuture return
// to WebKit's single-userdata + void return, and translate status enums.
// ═══════════════════════════════════════════════════════════════════

struct AdapterBridge {
    DawnRequestAdapterCB cb;
    void* ud1;
    void* ud2;
};

static void adapter_cb_wrapper(
    WGPURequestAdapterStatus status, WGPUAdapter adapter,
    char const* message, void* userdata
) {
    auto* b = static_cast<AdapterBridge*>(userdata);
    DawnStringView sv = { message, message ? strlen(message) : 0 };
    b->cb(webkitAdapterStatusToDawn(status), adapter, sv, b->ud1, b->ud2);
    delete b;
}

struct DeviceBridge {
    DawnRequestDeviceCB cb;
    void* ud1;
    void* ud2;
};

static void device_cb_wrapper(
    WGPURequestDeviceStatus status, WGPUDevice device,
    char const* message, void* userdata
) {
    auto* b = static_cast<DeviceBridge*>(userdata);
    DawnStringView sv = { message, message ? strlen(message) : 0 };
    b->cb(webkitDeviceStatusToDawn(status), device, sv, b->ud1, b->ud2);
    delete b;
}

struct QueueDoneBridge {
    DawnQueueWorkDoneCB cb;
    void* ud1;
    void* ud2;
};

static void queue_done_cb_wrapper(WGPUQueueWorkDoneStatus status, void* userdata) {
    auto* b = static_cast<QueueDoneBridge*>(userdata);
    DawnStringView sv = { nullptr, 0 };
    b->cb(webkitQueueStatusToDawn(status), sv, b->ud1, b->ud2);
    delete b;
}

// ═══════════════════════════════════════════════════════════════════
// Exported symbols — asm("_wgpuFoo") on cshim_wgpuFoo so dlsym works.
// ═══════════════════════════════════════════════════════════════════

#define SHIM_EXPORT extern "C" __attribute__((visibility("default")))

// ── Shim identity probe ─────────────────────────────────────────────
// The runtime calls dlsym("doe_shim_get_backend_identity") after loading
// the library. If it resolves, the loaded library is the WebKit shim.
// Dawn does not export this symbol, so resolution is proof of identity.
SHIM_EXPORT char const* doe_shim_get_backend_identity(void);

// ── Forward declarations with asm labels ────────────────────────────

// Struct-translating functions (Dawn struct → WebKit struct)
SHIM_EXPORT WGPUInstance            cshim_wgpuCreateInstance(DawnInstanceDescriptor const *d)                                                   asm("_wgpuCreateInstance");
SHIM_EXPORT DawnFuture              cshim_wgpuInstanceRequestAdapter(WGPUInstance i, DawnRequestAdapterOptions const *o, DawnRequestAdapterCBInfo info)  asm("_wgpuInstanceRequestAdapter");
SHIM_EXPORT DawnFuture              cshim_wgpuAdapterRequestDevice(WGPUAdapter a, DawnDeviceDescriptor const *d, DawnRequestDeviceCBInfo info)   asm("_wgpuAdapterRequestDevice");
SHIM_EXPORT WGPUBuffer              cshim_wgpuDeviceCreateBuffer(WGPUDevice d, DawnBufferDescriptor const *desc)                                asm("_wgpuDeviceCreateBuffer");
SHIM_EXPORT WGPUShaderModule        cshim_wgpuDeviceCreateShaderModule(WGPUDevice d, DawnShaderModuleDescriptor const *desc)                    asm("_wgpuDeviceCreateShaderModule");
SHIM_EXPORT WGPUBindGroupLayout     cshim_wgpuDeviceCreateBindGroupLayout(WGPUDevice d, DawnBindGroupLayoutDescriptor const *desc)              asm("_wgpuDeviceCreateBindGroupLayout");
SHIM_EXPORT WGPUBindGroup           cshim_wgpuDeviceCreateBindGroup(WGPUDevice d, DawnBindGroupDescriptor const *desc)                          asm("_wgpuDeviceCreateBindGroup");
SHIM_EXPORT WGPUPipelineLayout      cshim_wgpuDeviceCreatePipelineLayout(WGPUDevice d, DawnPipelineLayoutDescriptor const *desc)                asm("_wgpuDeviceCreatePipelineLayout");
SHIM_EXPORT WGPUComputePipeline     cshim_wgpuDeviceCreateComputePipeline(WGPUDevice d, DawnComputePipelineDescriptor const *desc)              asm("_wgpuDeviceCreateComputePipeline");
SHIM_EXPORT WGPUCommandEncoder      cshim_wgpuDeviceCreateCommandEncoder(WGPUDevice d, DawnCommandEncoderDescriptor const *desc)                asm("_wgpuDeviceCreateCommandEncoder");
SHIM_EXPORT WGPUComputePassEncoder  cshim_wgpuCommandEncoderBeginComputePass(WGPUCommandEncoder e, DawnComputePassDescriptor const *desc)       asm("_wgpuCommandEncoderBeginComputePass");
SHIM_EXPORT WGPUCommandBuffer       cshim_wgpuCommandEncoderFinish(WGPUCommandEncoder e, DawnCommandBufferDescriptor const *desc)               asm("_wgpuCommandEncoderFinish");

// Enum-translating function
SHIM_EXPORT WGPUBool                cshim_wgpuAdapterHasFeature(WGPUAdapter a, uint32_t dawn_feature)                                           asm("_wgpuAdapterHasFeature");

// Limits query (WebKit struct → Dawn struct translation)
SHIM_EXPORT uint32_t                cshim_wgpuAdapterGetLimits(WGPUAdapter a, void *out)                                                       asm("_wgpuAdapterGetLimits");
SHIM_EXPORT uint32_t                cshim_wgpuDeviceGetLimits(WGPUDevice d, void *out)                                                         asm("_wgpuDeviceGetLimits");

// Opaque handle passthrough (no struct translation needed)
SHIM_EXPORT void                    cshim_wgpuInstanceProcessEvents(WGPUInstance i)                                                             asm("_wgpuInstanceProcessEvents");
SHIM_EXPORT void                    cshim_wgpuInstanceRelease(WGPUInstance i)                                                                   asm("_wgpuInstanceRelease");
SHIM_EXPORT void                    cshim_wgpuAdapterRelease(WGPUAdapter a)                                                                     asm("_wgpuAdapterRelease");
SHIM_EXPORT WGPUQueue               cshim_wgpuDeviceGetQueue(WGPUDevice d)                                                                      asm("_wgpuDeviceGetQueue");
SHIM_EXPORT void                    cshim_wgpuDeviceDestroy(WGPUDevice d)                                                                       asm("_wgpuDeviceDestroy");
SHIM_EXPORT void                    cshim_wgpuDeviceRelease(WGPUDevice d)                                                                       asm("_wgpuDeviceRelease");
SHIM_EXPORT void                    cshim_wgpuQueueSubmit(WGPUQueue q, size_t count, WGPUCommandBuffer const *bufs)                             asm("_wgpuQueueSubmit");
SHIM_EXPORT void                    cshim_wgpuQueueRelease(WGPUQueue q)                                                                         asm("_wgpuQueueRelease");
SHIM_EXPORT void                    cshim_wgpuBufferRelease(WGPUBuffer b)                                                                       asm("_wgpuBufferRelease");
SHIM_EXPORT void                    cshim_wgpuShaderModuleRelease(WGPUShaderModule m)                                                           asm("_wgpuShaderModuleRelease");
SHIM_EXPORT void                    cshim_wgpuBindGroupLayoutRelease(WGPUBindGroupLayout l)                                                     asm("_wgpuBindGroupLayoutRelease");
SHIM_EXPORT void                    cshim_wgpuBindGroupRelease(WGPUBindGroup g)                                                                 asm("_wgpuBindGroupRelease");
SHIM_EXPORT void                    cshim_wgpuPipelineLayoutRelease(WGPUPipelineLayout l)                                                       asm("_wgpuPipelineLayoutRelease");
SHIM_EXPORT void                    cshim_wgpuComputePipelineRelease(WGPUComputePipeline p)                                                     asm("_wgpuComputePipelineRelease");
SHIM_EXPORT void                    cshim_wgpuCommandEncoderRelease(WGPUCommandEncoder e)                                                       asm("_wgpuCommandEncoderRelease");
SHIM_EXPORT void                    cshim_wgpuComputePassEncoderSetPipeline(WGPUComputePassEncoder e, WGPUComputePipeline p)                    asm("_wgpuComputePassEncoderSetPipeline");
SHIM_EXPORT void                    cshim_wgpuComputePassEncoderDispatchWorkgroups(WGPUComputePassEncoder e, uint32_t x, uint32_t y, uint32_t z) asm("_wgpuComputePassEncoderDispatchWorkgroups");
SHIM_EXPORT void                    cshim_wgpuComputePassEncoderEnd(WGPUComputePassEncoder e)                                                   asm("_wgpuComputePassEncoderEnd");
SHIM_EXPORT void                    cshim_wgpuComputePassEncoderRelease(WGPUComputePassEncoder e)                                               asm("_wgpuComputePassEncoderRelease");
SHIM_EXPORT void                    cshim_wgpuCommandBufferRelease(WGPUCommandBuffer b)                                                         asm("_wgpuCommandBufferRelease");

// C++ type bridges
SHIM_EXPORT void cshim_wgpuQueueWriteBuffer(WGPUQueue q, WGPUBuffer b, uint64_t offset, void const *data, size_t size)                          asm("_wgpuQueueWriteBuffer");
SHIM_EXPORT void cshim_wgpuComputePassEncoderSetBindGroup(WGPUComputePassEncoder e, uint32_t idx, WGPUBindGroup g, size_t dynOffsetCount, uint32_t const *dynOffsets) asm("_wgpuComputePassEncoderSetBindGroup");

// Callback pattern bridge (also does struct + status translation)
SHIM_EXPORT DawnFuture cshim_wgpuQueueOnSubmittedWorkDone(WGPUQueue q, DawnQueueWorkDoneCBInfo info) asm("_wgpuQueueOnSubmittedWorkDone");

// ═══════════════════════════════════════════════════════════════════
// Implementation — struct-translating functions
// ═══════════════════════════════════════════════════════════════════

// ── wgpuCreateInstance ──────────────────────────────────────────────
// Dawn: {nextInChain, requiredFeatureCount, requiredFeatures, requiredLimits}
// WebKit: {cocoaDescriptor: {scheduleWorkBlock, webProcessResourceOwner}}
// Executor passes: nextInChain=null (default). Ignore Dawn fields,
// create default WebKit descriptor (null block → use processEvents).
WGPUInstance cshim_wgpuCreateInstance(DawnInstanceDescriptor const *d) {
    WGPUInstanceDescriptor webkit_desc = {};
    webkit_desc.cocoaDescriptor.scheduleWorkBlock = nil;
    webkit_desc.cocoaDescriptor.webProcessResourceOwner = nullptr;
    return wgpuCreateInstance(&webkit_desc);
}

// ── wgpuInstanceRequestAdapter ──────────────────────────────────────
// Dawn: {nextInChain, featureLevel, powerPreference, forceFallbackAdapter, backendType, compatibleSurface}
// WebKit: {compatibleSurface, powerPreference, backendType, forceFallbackAdapter, xrCompatible}
DawnFuture cshim_wgpuInstanceRequestAdapter(
    WGPUInstance i, DawnRequestAdapterOptions const *o,
    DawnRequestAdapterCBInfo info
) {
    WGPURequestAdapterOptions webkit_opts = {};
    if (o) {
        webkit_opts.compatibleSurface = static_cast<WGPUSurface>(o->compatibleSurface);
        webkit_opts.powerPreference = static_cast<WGPUPowerPreference>(o->powerPreference);
        webkit_opts.backendType = static_cast<WGPUBackendType>(o->backendType);
        webkit_opts.forceFallbackAdapter = o->forceFallbackAdapter;
        webkit_opts.xrCompatible = 0;
    }
    auto *bridge = new AdapterBridge{info.callback, info.userdata1, info.userdata2};
    wgpuInstanceRequestAdapter(i, &webkit_opts, adapter_cb_wrapper, bridge);
    return DawnFuture{1};
}

// ── wgpuAdapterHasFeature ───────────────────────────────────────────
// Enum values differ; translate Dawn feature → WebKit feature.
WGPUBool cshim_wgpuAdapterHasFeature(WGPUAdapter a, uint32_t dawn_feature) {
    return wgpuAdapterHasFeature(a, translateFeatureName(dawn_feature));
}

// ── wgpuAdapterGetLimits / wgpuDeviceGetLimits ──────────────────────
// Dawn layout:  { nextInChain(ptr), fields..., maxImmediateSize(u32) }
// WebKit layout: { fields..., maxInterStageShaderComponents(u32) inserted,
//                  extra fragment/vertex stage fields at end }
// Return: Dawn WGPUStatus (1=Success), WebKit WGPUBool (1=true).

// Dawn WGPULimits — binary-compatible with the Zig extern struct.
struct DawnLimits {
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
};

static void webkitLimitsToDawn(WGPULimits const& src, DawnLimits* dst) {
    dst->nextInChain                              = nullptr;
    dst->maxTextureDimension1D                    = src.maxTextureDimension1D;
    dst->maxTextureDimension2D                    = src.maxTextureDimension2D;
    dst->maxTextureDimension3D                    = src.maxTextureDimension3D;
    dst->maxTextureArrayLayers                    = src.maxTextureArrayLayers;
    dst->maxBindGroups                            = src.maxBindGroups;
    dst->maxBindGroupsPlusVertexBuffers           = src.maxBindGroupsPlusVertexBuffers;
    dst->maxBindingsPerBindGroup                  = src.maxBindingsPerBindGroup;
    dst->maxDynamicUniformBuffersPerPipelineLayout = src.maxDynamicUniformBuffersPerPipelineLayout;
    dst->maxDynamicStorageBuffersPerPipelineLayout = src.maxDynamicStorageBuffersPerPipelineLayout;
    dst->maxSampledTexturesPerShaderStage         = src.maxSampledTexturesPerShaderStage;
    dst->maxSamplersPerShaderStage                = src.maxSamplersPerShaderStage;
    dst->maxStorageBuffersPerShaderStage          = src.maxStorageBuffersPerShaderStage;
    dst->maxStorageTexturesPerShaderStage         = src.maxStorageTexturesPerShaderStage;
    dst->maxUniformBuffersPerShaderStage          = src.maxUniformBuffersPerShaderStage;
    dst->maxUniformBufferBindingSize              = src.maxUniformBufferBindingSize;
    dst->maxStorageBufferBindingSize              = src.maxStorageBufferBindingSize;
    dst->minUniformBufferOffsetAlignment          = src.minUniformBufferOffsetAlignment;
    dst->minStorageBufferOffsetAlignment          = src.minStorageBufferOffsetAlignment;
    dst->maxVertexBuffers                         = src.maxVertexBuffers;
    dst->maxBufferSize                            = src.maxBufferSize;
    dst->maxVertexAttributes                      = src.maxVertexAttributes;
    dst->maxVertexBufferArrayStride               = src.maxVertexBufferArrayStride;
    dst->maxInterStageShaderVariables             = src.maxInterStageShaderVariables;
    dst->maxColorAttachments                      = src.maxColorAttachments;
    dst->maxColorAttachmentBytesPerSample         = src.maxColorAttachmentBytesPerSample;
    dst->maxComputeWorkgroupStorageSize           = src.maxComputeWorkgroupStorageSize;
    dst->maxComputeInvocationsPerWorkgroup        = src.maxComputeInvocationsPerWorkgroup;
    dst->maxComputeWorkgroupSizeX                 = src.maxComputeWorkgroupSizeX;
    dst->maxComputeWorkgroupSizeY                 = src.maxComputeWorkgroupSizeY;
    dst->maxComputeWorkgroupSizeZ                 = src.maxComputeWorkgroupSizeZ;
    dst->maxComputeWorkgroupsPerDimension         = src.maxComputeWorkgroupsPerDimension;
    dst->maxImmediateSize                         = 0; // WebKit has no equivalent
}

uint32_t cshim_wgpuAdapterGetLimits(WGPUAdapter a, void *out) {
    WGPUSupportedLimits webkit_limits = {};
    WGPUBool ok = wgpuAdapterGetLimits(a, &webkit_limits);
    if (!ok) return 2; // WGPUStatus_Error
    webkitLimitsToDawn(webkit_limits.limits, static_cast<DawnLimits*>(out));
    return 1; // WGPUStatus_Success
}

uint32_t cshim_wgpuDeviceGetLimits(WGPUDevice d, void *out) {
    WGPUSupportedLimits webkit_limits = {};
    WGPUBool ok = wgpuDeviceGetLimits(d, &webkit_limits);
    if (!ok) return 2; // WGPUStatus_Error
    webkitLimitsToDawn(webkit_limits.limits, static_cast<DawnLimits*>(out));
    return 1; // WGPUStatus_Success
}

// ── wgpuAdapterRequestDevice ────────────────────────────────────────
// Dawn: {nextInChain, label(StringView), requiredFeatureCount, requiredFeatures,
//        requiredLimits, defaultQueue, deviceLostCallbackInfo, uncapturedErrorCallbackInfo}
// WebKit: {label(char*), requiredFeatureCount, requiredFeatures,
//          requiredLimits, defaultQueue, deviceLostCallback, deviceLostUserdata}
DawnFuture cshim_wgpuAdapterRequestDevice(
    WGPUAdapter a, DawnDeviceDescriptor const *d,
    DawnRequestDeviceCBInfo info
) {
    // Translate feature names from Dawn enum values to WebKit enum values
    size_t feature_count = d ? d->requiredFeatureCount : 0;
    WGPUFeatureName* webkit_features = nullptr;
    if (feature_count > 0 && d->requiredFeatures) {
        webkit_features = new WGPUFeatureName[feature_count];
        for (size_t i = 0; i < feature_count; i++) {
            webkit_features[i] = translateFeatureName(d->requiredFeatures[i]);
        }
    }

    WGPUDeviceDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.requiredFeatureCount = feature_count;
    webkit_desc.requiredFeatures = webkit_features;
    webkit_desc.requiredLimits = nullptr;  // executor passes null
    webkit_desc.defaultQueue = {};
    webkit_desc.defaultQueue.label = nullptr;
    webkit_desc.deviceLostCallback = nullptr;
    webkit_desc.deviceLostUserdata = nullptr;

    auto *bridge = new DeviceBridge{info.callback, info.userdata1, info.userdata2};
    wgpuAdapterRequestDevice(a, &webkit_desc, device_cb_wrapper, bridge);

    delete[] webkit_features;
    return DawnFuture{1};
}

// ── wgpuDeviceCreateBuffer ──────────────────────────────────────────
// Dawn: {nextInChain, label(StringView), usage(uint64), size, mappedAtCreation}
// WebKit: {label(char*), usage(uint32), size, mappedAtCreation}
WGPUBuffer cshim_wgpuDeviceCreateBuffer(WGPUDevice d, DawnBufferDescriptor const *desc) {
    WGPUBufferDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.usage = static_cast<WGPUBufferUsageFlags>(desc->usage);  // truncate 64→32
    webkit_desc.size = desc->size;
    webkit_desc.mappedAtCreation = desc->mappedAtCreation;
    return wgpuDeviceCreateBuffer(d, &webkit_desc);
}

// ── wgpuDeviceCreateShaderModule ────────────────────────────────────
// Dawn: {nextInChain→WGPUShaderSourceWGSL{chain, code(StringView)}, label(StringView)}
// WebKit: {wgslDescriptor(WTF::String), label(char*), hintCount, hints}
WGPUShaderModule cshim_wgpuDeviceCreateShaderModule(WGPUDevice d, DawnShaderModuleDescriptor const *desc) {
    // Follow Dawn's chained struct to find WGSL source
    WTF::String wgsl_code;
    if (desc->nextInChain) {
        auto* chain = desc->nextInChain;
        // WGPUSType_ShaderSourceWGSL = 0x02 in Dawn
        if (chain->sType == 0x02) {
            auto* wgsl_src = reinterpret_cast<DawnShaderSourceWGSL const*>(chain);
            if (wgsl_src->code.data && wgsl_src->code.length > 0) {
                wgsl_code = WTF::String::fromUTF8(
                    std::span<const char>(wgsl_src->code.data, wgsl_src->code.length));
            }
        }
    }

    WGPUShaderModuleDescriptor webkit_desc = {};
    webkit_desc.wgslDescriptor = std::move(wgsl_code);
    webkit_desc.label = nullptr;
    webkit_desc.hintCount = 0;
    webkit_desc.hints = nullptr;
    return wgpuDeviceCreateShaderModule(d, &webkit_desc);
}

// ── wgpuDeviceCreateBindGroupLayout ─────────────────────────────────
// Dawn entries: {nextInChain, binding, visibility(uint64), bindingArraySize,
//               buffer{nextInChain, type, hasDynamicOffset, minBindingSize}, ...}
// WebKit entries: {binding, metalBinding[3], visibility(uint32),
//                 buffer{type, hasDynamicOffset, minBindingSize, bufferSizeForBinding}, ...}

// Dawn added BindingNotUsed=0x00 before Undefined, shifting all buffer binding type
// values by +1 relative to WebKit.  Translate back:
//   Dawn 0x01 (Undefined)        → WebKit 0x00 (Undefined)
//   Dawn 0x02 (Uniform)          → WebKit 0x01 (Uniform)
//   Dawn 0x03 (Storage)          → WebKit 0x02 (Storage)
//   Dawn 0x04 (ReadOnlyStorage)  → WebKit 0x03 (ReadOnlyStorage)
static WGPUBufferBindingType translateBufferBindingType(uint32_t dawn_val) {
    if (dawn_val == 0) return WGPUBufferBindingType_Undefined;  // BindingNotUsed → Undefined
    if (dawn_val > 4) return WGPUBufferBindingType_Undefined;   // out of range guard
    return static_cast<WGPUBufferBindingType>(dawn_val - 1);
}

// Dawn added Undefined=0x00 before the real values, shifting all texture aspect
// values by +1 relative to WebKit.
//   Dawn 0x00 (Undefined)    → WebKit 0x00 (All, best default)
//   Dawn 0x01 (All)          → WebKit 0x00 (All)
//   Dawn 0x02 (StencilOnly)  → WebKit 0x01 (StencilOnly)
//   Dawn 0x03 (DepthOnly)    → WebKit 0x02 (DepthOnly)
static WGPUTextureAspect translateTextureAspect(uint32_t dawn_val) {
    if (dawn_val == 0) return WGPUTextureAspect_All;            // Undefined → All
    if (dawn_val > 3) return WGPUTextureAspect_All;             // out of range guard
    return static_cast<WGPUTextureAspect>(dawn_val - 1);
}

// Dawn added Undefined=0x00 before the real values:
//   Dawn 0x00 (Undefined) → WebKit 0x01 (_2D, safe default)
//   Dawn 0x01 (_1D)       → WebKit 0x00 (_1D)
//   Dawn 0x02 (_2D)       → WebKit 0x01 (_2D)
//   Dawn 0x03 (_3D)       → WebKit 0x02 (_3D)
static WGPUTextureDimension translateTextureDimension(uint32_t dawn_val) {
    if (dawn_val == 0) return WGPUTextureDimension_2D;          // Undefined → 2D
    if (dawn_val > 3) return WGPUTextureDimension_2D;           // out of range guard
    return static_cast<WGPUTextureDimension>(dawn_val - 1);
}

// Dawn: Occlusion=0x01, Timestamp=0x02
// WebKit: Occlusion=0x00, Timestamp=0x01
static WGPUQueryType translateQueryType(uint32_t dawn_val) {
    if (dawn_val == 0 || dawn_val > 2) return WGPUQueryType_Occlusion;  // guard
    return static_cast<WGPUQueryType>(dawn_val - 1);
}

WGPUBindGroupLayout cshim_wgpuDeviceCreateBindGroupLayout(WGPUDevice d, DawnBindGroupLayoutDescriptor const *desc) {
    size_t count = desc->entryCount;
    auto* webkit_entries = new WGPUBindGroupLayoutEntry[count];
    for (size_t i = 0; i < count; i++) {
        auto& src = desc->entries[i];
        auto& dst = webkit_entries[i];
        memset(&dst, 0, sizeof(dst));

        dst.binding = src.binding;
        // metalBinding: set all stages to the binding index (identity mapping)
        dst.metalBinding[0] = src.binding;  // vertex
        dst.metalBinding[1] = src.binding;  // fragment
        dst.metalBinding[2] = src.binding;  // compute
        dst.visibility = static_cast<WGPUShaderStageFlags>(src.visibility);  // truncate 64→32

        // Buffer binding layout — translate Dawn enum → WebKit enum
        dst.buffer.type = translateBufferBindingType(src.buffer.type);
        dst.buffer.hasDynamicOffset = src.buffer.hasDynamicOffset;
        dst.buffer.minBindingSize = src.buffer.minBindingSize;
        dst.buffer.bufferSizeForBinding = 0;

        // Sampler/texture/storageTexture — zero-init from memset is fine
    }

    WGPUBindGroupLayoutDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.entryCount = count;
    webkit_desc.entries = webkit_entries;
    auto result = wgpuDeviceCreateBindGroupLayout(d, &webkit_desc);
    delete[] webkit_entries;
    return result;
}

// ── wgpuDeviceCreatePipelineLayout ──────────────────────────────────
// Dawn: {nextInChain, label(StringView), bindGroupLayoutCount, bindGroupLayouts, immediateSize}
// WebKit: {label(char*), bindGroupLayoutCount, bindGroupLayouts}
WGPUPipelineLayout cshim_wgpuDeviceCreatePipelineLayout(WGPUDevice d, DawnPipelineLayoutDescriptor const *desc) {
    WGPUPipelineLayoutDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.bindGroupLayoutCount = desc->bindGroupLayoutCount;
    webkit_desc.bindGroupLayouts = desc->bindGroupLayouts;  // opaque handles pass through
    return wgpuDeviceCreatePipelineLayout(d, &webkit_desc);
}

// ── wgpuDeviceCreateComputePipeline ─────────────────────────────────
// Dawn: {nextInChain, label(StringView), layout, compute{nextInChain, module,
//        entryPoint(StringView), constantCount, constants}}
// WebKit: {label(char*), layout, compute{module, entryPoint(char*),
//          constantCount, constants}}
WGPUComputePipeline cshim_wgpuDeviceCreateComputePipeline(WGPUDevice d, DawnComputePipelineDescriptor const *desc) {
    // Null-terminate entry point name
    char ep_buf[256];
    const char* entry_point = nullptr;
    if (desc->compute.entryPoint.data && desc->compute.entryPoint.length > 0) {
        size_t len = desc->compute.entryPoint.length;
        if (len >= sizeof(ep_buf)) len = sizeof(ep_buf) - 1;
        memcpy(ep_buf, desc->compute.entryPoint.data, len);
        ep_buf[len] = '\0';
        entry_point = ep_buf;
    }

    WGPUProgrammableStageDescriptor webkit_compute = {};
    webkit_compute.module = desc->compute.module;  // opaque handle
    webkit_compute.entryPoint = entry_point;
    webkit_compute.constantCount = 0;
    webkit_compute.constants = nullptr;

    WGPUComputePipelineDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.layout = desc->layout;  // opaque handle
    webkit_desc.compute = webkit_compute;
    return wgpuDeviceCreateComputePipeline(d, &webkit_desc);
}

// ── wgpuDeviceCreateBindGroup ───────────────────────────────────────
// Dawn entries: {nextInChain, binding, buffer, offset, size, sampler, textureView}
// WebKit entries: {binding, buffer, offset, size, sampler, texture, textureView, externalTexture}
WGPUBindGroup cshim_wgpuDeviceCreateBindGroup(WGPUDevice d, DawnBindGroupDescriptor const *desc) {
    size_t count = desc->entryCount;
    auto* webkit_entries = new WGPUBindGroupEntry[count];
    for (size_t i = 0; i < count; i++) {
        auto& src = desc->entries[i];
        auto& dst = webkit_entries[i];
        memset(&dst, 0, sizeof(dst));

        dst.binding = src.binding;
        dst.buffer = src.buffer;    // opaque handle
        dst.offset = src.offset;
        dst.size = src.size;
        dst.sampler = src.sampler;  // opaque handle (null for compute)
        dst.texture = nullptr;
        dst.textureView = src.textureView;  // opaque handle (null for compute)
        dst.externalTexture = nullptr;
    }

    WGPUBindGroupDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.layout = desc->layout;  // opaque handle
    webkit_desc.entryCount = count;
    webkit_desc.entries = webkit_entries;
    auto result = wgpuDeviceCreateBindGroup(d, &webkit_desc);
    delete[] webkit_entries;
    return result;
}

// ── wgpuDeviceCreateCommandEncoder ──────────────────────────────────
// Dawn: {nextInChain, label(StringView)}
// WebKit: {label(char*)}
WGPUCommandEncoder cshim_wgpuDeviceCreateCommandEncoder(WGPUDevice d, DawnCommandEncoderDescriptor const *desc) {
    WGPUCommandEncoderDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    return wgpuDeviceCreateCommandEncoder(d, &webkit_desc);
}

// ── wgpuCommandEncoderBeginComputePass ──────────────────────────────
// Dawn: {nextInChain, label(StringView), timestampWrites*}
// WebKit: {label(WTF::String), timestampWrites*}
WGPUComputePassEncoder cshim_wgpuCommandEncoderBeginComputePass(WGPUCommandEncoder e, DawnComputePassDescriptor const *desc) {
    WGPUComputePassDescriptor webkit_desc = {};
    webkit_desc.label = WTF::String();
    webkit_desc.timestampWrites = nullptr;  // executor always passes null
    return wgpuCommandEncoderBeginComputePass(e, &webkit_desc);
}

// ── wgpuCommandEncoderFinish ────────────────────────────────────────
// Dawn: {nextInChain, label(StringView)}
// WebKit: {label(WTF::String)}
WGPUCommandBuffer cshim_wgpuCommandEncoderFinish(WGPUCommandEncoder e, DawnCommandBufferDescriptor const *desc) {
    WGPUCommandBufferDescriptor webkit_desc = {};
    webkit_desc.label = WTF::String();
    return wgpuCommandEncoderFinish(e, &webkit_desc);
}

// ═══════════════════════════════════════════════════════════════════
// Opaque handle passthrough — no struct translation needed.
// ═══════════════════════════════════════════════════════════════════

void cshim_wgpuInstanceProcessEvents(WGPUInstance i) {
    wgpuInstanceProcessEvents(i);
}
void cshim_wgpuInstanceRelease(WGPUInstance i) {
    wgpuInstanceRelease(i);
}
void cshim_wgpuAdapterRelease(WGPUAdapter a) {
    wgpuAdapterRelease(a);
}
WGPUQueue cshim_wgpuDeviceGetQueue(WGPUDevice d) {
    return wgpuDeviceGetQueue(d);
}
void cshim_wgpuDeviceDestroy(WGPUDevice d) {
    // WebKit's wgpuDeviceDestroy triggers Device::loseTheDevice which
    // segfaults in libobjc during cleanup. Skip the call — the runtime
    // only calls this during deinit right before process exit, so the
    // resource leak is harmless.
    (void)d;
}
void cshim_wgpuDeviceRelease(WGPUDevice d) {
    wgpuDeviceRelease(d);
}
void cshim_wgpuQueueSubmit(WGPUQueue q, size_t count, WGPUCommandBuffer const *bufs) {
    wgpuQueueSubmit(q, count, bufs);
}
void cshim_wgpuQueueRelease(WGPUQueue q) {
    wgpuQueueRelease(q);
}
void cshim_wgpuBufferRelease(WGPUBuffer b) {
    wgpuBufferRelease(b);
}
void cshim_wgpuShaderModuleRelease(WGPUShaderModule m) {
    wgpuShaderModuleRelease(m);
}
void cshim_wgpuBindGroupLayoutRelease(WGPUBindGroupLayout l) {
    wgpuBindGroupLayoutRelease(l);
}
void cshim_wgpuBindGroupRelease(WGPUBindGroup g) {
    wgpuBindGroupRelease(g);
}
void cshim_wgpuPipelineLayoutRelease(WGPUPipelineLayout l) {
    wgpuPipelineLayoutRelease(l);
}
void cshim_wgpuComputePipelineRelease(WGPUComputePipeline p) {
    wgpuComputePipelineRelease(p);
}
void cshim_wgpuCommandEncoderRelease(WGPUCommandEncoder e) {
    wgpuCommandEncoderRelease(e);
}
void cshim_wgpuComputePassEncoderSetPipeline(WGPUComputePassEncoder e, WGPUComputePipeline p) {
    wgpuComputePassEncoderSetPipeline(e, p);
}
void cshim_wgpuComputePassEncoderDispatchWorkgroups(WGPUComputePassEncoder e, uint32_t x, uint32_t y, uint32_t z) {
    wgpuComputePassEncoderDispatchWorkgroups(e, x, y, z);
}
void cshim_wgpuComputePassEncoderEnd(WGPUComputePassEncoder e) {
    wgpuComputePassEncoderEnd(e);
}
void cshim_wgpuComputePassEncoderRelease(WGPUComputePassEncoder e) {
    wgpuComputePassEncoderRelease(e);
}
void cshim_wgpuCommandBufferRelease(WGPUCommandBuffer b) {
    wgpuCommandBufferRelease(b);
}

// ═══════════════════════════════════════════════════════════════════
// C++ type bridge definitions
// ═══════════════════════════════════════════════════════════════════

// Dawn:   wgpuQueueWriteBuffer(queue, buffer, offset, void const *data, size_t size)
// WebKit: wgpuQueueWriteBuffer(queue, buffer, offset, std::span<uint8_t> data)
void cshim_wgpuQueueWriteBuffer(WGPUQueue q, WGPUBuffer b, uint64_t offset, void const *data, size_t size) {
    auto span = std::span<uint8_t>(
        const_cast<uint8_t *>(static_cast<uint8_t const *>(data)), size);
    wgpuQueueWriteBuffer(q, b, offset, span);
}

// Dawn:   wgpuComputePassEncoderSetBindGroup(enc, idx, group, dynOffsetCount, dynOffsets)
// WebKit: wgpuComputePassEncoderSetBindGroup(enc, idx, group, std::optional<Vector<uint32_t>>&&)
void cshim_wgpuComputePassEncoderSetBindGroup(
    WGPUComputePassEncoder e, uint32_t idx, WGPUBindGroup g,
    size_t dynOffsetCount, uint32_t const *dynOffsets
) {
    if (dynOffsetCount == 0 || dynOffsets == nullptr) {
        wgpuComputePassEncoderSetBindGroup(e, idx, g, std::nullopt);
    } else {
        Vector<uint32_t> offsets;
        offsets.reserveInitialCapacity(dynOffsetCount);
        for (size_t i = 0; i < dynOffsetCount; ++i)
            offsets.append(dynOffsets[i]);
        wgpuComputePassEncoderSetBindGroup(e, idx, g, std::move(offsets));
    }
}

// ═══════════════════════════════════════════════════════════════════
// Callback pattern bridge — queue work done
// ═══════════════════════════════════════════════════════════════════

DawnFuture cshim_wgpuQueueOnSubmittedWorkDone(
    WGPUQueue q, DawnQueueWorkDoneCBInfo info
) {
    auto *bridge = new QueueDoneBridge{info.callback, info.userdata1, info.userdata2};
    wgpuQueueOnSubmittedWorkDone(q, queue_done_cb_wrapper, bridge);
    return DawnFuture{1};
}

// ═══════════════════════════════════════════════════════════════════
// Extended API surface — required by doe-zig-runtime's full loader.
// ═══════════════════════════════════════════════════════════════════

// ── Dawn descriptor types for extended API ──────────────────────────

struct DawnQuerySetDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    uint32_t type;
    uint32_t count;
};

struct DawnTextureDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    DawnFlags usage;        // uint64_t in Dawn
    uint32_t dimension;
    uint32_t width;
    uint32_t height;
    uint32_t depthOrArrayLayers;
    uint32_t format;
    uint32_t mipLevelCount;
    uint32_t sampleCount;
    size_t viewFormatCount;
    uint32_t const* viewFormats;
};

struct DawnTextureViewDescriptor {
    DawnChainedStruct* nextInChain;
    DawnStringView label;
    uint32_t format;
    uint32_t dimension;
    uint32_t baseMipLevel;
    uint32_t mipLevelCount;
    uint32_t baseArrayLayer;
    uint32_t arrayLayerCount;
    uint32_t aspect;
    DawnFlags usage;        // uint64_t in Dawn
};

// Dawn's TexelCopy types — same binary layout as WebKit's ImageCopy types
// for the fields that matter (offset, bytesPerRow, rowsPerImage, buffer/texture, etc.)
struct DawnTexelCopyBufferLayout {
    uint64_t offset;
    uint32_t bytesPerRow;
    uint32_t rowsPerImage;
};

struct DawnTexelCopyBufferInfo {
    DawnTexelCopyBufferLayout layout;
    WGPUBuffer buffer;
};

struct DawnTexelCopyTextureInfo {
    WGPUTexture texture;
    uint32_t mipLevel;
    uint32_t originX;
    uint32_t originY;
    uint32_t originZ;
    uint32_t aspect;
};

struct DawnExtent3D {
    uint32_t width;
    uint32_t height;
    uint32_t depthOrArrayLayers;
};

// Dawn buffer map callback (dual-userdata + WGPUFuture return)
typedef void (*DawnBufferMapCB)(
    uint32_t status, DawnStringView msg, void* ud1, void* ud2);

struct DawnBufferMapCBInfo {
    void*            nextInChain;
    uint32_t         mode;
    DawnBufferMapCB  callback;
    void*            userdata1;
    void*            userdata2;
};

// ── Status translation for buffer map ───────────────────────────────
// Dawn MapAsyncStatus:  Success=1
// WebKit BufferMapAsyncStatus: Success=0
static uint32_t webkitBufferMapStatusToDawn(WGPUBufferMapAsyncStatus ws) {
    switch (ws) {
        case WGPUBufferMapAsyncStatus_Success: return 1;
        default:                                return 2; // Dawn Error
    }
}

// ── Buffer map callback adapter ─────────────────────────────────────
struct BufferMapBridge {
    DawnBufferMapCB cb;
    void* ud1;
    void* ud2;
};

static void buffer_map_cb_wrapper(WGPUBufferMapAsyncStatus status, void* userdata) {
    auto* b = static_cast<BufferMapBridge*>(userdata);
    DawnStringView sv = { nullptr, 0 };
    b->cb(webkitBufferMapStatusToDawn(status), sv, b->ud1, b->ud2);
    delete b;
}

// ── Forward declarations with asm labels ────────────────────────────

// Buffer mapping
SHIM_EXPORT DawnFuture cshim_wgpuBufferMapAsync(WGPUBuffer b, uint32_t mode, size_t offset, size_t size, DawnBufferMapCBInfo info)  asm("_wgpuBufferMapAsync");
SHIM_EXPORT void const* cshim_wgpuBufferGetConstMappedRange(WGPUBuffer b, size_t offset, size_t size)                                asm("_wgpuBufferGetConstMappedRange");
SHIM_EXPORT void*       cshim_wgpuBufferGetMappedRange(WGPUBuffer b, size_t offset, size_t size)                                     asm("_wgpuBufferGetMappedRange");
SHIM_EXPORT void        cshim_wgpuBufferUnmap(WGPUBuffer b)                                                                          asm("_wgpuBufferUnmap");

// Copy operations
SHIM_EXPORT void cshim_wgpuCommandEncoderCopyBufferToBuffer(WGPUCommandEncoder e, WGPUBuffer src, uint64_t srcOff, WGPUBuffer dst, uint64_t dstOff, uint64_t size) asm("_wgpuCommandEncoderCopyBufferToBuffer");
SHIM_EXPORT void cshim_wgpuCommandEncoderCopyBufferToTexture(WGPUCommandEncoder e, DawnTexelCopyBufferInfo const* src, DawnTexelCopyTextureInfo const* dst, DawnExtent3D const* sz) asm("_wgpuCommandEncoderCopyBufferToTexture");
SHIM_EXPORT void cshim_wgpuCommandEncoderCopyTextureToBuffer(WGPUCommandEncoder e, DawnTexelCopyTextureInfo const* src, DawnTexelCopyBufferInfo const* dst, DawnExtent3D const* sz) asm("_wgpuCommandEncoderCopyTextureToBuffer");
SHIM_EXPORT void cshim_wgpuCommandEncoderCopyTextureToTexture(WGPUCommandEncoder e, DawnTexelCopyTextureInfo const* src, DawnTexelCopyTextureInfo const* dst, DawnExtent3D const* sz) asm("_wgpuCommandEncoderCopyTextureToTexture");

// Query set
SHIM_EXPORT WGPUQuerySet cshim_wgpuDeviceCreateQuerySet(WGPUDevice d, DawnQuerySetDescriptor const* desc)                            asm("_wgpuDeviceCreateQuerySet");
SHIM_EXPORT void         cshim_wgpuCommandEncoderResolveQuerySet(WGPUCommandEncoder e, WGPUQuerySet qs, uint32_t first, uint32_t count, WGPUBuffer dst, uint64_t dstOff) asm("_wgpuCommandEncoderResolveQuerySet");
SHIM_EXPORT void         cshim_wgpuQuerySetRelease(WGPUQuerySet qs)                                                                   asm("_wgpuQuerySetRelease");

// Texture
SHIM_EXPORT WGPUTexture     cshim_wgpuDeviceCreateTexture(WGPUDevice d, DawnTextureDescriptor const* desc)                            asm("_wgpuDeviceCreateTexture");
SHIM_EXPORT WGPUTextureView cshim_wgpuTextureCreateView(WGPUTexture t, DawnTextureViewDescriptor const* desc)                         asm("_wgpuTextureCreateView");
SHIM_EXPORT void             cshim_wgpuTextureRelease(WGPUTexture t)                                                                  asm("_wgpuTextureRelease");
SHIM_EXPORT void             cshim_wgpuTextureViewRelease(WGPUTextureView v)                                                          asm("_wgpuTextureViewRelease");

// Instance wait (Dawn-specific, no WebKit equivalent — stub for process-events mode)
SHIM_EXPORT uint32_t cshim_wgpuInstanceWaitAny(WGPUInstance i, size_t futureCount, void* futures, uint64_t timeoutNS) asm("_wgpuInstanceWaitAny");

// ═══════════════════════════════════════════════════════════════════
// Extended API implementations
// ═══════════════════════════════════════════════════════════════════

// ── Buffer mapping ──────────────────────────────────────────────────

DawnFuture cshim_wgpuBufferMapAsync(WGPUBuffer b, uint32_t mode, size_t offset, size_t size, DawnBufferMapCBInfo info) {
    auto *bridge = new BufferMapBridge{info.callback, info.userdata1, info.userdata2};
    wgpuBufferMapAsync(b, static_cast<WGPUMapModeFlags>(mode), offset, size, buffer_map_cb_wrapper, bridge);
    return DawnFuture{1};
}

void const* cshim_wgpuBufferGetConstMappedRange(WGPUBuffer b, size_t offset, size_t size) {
    // WebKit only has getMappedRange (non-const). Return it as const.
    auto span = wgpuBufferGetMappedRange(b, offset, size);
    return span.data();
}

void* cshim_wgpuBufferGetMappedRange(WGPUBuffer b, size_t offset, size_t size) {
    auto span = wgpuBufferGetMappedRange(b, offset, size);
    return span.data();
}

void cshim_wgpuBufferUnmap(WGPUBuffer b) {
    wgpuBufferUnmap(b);
}

// ── Copy operations ─────────────────────────────────────────────────

void cshim_wgpuCommandEncoderCopyBufferToBuffer(
    WGPUCommandEncoder e, WGPUBuffer src, uint64_t srcOff,
    WGPUBuffer dst, uint64_t dstOff, uint64_t size
) {
    wgpuCommandEncoderCopyBufferToBuffer(e, src, srcOff, dst, dstOff, size);
}

void cshim_wgpuCommandEncoderCopyBufferToTexture(
    WGPUCommandEncoder e, DawnTexelCopyBufferInfo const* src,
    DawnTexelCopyTextureInfo const* dst, DawnExtent3D const* sz
) {
    WGPUImageCopyBuffer webkit_src = {};
    webkit_src.layout.offset = src->layout.offset;
    webkit_src.layout.bytesPerRow = src->layout.bytesPerRow;
    webkit_src.layout.rowsPerImage = src->layout.rowsPerImage;
    webkit_src.buffer = src->buffer;

    WGPUImageCopyTexture webkit_dst = {};
    webkit_dst.texture = dst->texture;
    webkit_dst.mipLevel = dst->mipLevel;
    webkit_dst.origin = { dst->originX, dst->originY, dst->originZ };
    webkit_dst.aspect = translateTextureAspect(dst->aspect);

    WGPUExtent3D extent = { sz->width, sz->height, sz->depthOrArrayLayers };
    wgpuCommandEncoderCopyBufferToTexture(e, &webkit_src, &webkit_dst, &extent);
}

void cshim_wgpuCommandEncoderCopyTextureToBuffer(
    WGPUCommandEncoder e, DawnTexelCopyTextureInfo const* src,
    DawnTexelCopyBufferInfo const* dst, DawnExtent3D const* sz
) {
    WGPUImageCopyTexture webkit_src = {};
    webkit_src.texture = src->texture;
    webkit_src.mipLevel = src->mipLevel;
    webkit_src.origin = { src->originX, src->originY, src->originZ };
    webkit_src.aspect = translateTextureAspect(src->aspect);

    WGPUImageCopyBuffer webkit_dst = {};
    webkit_dst.layout.offset = dst->layout.offset;
    webkit_dst.layout.bytesPerRow = dst->layout.bytesPerRow;
    webkit_dst.layout.rowsPerImage = dst->layout.rowsPerImage;
    webkit_dst.buffer = dst->buffer;

    WGPUExtent3D extent = { sz->width, sz->height, sz->depthOrArrayLayers };
    wgpuCommandEncoderCopyTextureToBuffer(e, &webkit_src, &webkit_dst, &extent);
}

void cshim_wgpuCommandEncoderCopyTextureToTexture(
    WGPUCommandEncoder e, DawnTexelCopyTextureInfo const* src,
    DawnTexelCopyTextureInfo const* dst, DawnExtent3D const* sz
) {
    WGPUImageCopyTexture webkit_src = {};
    webkit_src.texture = src->texture;
    webkit_src.mipLevel = src->mipLevel;
    webkit_src.origin = { src->originX, src->originY, src->originZ };
    webkit_src.aspect = translateTextureAspect(src->aspect);

    WGPUImageCopyTexture webkit_dst = {};
    webkit_dst.texture = dst->texture;
    webkit_dst.mipLevel = dst->mipLevel;
    webkit_dst.origin = { dst->originX, dst->originY, dst->originZ };
    webkit_dst.aspect = translateTextureAspect(dst->aspect);

    WGPUExtent3D extent = { sz->width, sz->height, sz->depthOrArrayLayers };
    wgpuCommandEncoderCopyTextureToTexture(e, &webkit_src, &webkit_dst, &extent);
}

// ── Query set ───────────────────────────────────────────────────────

WGPUQuerySet cshim_wgpuDeviceCreateQuerySet(WGPUDevice d, DawnQuerySetDescriptor const* desc) {
    WGPUQuerySetDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.type = translateQueryType(desc->type);
    webkit_desc.count = desc->count;
    return wgpuDeviceCreateQuerySet(d, &webkit_desc);
}

void cshim_wgpuCommandEncoderResolveQuerySet(
    WGPUCommandEncoder e, WGPUQuerySet qs, uint32_t first,
    uint32_t count, WGPUBuffer dst, uint64_t dstOff
) {
    wgpuCommandEncoderResolveQuerySet(e, qs, first, count, dst, dstOff);
}

void cshim_wgpuQuerySetRelease(WGPUQuerySet qs) {
    wgpuQuerySetRelease(qs);
}

// ── Texture ─────────────────────────────────────────────────────────

WGPUTexture cshim_wgpuDeviceCreateTexture(WGPUDevice d, DawnTextureDescriptor const* desc) {
    WGPUTextureDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.usage = static_cast<WGPUTextureUsageFlags>(desc->usage);  // truncate 64→32
    webkit_desc.dimension = translateTextureDimension(desc->dimension);
    webkit_desc.size = { desc->width, desc->height, desc->depthOrArrayLayers };
    webkit_desc.format = static_cast<WGPUTextureFormat>(desc->format);
    webkit_desc.mipLevelCount = desc->mipLevelCount;
    webkit_desc.sampleCount = desc->sampleCount;
    webkit_desc.viewFormatCount = desc->viewFormatCount;
    webkit_desc.viewFormats = reinterpret_cast<WGPUTextureFormat const*>(desc->viewFormats);
    return wgpuDeviceCreateTexture(d, &webkit_desc);
}

WGPUTextureView cshim_wgpuTextureCreateView(WGPUTexture t, DawnTextureViewDescriptor const* desc) {
    if (!desc) return wgpuTextureCreateView(t, nullptr);

    WGPUTextureViewDescriptor webkit_desc = {};
    webkit_desc.label = nullptr;
    webkit_desc.format = static_cast<WGPUTextureFormat>(desc->format);
    webkit_desc.dimension = static_cast<WGPUTextureViewDimension>(desc->dimension);
    webkit_desc.baseMipLevel = desc->baseMipLevel;
    webkit_desc.mipLevelCount = desc->mipLevelCount;
    webkit_desc.baseArrayLayer = desc->baseArrayLayer;
    webkit_desc.arrayLayerCount = desc->arrayLayerCount;
    webkit_desc.aspect = translateTextureAspect(desc->aspect);
    webkit_desc.usage = static_cast<WGPUTextureUsageFlags>(desc->usage);  // truncate 64→32
    return wgpuTextureCreateView(t, &webkit_desc);
}

void cshim_wgpuTextureRelease(WGPUTexture t) {
    wgpuTextureRelease(t);
}

void cshim_wgpuTextureViewRelease(WGPUTextureView v) {
    wgpuTextureViewRelease(v);
}

// ── Instance wait (stub) ────────────────────────────────────────────
// WebKit has no wgpuInstanceWaitAny. The runtime uses process-events
// mode for webkit lanes, so this should never be called. If it is,
// return TimedOut (Dawn value 3) so the caller falls back gracefully.
uint32_t cshim_wgpuInstanceWaitAny(WGPUInstance i, size_t futureCount, void* futures, uint64_t timeoutNS) {
    (void)i; (void)futureCount; (void)futures; (void)timeoutNS;
    return 3; // WGPUWaitStatus_TimedOut
}

// ── Shim identity probe ─────────────────────────────────────────────
// Returns a fixed identity string. The runtime calls
// dlsym("doe_shim_get_backend_identity") after loading the WebGPU
// library. If this symbol resolves, the library is the WebKit shim.
// Dawn does not export this symbol.
char const* doe_shim_get_backend_identity(void) {
    return "webkit_webgpu_cshim_v1";
}
