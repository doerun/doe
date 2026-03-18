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
#include <stdio.h>

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
#define WGPU_WAIT_STATUS_TIMED_OUT 2
#define WGPU_WAIT_STATUS_ERROR 3
#define WGPU_STATUS_SUCCESS 1
#define WGPU_MAP_ASYNC_STATUS_SUCCESS 1
#define WGPU_REQUEST_STATUS_SUCCESS 1
#define WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS 2
#define DOE_DEFAULT_TIMEOUT_NS 2000000000ULL
#define DOE_WAIT_SLICE_NS 1000ULL
#define DOE_ERROR_BUF_CAP 512

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
    uint32_t group;
    uint32_t binding;
    uint32_t kind;
    uint32_t addr_space;
    uint32_t access;
} DoeShaderBindingInfo;

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
    uint32_t x;
    uint32_t y;
    uint32_t z;
} WGPUOrigin3D;

typedef struct {
    uint64_t offset;
    uint32_t bytesPerRow;
    uint32_t rowsPerImage;
} WGPUTexelCopyBufferLayout;

typedef struct {
    WGPUTexelCopyBufferLayout layout;
    WGPUBuffer buffer;
} WGPUTexelCopyBufferInfo;

typedef struct {
    WGPUTexture texture;
    uint32_t mipLevel;
    WGPUOrigin3D origin;
    uint32_t aspect;
} WGPUTexelCopyTextureInfo;

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
    WGPUTextureView view;
    uint32_t depthLoadOp;
    uint32_t depthStoreOp;
    float depthClearValue;
    WGPUBool depthReadOnly;
    uint32_t stencilLoadOp;
    uint32_t stencilStoreOp;
    uint32_t stencilClearValue;
    WGPUBool stencilReadOnly;
} WGPURenderPassDepthStencilAttachment;

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
    void* nextInChain;
    WGPUStringView key;
    double value;
} WGPUConstantEntry;

typedef struct {
    void* nextInChain;
    WGPUShaderModule module;
    WGPUStringView entryPoint;
    size_t constantCount;
    const WGPUConstantEntry* constants;
    size_t bufferCount;
    const void* buffers;
} WGPURenderVertexState;

typedef struct {
    void* nextInChain;
    uint32_t format;
    uint64_t offset;
    uint32_t shaderLocation;
} WGPURenderVertexAttribute;

typedef struct {
    void* nextInChain;
    uint32_t stepMode;
    uint64_t arrayStride;
    size_t attributeCount;
    const WGPURenderVertexAttribute* attributes;
} WGPURenderVertexBufferLayout;

typedef struct {
    void* nextInChain;
    uint32_t format;
    const void* blend;
    uint64_t writeMask;
} WGPURenderColorTargetState;

typedef struct {
    void* nextInChain;
    WGPUShaderModule module;
    WGPUStringView entryPoint;
    size_t constantCount;
    const WGPUConstantEntry* constants;
    size_t targetCount;
    const WGPURenderColorTargetState* targets;
} WGPURenderFragmentState;

typedef struct {
    void* nextInChain;
    uint32_t topology;
    uint32_t stripIndexFormat;
    uint32_t frontFace;
    uint32_t cullMode;
    WGPUBool unclippedDepth;
} WGPURenderPrimitiveState;

typedef struct {
    void* nextInChain;
    uint32_t count;
    uint32_t mask;
    WGPUBool alphaToCoverageEnabled;
} WGPURenderMultisampleState;

typedef struct {
    uint32_t compare;
    uint32_t failOp;
    uint32_t depthFailOp;
    uint32_t passOp;
} WGPURenderStencilFaceState;

typedef struct {
    void* nextInChain;
    uint32_t format;
    uint32_t depthWriteEnabled;
    uint32_t depthCompare;
    WGPURenderStencilFaceState stencilFront;
    WGPURenderStencilFaceState stencilBack;
    uint32_t stencilReadMask;
    uint32_t stencilWriteMask;
    int32_t depthBias;
    float depthBiasSlopeScale;
    float depthBiasClamp;
} WGPURenderDepthStencilState;

typedef struct {
    void* nextInChain;
    WGPUStringView label;
    WGPUPipelineLayout layout;
    WGPURenderVertexState vertex;
    WGPURenderPrimitiveState primitive;
    const WGPURenderDepthStencilState* depthStencil;
    WGPURenderMultisampleState multisample;
    const WGPURenderFragmentState* fragment;
} WGPURenderPipelineDescriptor;

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
DECL_PFN(uint32_t, wgpuAdapterGetLimits, (WGPUAdapter, void*));
DECL_PFN(WGPUFuture, wgpuAdapterRequestDevice, (WGPUAdapter, const void*, WGPURequestDeviceCallbackInfo));
DECL_PFN(void, wgpuDeviceRelease, (WGPUDevice));
DECL_PFN(WGPUBool, wgpuDeviceHasFeature, (WGPUDevice, uint32_t));
DECL_PFN(uint32_t, wgpuDeviceGetLimits, (WGPUDevice, void*));
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
DECL_PFN(void, wgpuCommandEncoderCopyBufferToTexture, (WGPUCommandEncoder, const WGPUTexelCopyBufferInfo*, const WGPUTexelCopyTextureInfo*, const WGPUExtent3D*));
DECL_PFN(void, wgpuCommandEncoderCopyTextureToBuffer, (WGPUCommandEncoder, const WGPUTexelCopyTextureInfo*, const WGPUTexelCopyBufferInfo*, const WGPUExtent3D*));
DECL_PFN(void, doeNativeCommandEncoderCopyBufferToTexture, (WGPUCommandEncoder, WGPUBuffer, uint64_t, uint32_t, uint32_t, WGPUTexture, uint32_t, uint32_t, uint32_t, uint32_t));
DECL_PFN(void, doeNativeCommandEncoderCopyTextureToBuffer, (WGPUCommandEncoder, WGPUTexture, uint32_t, WGPUBuffer, uint64_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t));
DECL_PFN(WGPUCommandBuffer, wgpuCommandEncoderFinish, (WGPUCommandEncoder, const WGPUCommandBufferDescriptor*));
DECL_PFN(void, wgpuComputePassEncoderSetPipeline, (WGPUComputePassEncoder, WGPUComputePipeline));
DECL_PFN(void, wgpuComputePassEncoderSetBindGroup, (WGPUComputePassEncoder, uint32_t, WGPUBindGroup, size_t, const uint32_t*));
DECL_PFN(void, wgpuComputePassEncoderDispatchWorkgroups, (WGPUComputePassEncoder, uint32_t, uint32_t, uint32_t));
DECL_PFN(void, wgpuComputePassEncoderDispatchWorkgroupsIndirect, (WGPUComputePassEncoder, WGPUBuffer, uint64_t));
DECL_PFN(void, doeNativeComputePassDispatchIndirect, (WGPUComputePassEncoder, WGPUBuffer, uint64_t));
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
DECL_PFN(void, wgpuRenderPassEncoderSetBindGroup, (WGPURenderPassEncoder, uint32_t, WGPUBindGroup, size_t, const uint32_t*));
DECL_PFN(void, wgpuRenderPassEncoderSetVertexBuffer, (WGPURenderPassEncoder, uint32_t, WGPUBuffer, uint64_t, uint64_t));
DECL_PFN(void, wgpuRenderPassEncoderSetIndexBuffer, (WGPURenderPassEncoder, WGPUBuffer, uint32_t, uint64_t, uint64_t));
DECL_PFN(void, wgpuRenderPassEncoderDraw, (WGPURenderPassEncoder, uint32_t, uint32_t, uint32_t, uint32_t));
DECL_PFN(void, wgpuRenderPassEncoderDrawIndexed, (WGPURenderPassEncoder, uint32_t, uint32_t, uint32_t, int32_t, uint32_t));
DECL_PFN(void, wgpuRenderPassEncoderEnd, (WGPURenderPassEncoder));
DECL_PFN(void, wgpuRenderPassEncoderRelease, (WGPURenderPassEncoder));
DECL_PFN(uint32_t, doeNativeAdapterGetLimits, (WGPUAdapter, void*));
DECL_PFN(uint32_t, doeNativeDeviceGetLimits, (WGPUDevice, void*));
DECL_PFN(uint32_t, doeNativeAdapterHasFeature, (WGPUAdapter, uint32_t));
DECL_PFN(uint32_t, doeNativeDeviceHasFeature, (WGPUDevice, uint32_t));
DECL_PFN(size_t, doeNativeCopyLastErrorMessage, (char*, size_t));
DECL_PFN(size_t, doeNativeCopyLastErrorStage, (char*, size_t));
DECL_PFN(size_t, doeNativeCopyLastErrorKind, (char*, size_t));
DECL_PFN(uint32_t, doeNativeGetLastErrorLine, (void));
DECL_PFN(uint32_t, doeNativeGetLastErrorColumn, (void));
DECL_PFN(uint32_t, doeNativeCheckShaderSource, (const char*, size_t));
DECL_PFN(size_t, doeNativeShaderModuleGetBindings, (WGPUShaderModule, DoeShaderBindingInfo*, size_t));
DECL_PFN(WGPUFuture, doeNativeAdapterRequestDevice, (WGPUAdapter, const void*, WGPURequestDeviceCallbackInfo));

/* New symbols added for 14-binding expansion */
typedef uint32_t (*FnAdapterGetPreferredCanvasFormat)(void* adapter);
typedef void (*FnDeviceAddEventListener)(void* dev, const char* type, size_t type_len, void* callback, void* userdata);
typedef void (*FnDeviceRemoveEventListener)(void* dev, const char* type, size_t type_len, void* callback, void* userdata);
typedef void* (*FnDeviceImportExternalTexture)(void* dev, const void* descriptor);
typedef void (*FnBindingCommandsSetImmediates)(void* encoder, uint32_t index, const uint8_t* data, size_t data_len);
typedef void (*FnComputePassSetImmediates)(void* encoder, uint32_t index, const uint8_t* data, size_t data_len);
typedef void (*FnRenderPassSetImmediates)(void* encoder, uint32_t index, const uint8_t* data, size_t data_len);
typedef void (*FnRenderBundleEncoderSetImmediates)(void* encoder, uint32_t index, const uint8_t* data, size_t data_len);

static FnAdapterGetPreferredCanvasFormat pfn_doeNativeAdapterGetPreferredCanvasFormat = NULL;
static FnDeviceAddEventListener pfn_doeNativeDeviceAddEventListener = NULL;
static FnDeviceRemoveEventListener pfn_doeNativeDeviceRemoveEventListener = NULL;
static FnDeviceImportExternalTexture pfn_doeNativeDeviceImportExternalTexture = NULL;
static FnBindingCommandsSetImmediates pfn_doeNativeBindingCommandsSetImmediates = NULL;
static FnComputePassSetImmediates pfn_doeNativeComputePassSetImmediates = NULL;
static FnRenderPassSetImmediates pfn_doeNativeRenderPassSetImmediates = NULL;
static FnRenderBundleEncoderSetImmediates pfn_doeNativeRenderBundleEncoderSetImmediates = NULL;

/* GPURenderPassEncoder control methods */
typedef void (*FnRenderPassSetViewport)(void* encoder, double x, double y, double width, double height, double min_depth, double max_depth);
typedef void (*FnRenderPassSetScissorRect)(void* encoder, uint32_t x, uint32_t y, uint32_t width, uint32_t height);
typedef void (*FnRenderPassSetBlendConstant)(void* encoder, double r, double g, double b, double a);
typedef void (*FnRenderPassSetStencilReference)(void* encoder, uint32_t reference);
typedef void (*FnRenderPassPushDebugGroup)(void* encoder, const char* label, size_t label_len);
typedef void (*FnRenderPassPopDebugGroup)(void* encoder);
typedef void (*FnRenderPassInsertDebugMarker)(void* encoder, const char* label, size_t label_len);

static FnRenderPassSetViewport pfn_doeNativeRenderPassSetViewport = NULL;
static FnRenderPassSetScissorRect pfn_doeNativeRenderPassSetScissorRect = NULL;
static FnRenderPassSetBlendConstant pfn_doeNativeRenderPassSetBlendConstant = NULL;
static FnRenderPassSetStencilReference pfn_doeNativeRenderPassSetStencilReference = NULL;
static FnRenderPassPushDebugGroup pfn_doeNativeRenderPassPushDebugGroup = NULL;
static FnRenderPassPopDebugGroup pfn_doeNativeRenderPassPopDebugGroup = NULL;
static FnRenderPassInsertDebugMarker pfn_doeNativeRenderPassInsertDebugMarker = NULL;

/* GPUAdapter.info and GPUShaderModule.getCompilationInfo */
typedef void (*FnAdapterGetInfo)(void* adapter,
    const char** out_vendor, const char** out_arch,
    const char** out_device, const char** out_desc,
    char** out_block);
typedef void (*FnAdapterFreeInfo)(char* block);
typedef const char* (*FnShaderModuleGetCompilationInfo)(void* module);
typedef struct {
    void* next_in_chain;
    uint32_t mode;
    void (*callback)(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2);
    void* userdata1;
    void* userdata2;
} WGPUPopErrorScopeCallbackInfo2;
typedef void (*FnDevicePushErrorScope)(void* device, uint32_t filter);
typedef WGPUFuture (*FnDevicePopErrorScope)(void* device, WGPUPopErrorScopeCallbackInfo2 callback_info);
typedef void (*FnDeviceSetUncapturedErrorCallback)(
    void* device,
    void (*callback)(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2),
    void* userdata1,
    void* userdata2);
typedef void (*FnDeviceRegisterLostCallback)(
    void* device,
    void (*callback)(uint32_t reason, const char* message_ptr, size_t message_len, void* userdata),
    void* userdata);

static FnAdapterGetInfo  pfn_doeNativeAdapterGetInfo = NULL;
static FnAdapterFreeInfo pfn_doeNativeAdapterFreeInfo = NULL;
static FnShaderModuleGetCompilationInfo pfn_doeNativeShaderModuleGetCompilationInfo = NULL;
static FnDevicePushErrorScope pfn_doeNativeDevicePushErrorScope = NULL;
static FnDevicePopErrorScope pfn_doeNativeDevicePopErrorScope = NULL;
static FnDevicePushErrorScope pfn_wgpuDevicePushErrorScope = NULL;
static FnDevicePopErrorScope pfn_wgpuDevicePopErrorScope = NULL;
static FnDeviceSetUncapturedErrorCallback pfn_doeNativeDeviceSetUncapturedErrorCallback = NULL;
static FnDeviceRegisterLostCallback pfn_doeNativeDeviceRegisterLostCallback = NULL;

/* renderPipelineGetBindGroupLayout — doe-native reflect path */
typedef void* (*FnRenderPipelineGetBindGroupLayout)(void* pipeline, uint32_t group_index);

static FnRenderPipelineGetBindGroupLayout pfn_doeNativeRenderPipelineGetBindGroupLayout = NULL;

/* clearBuffer / copyTextureToTexture / writeTexture */
typedef void (*FnCommandEncoderClearBuffer)(void* encoder, void* buffer, uint64_t offset, uint64_t size);
typedef void (*FnCommandEncoderCopyTextureToTexture)(
    void* encoder,
    void* src_texture, uint32_t src_mip, uint32_t src_slice, uint32_t src_x, uint32_t src_y, uint32_t src_z,
    void* dst_texture, uint32_t dst_mip, uint32_t dst_slice, uint32_t dst_x, uint32_t dst_y, uint32_t dst_z,
    uint32_t width, uint32_t height, uint32_t depth_or_layers);
typedef void (*FnWgpuCommandEncoderCopyTextureToTexture)(
    WGPUCommandEncoder encoder,
    const WGPUTexelCopyTextureInfo* source,
    const WGPUTexelCopyTextureInfo* destination,
    const WGPUExtent3D* copy_size);
typedef void (*FnQueueWriteTexture)(
    void* queue, void* texture,
    const void* data, size_t data_len,
    uint32_t bytes_per_row, uint32_t rows_per_image,
    uint32_t dst_x, uint32_t dst_y, uint32_t dst_z,
    uint32_t dst_mip, uint32_t dst_slice,
    uint32_t width, uint32_t height, uint32_t depth_or_layers);

static FnCommandEncoderClearBuffer         pfn_doeNativeCommandEncoderClearBuffer = NULL;
static FnCommandEncoderCopyTextureToTexture pfn_doeNativeCommandEncoderCopyTextureToTexture = NULL;
static FnWgpuCommandEncoderCopyTextureToTexture pfn_wgpuCommandEncoderCopyTextureToTexture = NULL;
static FnQueueWriteTexture                 pfn_doeNativeQueueWriteTexture = NULL;

typedef struct DeviceCallbackBinding {
    void* device;
    napi_threadsafe_function tsfn;
    napi_ref value_ref;
    struct DeviceCallbackBinding* next;
} DeviceCallbackBinding;

typedef struct {
    napi_env env;
    napi_deferred deferred;
} PopErrorScopeRequest;

typedef struct {
    uint32_t error_type;
    char* message;
} UncapturedCallbackData;

typedef struct {
    uint32_t reason;
    char* message;
} LostCallbackData;

static DeviceCallbackBinding* g_uncaptured_bindings = NULL;
static DeviceCallbackBinding* g_lost_bindings = NULL;

/* GPURenderBundleEncoder / GPURenderBundle */
typedef void* (*FnDeviceCreateRenderBundleEncoder)(void* device, const void* desc);
typedef void  (*FnRenderBundleEncoderRelease)(void* encoder);
typedef void  (*FnRenderBundleEncoderSetPipeline)(void* encoder, void* pipeline);
typedef void  (*FnRenderBundleEncoderSetBindGroup)(void* encoder, uint32_t index, void* bind_group, size_t dynamic_offset_count, const uint32_t* dynamic_offsets);
typedef void  (*FnRenderBundleEncoderSetVertexBuffer)(void* encoder, uint32_t slot, void* buffer, uint64_t offset, uint64_t size);
typedef void  (*FnRenderBundleEncoderSetIndexBuffer)(void* encoder, void* buffer, uint32_t format, uint64_t offset, uint64_t size);
typedef void  (*FnRenderBundleEncoderDraw)(void* encoder, uint32_t vertex_count, uint32_t instance_count, uint32_t first_vertex, uint32_t first_instance);
typedef void  (*FnRenderBundleEncoderDrawIndexed)(void* encoder, uint32_t index_count, uint32_t instance_count, uint32_t first_index, int32_t base_vertex, uint32_t first_instance);
typedef void* (*FnRenderBundleEncoderFinish)(void* encoder, const void* desc);
typedef void  (*FnRenderBundleRelease)(void* bundle);

static FnDeviceCreateRenderBundleEncoder   pfn_doeNativeDeviceCreateRenderBundleEncoder = NULL;
static FnRenderBundleEncoderRelease        pfn_doeNativeRenderBundleEncoderRelease = NULL;
static FnRenderBundleEncoderSetPipeline    pfn_doeNativeRenderBundleEncoderSetPipeline = NULL;
static FnRenderBundleEncoderSetBindGroup   pfn_doeNativeRenderBundleEncoderSetBindGroup = NULL;
static FnRenderBundleEncoderSetVertexBuffer pfn_doeNativeRenderBundleEncoderSetVertexBuffer = NULL;
static FnRenderBundleEncoderSetIndexBuffer  pfn_doeNativeRenderBundleEncoderSetIndexBuffer = NULL;
static FnRenderBundleEncoderDraw           pfn_doeNativeRenderBundleEncoderDraw = NULL;
static FnRenderBundleEncoderDrawIndexed    pfn_doeNativeRenderBundleEncoderDrawIndexed = NULL;
static FnRenderBundleEncoderFinish         pfn_doeNativeRenderBundleEncoderFinish = NULL;
static FnRenderBundleRelease               pfn_doeNativeRenderBundleRelease = NULL;

/* Flat helpers are optional. When absent, the addon assembles the callback-info
 * structs directly and calls the standard WebGPU request entrypoints. */
DECL_PFN(WGPUFuture, doeRequestAdapterFlat, (WGPUInstance, const void*, uint32_t, WGPURequestAdapterCallback, void*, void*));
DECL_PFN(WGPUFuture, doeRequestDeviceFlat, (WGPUAdapter, const void*, uint32_t, WGPURequestDeviceCallback, void*, void*));
DECL_PFN(void, doeNativeQueueFlush, (void*));
DECL_PFN(void, doeNativeComputeDispatchFlush, (void*, void*, void**, uint32_t, uint32_t, uint32_t, uint32_t, void*, uint64_t, void*, uint64_t, uint64_t));
DECL_PFN(WGPUQuerySet, doeNativeDeviceCreateQuerySet, (WGPUDevice, uint32_t, uint32_t));
DECL_PFN(void, doeNativeCommandEncoderWriteTimestamp, (WGPUCommandEncoder, WGPUQuerySet, uint32_t));
DECL_PFN(void, doeNativeCommandEncoderResolveQuerySet, (WGPUCommandEncoder, WGPUQuerySet, uint32_t, uint32_t, WGPUBuffer, uint64_t));
DECL_PFN(void, doeNativeQuerySetDestroy, (WGPUQuerySet));
typedef struct {
    void* nextInChain;
    uint32_t mode;
    WGPUBufferMapCallback callback;
    void* userdata1;
    void* userdata2;
} WGPUBufferMapCallbackInfo;

DECL_PFN(WGPUFuture, doeNativeBufferMapAsync, (WGPUBuffer, uint64_t, size_t, size_t, WGPUBufferMapCallbackInfo));

typedef WGPUFuture (*PFN_wgpuBufferMapAsync2)(WGPUBuffer, uint64_t, size_t, size_t, WGPUBufferMapCallbackInfo);
static PFN_wgpuBufferMapAsync2 pfn_wgpuBufferMapAsync2 = NULL;

static void* g_lib = NULL;
static uint64_t g_timeout_ns = DOE_DEFAULT_TIMEOUT_NS;

static uint64_t current_timeout_ns(void) {
    return g_timeout_ns;
}

static void copy_library_error_message(char* out, size_t out_len) {
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!pfn_doeNativeCopyLastErrorMessage) return;
    pfn_doeNativeCopyLastErrorMessage(out, out_len);
}

static void copy_library_error_meta(PFN_doeNativeCopyLastErrorMessage fn, char* out, size_t out_len) {
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!fn) return;
    fn(out, out_len);
}

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

static napi_value native_direct_resolved_promise(napi_env env, napi_value value);

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

static void copy_string_view_message(WGPUStringView message, char* out, size_t out_len) {
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!message.data || message.length == 0) return;
    size_t copy_len = message.length;
    if (copy_len >= out_len) copy_len = out_len - 1;
    memcpy(out, message.data, copy_len);
    out[copy_len] = '\0';
}

static char* dup_string_view(WGPUStringView message) {
    size_t len = message.data ? message.length : 0;
    char* out = (char*)malloc(len + 1);
    if (!out) return NULL;
    if (len > 0 && message.data) {
        memcpy(out, message.data, len);
    }
    out[len] = '\0';
    return out;
}

static char* dup_c_string(const char* message_ptr, size_t message_len) {
    size_t len = message_ptr ? message_len : 0;
    char* out = (char*)malloc(len + 1);
    if (!out) return NULL;
    if (len > 0 && message_ptr) {
        memcpy(out, message_ptr, len);
    }
    out[len] = '\0';
    return out;
}

static const char* error_type_string(uint32_t error_type) {
    switch (error_type) {
        case 0x00000001: return "no-error";
        case 0x00000002: return "validation";
        case 0x00000003: return "out-of-memory";
        case 0x00000004: return "internal";
        default: return "unknown";
    }
}

static const char* lost_reason_string(uint32_t reason) {
    switch (reason) {
        case 0: return "unknown";
        case 1: return "destroyed";
        case 3: return "callback-cancelled";
        case 4: return "failed-creation";
        default: return "unknown";
    }
}

static DeviceCallbackBinding* binding_take(DeviceCallbackBinding** head, void* device) {
    DeviceCallbackBinding* prev = NULL;
    DeviceCallbackBinding* cur = *head;
    while (cur) {
        if (cur->device == device) {
            if (prev) {
                prev->next = cur->next;
            } else {
                *head = cur->next;
            }
            cur->next = NULL;
            return cur;
        }
        prev = cur;
        cur = cur->next;
    }
    return NULL;
}

static void binding_insert(DeviceCallbackBinding** head, DeviceCallbackBinding* binding) {
    binding->next = *head;
    *head = binding;
}

static void binding_finalize(napi_env env, void* finalize_data, void* finalize_hint) {
    (void)env;
    (void)finalize_hint;
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)finalize_data;
    if (binding && binding->value_ref) {
        napi_delete_reference(env, binding->value_ref);
    }
    free(binding);
}

static void release_binding(DeviceCallbackBinding* binding) {
    if (!binding) return;
    if (binding->tsfn) {
        napi_release_threadsafe_function(binding->tsfn, napi_tsfn_release);
    }
}

static DeviceCallbackBinding* create_device_callback_binding(
    napi_env env,
    void* device,
    napi_value js_cb,
    const char* resource_name,
    napi_threadsafe_function_call_js call_js,
    napi_value retained_value
) {
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)calloc(1, sizeof(DeviceCallbackBinding));
    if (!binding) return NULL;
    binding->device = device;

    napi_value async_name;
    if (napi_create_string_utf8(env, resource_name, NAPI_AUTO_LENGTH, &async_name) != napi_ok) {
        free(binding);
        return NULL;
    }
    if (retained_value != NULL) {
        if (napi_create_reference(env, retained_value, 1, &binding->value_ref) != napi_ok) {
            free(binding);
            return NULL;
        }
    }
    if (napi_create_threadsafe_function(
            env,
            js_cb,
            NULL,
            async_name,
            0,
            1,
            binding,
            binding_finalize,
            NULL,
            call_js,
            &binding->tsfn) != napi_ok) {
        if (binding->value_ref) {
            napi_delete_reference(env, binding->value_ref);
        }
        free(binding);
        return NULL;
    }
    napi_unref_threadsafe_function(env, binding->tsfn);
    return binding;
}

static napi_value create_gpu_error_value(napi_env env, uint32_t error_type, const char* message) {
    napi_value global;
    napi_value error_ctor;
    napi_value message_val;
    napi_value error_val;
    napi_value name_val;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "Error", &error_ctor);
    napi_create_string_utf8(env, message ? message : "", NAPI_AUTO_LENGTH, &message_val);
    napi_new_instance(env, error_ctor, 1, &message_val, &error_val);
    napi_create_string_utf8(env,
        error_type == 0x00000002 ? "GPUValidationError"
        : error_type == 0x00000003 ? "GPUOutOfMemoryError"
        : error_type == 0x00000004 ? "GPUInternalError"
        : "GPUError",
        NAPI_AUTO_LENGTH,
        &name_val);
    napi_set_named_property(env, error_val, "name", name_val);
    return error_val;
}

static void pop_error_scope_native_callback(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    PopErrorScopeRequest* request = (PopErrorScopeRequest*)userdata1;
    if (!request) return;

    napi_value result;
    if (error_type == 0x00000001) {
        napi_get_null(request->env, &result);
    } else {
        char error_message[DOE_ERROR_BUF_CAP];
        copy_string_view_message(message, error_message, sizeof(error_message));
        result = create_gpu_error_value(request->env, error_type, error_message);
    }
    napi_resolve_deferred(request->env, request->deferred, result);
    free(request);
}

static void js_call_uncaptured_error(napi_env env, napi_value js_cb, void* context, void* data) {
    (void)context;
    UncapturedCallbackData* payload = (UncapturedCallbackData*)data;
    if (!payload) return;
    if (env != NULL && js_cb != NULL) {
        napi_value global;
        napi_value undefined_value;
        napi_value error_ctor;
        napi_value message_val;
        napi_value error_val;
        napi_value name_val;
        napi_value event_obj;
        napi_value type_val;
        napi_value error_type_val;
        napi_value args[1];

        napi_get_global(env, &global);
        napi_get_undefined(env, &undefined_value);
        napi_get_named_property(env, global, "Error", &error_ctor);
        napi_create_string_utf8(env, payload->message ? payload->message : "", NAPI_AUTO_LENGTH, &message_val);
        napi_new_instance(env, error_ctor, 1, &message_val, &error_val);
        napi_create_string_utf8(env,
            payload->error_type == 0x00000002 ? "GPUValidationError"
            : payload->error_type == 0x00000003 ? "GPUOutOfMemoryError"
            : payload->error_type == 0x00000004 ? "GPUInternalError"
            : "GPUError",
            NAPI_AUTO_LENGTH,
            &name_val);
        napi_set_named_property(env, error_val, "name", name_val);

        napi_create_object(env, &event_obj);
        napi_create_string_utf8(env, "uncapturederror", NAPI_AUTO_LENGTH, &type_val);
        napi_create_string_utf8(env, error_type_string(payload->error_type), NAPI_AUTO_LENGTH, &error_type_val);
        napi_set_named_property(env, event_obj, "type", type_val);
        napi_set_named_property(env, event_obj, "error", error_val);
        napi_set_named_property(env, event_obj, "message", message_val);
        napi_set_named_property(env, event_obj, "errorType", error_type_val);
        args[0] = event_obj;
        napi_call_function(env, undefined_value, js_cb, 1, args, NULL);
    }
    if (payload->message) free(payload->message);
    free(payload);
}

static void js_call_lost_callback(napi_env env, napi_value js_cb, void* context, void* data) {
    (void)context;
    LostCallbackData* payload = (LostCallbackData*)data;
    if (!payload) return;
    if (env != NULL && js_cb != NULL) {
        napi_value global;
        napi_value undefined_value;
        napi_value result_obj;
        napi_value reason_val;
        napi_value message_val;
        napi_value args[1];

        napi_get_global(env, &global);
        napi_get_undefined(env, &undefined_value);
        napi_create_object(env, &result_obj);
        napi_create_string_utf8(env, lost_reason_string(payload->reason), NAPI_AUTO_LENGTH, &reason_val);
        napi_create_string_utf8(env, payload->message ? payload->message : "", NAPI_AUTO_LENGTH, &message_val);
        napi_set_named_property(env, result_obj, "reason", reason_val);
        napi_set_named_property(env, result_obj, "message", message_val);
        args[0] = result_obj;
        napi_call_function(env, undefined_value, js_cb, 1, args, NULL);
    }
    if (payload->message) free(payload->message);
    free(payload);
}

static void uncaptured_error_native_callback(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)userdata1;
    if (!binding || !binding->tsfn) return;
    UncapturedCallbackData* payload = (UncapturedCallbackData*)malloc(sizeof(UncapturedCallbackData));
    if (!payload) return;
    payload->error_type = error_type;
    payload->message = dup_string_view(message);
    if (napi_call_threadsafe_function(binding->tsfn, payload, napi_tsfn_nonblocking) != napi_ok) {
        if (payload->message) free(payload->message);
        free(payload);
    }
}

static void lost_native_callback(uint32_t reason, const char* message_ptr, size_t message_len, void* userdata) {
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)userdata;
    if (!binding || !binding->tsfn) return;
    LostCallbackData* payload = (LostCallbackData*)malloc(sizeof(LostCallbackData));
    if (!payload) return;
    payload->reason = reason;
    payload->message = dup_c_string(message_ptr, message_len);
    if (napi_call_threadsafe_function(binding->tsfn, payload, napi_tsfn_nonblocking) != napi_ok) {
        if (payload->message) free(payload->message);
        free(payload);
    }
    binding_take(&g_lost_bindings, binding->device);
    release_binding(binding);
}

static napi_value throw_status_error(napi_env env, const char* code, const char* prefix, uint32_t status, const char* detail) {
    char msg[DOE_ERROR_BUF_CAP];
    if (detail && detail[0] != '\0') {
        snprintf(msg, sizeof(msg), "%s (status=%u, detail=%s)", prefix, status, detail);
    } else {
        snprintf(msg, sizeof(msg), "%s (status=%u)", prefix, status);
    }
    napi_throw_error(env, code, msg);
    return NULL;
}

/* ================================================================
 * N-API utility helpers
 * ================================================================ */

#define NAPI_THROW(env, msg) do { napi_throw_error(env, "DOE_ERROR", msg); return NULL; } while(0)
#define MAX_NAPI_ARGS 16
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

static int64_t get_int64_value(napi_env env, napi_value value) {
    int64_t out = 0;
    napi_get_value_int64(env, value, &out);
    return out;
}

static double get_double_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    double out = 0.0;
    napi_get_value_double(env, val, &out);
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

static char* dup_string_value(napi_env env, napi_value value, size_t* out_len) {
    size_t len = 0;
    napi_get_value_string_utf8(env, value, NULL, 0, &len);
    char* out = (char*)malloc(len + 1);
    if (!out) return NULL;
    napi_get_value_string_utf8(env, value, out, len + 1, &len);
    if (out_len) *out_len = len;
    return out;
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

    const char* timeout_env = getenv("DOE_TIMEOUT_MS");
    if (timeout_env && timeout_env[0] != '\0') {
        char* end = NULL;
        unsigned long parsed = strtoul(timeout_env, &end, 10);
        if (end && *end == '\0') {
            g_timeout_ns = (uint64_t)parsed * 1000000ULL;
        }
    }

    LOAD_SYM(wgpuCreateInstance);
    LOAD_SYM(wgpuInstanceRelease);
    LOAD_SYM(wgpuInstanceRequestAdapter);
    LOAD_SYM(wgpuInstanceWaitAny);
    LOAD_SYM(wgpuInstanceProcessEvents);
    LOAD_SYM(wgpuAdapterRelease);
    LOAD_SYM(wgpuAdapterHasFeature);
    LOAD_SYM(wgpuAdapterGetLimits);
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
    LOAD_SYM(wgpuCommandEncoderCopyBufferToTexture);
    LOAD_SYM(wgpuCommandEncoderCopyTextureToBuffer);
    LOAD_SYM(doeNativeCommandEncoderCopyBufferToTexture);
    LOAD_SYM(doeNativeCommandEncoderCopyTextureToBuffer);
    LOAD_SYM(wgpuCommandEncoderFinish);
    LOAD_SYM(wgpuComputePassEncoderSetPipeline);
    LOAD_SYM(wgpuComputePassEncoderSetBindGroup);
    LOAD_SYM(wgpuComputePassEncoderDispatchWorkgroups);
    LOAD_SYM(wgpuComputePassEncoderDispatchWorkgroupsIndirect);
    LOAD_SYM(doeNativeComputePassDispatchIndirect);
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
    LOAD_SYM(wgpuRenderPassEncoderSetBindGroup);
    LOAD_SYM(wgpuRenderPassEncoderSetVertexBuffer);
    LOAD_SYM(wgpuRenderPassEncoderSetIndexBuffer);
    LOAD_SYM(wgpuRenderPassEncoderDraw);
    LOAD_SYM(wgpuRenderPassEncoderDrawIndexed);
    LOAD_SYM(wgpuRenderPassEncoderEnd);
    LOAD_SYM(wgpuRenderPassEncoderRelease);
    LOAD_SYM(wgpuAdapterGetLimits);
    LOAD_SYM(wgpuAdapterHasFeature);
    LOAD_SYM(wgpuDeviceHasFeature);
    LOAD_SYM(wgpuDeviceGetLimits);
    pfn_doeNativeAdapterGetLimits = (PFN_doeNativeAdapterGetLimits)LIB_SYM(g_lib, "doeNativeAdapterGetLimits");
    pfn_doeNativeDeviceGetLimits = (PFN_doeNativeDeviceGetLimits)LIB_SYM(g_lib, "doeNativeDeviceGetLimits");
    pfn_doeNativeAdapterHasFeature = (PFN_doeNativeAdapterHasFeature)LIB_SYM(g_lib, "doeNativeAdapterHasFeature");
    pfn_doeNativeDeviceHasFeature = (PFN_doeNativeDeviceHasFeature)LIB_SYM(g_lib, "doeNativeDeviceHasFeature");
    pfn_doeNativeCopyLastErrorMessage = (PFN_doeNativeCopyLastErrorMessage)LIB_SYM(g_lib, "doeNativeCopyLastErrorMessage");
    pfn_doeNativeCopyLastErrorStage = (PFN_doeNativeCopyLastErrorStage)LIB_SYM(g_lib, "doeNativeCopyLastErrorStage");
    pfn_doeNativeCopyLastErrorKind = (PFN_doeNativeCopyLastErrorKind)LIB_SYM(g_lib, "doeNativeCopyLastErrorKind");
    pfn_doeNativeGetLastErrorLine = (PFN_doeNativeGetLastErrorLine)LIB_SYM(g_lib, "doeNativeGetLastErrorLine");
    pfn_doeNativeGetLastErrorColumn = (PFN_doeNativeGetLastErrorColumn)LIB_SYM(g_lib, "doeNativeGetLastErrorColumn");
    pfn_doeNativeCheckShaderSource = (PFN_doeNativeCheckShaderSource)LIB_SYM(g_lib, "doeNativeCheckShaderSource");
    pfn_doeNativeShaderModuleGetBindings = (PFN_doeNativeShaderModuleGetBindings)LIB_SYM(g_lib, "doeNativeShaderModuleGetBindings");
    pfn_doeNativeAdapterRequestDevice = (PFN_doeNativeAdapterRequestDevice)LIB_SYM(g_lib, "doeNativeAdapterRequestDevice");
    pfn_doeNativeBufferMapAsync = (PFN_doeNativeBufferMapAsync)LIB_SYM(g_lib, "doeNativeBufferMapAsync");
    pfn_doeRequestAdapterFlat = (PFN_doeRequestAdapterFlat)LIB_SYM(g_lib, "doeRequestAdapterFlat");
    pfn_doeRequestDeviceFlat = (PFN_doeRequestDeviceFlat)LIB_SYM(g_lib, "doeRequestDeviceFlat");
    pfn_wgpuBufferMapAsync2 = (PFN_wgpuBufferMapAsync2)LIB_SYM(g_lib, "wgpuBufferMapAsync");
    pfn_doeNativeQueueFlush = (PFN_doeNativeQueueFlush)LIB_SYM(g_lib, "doeNativeQueueFlush");
    pfn_doeNativeComputeDispatchFlush = (PFN_doeNativeComputeDispatchFlush)LIB_SYM(g_lib, "doeNativeComputeDispatchFlush");
    pfn_doeNativeDeviceCreateQuerySet = (PFN_doeNativeDeviceCreateQuerySet)LIB_SYM(g_lib, "doeNativeDeviceCreateQuerySet");
    pfn_doeNativeCommandEncoderWriteTimestamp = (PFN_doeNativeCommandEncoderWriteTimestamp)LIB_SYM(g_lib, "doeNativeCommandEncoderWriteTimestamp");
    pfn_doeNativeCommandEncoderResolveQuerySet = (PFN_doeNativeCommandEncoderResolveQuerySet)LIB_SYM(g_lib, "doeNativeCommandEncoderResolveQuerySet");
    pfn_doeNativeQuerySetDestroy = (PFN_doeNativeQuerySetDestroy)LIB_SYM(g_lib, "doeNativeQuerySetDestroy");

    /* Optional symbols for new 14-binding expansion — absent until parallel agent delivers them. */
    pfn_doeNativeAdapterGetPreferredCanvasFormat = (FnAdapterGetPreferredCanvasFormat)LIB_SYM(g_lib, "doeNativeAdapterGetPreferredCanvasFormat");
    pfn_doeNativeDeviceAddEventListener = (FnDeviceAddEventListener)LIB_SYM(g_lib, "doeNativeDeviceAddEventListener");
    pfn_doeNativeDeviceRemoveEventListener = (FnDeviceRemoveEventListener)LIB_SYM(g_lib, "doeNativeDeviceRemoveEventListener");
    pfn_doeNativeDeviceImportExternalTexture = (FnDeviceImportExternalTexture)LIB_SYM(g_lib, "doeNativeDeviceImportExternalTexture");
    pfn_doeNativeBindingCommandsSetImmediates = (FnBindingCommandsSetImmediates)LIB_SYM(g_lib, "doeNativeBindingCommandsSetImmediates");
    pfn_doeNativeComputePassSetImmediates = (FnComputePassSetImmediates)LIB_SYM(g_lib, "doeNativeComputePassSetImmediates");
    pfn_doeNativeRenderPassSetImmediates = (FnRenderPassSetImmediates)LIB_SYM(g_lib, "doeNativeRenderPassSetImmediates");
    pfn_doeNativeRenderBundleEncoderSetImmediates = (FnRenderBundleEncoderSetImmediates)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetImmediates");

    /* GPUAdapter.info and GPUShaderModule.getCompilationInfo — optional; absent on older builds. */
    pfn_doeNativeAdapterGetInfo = (FnAdapterGetInfo)LIB_SYM(g_lib, "doeNativeAdapterGetInfo");
    pfn_doeNativeAdapterFreeInfo = (FnAdapterFreeInfo)LIB_SYM(g_lib, "doeNativeAdapterFreeInfo");
    pfn_doeNativeShaderModuleGetCompilationInfo = (FnShaderModuleGetCompilationInfo)LIB_SYM(g_lib, "doeNativeShaderModuleGetCompilationInfo");
    pfn_doeNativeDevicePushErrorScope = (FnDevicePushErrorScope)LIB_SYM(g_lib, "doeNativeDevicePushErrorScope");
    pfn_doeNativeDevicePopErrorScope = (FnDevicePopErrorScope)LIB_SYM(g_lib, "doeNativeDevicePopErrorScope");
    pfn_wgpuDevicePushErrorScope = (FnDevicePushErrorScope)LIB_SYM(g_lib, "wgpuDevicePushErrorScope");
    pfn_wgpuDevicePopErrorScope = (FnDevicePopErrorScope)LIB_SYM(g_lib, "wgpuDevicePopErrorScope");
    pfn_doeNativeDeviceSetUncapturedErrorCallback = (FnDeviceSetUncapturedErrorCallback)LIB_SYM(g_lib, "doeNativeDeviceSetUncapturedErrorCallback");
    pfn_doeNativeDeviceRegisterLostCallback = (FnDeviceRegisterLostCallback)LIB_SYM(g_lib, "doeNativeDeviceRegisterLostCallback");

    /* GPURenderPassEncoder control methods — optional; absent on older builds. */
    pfn_doeNativeRenderPassSetViewport = (FnRenderPassSetViewport)LIB_SYM(g_lib, "doeNativeRenderPassSetViewport");
    pfn_doeNativeRenderPassSetScissorRect = (FnRenderPassSetScissorRect)LIB_SYM(g_lib, "doeNativeRenderPassSetScissorRect");
    pfn_doeNativeRenderPassSetBlendConstant = (FnRenderPassSetBlendConstant)LIB_SYM(g_lib, "doeNativeRenderPassSetBlendConstant");
    pfn_doeNativeRenderPassSetStencilReference = (FnRenderPassSetStencilReference)LIB_SYM(g_lib, "doeNativeRenderPassSetStencilReference");
    pfn_doeNativeRenderPassPushDebugGroup = (FnRenderPassPushDebugGroup)LIB_SYM(g_lib, "doeNativeRenderPassPushDebugGroup");
    pfn_doeNativeRenderPassPopDebugGroup = (FnRenderPassPopDebugGroup)LIB_SYM(g_lib, "doeNativeRenderPassPopDebugGroup");
    pfn_doeNativeRenderPassInsertDebugMarker = (FnRenderPassInsertDebugMarker)LIB_SYM(g_lib, "doeNativeRenderPassInsertDebugMarker");

    /* clearBuffer / copyTextureToTexture / writeTexture — optional; absent on older builds. */
    pfn_doeNativeCommandEncoderClearBuffer = (FnCommandEncoderClearBuffer)LIB_SYM(g_lib, "doeNativeCommandEncoderClearBuffer");
    pfn_doeNativeCommandEncoderCopyTextureToTexture = (FnCommandEncoderCopyTextureToTexture)LIB_SYM(g_lib, "doeNativeCommandEncoderCopyTextureToTexture");
    pfn_wgpuCommandEncoderCopyTextureToTexture = (FnWgpuCommandEncoderCopyTextureToTexture)LIB_SYM(g_lib, "wgpuCommandEncoderCopyTextureToTexture");
    pfn_doeNativeQueueWriteTexture = (FnQueueWriteTexture)LIB_SYM(g_lib, "doeNativeQueueWriteTexture");

    /* renderPipelineGetBindGroupLayout — optional; absent on older builds. */
    pfn_doeNativeRenderPipelineGetBindGroupLayout = (FnRenderPipelineGetBindGroupLayout)LIB_SYM(g_lib, "doeNativeRenderPipelineGetBindGroupLayout");

    /* GPURenderBundleEncoder / GPURenderBundle — optional; absent on older builds. */
    pfn_doeNativeDeviceCreateRenderBundleEncoder   = (FnDeviceCreateRenderBundleEncoder)LIB_SYM(g_lib, "doeNativeDeviceCreateRenderBundleEncoder");
    pfn_doeNativeRenderBundleEncoderRelease        = (FnRenderBundleEncoderRelease)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderRelease");
    pfn_doeNativeRenderBundleEncoderSetPipeline    = (FnRenderBundleEncoderSetPipeline)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetPipeline");
    pfn_doeNativeRenderBundleEncoderSetBindGroup   = (FnRenderBundleEncoderSetBindGroup)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetBindGroup");
    pfn_doeNativeRenderBundleEncoderSetVertexBuffer = (FnRenderBundleEncoderSetVertexBuffer)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetVertexBuffer");
    pfn_doeNativeRenderBundleEncoderSetIndexBuffer  = (FnRenderBundleEncoderSetIndexBuffer)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetIndexBuffer");
    pfn_doeNativeRenderBundleEncoderDraw           = (FnRenderBundleEncoderDraw)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderDraw");
    pfn_doeNativeRenderBundleEncoderDrawIndexed    = (FnRenderBundleEncoderDrawIndexed)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderDrawIndexed");
    pfn_doeNativeRenderBundleEncoderFinish         = (FnRenderBundleEncoderFinish)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderFinish");
    pfn_doeNativeRenderBundleRelease               = (FnRenderBundleRelease)LIB_SYM(g_lib, "doeNativeRenderBundleRelease");

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
    char message[DOE_ERROR_BUF_CAP];
} AdapterRequestResult;

static void adapter_callback(uint32_t status, WGPUAdapter adapter,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    AdapterRequestResult* r = (AdapterRequestResult*)userdata1;
    r->status = status;
    r->adapter = adapter;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

static napi_value doe_request_adapter(napi_env env, napi_callback_info info) {
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
    char message[DOE_ERROR_BUF_CAP];
} DeviceRequestResult;

static void device_callback(uint32_t status, WGPUDevice device,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    DeviceRequestResult* r = (DeviceRequestResult*)userdata1;
    r->status = status;
    r->device = device;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

static napi_value doe_request_device(napi_env env, napi_callback_info info) {
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

static napi_value doe_device_release(napi_env env, napi_callback_info info) {
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
    char message[DOE_ERROR_BUF_CAP];
} BufferMapResult;

typedef struct {
    uint32_t status;
    uint32_t done;
    char message[DOE_ERROR_BUF_CAP];
} QueueWorkDoneResult;

static void buffer_map_callback(uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2) {
    (void)userdata2;
    BufferMapResult* r = (BufferMapResult*)userdata1;
    r->status = status;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

static void queue_work_done_callback(uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2) {
    (void)userdata2;
    QueueWorkDoneResult* r = (QueueWorkDoneResult*)userdata1;
    r->status = status;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

/* bufferMapSync(instance, buffer, mode, offset, size) */
static napi_value doe_buffer_map_sync(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUBuffer buf = unwrap_ptr(env, _args[1]);
    if (!inst || !buf) NAPI_THROW(env, "bufferMapSync requires instance and buffer");
    uint32_t mode;
    napi_get_value_uint32(env, _args[2], &mode);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[3], &offset_i);
    napi_get_value_int64(env, _args[4], &size_i);

    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(
            buf,
            (uint64_t)mode,
            (size_t)offset_i,
            (size_t)size_i,
            cb_info
        );
        if (future.id == 0 || !result.done) NAPI_THROW(env, "doeNativeBufferMapAsync unavailable");
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "doeNativeBufferMapAsync failed", result.status, result.message);
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode,
            (size_t)offset_i, (size_t)size_i, cb_info);
        if (future.id == 0) NAPI_THROW(env, "bufferMapAsync future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns()))
            return throw_status_error(env, "DOE_BUFFER_MAP_TIMEOUT", "bufferMapAsync timed out", result.status, result.message);
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "bufferMapAsync failed", result.status, result.message);
    }

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

    /* pfn_wgpuBufferGetMappedRange resolves to Dawn for Doe-native buffers (~50us, returns NULL).
     * Go directly to pfn_wgpuBufferGetConstMappedRange (routes to doeNativeBufferGetConstMappedRange, fast). */
    void* data = (void*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!data) NAPI_THROW(env, "getMappedRange returned NULL");

    napi_value ab;
    napi_create_external_arraybuffer(env, data, (size_t)size_i, NULL, NULL, &ab);
    return ab;
}

static napi_value doe_buffer_read_copy(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[1], &offset_i);
    napi_get_value_int64(env, _args[2], &size_i);

    void* data = (void*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!data) NAPI_THROW(env, "bufferReadCopy getMappedRange returned NULL");

    void* copy = NULL;
    napi_value ab;
    napi_create_arraybuffer(env, (size_t)size_i, &copy, &ab);
    if (copy && size_i > 0) {
        memcpy(copy, data, (size_t)size_i);
    }
    return ab;
}

/* bufferGetStagedRange(buf, offset, size) → V8-heap ArrayBuffer for WRITE-mode maps.
 * Allocates a V8-managed buffer so TypedArray ops (fill, set, etc.) use V8's fast SIMD
 * paths rather than the slow external-memory path. Call bufferFlushStagedRange on unmap. */
static napi_value doe_buffer_get_staged_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    int64_t size_i = 0;
    napi_get_value_int64(env, _args[2], &size_i);
    void* copy = NULL;
    napi_value ab;
    napi_create_arraybuffer(env, (size_t)size_i, &copy, &ab);
    return ab;
}

/* bufferFlushStagedRange(buf, arraybuffer, offset, size) → memcpy staged V8 buffer → Metal. */
static napi_value doe_buffer_flush_staged_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    void* staged = NULL;
    size_t staged_len = 0;
    napi_get_arraybuffer_info(env, _args[1], &staged, &staged_len);
    int64_t offset_i = 0, size_i = 0;
    napi_get_value_int64(env, _args[2], &offset_i);
    napi_get_value_int64(env, _args[3], &size_i);
    if (!staged || size_i <= 0) return NULL;
    /* For Doe-native buffers pfn_wgpuBufferGetMappedRange resolves to Dawn (returns NULL, ~50us).
     * pfn_wgpuBufferGetConstMappedRange routes to doeNativeBufferGetConstMappedRange (fast, writable). */
    void* mapped = (void*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!mapped) NAPI_THROW(env, "bufferFlushStagedRange: mapped range unavailable");
    memcpy(mapped, staged, (size_t)size_i);
    return NULL;
}

static napi_value doe_buffer_write_mapped_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i = 0;
    napi_get_value_int64(env, _args[1], &offset_i);

    void* data = NULL;
    size_t byte_length = 0;
    bool is_typed_array = false;
    napi_is_typedarray(env, _args[2], &is_typed_array);
    if (is_typed_array) {
        napi_typedarray_type ta_type;
        size_t ta_length = 0;
        void* ta_data = NULL;
        napi_value ta_arraybuffer;
        size_t ta_byte_offset = 0;
        napi_get_typedarray_info(env, _args[2], &ta_type, &ta_length, &ta_data, &ta_arraybuffer, &ta_byte_offset);
        data = ta_data;
        switch (ta_type) {
            case napi_uint16_array: case napi_int16_array: byte_length = ta_length * 2; break;
            case napi_uint32_array: case napi_int32_array: case napi_float32_array: byte_length = ta_length * 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: byte_length = ta_length * 8; break;
            default: byte_length = ta_length; break;
        }
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, _args[2], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, _args[2], &data, &byte_length);
        } else {
            bool is_buffer = false;
            napi_is_buffer(env, _args[2], &is_buffer);
            if (is_buffer) {
                napi_get_buffer_info(env, _args[2], &data, &byte_length);
            } else {
                NAPI_THROW(env, "bufferWriteMappedRange: data must be TypedArray, ArrayBuffer, or Buffer");
            }
        }
    }

    void* mapped = pfn_wgpuBufferGetMappedRange(buf, (size_t)offset_i, byte_length);
    if (!mapped) NAPI_THROW(env, "bufferWriteMappedRange: mapped range unavailable");
    memcpy(mapped, data, byte_length);
    return NULL;
}

static napi_value doe_buffer_read_indirect_counts(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i = 0;
    napi_get_value_int64(env, _args[1], &offset_i);
    if (!buf) NAPI_THROW(env, "bufferReadIndirectCounts requires buffer");
    if (offset_i < 0) NAPI_THROW(env, "bufferReadIndirectCounts offset must be non-negative");

    const uint32_t* counts = (const uint32_t*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, 3 * sizeof(uint32_t));
    if (!counts) NAPI_THROW(env, "bufferReadIndirectCounts: unable to read indirect data");

    napi_value result;
    napi_create_object(env, &result);
    napi_value x;
    napi_value y;
    napi_value z;
    napi_create_uint32(env, counts[0], &x);
    napi_create_uint32(env, counts[1], &y);
    napi_create_uint32(env, counts[2], &z);
    napi_set_named_property(env, result, "x", x);
    napi_set_named_property(env, result, "y", y);
    napi_set_named_property(env, result, "z", z);
    return result;
}

/* bufferAssertMappedPrefixF32(buffer, expected, count) */
static napi_value doe_buffer_assert_mapped_prefix_f32(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    double expected = 0.0;
    uint32_t count = 0;
    napi_get_value_double(env, _args[1], &expected);
    napi_get_value_uint32(env, _args[2], &count);
    if (!buf) NAPI_THROW(env, "bufferAssertMappedPrefixF32 requires buffer");
    const float* mapped = (const float*)pfn_wgpuBufferGetConstMappedRange(buf, 0, count * sizeof(float));
    if (!mapped) NAPI_THROW(env, "bufferAssertMappedPrefixF32: mapped range unavailable");
    for (uint32_t i = 0; i < count; i++) {
        if ((double)mapped[i] != expected) {
            char msg[128];
            snprintf(msg, sizeof(msg), "expected readback[%u] === %.0f, got %.9g", i, expected, (double)mapped[i]);
            NAPI_THROW(env, msg);
        }
    }
    napi_value ok;
    napi_get_boolean(env, true, &ok);
    return ok;
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
    if (!mod) {
        char msg[DOE_ERROR_BUF_CAP];
        char stage[64];
        char kind[64];
        copy_library_error_message(msg, sizeof(msg));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));
        if (msg[0] != '\0') {
            char full_msg[DOE_ERROR_BUF_CAP];
            if (stage[0] != '\0' && kind[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s/%s] %s", stage, kind, msg);
            } else if (stage[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s] %s", stage, msg);
            } else {
                snprintf(full_msg, sizeof(full_msg), "%s", msg);
            }
            napi_throw_error(env, "DOE_SHADER_MODULE_ERROR", full_msg);
        } else {
            napi_throw_error(env, "DOE_SHADER_MODULE_ERROR", "createShaderModule failed (WGSL translation or compilation error)");
        }
        return NULL;
    }
    return wrap_ptr(env, mod);
}

static napi_value doe_check_shader_source(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    napi_valuetype value_type;
    if (napi_typeof(env, _args[0], &value_type) != napi_ok || value_type != napi_string) {
        NAPI_THROW(env, "checkShaderSource requires a WGSL source string");
    }
    napi_value result;
    napi_create_object(env, &result);
    if (!pfn_doeNativeCheckShaderSource) {
        napi_value ok;
        napi_get_boolean(env, true, &ok);
        napi_set_named_property(env, result, "ok", ok);
        return result;
    }

    size_t code_len = 0;
    napi_get_value_string_utf8(env, _args[0], NULL, 0, &code_len);
    char* code = (char*)malloc(code_len + 1);
    if (!code) NAPI_THROW(env, "checkShaderSource: out of memory");
    napi_get_value_string_utf8(env, _args[0], code, code_len + 1, &code_len);

    const uint32_t ok_status = pfn_doeNativeCheckShaderSource(code, code_len);
    free(code);

    napi_value ok;
    napi_get_boolean(env, ok_status != 0, &ok);
    napi_set_named_property(env, result, "ok", ok);
    if (ok_status != 0) return result;

    char message[DOE_ERROR_BUF_CAP];
    char stage[64];
    char kind[64];
    copy_library_error_message(message, sizeof(message));
    copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
    copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));

    napi_value message_val;
    napi_create_string_utf8(env, message, NAPI_AUTO_LENGTH, &message_val);
    napi_set_named_property(env, result, "message", message_val);
    if (stage[0] != '\0') {
        napi_value stage_val;
        napi_create_string_utf8(env, stage, NAPI_AUTO_LENGTH, &stage_val);
        napi_set_named_property(env, result, "stage", stage_val);
    }
    if (kind[0] != '\0') {
        napi_value kind_val;
        napi_create_string_utf8(env, kind, NAPI_AUTO_LENGTH, &kind_val);
        napi_set_named_property(env, result, "kind", kind_val);
    }
    if (pfn_doeNativeGetLastErrorLine) {
        uint32_t line = pfn_doeNativeGetLastErrorLine();
        if (line > 0) {
            napi_value line_val;
            napi_create_uint32(env, line, &line_val);
            napi_set_named_property(env, result, "line", line_val);
        }
    }
    if (pfn_doeNativeGetLastErrorColumn) {
        uint32_t col = pfn_doeNativeGetLastErrorColumn();
        if (col > 0) {
            napi_value col_val;
            napi_create_uint32(env, col, &col_val);
            napi_set_named_property(env, result, "column", col_val);
        }
    }
    return result;
}

static napi_value doe_shader_module_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* mod = unwrap_ptr(env, _args[0]);
    if (mod) pfn_wgpuShaderModuleRelease(mod);
    return NULL;
}

static const char* doe_binding_kind_name(uint32_t kind) {
    switch (kind) {
        case 0: return "buffer";
        case 1: return "sampler";
        case 2: return "texture";
        case 3: return "storage_texture";
        default: return "unknown";
    }
}

static const char* doe_binding_space_name(uint32_t addr_space) {
    switch (addr_space) {
        case 0: return "function";
        case 1: return "private";
        case 2: return "workgroup";
        case 3: return "uniform";
        case 4: return "storage";
        case 5: return "handle";
        default: return "unknown";
    }
}

static const char* doe_binding_access_name(uint32_t access) {
    switch (access) {
        case 0: return "read";
        case 1: return "write";
        case 2: return "read_write";
        default: return "unknown";
    }
}

static napi_value doe_shader_module_get_bindings(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUShaderModule shader_module = unwrap_ptr(env, _args[0]);
    if (!shader_module) NAPI_THROW(env, "shaderModuleGetBindings: null shader module");
    if (!pfn_doeNativeShaderModuleGetBindings) NAPI_THROW(env, "shaderModuleGetBindings: native binding metadata not available");

    DoeShaderBindingInfo bindings[16];
    size_t count = pfn_doeNativeShaderModuleGetBindings(shader_module, bindings, 16);

    napi_value array;
    napi_create_array_with_length(env, count, &array);
    for (size_t i = 0; i < count; i++) {
        napi_value entry;
        napi_create_object(env, &entry);

        napi_value group, binding, kind, space, access;
        napi_create_uint32(env, bindings[i].group, &group);
        napi_create_uint32(env, bindings[i].binding, &binding);
        napi_create_string_utf8(env, doe_binding_kind_name(bindings[i].kind), NAPI_AUTO_LENGTH, &kind);
        napi_create_string_utf8(env, doe_binding_space_name(bindings[i].addr_space), NAPI_AUTO_LENGTH, &space);
        napi_create_string_utf8(env, doe_binding_access_name(bindings[i].access), NAPI_AUTO_LENGTH, &access);

        napi_set_named_property(env, entry, "group", group);
        napi_set_named_property(env, entry, "binding", binding);
        napi_set_named_property(env, entry, "type", kind);
        napi_set_named_property(env, entry, "space", space);
        napi_set_named_property(env, entry, "access", access);
        napi_set_element(env, array, i, entry);
    }

    return array;
}

/* ================================================================
 * Compute Pipeline
 * createComputePipeline(device, shaderModule, entryPoint, pipelineLayout?, constants?)
 * ================================================================ */

/* Parse a JS constants object/map {key: value, ...} into a WGPUConstantEntry array.
 * Returns the number of entries written; caller must free the returned array. */
static size_t parse_js_override_constants(napi_env env, napi_value constants_obj,
                                           WGPUConstantEntry** out_entries) {
    *out_entries = NULL;
    if (!constants_obj) return 0;
    napi_valuetype vtype;
    napi_typeof(env, constants_obj, &vtype);
    if (vtype != napi_object) return 0;

    napi_value prop_names;
    napi_get_property_names(env, constants_obj, &prop_names);
    uint32_t count = 0;
    napi_get_array_length(env, prop_names, &count);
    if (count == 0) return 0;

    WGPUConstantEntry* entries = (WGPUConstantEntry*)calloc(count, sizeof(WGPUConstantEntry));
    if (!entries) return 0;
    /* Allocate key string storage — each key needs a null-terminated copy. */
    for (uint32_t i = 0; i < count; i++) {
        napi_value key_val;
        napi_get_element(env, prop_names, i, &key_val);
        size_t key_len = 0;
        napi_get_value_string_utf8(env, key_val, NULL, 0, &key_len);
        char* key_str = (char*)malloc(key_len + 1);
        if (!key_str) { free(entries); *out_entries = NULL; return 0; }
        napi_get_value_string_utf8(env, key_val, key_str, key_len + 1, &key_len);
        entries[i].nextInChain = NULL;
        entries[i].key.data = key_str;
        entries[i].key.length = key_len;
        napi_value val;
        napi_get_property(env, constants_obj, key_val, &val);
        napi_get_value_double(env, val, &entries[i].value);
    }
    *out_entries = entries;
    return count;
}

static void free_override_constants(WGPUConstantEntry* entries, size_t count) {
    if (!entries) return;
    for (size_t i = 0; i < count; i++) {
        free((void*)entries[i].key.data);
    }
    free(entries);
}

static napi_value doe_create_compute_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
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

    /* Parse optional override constants (5th arg) */
    WGPUConstantEntry* override_entries = NULL;
    size_t override_count = 0;
    if (_argc > 4) {
        napi_valuetype const_type;
        napi_typeof(env, _args[4], &const_type);
        if (const_type == napi_object) {
            override_count = parse_js_override_constants(env, _args[4], &override_entries);
        }
    }

    WGPUComputePipelineDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.layout = layout;
    desc.compute.module = shader;
    desc.compute.entryPoint.data = ep;
    desc.compute.entryPoint.length = ep_len;
    desc.compute.constantCount = override_count;
    desc.compute.constants = override_entries;

    WGPUComputePipeline pipeline = pfn_wgpuDeviceCreateComputePipeline(device, &desc);
    free(ep);
    free_override_constants(override_entries, override_count);
    if (!pipeline) {
        char msg[DOE_ERROR_BUF_CAP];
        char stage[64];
        char kind[64];
        copy_library_error_message(msg, sizeof(msg));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));
        if (msg[0] != '\0') {
            char full_msg[DOE_ERROR_BUF_CAP];
            if (stage[0] != '\0' && kind[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s/%s] %s", stage, kind, msg);
            } else if (stage[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s] %s", stage, msg);
            } else {
                snprintf(full_msg, sizeof(full_msg), "%s", msg);
            }
            napi_throw_error(env, "DOE_COMPUTE_PIPELINE_ERROR", full_msg);
        } else {
            napi_throw_error(env, "DOE_COMPUTE_PIPELINE_ERROR", "createComputePipeline failed");
        }
        return NULL;
    }
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
 * Each entry: { binding, visibility, buffer?: { type }, sampler?: { type },
 *               texture?: { sampleType, viewDimension, multisampled },
 *               storageTexture?: { access, format, viewDimension } }
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

static uint32_t sampler_binding_type_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0x00000001; /* Undefined */
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "filtering") == 0) return 0x00000002;
    if (strcmp(buf, "non-filtering") == 0 || strcmp(buf, "non_filtering") == 0) return 0x00000003;
    if (strcmp(buf, "comparison") == 0) return 0x00000004;
    return 0x00000001;
}

static uint32_t texture_sample_type_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0x00000001; /* Undefined */
    char buf[64] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "float") == 0) return 0x00000002;
    if (strcmp(buf, "unfilterable-float") == 0 || strcmp(buf, "unfilterable_float") == 0) return 0x00000003;
    if (strcmp(buf, "depth") == 0) return 0x00000004;
    if (strcmp(buf, "sint") == 0) return 0x00000005;
    if (strcmp(buf, "uint") == 0) return 0x00000006;
    return 0x00000001;
}

static uint32_t texture_view_dimension_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0x00000000; /* Undefined */
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "1d") == 0) return 0x00000001;
    if (strcmp(buf, "2d") == 0) return 0x00000002;
    if (strcmp(buf, "2d-array") == 0 || strcmp(buf, "2d_array") == 0) return 0x00000003;
    if (strcmp(buf, "cube") == 0) return 0x00000004;
    if (strcmp(buf, "cube-array") == 0 || strcmp(buf, "cube_array") == 0) return 0x00000005;
    if (strcmp(buf, "3d") == 0) return 0x00000006;
    return 0x00000000;
}

static uint32_t storage_texture_access_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0x00000001; /* Undefined */
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "write-only") == 0 || strcmp(buf, "write_only") == 0) return 0x00000002;
    if (strcmp(buf, "read-only") == 0 || strcmp(buf, "read_only") == 0) return 0x00000003;
    if (strcmp(buf, "read-write") == 0 || strcmp(buf, "read_write") == 0) return 0x00000004;
    return 0x00000001;
}

static uint32_t texture_format_from_string(napi_env env, napi_value val);
static uint32_t primitive_topology_from_string(napi_env env, napi_value val);
static uint32_t front_face_from_string(napi_env env, napi_value val);
static uint32_t cull_mode_from_string(napi_env env, napi_value val);

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

        if (has_prop(env, elem, "sampler") && prop_type(env, elem, "sampler") == napi_object) {
            napi_value sampler_obj = get_prop(env, elem, "sampler");
            entries[i].sampler.type = sampler_binding_type_from_string(
                env, get_prop(env, sampler_obj, "type"));
        }

        if (has_prop(env, elem, "texture") && prop_type(env, elem, "texture") == napi_object) {
            napi_value tex_obj = get_prop(env, elem, "texture");
            entries[i].texture.sampleType = texture_sample_type_from_string(
                env, get_prop(env, tex_obj, "sampleType"));
            entries[i].texture.viewDimension = texture_view_dimension_from_string(
                env, get_prop(env, tex_obj, "viewDimension"));
            if (has_prop(env, tex_obj, "multisampled"))
                entries[i].texture.multisampled = get_bool_prop(env, tex_obj, "multisampled") ? 1 : 0;
        }

        if (has_prop(env, elem, "storageTexture") && prop_type(env, elem, "storageTexture") == napi_object) {
            napi_value st_obj = get_prop(env, elem, "storageTexture");
            entries[i].storageTexture.access = storage_texture_access_from_string(env, get_prop(env, st_obj, "access"));
            entries[i].storageTexture.format = texture_format_from_string(env, get_prop(env, st_obj, "format"));
            entries[i].storageTexture.viewDimension = texture_view_dimension_from_string(env, get_prop(env, st_obj, "viewDimension"));
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
 * Each entry: { binding, buffer?, offset?, size?, sampler?, textureView? }
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

        if (has_prop(env, elem, "sampler") && prop_type(env, elem, "sampler") == napi_external)
            entries[i].sampler = unwrap_ptr(env, get_prop(env, elem, "sampler"));

        if (has_prop(env, elem, "textureView") && prop_type(env, elem, "textureView") == napi_external)
            entries[i].textureView = unwrap_ptr(env, get_prop(env, elem, "textureView"));

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

static napi_value doe_command_encoder_copy_buffer_to_texture(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 14);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUBuffer src_buffer = unwrap_ptr(env, _args[1]);
    if (!enc || !src_buffer) NAPI_THROW(env, "commandEncoderCopyBufferToTexture requires encoder and buffer");

    WGPUTexelCopyBufferInfo src;
    memset(&src, 0, sizeof(src));
    src.buffer = src_buffer;
    int64_t src_offset = 0;
    napi_get_value_int64(env, _args[2], &src_offset);
    src.layout.offset = (uint64_t)src_offset;
    napi_get_value_uint32(env, _args[3], &src.layout.bytesPerRow);
    napi_get_value_uint32(env, _args[4], &src.layout.rowsPerImage);

    WGPUTexelCopyTextureInfo dst;
    memset(&dst, 0, sizeof(dst));
    dst.texture = unwrap_ptr(env, _args[5]);
    if (!dst.texture) NAPI_THROW(env, "commandEncoderCopyBufferToTexture requires destination texture");
    napi_get_value_uint32(env, _args[6], &dst.mipLevel);
    napi_get_value_uint32(env, _args[7], &dst.origin.x);
    napi_get_value_uint32(env, _args[8], &dst.origin.y);
    napi_get_value_uint32(env, _args[9], &dst.origin.z);
    napi_get_value_uint32(env, _args[10], &dst.aspect);

    WGPUExtent3D size;
    napi_get_value_uint32(env, _args[11], &size.width);
    napi_get_value_uint32(env, _args[12], &size.height);
    napi_get_value_uint32(env, _args[13], &size.depthOrArrayLayers);

    if (pfn_doeNativeCommandEncoderCopyBufferToTexture) {
        pfn_doeNativeCommandEncoderCopyBufferToTexture(
            enc,
            src.buffer,
            src.layout.offset,
            src.layout.bytesPerRow,
            src.layout.rowsPerImage,
            dst.texture,
            dst.mipLevel,
            size.width,
            size.height,
            size.depthOrArrayLayers
        );
    } else if (pfn_wgpuCommandEncoderCopyBufferToTexture) {
        pfn_wgpuCommandEncoderCopyBufferToTexture(enc, &src, &dst, &size);
    } else {
        NAPI_THROW(env, "commandEncoderCopyBufferToTexture: no implementation available in loaded library");
    }
    return NULL;
}

static napi_value doe_command_encoder_copy_texture_to_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 14);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUTexture src_texture = unwrap_ptr(env, _args[1]);
    if (!enc || !src_texture) NAPI_THROW(env, "commandEncoderCopyTextureToBuffer requires encoder and texture");

    WGPUTexelCopyTextureInfo src;
    memset(&src, 0, sizeof(src));
    src.texture = src_texture;
    napi_get_value_uint32(env, _args[2], &src.mipLevel);
    napi_get_value_uint32(env, _args[3], &src.origin.x);
    napi_get_value_uint32(env, _args[4], &src.origin.y);
    napi_get_value_uint32(env, _args[5], &src.origin.z);
    napi_get_value_uint32(env, _args[6], &src.aspect);

    WGPUTexelCopyBufferInfo dst;
    memset(&dst, 0, sizeof(dst));
    dst.buffer = unwrap_ptr(env, _args[7]);
    if (!dst.buffer) NAPI_THROW(env, "commandEncoderCopyTextureToBuffer requires destination buffer");
    int64_t dst_offset = 0;
    napi_get_value_int64(env, _args[8], &dst_offset);
    dst.layout.offset = (uint64_t)dst_offset;
    napi_get_value_uint32(env, _args[9], &dst.layout.bytesPerRow);
    napi_get_value_uint32(env, _args[10], &dst.layout.rowsPerImage);

    WGPUExtent3D size;
    napi_get_value_uint32(env, _args[11], &size.width);
    napi_get_value_uint32(env, _args[12], &size.height);
    napi_get_value_uint32(env, _args[13], &size.depthOrArrayLayers);

    if (pfn_doeNativeCommandEncoderCopyTextureToBuffer) {
        pfn_doeNativeCommandEncoderCopyTextureToBuffer(
            enc,
            src.texture,
            src.mipLevel,
            dst.buffer,
            dst.layout.offset,
            dst.layout.bytesPerRow,
            dst.layout.rowsPerImage,
            size.width,
            size.height,
            size.depthOrArrayLayers
        );
    } else {
        pfn_wgpuCommandEncoderCopyTextureToBuffer(enc, &src, &dst, &size);
    }
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
    if (pfn_doeNativeComputePassDispatchIndirect) {
        pfn_doeNativeComputePassDispatchIndirect(pass, buffer, (uint64_t)offset);
    } else {
        pfn_wgpuComputePassEncoderDispatchWorkgroupsIndirect(pass, buffer, (uint64_t)offset);
    }
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
    if (!queue || !buf) NAPI_THROW(env, "queueWriteBuffer requires queue and buffer");
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

/* queueFlush(instance, queue) — wait for all pending GPU work to complete.
 * Use the Doe-native queue flush when available; otherwise fall back to the
 * portable queue work-done callback path and process events until completion. */
static napi_value doe_queue_flush(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUQueue queue = unwrap_ptr(env, _args[1]);
    if (!queue) NAPI_THROW(env, "queueFlush requires queue");
    if (pfn_doeNativeQueueFlush) {
        pfn_doeNativeQueueFlush(queue);
        return NULL;
    }
    if (!inst) {
        napi_throw_error(env, "DOE_QUEUE_UNAVAILABLE", "queueFlush requires instance when doeNativeQueueFlush is unavailable");
        return NULL;
    }

    QueueWorkDoneResult result = {0};
    WGPUQueueWorkDoneCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
        .callback = queue_work_done_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
    if (future.id == 0) NAPI_THROW(env, "queueFlush: queue work-done future unavailable");
    uint64_t start_ns = monotonic_now_ns();
    while (!result.done) {
        WGPUFutureWaitInfo wait_info = {
            .future = future,
            .completed = 0,
        };
        uint32_t wait_status = pfn_wgpuInstanceWaitAny(inst, 1, &wait_info, 0);
        if (wait_status == WGPU_WAIT_STATUS_SUCCESS) {
            if (!result.done) {
                pfn_wgpuInstanceProcessEvents(inst);
            }
        } else if (wait_status == WGPU_WAIT_STATUS_TIMED_OUT) {
            pfn_wgpuInstanceProcessEvents(inst);
            if (monotonic_now_ns() - start_ns >= current_timeout_ns()) {
                napi_throw_error(env, "DOE_QUEUE_TIMEOUT", "queueFlush: queue wait timed out");
                return NULL;
            }
            wait_slice();
        } else if (wait_status == WGPU_WAIT_STATUS_ERROR) {
            napi_throw_error(env, "DOE_QUEUE_UNAVAILABLE", "queueFlush: wgpuInstanceWaitAny failed");
            return NULL;
        } else {
            NAPI_THROW(env, "queueFlush: unsupported wait status");
        }
    }
    if (result.status != WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS)
        return throw_status_error(env, "DOE_QUEUE_FLUSH_ERROR", "queueFlush: queue work did not complete", result.status, result.message);
    return NULL;
}

/* submitBatched(device, queue, commandsArray)
 * Fast path: single dispatch or dispatch+copy → doeNativeComputeDispatchFlush.
 * Larger or mixed batches stay on the standard wgpu path. */
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

    /* Fast path: exactly one dispatch, or dispatch followed by copy. */
    if (pfn_doeNativeComputeDispatchFlush && (cmd_count == 1 || cmd_count == 2)) {
        napi_value cmd0;
        napi_get_element(env, commands, 0, &cmd0);
        uint32_t t0 = get_uint32_prop(env, cmd0, "t");
        uint32_t t1 = UINT32_MAX;
        napi_value cmd1 = NULL;
        if (cmd_count == 2) {
            napi_get_element(env, commands, 1, &cmd1);
            t1 = get_uint32_prop(env, cmd1, "t");
        }
        if (t0 == 0 && (cmd_count == 1 || t1 == 1)) {
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
            void* copy_src = NULL;
            uint64_t copy_src_off = 0;
            void* copy_dst = NULL;
            uint64_t copy_dst_off = 0;
            uint64_t copy_size = 0;
            if (cmd_count == 2) {
                copy_src = unwrap_ptr(env, get_prop(env, cmd1, "s"));
                copy_dst = unwrap_ptr(env, get_prop(env, cmd1, "d"));
                copy_src_off = (uint64_t)get_int64_prop(env, cmd1, "so");
                copy_dst_off = (uint64_t)get_int64_prop(env, cmd1, "do");
                copy_size = (uint64_t)get_int64_prop(env, cmd1, "sz");
            }
            pfn_doeNativeComputeDispatchFlush(
                queue, pipeline, (void**)bg_ptrs, bg_count,
                dx, dy, dz,
                copy_src, copy_src_off, copy_dst, copy_dst_off, copy_size);
            return NULL;
        }
    }

    /* Fallback: standard wgpu path. */
    int flush_after_submit = 0;
    if (cmd_count == 2) {
        napi_value cmd0;
        napi_value cmd1;
        napi_get_element(env, commands, 0, &cmd0);
        napi_get_element(env, commands, 1, &cmd1);
        if (get_uint32_prop(env, cmd0, "t") == 0 && get_uint32_prop(env, cmd1, "t") == 1) {
            flush_after_submit = 1;
        }
    }
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
    if (flush_after_submit && pfn_doeNativeQueueFlush) {
        pfn_doeNativeQueueFlush(queue);
    }
    pfn_wgpuCommandBufferRelease(cmd_buf);
    pfn_wgpuCommandEncoderRelease(encoder);
    return NULL;
}

/* submitComputeDispatchCopy(device, queue, pipeline, bindGroups, x, y, z, src, srcOff, dst, dstOff, size)
 * Direct addon surface for the exact package compute_e2e shape so JS runtimes
 * do not pay generic command-array parsing on every timed sample. */
static napi_value doe_submit_compute_dispatch_copy(napi_env env, napi_callback_info info) {
    size_t argc = 12;
    napi_value args[12];
    napi_status status = napi_get_cb_info(env, info, &argc, args, NULL, NULL);
    if (status != napi_ok || argc != 12) NAPI_THROW(env, "submitComputeDispatchCopy requires 12 arguments");
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, args[0]);
    WGPUQueue queue = unwrap_ptr(env, args[1]);
    void* pipeline = unwrap_ptr(env, args[2]);
    napi_value bgs = args[3];
    uint32_t dx = 0;
    uint32_t dy = 0;
    uint32_t dz = 0;
    int64_t copy_src_off_i = 0;
    int64_t copy_dst_off_i = 0;
    int64_t copy_size_i = 0;
    napi_get_value_uint32(env, args[4], &dx);
    napi_get_value_uint32(env, args[5], &dy);
    napi_get_value_uint32(env, args[6], &dz);
    void* copy_src = unwrap_ptr(env, args[7]);
    napi_get_value_int64(env, args[8], &copy_src_off_i);
    void* copy_dst = unwrap_ptr(env, args[9]);
    napi_get_value_int64(env, args[10], &copy_dst_off_i);
    napi_get_value_int64(env, args[11], &copy_size_i);
    uint64_t copy_src_off = (uint64_t)copy_src_off_i;
    uint64_t copy_dst_off = (uint64_t)copy_dst_off_i;
    uint64_t copy_size = (uint64_t)copy_size_i;
    if (!device || !queue || !pipeline) NAPI_THROW(env, "submitComputeDispatchCopy requires device, queue, and pipeline");

    uint32_t bg_count = 0;
    napi_get_array_length(env, bgs, &bg_count);
    if (bg_count > BATCH_MAX_BIND_GROUPS) bg_count = BATCH_MAX_BIND_GROUPS;
    void* bg_ptrs[BATCH_MAX_BIND_GROUPS] = {NULL};
    for (uint32_t j = 0; j < bg_count; j++) {
        napi_value bg_val;
        napi_get_element(env, bgs, j, &bg_val);
        bg_ptrs[j] = unwrap_ptr(env, bg_val);
    }

    if (pfn_doeNativeComputeDispatchFlush) {
        pfn_doeNativeComputeDispatchFlush(
            queue, pipeline, (void**)bg_ptrs, bg_count,
            dx, dy, dz,
            copy_src, copy_src_off, copy_dst, copy_dst_off, copy_size);
        return NULL;
    }

    WGPUCommandEncoder encoder = pfn_wgpuDeviceCreateCommandEncoder(device, NULL);
    if (!encoder) NAPI_THROW(env, "submitComputeDispatchCopy: createCommandEncoder failed");
    WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(encoder, NULL);
    if (!pass) {
        pfn_wgpuCommandEncoderRelease(encoder);
        NAPI_THROW(env, "submitComputeDispatchCopy: beginComputePass failed");
    }
    pfn_wgpuComputePassEncoderSetPipeline(pass, pipeline);
    for (uint32_t j = 0; j < bg_count; j++) {
        if (bg_ptrs[j]) pfn_wgpuComputePassEncoderSetBindGroup(pass, j, bg_ptrs[j], 0, NULL);
    }
    pfn_wgpuComputePassEncoderDispatchWorkgroups(pass, dx, dy, dz);
    pfn_wgpuComputePassEncoderEnd(pass);
    pfn_wgpuComputePassEncoderRelease(pass);
    pfn_wgpuCommandEncoderCopyBufferToBuffer(
        encoder,
        copy_src,
        copy_src_off,
        copy_dst,
        copy_dst_off,
        copy_size
    );
    WGPUCommandBuffer cmd_buf = pfn_wgpuCommandEncoderFinish(encoder, NULL);
    if (!cmd_buf) {
        pfn_wgpuCommandEncoderRelease(encoder);
        NAPI_THROW(env, "submitComputeDispatchCopy: finish failed");
    }
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
    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(
            buf,
            (uint64_t)mode,
            (size_t)offset_i,
            (size_t)size_i,
            cb_info
        );
        if (future.id == 0 || !result.done) NAPI_THROW(env, "flushAndMapSync: doeNativeBufferMapAsync unavailable");
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "flushAndMapSync: doeNativeBufferMapAsync failed", result.status, result.message);
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode,
            (size_t)offset_i, (size_t)size_i, cb_info);
        if (future.id == 0) NAPI_THROW(env, "flushAndMapSync: bufferMapAsync future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns()))
            return throw_status_error(env, "DOE_BUFFER_MAP_TIMEOUT", "flushAndMapSync: bufferMapAsync timed out", result.status, result.message);
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "flushAndMapSync: bufferMapAsync failed", result.status, result.message);
    }

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

/* queueWriteTexture(queueNative, textureNative, dataBuffer, dataOffset,
 *                  bytesPerRow, rowsPerImage, mipLevel,
 *                  originX, originY, originZ, width, height, depthOrArrayLayers) */
static napi_value doe_queue_write_texture(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 13);
    CHECK_LIB_LOADED(env);
    void* queue   = unwrap_ptr(env, _args[0]);
    void* texture = unwrap_ptr(env, _args[1]);
    if (!queue || !texture) NAPI_THROW(env, "queueWriteTexture: invalid queue or texture");

    /* data: ArrayBuffer or TypedArray */
    void*  data     = NULL;
    size_t data_len = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, _args[2], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length;
        napi_value ab;
        size_t byte_offset;
        napi_get_typedarray_info(env, _args[2], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        data_len = ta_length * elem_size;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, _args[2], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, _args[2], &data, &data_len);
        } else {
            NAPI_THROW(env, "queueWriteTexture: data must be TypedArray or ArrayBuffer");
        }
    }

    uint32_t data_offset      = 0; napi_get_value_uint32(env, _args[3], &data_offset);
    uint32_t bytes_per_row    = 0; napi_get_value_uint32(env, _args[4], &bytes_per_row);
    uint32_t rows_per_image   = 0; napi_get_value_uint32(env, _args[5], &rows_per_image);
    uint32_t mip_level        = 0; napi_get_value_uint32(env, _args[6], &mip_level);
    uint32_t origin_x         = 0; napi_get_value_uint32(env, _args[7], &origin_x);
    uint32_t origin_y         = 0; napi_get_value_uint32(env, _args[8], &origin_y);
    uint32_t origin_z         = 0; napi_get_value_uint32(env, _args[9], &origin_z);
    uint32_t width            = 1; napi_get_value_uint32(env, _args[10], &width);
    uint32_t height           = 1; napi_get_value_uint32(env, _args[11], &height);
    uint32_t depth_or_layers  = 1; napi_get_value_uint32(env, _args[12], &depth_or_layers);

    if (data_offset > 0 && data_offset < (uint32_t)data_len) {
        data     = ((uint8_t*)data) + data_offset;
        data_len -= data_offset;
    }

    if (pfn_doeNativeQueueWriteTexture) {
        pfn_doeNativeQueueWriteTexture(
            queue, texture,
            data, data_len,
            bytes_per_row, rows_per_image,
            origin_x, origin_y, origin_z, mip_level, 0,
            width, height, depth_or_layers);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
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
    if (strcmp(buf, "r8unorm") == 0)          return 0x00000001;
    if (strcmp(buf, "r8snorm") == 0)          return 0x00000002;
    if (strcmp(buf, "r8uint") == 0)           return 0x00000003;
    if (strcmp(buf, "r8sint") == 0)           return 0x00000004;
    if (strcmp(buf, "r16uint") == 0)          return 0x00000007;
    if (strcmp(buf, "r16sint") == 0)          return 0x00000008;
    if (strcmp(buf, "r16float") == 0)         return 0x00000009;
    if (strcmp(buf, "rg8unorm") == 0)         return 0x0000000A;
    if (strcmp(buf, "rg8snorm") == 0)         return 0x0000000B;
    if (strcmp(buf, "rg8uint") == 0)          return 0x0000000C;
    if (strcmp(buf, "rg8sint") == 0)          return 0x0000000D;
    if (strcmp(buf, "r32float") == 0)         return 0x0000000E;
    if (strcmp(buf, "r32uint") == 0)          return 0x0000000F;
    if (strcmp(buf, "r32sint") == 0)          return 0x00000010;
    if (strcmp(buf, "rg16uint") == 0)         return 0x00000013;
    if (strcmp(buf, "rg16sint") == 0)         return 0x00000014;
    if (strcmp(buf, "rg16float") == 0)        return 0x00000015;
    if (strcmp(buf, "rgba8unorm") == 0)       return 0x00000016;
    if (strcmp(buf, "rgba8unorm-srgb") == 0)  return 0x00000017;
    if (strcmp(buf, "rgba8snorm") == 0)       return 0x00000018;
    if (strcmp(buf, "rgba8uint") == 0)        return 0x00000019;
    if (strcmp(buf, "rgba8sint") == 0)        return 0x0000001A;
    if (strcmp(buf, "bgra8unorm") == 0)       return 0x0000001B;
    if (strcmp(buf, "bgra8unorm-srgb") == 0)  return 0x0000001C;
    if (strcmp(buf, "rgb10a2uint") == 0)      return 0x0000001D;
    if (strcmp(buf, "rgb10a2unorm") == 0)     return 0x0000001E;
    if (strcmp(buf, "rg11b10ufloat") == 0)    return 0x0000001F;
    if (strcmp(buf, "rgb9e5ufloat") == 0)     return 0x00000020;
    if (strcmp(buf, "rg32float") == 0)        return 0x00000021;
    if (strcmp(buf, "rg32uint") == 0)         return 0x00000022;
    if (strcmp(buf, "rg32sint") == 0)         return 0x00000023;
    if (strcmp(buf, "rgba16uint") == 0)       return 0x00000024;
    if (strcmp(buf, "rgba16sint") == 0)       return 0x00000025;
    if (strcmp(buf, "rgba16float") == 0)      return 0x00000026;
    if (strcmp(buf, "rgba32float") == 0)      return 0x00000027;
    if (strcmp(buf, "rgba32uint") == 0)       return 0x00000028;
    if (strcmp(buf, "rgba32sint") == 0)       return 0x00000029;
    if (strcmp(buf, "stencil8") == 0)         return 0x0000002C;
    if (strcmp(buf, "depth16unorm") == 0)     return 0x0000002D;
    if (strcmp(buf, "depth24plus") == 0)      return 0x0000002E;
    if (strcmp(buf, "depth24plus-stencil8") == 0) return 0x0000002F;
    if (strcmp(buf, "depth32float") == 0)     return 0x00000030;
    if (strcmp(buf, "depth32float-stencil8") == 0) return 0x00000031;
    /* BC compressed formats */
    if (strcmp(buf, "bc1-rgba-unorm") == 0)      return 0x00000032;
    if (strcmp(buf, "bc1-rgba-unorm-srgb") == 0) return 0x00000033;
    if (strcmp(buf, "bc2-rgba-unorm") == 0)      return 0x00000034;
    if (strcmp(buf, "bc2-rgba-unorm-srgb") == 0) return 0x00000035;
    if (strcmp(buf, "bc3-rgba-unorm") == 0)      return 0x00000036;
    if (strcmp(buf, "bc3-rgba-unorm-srgb") == 0) return 0x00000037;
    if (strcmp(buf, "bc4-r-unorm") == 0)         return 0x00000038;
    if (strcmp(buf, "bc4-r-snorm") == 0)         return 0x00000039;
    if (strcmp(buf, "bc5-rg-unorm") == 0)        return 0x0000003A;
    if (strcmp(buf, "bc5-rg-snorm") == 0)        return 0x0000003B;
    if (strcmp(buf, "bc6h-rgb-ufloat") == 0)     return 0x0000003C;
    if (strcmp(buf, "bc6h-rgb-float") == 0)      return 0x0000003D;
    if (strcmp(buf, "bc7-rgba-unorm") == 0)      return 0x0000003E;
    if (strcmp(buf, "bc7-rgba-unorm-srgb") == 0) return 0x0000003F;
    /* ETC2/EAC compressed formats */
    if (strcmp(buf, "etc2-rgb8unorm") == 0)       return 0x00000040;
    if (strcmp(buf, "etc2-rgb8unorm-srgb") == 0)  return 0x00000041;
    if (strcmp(buf, "etc2-rgb8a1unorm") == 0)     return 0x00000042;
    if (strcmp(buf, "etc2-rgb8a1unorm-srgb") == 0) return 0x00000043;
    if (strcmp(buf, "etc2-rgba8unorm") == 0)      return 0x00000044;
    if (strcmp(buf, "etc2-rgba8unorm-srgb") == 0) return 0x00000045;
    if (strcmp(buf, "eac-r11unorm") == 0)         return 0x00000046;
    if (strcmp(buf, "eac-r11snorm") == 0)         return 0x00000047;
    if (strcmp(buf, "eac-rg11unorm") == 0)        return 0x00000048;
    if (strcmp(buf, "eac-rg11snorm") == 0)        return 0x00000049;
    /* ASTC compressed formats */
    if (strcmp(buf, "astc-4x4-unorm") == 0)       return 0x0000004A;
    if (strcmp(buf, "astc-4x4-unorm-srgb") == 0)  return 0x0000004B;
    if (strcmp(buf, "astc-5x4-unorm") == 0)       return 0x0000004C;
    if (strcmp(buf, "astc-5x4-unorm-srgb") == 0)  return 0x0000004D;
    if (strcmp(buf, "astc-5x5-unorm") == 0)       return 0x0000004E;
    if (strcmp(buf, "astc-5x5-unorm-srgb") == 0)  return 0x0000004F;
    if (strcmp(buf, "astc-6x5-unorm") == 0)       return 0x00000050;
    if (strcmp(buf, "astc-6x5-unorm-srgb") == 0)  return 0x00000051;
    if (strcmp(buf, "astc-6x6-unorm") == 0)       return 0x00000052;
    if (strcmp(buf, "astc-6x6-unorm-srgb") == 0)  return 0x00000053;
    if (strcmp(buf, "astc-8x5-unorm") == 0)       return 0x00000054;
    if (strcmp(buf, "astc-8x5-unorm-srgb") == 0)  return 0x00000055;
    if (strcmp(buf, "astc-8x6-unorm") == 0)       return 0x00000056;
    if (strcmp(buf, "astc-8x6-unorm-srgb") == 0)  return 0x00000057;
    if (strcmp(buf, "astc-8x8-unorm") == 0)       return 0x00000058;
    if (strcmp(buf, "astc-8x8-unorm-srgb") == 0)  return 0x00000059;
    if (strcmp(buf, "astc-10x5-unorm") == 0)      return 0x0000005A;
    if (strcmp(buf, "astc-10x5-unorm-srgb") == 0) return 0x0000005B;
    if (strcmp(buf, "astc-10x6-unorm") == 0)      return 0x0000005C;
    if (strcmp(buf, "astc-10x6-unorm-srgb") == 0) return 0x0000005D;
    if (strcmp(buf, "astc-10x8-unorm") == 0)      return 0x0000005E;
    if (strcmp(buf, "astc-10x8-unorm-srgb") == 0) return 0x0000005F;
    if (strcmp(buf, "astc-10x10-unorm") == 0)     return 0x00000060;
    if (strcmp(buf, "astc-10x10-unorm-srgb") == 0) return 0x00000061;
    if (strcmp(buf, "astc-12x10-unorm") == 0)     return 0x00000062;
    if (strcmp(buf, "astc-12x10-unorm-srgb") == 0) return 0x00000063;
    if (strcmp(buf, "astc-12x12-unorm") == 0)     return 0x00000064;
    if (strcmp(buf, "astc-12x12-unorm-srgb") == 0) return 0x00000065;
    return 0x00000016;
}

static uint32_t primitive_topology_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "point-list") == 0) return 0x00000001;
    if (strcmp(buf, "line-list") == 0) return 0x00000002;
    if (strcmp(buf, "line-strip") == 0) return 0x00000003;
    if (strcmp(buf, "triangle-list") == 0) return 0x00000004;
    if (strcmp(buf, "triangle-strip") == 0) return 0x00000005;
    napi_throw_error(env, "DOE_ERROR", "Unsupported primitive topology");
    return 0;
}

static uint32_t front_face_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[16] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "ccw") == 0) return 0x00000001;
    if (strcmp(buf, "cw") == 0) return 0x00000002;
    napi_throw_error(env, "DOE_ERROR", "Unsupported frontFace");
    return 0;
}

static uint32_t cull_mode_from_string(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[16] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "none") == 0) return 0x00000001;
    if (strcmp(buf, "front") == 0) return 0x00000002;
    if (strcmp(buf, "back") == 0) return 0x00000003;
    napi_throw_error(env, "DOE_ERROR", "Unsupported cullMode");
    return 0;
}

static uint32_t compare_func_from_value(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[24] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "never") == 0) return 0x00000001;
    if (strcmp(buf, "less") == 0) return 0x00000002;
    if (strcmp(buf, "equal") == 0) return 0x00000003;
    if (strcmp(buf, "less-equal") == 0) return 0x00000004;
    if (strcmp(buf, "greater") == 0) return 0x00000005;
    if (strcmp(buf, "not-equal") == 0) return 0x00000006;
    if (strcmp(buf, "greater-equal") == 0) return 0x00000007;
    if (strcmp(buf, "always") == 0) return 0x00000008;
    napi_throw_error(env, "DOE_ERROR", "Unsupported compare function");
    return 0;
}

static uint32_t vertex_step_mode_from_value(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[24] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "vertex") == 0) return 0x00000001;
    if (strcmp(buf, "instance") == 0) return 0x00000002;
    napi_throw_error(env, "DOE_ERROR", "Unsupported vertex stepMode");
    return 0;
}

static uint32_t vertex_format_from_value(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[32] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "float32") == 0) return 0x00000019;
    if (strcmp(buf, "float32x2") == 0) return 0x0000001A;
    if (strcmp(buf, "float32x3") == 0) return 0x0000001B;
    if (strcmp(buf, "float32x4") == 0) return 0x0000001C;
    if (strcmp(buf, "uint32") == 0) return 0x00000021;
    if (strcmp(buf, "uint32x2") == 0) return 0x00000022;
    if (strcmp(buf, "uint32x3") == 0) return 0x00000023;
    if (strcmp(buf, "uint32x4") == 0) return 0x00000024;
    if (strcmp(buf, "sint32") == 0) return 0x00000025;
    if (strcmp(buf, "sint32x2") == 0) return 0x00000026;
    if (strcmp(buf, "sint32x3") == 0) return 0x00000027;
    if (strcmp(buf, "sint32x4") == 0) return 0x00000028;
    napi_throw_error(env, "DOE_ERROR", "Unsupported vertex format");
    return 0;
}

static uint32_t index_format_from_value(napi_env env, napi_value val) {
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt == napi_number) {
        uint32_t out = 0;
        napi_get_value_uint32(env, val, &out);
        return out;
    }
    char buf[16] = {0};
    size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "uint16") == 0) return 0x00000001;
    if (strcmp(buf, "uint32") == 0) return 0x00000002;
    napi_throw_error(env, "DOE_ERROR", "Unsupported index format");
    return 0;
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
    desc.dimension = 2; /* WGPUTextureDimension_2D */
    if (has_prop(env, _args[1], "dimension"))
        desc.dimension = get_uint32_prop(env, _args[1], "dimension");

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
 * Render Pipeline
 * createRenderPipeline(device, descriptor)
 * ================================================================ */

static napi_value doe_create_render_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    napi_valuetype descriptor_type;
    napi_typeof(env, _args[1], &descriptor_type);
    if (descriptor_type != napi_object) NAPI_THROW(env, "createRenderPipeline requires a descriptor object");

    if (prop_type(env, _args[1], "vertex") != napi_object) {
        NAPI_THROW(env, "createRenderPipeline requires descriptor.vertex");
    }
    if (prop_type(env, _args[1], "fragment") != napi_object) {
        NAPI_THROW(env, "createRenderPipeline requires descriptor.fragment");
    }

    napi_value vertex = get_prop(env, _args[1], "vertex");
    napi_value fragment = get_prop(env, _args[1], "fragment");

    napi_value targets = get_prop(env, fragment, "targets");
    bool is_targets_array = false;
    napi_is_array(env, targets, &is_targets_array);
    if (!is_targets_array) NAPI_THROW(env, "createRenderPipeline requires descriptor.fragment.targets");
    uint32_t target_count = 0;
    napi_get_array_length(env, targets, &target_count);
    if (target_count == 0) NAPI_THROW(env, "createRenderPipeline requires at least one fragment target");
    if (target_count > 1) NAPI_THROW(env, "createRenderPipeline currently supports one color target on this package surface");

    napi_value vertex_module_value = get_prop(env, vertex, "module");
    WGPUShaderModule vertex_module = unwrap_ptr(env, vertex_module_value);
    if (!vertex_module) NAPI_THROW(env, "createRenderPipeline: descriptor.vertex.module must be a shader module");
    napi_value fragment_module_value = get_prop(env, fragment, "module");
    WGPUShaderModule fragment_module = unwrap_ptr(env, fragment_module_value);
    if (!fragment_module) NAPI_THROW(env, "createRenderPipeline: descriptor.fragment.module must be a shader module");

    size_t vertex_entry_len = 0;
    size_t fragment_entry_len = 0;
    char* vertex_entry = has_prop(env, vertex, "entryPoint")
        ? dup_string_value(env, get_prop(env, vertex, "entryPoint"), &vertex_entry_len)
        : strdup("main");
    if (!has_prop(env, vertex, "entryPoint")) vertex_entry_len = 4;
    char* fragment_entry = has_prop(env, fragment, "entryPoint")
        ? dup_string_value(env, get_prop(env, fragment, "entryPoint"), &fragment_entry_len)
        : strdup("main");
    if (!has_prop(env, fragment, "entryPoint")) fragment_entry_len = 4;
    if (!vertex_entry || !fragment_entry) {
        free(vertex_entry);
        free(fragment_entry);
        NAPI_THROW(env, "createRenderPipeline: out of memory");
    }

    WGPURenderVertexBufferLayout* vertex_buffers = NULL;
    WGPURenderVertexAttribute* vertex_attributes = NULL;
    WGPURenderDepthStencilState* depth_stencil = NULL;
    uint32_t vertex_buffer_count = 0;

    if (has_prop(env, vertex, "buffers")) {
        napi_value buffers = get_prop(env, vertex, "buffers");
        bool is_array = false;
        napi_is_array(env, buffers, &is_array);
        if (!is_array) {
            free(vertex_entry);
            free(fragment_entry);
            NAPI_THROW(env, "createRenderPipeline: descriptor.vertex.buffers must be an array");
        }
        napi_get_array_length(env, buffers, &vertex_buffer_count);
        if (vertex_buffer_count > 0) {
            size_t total_attributes = 0;
            for (uint32_t i = 0; i < vertex_buffer_count; i++) {
                napi_value buffer_desc;
                napi_get_element(env, buffers, i, &buffer_desc);
                if (prop_type(env, buffer_desc, "attributes") == napi_object) {
                    napi_value attrs = get_prop(env, buffer_desc, "attributes");
                    bool attrs_is_array = false;
                    napi_is_array(env, attrs, &attrs_is_array);
                    if (!attrs_is_array) {
                        free(vertex_entry);
                        free(fragment_entry);
                        NAPI_THROW(env, "createRenderPipeline: descriptor.vertex.buffers[*].attributes must be an array");
                    }
                    uint32_t attr_count = 0;
                    napi_get_array_length(env, attrs, &attr_count);
                    total_attributes += attr_count;
                }
            }

            vertex_buffers = (WGPURenderVertexBufferLayout*)calloc(vertex_buffer_count, sizeof(WGPURenderVertexBufferLayout));
            if (!vertex_buffers) {
                free(vertex_entry);
                free(fragment_entry);
                NAPI_THROW(env, "createRenderPipeline: out of memory");
            }
            if (total_attributes > 0) {
                vertex_attributes = (WGPURenderVertexAttribute*)calloc(total_attributes, sizeof(WGPURenderVertexAttribute));
                if (!vertex_attributes) {
                    free(vertex_buffers);
                    free(vertex_entry);
                    free(fragment_entry);
                    NAPI_THROW(env, "createRenderPipeline: out of memory");
                }
            }

            size_t attr_index = 0;
            for (uint32_t i = 0; i < vertex_buffer_count; i++) {
                napi_value buffer_desc;
                napi_get_element(env, buffers, i, &buffer_desc);
                vertex_buffers[i].nextInChain = NULL;
                vertex_buffers[i].stepMode = has_prop(env, buffer_desc, "stepMode")
                    ? vertex_step_mode_from_value(env, get_prop(env, buffer_desc, "stepMode"))
                    : 0x00000001;
                vertex_buffers[i].arrayStride = has_prop(env, buffer_desc, "arrayStride")
                    ? (uint64_t)get_int64_prop(env, buffer_desc, "arrayStride")
                    : 0;
                vertex_buffers[i].attributeCount = 0;
                vertex_buffers[i].attributes = NULL;

                if (prop_type(env, buffer_desc, "attributes") == napi_object) {
                    napi_value attrs = get_prop(env, buffer_desc, "attributes");
                    uint32_t attr_count = 0;
                    napi_get_array_length(env, attrs, &attr_count);
                    vertex_buffers[i].attributeCount = attr_count;
                    vertex_buffers[i].attributes = attr_count > 0 ? &vertex_attributes[attr_index] : NULL;
                    for (uint32_t j = 0; j < attr_count; j++) {
                        napi_value attr;
                        napi_get_element(env, attrs, j, &attr);
                        vertex_attributes[attr_index].nextInChain = NULL;
                        vertex_attributes[attr_index].format = vertex_format_from_value(env, get_prop(env, attr, "format"));
                        vertex_attributes[attr_index].offset = has_prop(env, attr, "offset")
                            ? (uint64_t)get_int64_prop(env, attr, "offset")
                            : 0;
                        vertex_attributes[attr_index].shaderLocation = get_uint32_prop(env, attr, "shaderLocation");
                        attr_index += 1;
                    }
                }
            }
        }
    }

    napi_value target0;
    napi_get_element(env, targets, 0, &target0);

    WGPURenderColorTargetState color_target;
    memset(&color_target, 0, sizeof(color_target));
    color_target.nextInChain = NULL;
    color_target.format = texture_format_from_string(env, get_prop(env, target0, "format"));
    color_target.blend = NULL;
    color_target.writeMask = 0xF;

    WGPURenderFragmentState fragment_state;
    memset(&fragment_state, 0, sizeof(fragment_state));
    fragment_state.nextInChain = NULL;
    fragment_state.module = fragment_module;
    fragment_state.entryPoint.data = fragment_entry;
    fragment_state.entryPoint.length = fragment_entry_len;
    fragment_state.constantCount = 0;
    fragment_state.constants = NULL;
    fragment_state.targetCount = 1;
    fragment_state.targets = &color_target;

    WGPURenderPipelineDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.nextInChain = NULL;
    desc.label.data = NULL;
    desc.label.length = 0;
    desc.layout = has_prop(env, _args[1], "layout") && prop_type(env, _args[1], "layout") == napi_external
        ? unwrap_ptr(env, get_prop(env, _args[1], "layout"))
        : NULL;
    desc.vertex.nextInChain = NULL;
    desc.vertex.module = vertex_module;
    desc.vertex.entryPoint.data = vertex_entry;
    desc.vertex.entryPoint.length = vertex_entry_len;
    desc.vertex.constantCount = 0;
    desc.vertex.constants = NULL;
    desc.vertex.bufferCount = vertex_buffer_count;
    desc.vertex.buffers = vertex_buffers;
    desc.primitive.nextInChain = NULL;
    desc.primitive.topology = 0x00000004;
    desc.primitive.stripIndexFormat = 0;
    desc.primitive.frontFace = 0x00000001;
    desc.primitive.cullMode = 0x00000001;
    desc.primitive.unclippedDepth = 0;
    if (has_prop(env, _args[1], "primitive") && prop_type(env, _args[1], "primitive") == napi_object) {
        napi_value primitive = get_prop(env, _args[1], "primitive");
        if (has_prop(env, primitive, "topology"))
            desc.primitive.topology = primitive_topology_from_string(env, get_prop(env, primitive, "topology"));
        if (has_prop(env, primitive, "frontFace"))
            desc.primitive.frontFace = front_face_from_string(env, get_prop(env, primitive, "frontFace"));
        if (has_prop(env, primitive, "cullMode"))
            desc.primitive.cullMode = cull_mode_from_string(env, get_prop(env, primitive, "cullMode"));
        if (has_prop(env, primitive, "unclippedDepth"))
            desc.primitive.unclippedDepth = get_bool_prop(env, primitive, "unclippedDepth") ? 1 : 0;
    }
    desc.depthStencil = NULL;
    if (has_prop(env, _args[1], "depthStencil") && prop_type(env, _args[1], "depthStencil") == napi_object) {
        napi_value depth_obj = get_prop(env, _args[1], "depthStencil");
        depth_stencil = (WGPURenderDepthStencilState*)calloc(1, sizeof(WGPURenderDepthStencilState));
        if (!depth_stencil) {
            free(vertex_buffers);
            free(vertex_attributes);
            free(vertex_entry);
            free(fragment_entry);
            NAPI_THROW(env, "createRenderPipeline: out of memory");
        }
        depth_stencil->nextInChain = NULL;
        depth_stencil->format = texture_format_from_string(env, get_prop(env, depth_obj, "format"));
        depth_stencil->depthWriteEnabled = has_prop(env, depth_obj, "depthWriteEnabled")
            ? (get_bool_prop(env, depth_obj, "depthWriteEnabled") ? 1 : 0)
            : 0;
        depth_stencil->depthCompare = has_prop(env, depth_obj, "depthCompare")
            ? compare_func_from_value(env, get_prop(env, depth_obj, "depthCompare"))
            : 0x00000008;
        depth_stencil->stencilReadMask = 0xFFFFFFFFu;
        depth_stencil->stencilWriteMask = 0xFFFFFFFFu;
        desc.depthStencil = depth_stencil;
    }
    desc.multisample.nextInChain = NULL;
    desc.multisample.count = 1;
    desc.multisample.mask = 0xFFFFffffu;
    desc.multisample.alphaToCoverageEnabled = 0;
    if (has_prop(env, _args[1], "multisample") && prop_type(env, _args[1], "multisample") == napi_object) {
        napi_value multisample = get_prop(env, _args[1], "multisample");
        if (has_prop(env, multisample, "count"))
            desc.multisample.count = get_uint32_prop(env, multisample, "count");
        if (has_prop(env, multisample, "mask"))
            desc.multisample.mask = get_uint32_prop(env, multisample, "mask");
        if (has_prop(env, multisample, "alphaToCoverageEnabled"))
            desc.multisample.alphaToCoverageEnabled = get_bool_prop(env, multisample, "alphaToCoverageEnabled") ? 1 : 0;
    }
    desc.fragment = &fragment_state;

    WGPURenderPipeline rp = pfn_wgpuDeviceCreateRenderPipeline(device, &desc);
    free(depth_stencil);
    free(vertex_attributes);
    free(vertex_buffers);
    free(vertex_entry);
    free(fragment_entry);
    if (!rp) NAPI_THROW(env, "createRenderPipeline failed");
    return wrap_ptr(env, rp);
}

static napi_value doe_render_pipeline_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuRenderPipelineRelease(p);
    return NULL;
}

/* renderPipelineGetBindGroupLayout(pipeline, groupIndex) → bindGroupLayout */
static napi_value doe_render_pipeline_get_bind_group_layout(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    void* pipeline = unwrap_ptr(env, _args[0]);
    if (!pipeline) NAPI_THROW(env, "Invalid render pipeline");
    uint32_t index;
    napi_get_value_uint32(env, _args[1], &index);
    if (!pfn_doeNativeRenderPipelineGetBindGroupLayout) NAPI_THROW(env, "renderPipelineGetBindGroupLayout not available");
    void* layout = pfn_doeNativeRenderPipelineGetBindGroupLayout(pipeline, index);
    if (!layout) NAPI_THROW(env, "renderPipelineGetBindGroupLayout failed");
    return wrap_ptr(env, layout);
}

/* ================================================================
 * Render Pass
 * beginRenderPass(encoder, descriptor)
 * ================================================================ */

static napi_value doe_begin_render_pass(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");

    if (prop_type(env, _args[1], "colorAttachments") != napi_object) {
        NAPI_THROW(env, "beginRenderPass requires descriptor.colorAttachments");
    }

    napi_value color_attachments = get_prop(env, _args[1], "colorAttachments");
    uint32_t att_count = 0;
    napi_get_array_length(env, color_attachments, &att_count);
    if (att_count == 0) NAPI_THROW(env, "beginRenderPass: need at least one color attachment");

    WGPURenderPassColorAttachment* atts = (WGPURenderPassColorAttachment*)calloc(
        att_count, sizeof(WGPURenderPassColorAttachment));
    WGPURenderPassDepthStencilAttachment depth_att;
    memset(&depth_att, 0, sizeof(depth_att));
    bool has_depth_att = false;
    for (uint32_t i = 0; i < att_count; i++) {
        napi_value elem;
        napi_get_element(env, color_attachments, i, &elem);
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

    if (has_prop(env, _args[1], "depthStencilAttachment") && prop_type(env, _args[1], "depthStencilAttachment") == napi_object) {
        napi_value depth_obj = get_prop(env, _args[1], "depthStencilAttachment");
        depth_att.nextInChain = NULL;
        depth_att.view = unwrap_ptr(env, get_prop(env, depth_obj, "view"));
        depth_att.depthLoadOp = 1;
        depth_att.depthStoreOp = 1;
        depth_att.depthClearValue = has_prop(env, depth_obj, "depthClearValue")
            ? (float)get_double_prop(env, depth_obj, "depthClearValue")
            : 1.0f;
        depth_att.depthReadOnly = has_prop(env, depth_obj, "depthReadOnly")
            ? (get_bool_prop(env, depth_obj, "depthReadOnly") ? 1 : 0)
            : 0;
        depth_att.stencilLoadOp = 1;
        depth_att.stencilStoreOp = 1;
        depth_att.stencilClearValue = has_prop(env, depth_obj, "stencilClearValue")
            ? get_uint32_prop(env, depth_obj, "stencilClearValue")
            : 0;
        depth_att.stencilReadOnly = has_prop(env, depth_obj, "stencilReadOnly")
            ? (get_bool_prop(env, depth_obj, "stencilReadOnly") ? 1 : 0)
            : 0;
        has_depth_att = true;
    }

    WGPURenderPassDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.colorAttachmentCount = att_count;
    desc.colorAttachments = atts;
    desc.depthStencilAttachment = has_depth_att ? &depth_att : NULL;

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

static napi_value doe_render_pass_set_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t index = 0;
    napi_get_value_uint32(env, _args[1], &index);
    WGPUBindGroup bg = unwrap_ptr(env, _args[2]);
    pfn_wgpuRenderPassEncoderSetBindGroup(pass, index, bg, 0, NULL);
    return NULL;
}

static napi_value doe_render_pass_set_vertex_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t slot = 0;
    uint64_t offset = 0;
    uint64_t size = 0;
    napi_get_value_uint32(env, _args[1], &slot);
    WGPUBuffer buffer = unwrap_ptr(env, _args[2]);
    offset = (uint64_t)get_int64_value(env, _args[3]);
    size = (uint64_t)get_int64_value(env, _args[4]);
    pfn_wgpuRenderPassEncoderSetVertexBuffer(pass, slot, buffer, offset, size);
    return NULL;
}

static napi_value doe_render_pass_set_index_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    WGPUBuffer buffer = unwrap_ptr(env, _args[1]);
    uint32_t format = index_format_from_value(env, _args[2]);
    uint64_t offset = 0;
    uint64_t size = 0;
    offset = (uint64_t)get_int64_value(env, _args[3]);
    size = (uint64_t)get_int64_value(env, _args[4]);
    pfn_wgpuRenderPassEncoderSetIndexBuffer(pass, buffer, format, offset, size);
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

static napi_value doe_render_pass_draw_indexed(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t index_count = 0;
    uint32_t instance_count = 0;
    uint32_t first_index = 0;
    int32_t base_vertex = 0;
    uint32_t first_instance = 0;
    napi_get_value_uint32(env, _args[1], &index_count);
    napi_get_value_uint32(env, _args[2], &instance_count);
    napi_get_value_uint32(env, _args[3], &first_index);
    napi_get_value_int32(env, _args[4], &base_vertex);
    napi_get_value_uint32(env, _args[5], &first_instance);
    pfn_wgpuRenderPassEncoderDrawIndexed(pass, index_count, instance_count, first_index, base_vertex, first_instance);
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
 * GPURenderPassEncoder control methods — top-level module functions
 * The first argument is always the render pass encoder handle.
 * ================================================================ */

/* renderPassSetViewport(pass, x, y, width, height, minDepth, maxDepth) */
static napi_value doe_render_pass_set_viewport(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 7);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetViewport) return NULL;
    double x = 0, y = 0, width = 0, height = 0, min_depth = 0, max_depth = 1;
    napi_get_value_double(env, _args[1], &x);
    napi_get_value_double(env, _args[2], &y);
    napi_get_value_double(env, _args[3], &width);
    napi_get_value_double(env, _args[4], &height);
    napi_get_value_double(env, _args[5], &min_depth);
    napi_get_value_double(env, _args[6], &max_depth);
    pfn_doeNativeRenderPassSetViewport(pass, x, y, width, height, min_depth, max_depth);
    return NULL;
}

/* renderPassSetScissorRect(pass, x, y, width, height) */
static napi_value doe_render_pass_set_scissor_rect(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetScissorRect) return NULL;
    uint32_t x = 0, y = 0, width = 0, height = 0;
    napi_get_value_uint32(env, _args[1], &x);
    napi_get_value_uint32(env, _args[2], &y);
    napi_get_value_uint32(env, _args[3], &width);
    napi_get_value_uint32(env, _args[4], &height);
    pfn_doeNativeRenderPassSetScissorRect(pass, x, y, width, height);
    return NULL;
}

/* renderPassSetBlendConstant(pass, r, g, b, a) */
static napi_value doe_render_pass_set_blend_constant(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetBlendConstant) return NULL;
    double r = 0, g = 0, b = 0, a = 1;
    napi_get_value_double(env, _args[1], &r);
    napi_get_value_double(env, _args[2], &g);
    napi_get_value_double(env, _args[3], &b);
    napi_get_value_double(env, _args[4], &a);
    pfn_doeNativeRenderPassSetBlendConstant(pass, r, g, b, a);
    return NULL;
}

/* renderPassSetStencilReference(pass, reference) */
static napi_value doe_render_pass_set_stencil_reference(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetStencilReference) return NULL;
    uint32_t reference = 0;
    napi_get_value_uint32(env, _args[1], &reference);
    pfn_doeNativeRenderPassSetStencilReference(pass, reference);
    return NULL;
}

/* renderPassPushDebugGroup(pass, groupLabel) */
static napi_value doe_render_pass_push_debug_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassPushDebugGroup) return NULL;
    size_t label_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &label_len);
    char* label = (char*)malloc(label_len + 1);
    if (!label) return NULL;
    napi_get_value_string_utf8(env, _args[1], label, label_len + 1, &label_len);
    pfn_doeNativeRenderPassPushDebugGroup(pass, label, label_len);
    free(label);
    return NULL;
}

/* renderPassPopDebugGroup(pass) */
static napi_value doe_render_pass_pop_debug_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassPopDebugGroup) return NULL;
    pfn_doeNativeRenderPassPopDebugGroup(pass);
    return NULL;
}

/* renderPassInsertDebugMarker(pass, markerLabel) */
static napi_value doe_render_pass_insert_debug_marker(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassInsertDebugMarker) return NULL;
    size_t label_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &label_len);
    char* label = (char*)malloc(label_len + 1);
    if (!label) return NULL;
    napi_get_value_string_utf8(env, _args[1], label, label_len + 1, &label_len);
    pfn_doeNativeRenderPassInsertDebugMarker(pass, label, label_len);
    free(label);
    return NULL;
}

/* ================================================================
 * Render Bundle Encoder
 * ================================================================ */

/* RenderBundleEncoderDescriptor layout matching wgpu_render_types.zig:
 *   nextInChain (ptr), label (WGPUStringView = ptr+len),
 *   colorFormatCount (usize), colorFormats (ptr), depthStencilFormat (u32),
 *   sampleCount (u32), depthReadOnly (u32), stencilReadOnly (u32) */
typedef struct {
    void*    nextInChain;
    void*    label_data;
    size_t   label_len;
    size_t   colorFormatCount;
    uint32_t* colorFormats;
    uint32_t depthStencilFormat;
    uint32_t sampleCount;
    uint32_t depthReadOnly;
    uint32_t stencilReadOnly;
} BundleEncoderDescC;

/* createRenderBundleEncoder(deviceNative, colorFormats[], depthStencilFormat,
 *                           sampleCount, depthReadOnly, stencilReadOnly) */
static napi_value doe_create_render_bundle_encoder(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceCreateRenderBundleEncoder) NAPI_THROW(env, "doeNativeDeviceCreateRenderBundleEncoder not available");
    void* device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "createRenderBundleEncoder: invalid device");

    /* colorFormats: JS array of uint32 texture format values */
    uint32_t fmt_count = 0;
    bool is_array = false;
    napi_is_array(env, _args[1], &is_array);
    if (is_array) napi_get_array_length(env, _args[1], &fmt_count);
    uint32_t* fmts = fmt_count > 0 ? (uint32_t*)malloc(fmt_count * sizeof(uint32_t)) : NULL;
    for (uint32_t i = 0; i < fmt_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[1], i, &elem);
        napi_get_value_uint32(env, elem, &fmts[i]);
    }

    uint32_t depth_stencil_format = 0; napi_get_value_uint32(env, _args[2], &depth_stencil_format);
    uint32_t sample_count         = 1; napi_get_value_uint32(env, _args[3], &sample_count);
    bool     depth_read_only      = false; napi_get_value_bool(env, _args[4], &depth_read_only);
    bool     stencil_read_only    = false; napi_get_value_bool(env, _args[5], &stencil_read_only);

    BundleEncoderDescC desc = {
        .nextInChain         = NULL,
        .label_data          = NULL,
        .label_len           = 0,
        .colorFormatCount    = (size_t)fmt_count,
        .colorFormats        = fmts,
        .depthStencilFormat  = depth_stencil_format,
        .sampleCount         = sample_count == 0 ? 1 : sample_count,
        .depthReadOnly       = depth_read_only ? 1 : 0,
        .stencilReadOnly     = stencil_read_only ? 1 : 0,
    };

    void* enc = pfn_doeNativeDeviceCreateRenderBundleEncoder(device, &desc);
    free(fmts);
    if (!enc) NAPI_THROW(env, "createRenderBundleEncoder failed");
    return wrap_ptr(env, enc);
}

/* renderBundleEncoderSetPipeline(encoderNative, pipelineNative) */
static napi_value doe_render_bundle_encoder_set_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* enc      = unwrap_ptr(env, _args[0]);
    void* pipeline = unwrap_ptr(env, _args[1]);
    if (!enc || !pipeline) return NULL;
    if (pfn_doeNativeRenderBundleEncoderSetPipeline)
        pfn_doeNativeRenderBundleEncoderSetPipeline(enc, pipeline);
    return NULL;
}

/* renderBundleEncoderSetBindGroup(encoderNative, index, bindGroupNative) */
static napi_value doe_render_bundle_encoder_set_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) return NULL;
    uint32_t index = 0; napi_get_value_uint32(env, _args[1], &index);
    void* bg = unwrap_ptr(env, _args[2]);
    if (!bg) return NULL;
    if (pfn_doeNativeRenderBundleEncoderSetBindGroup)
        pfn_doeNativeRenderBundleEncoderSetBindGroup(enc, index, bg, 0, NULL);
    return NULL;
}

/* renderBundleEncoderSetVertexBuffer(encoderNative, slot, bufferNative, offset, size) */
static napi_value doe_render_bundle_encoder_set_vertex_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) return NULL;
    uint32_t slot = 0; napi_get_value_uint32(env, _args[1], &slot);
    void* buf = unwrap_ptr(env, _args[2]);
    if (!buf) return NULL;
    int64_t offset = 0; napi_get_value_int64(env, _args[3], &offset);
    int64_t size   = 0; napi_get_value_int64(env, _args[4], &size);
    if (pfn_doeNativeRenderBundleEncoderSetVertexBuffer)
        pfn_doeNativeRenderBundleEncoderSetVertexBuffer(enc, slot, buf, (uint64_t)offset, (uint64_t)size);
    return NULL;
}

/* renderBundleEncoderSetIndexBuffer(encoderNative, bufferNative, format, offset, size) */
static napi_value doe_render_bundle_encoder_set_index_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) return NULL;
    void* buf = unwrap_ptr(env, _args[1]);
    if (!buf) return NULL;
    uint32_t format = 0; napi_get_value_uint32(env, _args[2], &format);
    int64_t  offset = 0; napi_get_value_int64(env, _args[3], &offset);
    int64_t  size   = 0; napi_get_value_int64(env, _args[4], &size);
    if (pfn_doeNativeRenderBundleEncoderSetIndexBuffer)
        pfn_doeNativeRenderBundleEncoderSetIndexBuffer(enc, buf, format, (uint64_t)offset, (uint64_t)size);
    return NULL;
}

/* renderBundleEncoderDraw(encoderNative, vertexCount, instanceCount, firstVertex, firstInstance) */
static napi_value doe_render_bundle_encoder_draw(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) return NULL;
    uint32_t vertex_count   = 0; napi_get_value_uint32(env, _args[1], &vertex_count);
    uint32_t instance_count = 1; napi_get_value_uint32(env, _args[2], &instance_count);
    uint32_t first_vertex   = 0; napi_get_value_uint32(env, _args[3], &first_vertex);
    uint32_t first_instance = 0; napi_get_value_uint32(env, _args[4], &first_instance);
    if (pfn_doeNativeRenderBundleEncoderDraw)
        pfn_doeNativeRenderBundleEncoderDraw(enc, vertex_count, instance_count, first_vertex, first_instance);
    return NULL;
}

/* renderBundleEncoderDrawIndexed(encoderNative, indexCount, instanceCount,
 *                                firstIndex, baseVertex, firstInstance) */
static napi_value doe_render_bundle_encoder_draw_indexed(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) return NULL;
    uint32_t index_count    = 0; napi_get_value_uint32(env, _args[1], &index_count);
    uint32_t instance_count = 1; napi_get_value_uint32(env, _args[2], &instance_count);
    uint32_t first_index    = 0; napi_get_value_uint32(env, _args[3], &first_index);
    int32_t  base_vertex    = 0;
    napi_valuetype bv_type; napi_typeof(env, _args[4], &bv_type);
    if (bv_type == napi_number) { int64_t bv = 0; napi_get_value_int64(env, _args[4], &bv); base_vertex = (int32_t)bv; }
    uint32_t first_instance = 0; napi_get_value_uint32(env, _args[5], &first_instance);
    if (pfn_doeNativeRenderBundleEncoderDrawIndexed)
        pfn_doeNativeRenderBundleEncoderDrawIndexed(enc, index_count, instance_count, first_index, base_vertex, first_instance);
    return NULL;
}

/* renderBundleEncoderFinish(encoderNative) → bundleNative */
static napi_value doe_render_bundle_encoder_finish(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeRenderBundleEncoderFinish) NAPI_THROW(env, "doeNativeRenderBundleEncoderFinish not available");
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "renderBundleEncoderFinish: invalid encoder");
    void* bundle = pfn_doeNativeRenderBundleEncoderFinish(enc, NULL);
    if (!bundle) NAPI_THROW(env, "renderBundleEncoderFinish failed");
    return wrap_ptr(env, bundle);
}

/* renderBundleEncoderRelease(encoderNative) */
static napi_value doe_render_bundle_encoder_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* enc = unwrap_ptr(env, _args[0]);
    if (enc && pfn_doeNativeRenderBundleEncoderRelease)
        pfn_doeNativeRenderBundleEncoderRelease(enc);
    return NULL;
}

/* renderBundleRelease(bundleNative) */
static napi_value doe_render_bundle_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* bundle = unwrap_ptr(env, _args[0]);
    if (bundle && pfn_doeNativeRenderBundleRelease)
        pfn_doeNativeRenderBundleRelease(bundle);
    return NULL;
}

/* ================================================================
 * Device capabilities: limits, features
 * ================================================================ */

static napi_value create_limits_object(napi_env env, const WGPULimits* limits) {
    napi_value obj;
    napi_create_object(env, &obj);

#define SET_U32(name) do { napi_value v; napi_create_uint32(env, limits->name, &v); napi_set_named_property(env, obj, #name, v); } while(0)
#define SET_U64(name) do { napi_value v; napi_create_double(env, (double)limits->name, &v); napi_set_named_property(env, obj, #name, v); } while(0)

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

static napi_value doe_device_get_limits(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "deviceGetLimits: null device");
    uint32_t (*fn)(WGPUDevice, void*) = pfn_doeNativeDeviceGetLimits ? pfn_doeNativeDeviceGetLimits : pfn_wgpuDeviceGetLimits;
    if (!fn) {
        napi_value ret;
        napi_get_null(env, &ret);
        return ret;
    }

    WGPULimits limits;
    memset(&limits, 0, sizeof(limits));
    uint32_t status = fn(device, &limits);
    if (status != WGPU_STATUS_SUCCESS) {
        napi_value ret;
        napi_get_null(env, &ret);
        return ret;
    }

    return create_limits_object(env, &limits);
}

static napi_value doe_adapter_get_limits(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUAdapter adapter = unwrap_ptr(env, _args[0]);
    if (!adapter) NAPI_THROW(env, "adapterGetLimits: null adapter");
    uint32_t (*fn)(WGPUAdapter, void*) = pfn_doeNativeAdapterGetLimits ? pfn_doeNativeAdapterGetLimits : pfn_wgpuAdapterGetLimits;
    if (!fn) {
        napi_value ret;
        napi_get_null(env, &ret);
        return ret;
    }

    WGPULimits limits;
    memset(&limits, 0, sizeof(limits));
    uint32_t status = fn(adapter, &limits);
    if (status != WGPU_STATUS_SUCCESS) {
        napi_value ret;
        napi_get_null(env, &ret);
        return ret;
    }

    return create_limits_object(env, &limits);
}

static napi_value doe_adapter_has_feature(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUAdapter adapter = unwrap_ptr(env, _args[0]);
    uint32_t (*fn)(WGPUAdapter, uint32_t) = pfn_doeNativeAdapterHasFeature ? pfn_doeNativeAdapterHasFeature : pfn_wgpuAdapterHasFeature;
    if (!fn) {
        napi_value ret;
        napi_get_boolean(env, false, &ret);
        return ret;
    }
    uint32_t feature;
    napi_get_value_uint32(env, _args[1], &feature);
    uint32_t result = fn(adapter, feature);
    napi_value ret;
    napi_get_boolean(env, result != 0, &ret);
    return ret;
}

static napi_value doe_device_has_feature(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    uint32_t (*fn)(WGPUDevice, uint32_t) = pfn_doeNativeDeviceHasFeature ? pfn_doeNativeDeviceHasFeature : pfn_wgpuDeviceHasFeature;
    if (!fn) {
        napi_value ret;
        napi_get_boolean(env, false, &ret);
        return ret;
    }
    uint32_t feature;
    napi_get_value_uint32(env, _args[1], &feature);
    uint32_t result = fn(device, feature);
    napi_value ret;
    napi_get_boolean(env, result != 0, &ret);
    return ret;
}

static napi_value doe_get_last_error_stage(napi_env env, napi_callback_info info) {
    (void)info;
    char buf[64];
    copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, buf, sizeof(buf));
    if (buf[0] == '\0') return NULL;
    napi_value result;
    napi_create_string_utf8(env, buf, NAPI_AUTO_LENGTH, &result);
    return result;
}

static napi_value doe_get_last_error_kind(napi_env env, napi_callback_info info) {
    (void)info;
    char buf[64];
    copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, buf, sizeof(buf));
    if (buf[0] == '\0') return NULL;
    napi_value result;
    napi_create_string_utf8(env, buf, NAPI_AUTO_LENGTH, &result);
    return result;
}

static napi_value doe_get_last_error_line(napi_env env, napi_callback_info info) {
    (void)info;
    if (!pfn_doeNativeGetLastErrorLine) return NULL;
    uint32_t line = pfn_doeNativeGetLastErrorLine();
    napi_value result;
    napi_create_uint32(env, line, &result);
    return result;
}

static napi_value doe_get_last_error_column(napi_env env, napi_callback_info info) {
    (void)info;
    if (!pfn_doeNativeGetLastErrorColumn) return NULL;
    uint32_t col = pfn_doeNativeGetLastErrorColumn();
    napi_value result;
    napi_create_uint32(env, col, &result);
    return result;
}

static napi_value doe_adapter_get_info(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    void* adapter = unwrap_ptr(env, _args[0]);
    if (!adapter) NAPI_THROW(env, "Invalid adapter");

    napi_value obj;
    napi_create_object(env, &obj);

    const char* vendor = "";
    const char* arch = "";
    const char* device = "";
    const char* desc = "";
    char* block = NULL;

    if (pfn_doeNativeAdapterGetInfo && pfn_doeNativeAdapterFreeInfo) {
        pfn_doeNativeAdapterGetInfo(adapter, &vendor, &arch, &device, &desc, &block);
        if (!vendor) vendor = "";
        if (!arch) arch = "";
        if (!device) device = "";
        if (!desc) desc = "";
    }

    napi_value v_vendor, v_arch, v_device, v_desc, v_sg_min, v_sg_max;
    napi_create_string_utf8(env, vendor, NAPI_AUTO_LENGTH, &v_vendor);
    napi_create_string_utf8(env, arch, NAPI_AUTO_LENGTH, &v_arch);
    napi_create_string_utf8(env, device, NAPI_AUTO_LENGTH, &v_device);
    napi_create_string_utf8(env, desc, NAPI_AUTO_LENGTH, &v_desc);
    napi_create_uint32(env, 32, &v_sg_min);
    napi_create_uint32(env, 32, &v_sg_max);
    napi_set_named_property(env, obj, "vendor", v_vendor);
    napi_set_named_property(env, obj, "architecture", v_arch);
    napi_set_named_property(env, obj, "device", v_device);
    napi_set_named_property(env, obj, "description", v_desc);
    napi_set_named_property(env, obj, "subgroupMinSize", v_sg_min);
    napi_set_named_property(env, obj, "subgroupMaxSize", v_sg_max);

    if (block && pfn_doeNativeAdapterFreeInfo) {
        pfn_doeNativeAdapterFreeInfo(block);
    }
    return obj;
}

static napi_value doe_shader_module_get_compilation_info(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    void* shader_module = unwrap_ptr(env, _args[0]);

    const char* json_str = "[]";
    if (pfn_doeNativeShaderModuleGetCompilationInfo) {
        const char* native_json = pfn_doeNativeShaderModuleGetCompilationInfo(shader_module);
        if (native_json) json_str = native_json;
    }

    napi_value global, json_obj, json_parse_fn, json_str_val, parse_args[1], parsed, messages, compilation_info;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "JSON", &json_obj);
    napi_get_named_property(env, json_obj, "parse", &json_parse_fn);
    napi_create_string_utf8(env, json_str, NAPI_AUTO_LENGTH, &json_str_val);
    parse_args[0] = json_str_val;
    if (napi_call_function(env, json_obj, json_parse_fn, 1, parse_args, &parsed) != napi_ok) {
        napi_create_array_with_length(env, 0, &messages);
    } else {
        messages = parsed;
    }
    napi_create_object(env, &compilation_info);
    napi_set_named_property(env, compilation_info, "messages", messages);
    return native_direct_resolved_promise(env, compilation_info);
}

static napi_value doe_command_encoder_clear_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 4;
    napi_value argv[4];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (argc < 2) NAPI_THROW(env, "commandEncoderClearBuffer requires encoder and buffer");
    if (!pfn_doeNativeCommandEncoderClearBuffer) {
        NAPI_THROW(env, "commandEncoderClearBuffer: no implementation available in loaded library");
    }
    WGPUCommandEncoder enc = unwrap_ptr(env, argv[0]);
    WGPUBuffer buffer = unwrap_ptr(env, argv[1]);
    if (!enc || !buffer) NAPI_THROW(env, "commandEncoderClearBuffer requires encoder and buffer");
    uint64_t offset = 0;
    uint64_t size = WGPU_WHOLE_SIZE;
    if (argc >= 3) {
        napi_valuetype vt;
        napi_typeof(env, argv[2], &vt);
        if (vt == napi_number || vt == napi_bigint) {
            int64_t v = 0;
            napi_get_value_int64(env, argv[2], &v);
            if (v > 0) offset = (uint64_t)v;
        }
    }
    if (argc >= 4) {
        napi_valuetype vt;
        napi_typeof(env, argv[3], &vt);
        if (vt == napi_number || vt == napi_bigint) {
            int64_t v = 0;
            napi_get_value_int64(env, argv[3], &v);
            if (v > 0) size = (uint64_t)v;
            else if (v == 0) size = 0;
        }
    }
    pfn_doeNativeCommandEncoderClearBuffer(enc, buffer, offset, size);
    return NULL;
}

static napi_value doe_command_encoder_copy_texture_to_texture(napi_env env, napi_callback_info info) {
    size_t argc = 15;
    napi_value argv[15];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (argc != 14 && argc != 15) {
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture requires 14 or 15 arguments");
    }
    if (!pfn_doeNativeCommandEncoderCopyTextureToTexture && !pfn_wgpuCommandEncoderCopyTextureToTexture) {
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture: no implementation available in loaded library");
    }
    const size_t dst_index = argc == 15 ? 7 : 6;
    const size_t dst_mip_index = argc == 15 ? 8 : 7;
    const size_t dst_x_index = argc == 15 ? 9 : 8;
    const size_t dst_y_index = argc == 15 ? 10 : 9;
    const size_t dst_z_index = argc == 15 ? 11 : 10;
    const size_t width_index = argc == 15 ? 12 : 11;
    const size_t height_index = argc == 15 ? 13 : 12;
    const size_t depth_index = argc == 15 ? 14 : 13;

    WGPUCommandEncoder enc = unwrap_ptr(env, argv[0]);
    WGPUTexture src_texture = unwrap_ptr(env, argv[1]);
    WGPUTexture dst_texture = unwrap_ptr(env, argv[dst_index]);
    if (!enc || !src_texture || !dst_texture) {
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture requires encoder and textures");
    }
    uint32_t src_mip = 0, src_x = 0, src_y = 0, src_z = 0;
    uint32_t dst_mip = 0, dst_x = 0, dst_y = 0, dst_z = 0;
    uint32_t width = 1, height = 1, depth_or_layers = 1;
    napi_get_value_uint32(env, argv[2], &src_mip);
    napi_get_value_uint32(env, argv[3], &src_x);
    napi_get_value_uint32(env, argv[4], &src_y);
    napi_get_value_uint32(env, argv[5], &src_z);
    napi_get_value_uint32(env, argv[dst_mip_index], &dst_mip);
    napi_get_value_uint32(env, argv[dst_x_index], &dst_x);
    napi_get_value_uint32(env, argv[dst_y_index], &dst_y);
    napi_get_value_uint32(env, argv[dst_z_index], &dst_z);
    napi_get_value_uint32(env, argv[width_index], &width);
    napi_get_value_uint32(env, argv[height_index], &height);
    napi_get_value_uint32(env, argv[depth_index], &depth_or_layers);
    if (pfn_doeNativeCommandEncoderCopyTextureToTexture) {
        pfn_doeNativeCommandEncoderCopyTextureToTexture(
            enc,
            src_texture, src_mip, 0, src_x, src_y, src_z,
            dst_texture, dst_mip, 0, dst_x, dst_y, dst_z,
            width, height, depth_or_layers);
    } else {
        WGPUTexelCopyTextureInfo src;
        WGPUTexelCopyTextureInfo dst;
        WGPUExtent3D size;
        memset(&src, 0, sizeof(src));
        memset(&dst, 0, sizeof(dst));
        src.texture = src_texture;
        src.mipLevel = src_mip;
        src.origin.x = src_x;
        src.origin.y = src_y;
        src.origin.z = src_z;
        dst.texture = dst_texture;
        dst.mipLevel = dst_mip;
        dst.origin.x = dst_x;
        dst.origin.y = dst_y;
        dst.origin.z = dst_z;
        size.width = width;
        size.height = height;
        size.depthOrArrayLayers = depth_or_layers;
        pfn_wgpuCommandEncoderCopyTextureToTexture(enc, &src, &dst, &size);
    }
    return NULL;
}

typedef struct {
    uint32_t done;
    uint32_t error_type;
    char message[DOE_ERROR_BUF_CAP];
} DevicePopErrorScopeResult;

static void pop_error_scope_callback(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    DevicePopErrorScopeResult* result = (DevicePopErrorScopeResult*)userdata1;
    result->done = 1;
    result->error_type = error_type;
    copy_string_view_message(message, result->message, sizeof(result->message));
}

static napi_value doe_device_push_error_scope(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDevicePushErrorScope && !pfn_wgpuDevicePushErrorScope) NAPI_THROW(env, "devicePushErrorScope not available");
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    uint32_t filter = 0;
    napi_get_value_uint32(env, _args[1], &filter);
    if (pfn_doeNativeDevicePushErrorScope) {
        pfn_doeNativeDevicePushErrorScope(device, filter);
    } else {
        pfn_wgpuDevicePushErrorScope(device, filter);
    }
    return NULL;
}

static napi_value doe_device_pop_error_scope(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDevicePopErrorScope && !pfn_wgpuDevicePopErrorScope) NAPI_THROW(env, "devicePopErrorScope not available");
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    DevicePopErrorScopeResult result = {0};
    WGPUPopErrorScopeCallbackInfo2 cb_info = {
        .next_in_chain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = pop_error_scope_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    if (pfn_wgpuDevicePopErrorScope) {
        pfn_wgpuDevicePopErrorScope(device, cb_info);
    } else {
        pfn_doeNativeDevicePopErrorScope(device, cb_info);
    }
    if (!result.done) {
        NAPI_THROW(env, "popErrorScope: no active error scope");
    }
    if (result.error_type == 0x00000001) {
        return NULL;
    }

    napi_value out, type_val, message_val;
    napi_create_object(env, &out);
    napi_create_string_utf8(env, error_type_string(result.error_type), NAPI_AUTO_LENGTH, &type_val);
    napi_create_string_utf8(env, result.message, NAPI_AUTO_LENGTH, &message_val);
    napi_set_named_property(env, out, "type", type_val);
    napi_set_named_property(env, out, "message", message_val);
    return out;
}

static napi_value doe_device_set_uncaptured_error_callback(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceSetUncapturedErrorCallback) {
        napi_value result;
        napi_get_boolean(env, false, &result);
        return result;
    }
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    DeviceCallbackBinding* old = binding_take(&g_uncaptured_bindings, device);
    if (old) {
        pfn_doeNativeDeviceSetUncapturedErrorCallback(device, NULL, NULL, NULL);
        release_binding(old);
    }

    napi_valuetype cb_type;
    napi_typeof(env, _args[1], &cb_type);
    if (cb_type == napi_null || cb_type == napi_undefined) {
        return NULL;
    }
    if (cb_type != napi_function) {
        NAPI_THROW(env, "deviceSetUncapturedErrorCallback requires a function or null");
    }

    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)calloc(1, sizeof(DeviceCallbackBinding));
    if (!binding) NAPI_THROW(env, "Out of memory");
    binding->device = device;
    napi_value resource_name;
    napi_create_string_utf8(env, "doeDeviceUncapturedError", NAPI_AUTO_LENGTH, &resource_name);
    if (napi_create_threadsafe_function(
            env, _args[1], NULL, resource_name, 0, 1,
            binding, binding_finalize, NULL, js_call_uncaptured_error, &binding->tsfn) != napi_ok) {
        free(binding);
        NAPI_THROW(env, "Failed to create uncaptured-error callback bridge");
    }
    napi_unref_threadsafe_function(env, binding->tsfn);
    binding_insert(&g_uncaptured_bindings, binding);
    pfn_doeNativeDeviceSetUncapturedErrorCallback(device, uncaptured_error_native_callback, binding, NULL);
    napi_value result;
    napi_get_boolean(env, true, &result);
    return result;
}

static napi_value doe_device_register_lost_callback(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceRegisterLostCallback) {
        napi_value result;
        napi_get_boolean(env, false, &result);
        return result;
    }
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    DeviceCallbackBinding* old = binding_take(&g_lost_bindings, device);
    if (old) {
        release_binding(old);
    }

    napi_valuetype cb_type;
    napi_typeof(env, _args[1], &cb_type);
    if (cb_type != napi_function) {
        NAPI_THROW(env, "deviceRegisterLostCallback requires a function");
    }

    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)calloc(1, sizeof(DeviceCallbackBinding));
    if (!binding) NAPI_THROW(env, "Out of memory");
    binding->device = device;
    napi_value resource_name;
    napi_create_string_utf8(env, "doeDeviceLost", NAPI_AUTO_LENGTH, &resource_name);
    if (napi_create_threadsafe_function(
            env, _args[1], NULL, resource_name, 0, 1,
            binding, binding_finalize, NULL, js_call_lost_callback, &binding->tsfn) != napi_ok) {
        free(binding);
        NAPI_THROW(env, "Failed to create device-lost callback bridge");
    }
    napi_unref_threadsafe_function(env, binding->tsfn);
    binding_insert(&g_lost_bindings, binding);
    pfn_doeNativeDeviceRegisterLostCallback(device, lost_native_callback, binding);
    napi_value result;
    napi_get_boolean(env, true, &result);
    return result;
}

/* ================================================================
 * QuerySet (timestamp query)
 * ================================================================ */

static napi_value doe_create_query_set(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceCreateQuerySet) NAPI_THROW(env, "doeNativeDeviceCreateQuerySet not available");
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    uint32_t query_type = 0;
    napi_get_value_uint32(env, _args[1], &query_type);
    uint32_t count = 0;
    napi_get_value_uint32(env, _args[2], &count);
    WGPUQuerySet qs = pfn_doeNativeDeviceCreateQuerySet(device, query_type, count);
    if (!qs) NAPI_THROW(env, "timestamp query sets are not supported on this backend/device");
    return wrap_ptr(env, qs);
}

static napi_value doe_command_encoder_write_timestamp(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeCommandEncoderWriteTimestamp) NAPI_THROW(env, "doeNativeCommandEncoderWriteTimestamp not available");
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUQuerySet qs = unwrap_ptr(env, _args[1]);
    uint32_t query_index = 0;
    napi_get_value_uint32(env, _args[2], &query_index);
    pfn_doeNativeCommandEncoderWriteTimestamp(enc, qs, query_index);
    return NULL;
}

static napi_value doe_command_encoder_resolve_query_set(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeCommandEncoderResolveQuerySet) NAPI_THROW(env, "doeNativeCommandEncoderResolveQuerySet not available");
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUQuerySet qs = unwrap_ptr(env, _args[1]);
    uint32_t first_query = 0;
    napi_get_value_uint32(env, _args[2], &first_query);
    uint32_t query_count = 0;
    napi_get_value_uint32(env, _args[3], &query_count);
    WGPUBuffer dst = unwrap_ptr(env, _args[4]);
    int64_t dst_offset = 0;
    napi_get_value_int64(env, _args[5], &dst_offset);
    pfn_doeNativeCommandEncoderResolveQuerySet(enc, qs, first_query, query_count, dst, (uint64_t)dst_offset);
    return NULL;
}

static napi_value doe_query_set_destroy(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    if (!pfn_doeNativeQuerySetDestroy) return NULL;
    WGPUQuerySet qs = unwrap_ptr(env, _args[0]);
    if (qs) pfn_doeNativeQuerySetDestroy(qs);
    return NULL;
}

static napi_value doe_set_timeout_ms(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    uint32_t timeout_ms = 0;
    napi_get_value_uint32(env, _args[0], &timeout_ms);
    g_timeout_ns = (uint64_t)timeout_ms * 1000000ULL;
    return NULL;
}

#define DOE_DIRECT_NATIVE "__doe_native"
#define DOE_DIRECT_INSTANCE "__doe_instance"
#define DOE_DIRECT_QUEUE "__doe_queue"
#define DOE_DIRECT_QUEUE_NATIVE "__doe_queue_native"
#define DOE_DIRECT_SUBMITTED_SERIAL "__doe_submitted_serial"
#define DOE_DIRECT_COMPLETED_SERIAL "__doe_completed_serial"
#define DOE_DIRECT_DIAG_SUBMIT_WAIT_MS "__doe_diag_submit_wait_ms"
#define DOE_DIRECT_DIAG_QUEUE_FLUSH_MS "__doe_diag_queue_flush_ms"
#define DOE_DIRECT_DIAG_MAP_ASYNC_MS "__doe_diag_map_async_ms"
#define DOE_DIRECT_DIAG_MAP_QUEUE_FLUSH_MS "__doe_diag_map_queue_flush_ms"
#define DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS "__doe_diag_get_mapped_range_ms"

static napi_value create_native_direct_gpu_object(napi_env env, WGPUInstance instance);
static napi_value create_native_direct_adapter_object(napi_env env, WGPUInstance instance, WGPUAdapter adapter);
static napi_value create_native_direct_device_object(napi_env env, WGPUInstance instance, WGPUDevice device);
static napi_value create_native_direct_queue_object(napi_env env, WGPUInstance instance, WGPUQueue queue);
static napi_value create_native_direct_buffer_object(napi_env env, WGPUInstance instance, napi_value queue_obj, WGPUBuffer buffer, uint64_t size, uint64_t usage);
static napi_value create_native_direct_bind_group_layout_object(napi_env env, WGPUBindGroupLayout layout);
static napi_value create_native_direct_bind_group_object(napi_env env, WGPUBindGroup group);
static napi_value create_native_direct_pipeline_layout_object(napi_env env, WGPUPipelineLayout layout);
static napi_value create_native_direct_shader_module_object(napi_env env, WGPUShaderModule shader_module);
static napi_value create_native_direct_compute_pipeline_object(napi_env env, WGPUComputePipeline pipeline);
static napi_value create_native_direct_command_encoder_object(napi_env env, WGPUCommandEncoder encoder);
static napi_value create_native_direct_command_buffer_object(napi_env env, WGPUCommandBuffer command_buffer);
static napi_value create_native_direct_compute_pass_object(napi_env env, WGPUComputePassEncoder pass);

static napi_ref native_direct_method_gpu_request_adapter_ref;
static napi_ref native_direct_method_adapter_request_device_ref;
static napi_ref native_direct_method_adapter_destroy_ref;
static napi_ref native_direct_method_queue_submit_ref;
static napi_ref native_direct_method_queue_write_buffer_ref;
static napi_ref native_direct_method_queue_on_submitted_work_done_ref;
static napi_ref native_direct_method_device_create_buffer_ref;
static napi_ref native_direct_method_device_create_shader_module_ref;
static napi_ref native_direct_method_device_create_compute_pipeline_ref;
static napi_ref native_direct_method_device_create_compute_pipeline_async_ref;
static napi_ref native_direct_method_device_create_bind_group_layout_ref;
static napi_ref native_direct_method_device_create_bind_group_ref;
static napi_ref native_direct_method_device_create_pipeline_layout_ref;
static napi_ref native_direct_method_device_create_command_encoder_ref;
static napi_ref native_direct_method_device_destroy_ref;
static napi_ref native_direct_method_buffer_map_async_ref;
static napi_ref native_direct_method_buffer_get_mapped_range_ref;
static napi_ref native_direct_method_buffer_read_copy_ref;
static napi_ref native_direct_method_buffer_map_read_copy_unmap_ref;
static napi_ref native_direct_method_buffer_unmap_ref;
static napi_ref native_direct_method_buffer_destroy_ref;
static napi_ref native_direct_method_command_encoder_begin_compute_pass_ref;
static napi_ref native_direct_method_command_encoder_copy_buffer_to_buffer_ref;
static napi_ref native_direct_method_command_encoder_finish_ref;
static napi_ref native_direct_method_compute_pass_set_pipeline_ref;
static napi_ref native_direct_method_compute_pass_set_bind_group_ref;
static napi_ref native_direct_method_compute_pass_dispatch_workgroups_ref;
static napi_ref native_direct_method_compute_pass_dispatch_workgroups_indirect_ref;
static napi_ref native_direct_method_compute_pass_end_ref;
static napi_ref native_direct_method_compute_pass_set_immediates_ref;
static napi_ref native_direct_method_render_pass_set_immediates_ref;
static napi_ref native_direct_method_render_pass_set_viewport_ref;
static napi_ref native_direct_method_render_pass_set_scissor_rect_ref;
static napi_ref native_direct_method_render_pass_set_blend_constant_ref;
static napi_ref native_direct_method_render_pass_set_stencil_reference_ref;
static napi_ref native_direct_method_render_pass_push_debug_group_ref;
static napi_ref native_direct_method_render_pass_pop_debug_group_ref;
static napi_ref native_direct_method_render_pass_insert_debug_marker_ref;
static napi_ref native_direct_method_render_bundle_encoder_set_immediates_ref;
static napi_ref native_direct_method_adapter_get_preferred_canvas_format_ref;
static napi_ref native_direct_method_device_add_event_listener_ref;
static napi_ref native_direct_method_device_remove_event_listener_ref;
static napi_ref native_direct_method_device_import_external_texture_ref;
static napi_ref native_direct_method_command_encoder_clear_buffer_ref;
static napi_ref native_direct_method_command_encoder_copy_texture_to_texture_ref;
static napi_ref native_direct_method_queue_write_texture_ref;
static napi_ref native_direct_method_adapter_get_info_ref;
static napi_ref native_direct_method_shader_module_get_compilation_info_ref;

typedef struct {
    WGPUInstance instance;
    void* native;
} NativeDirectHandleCache;

typedef struct {
    WGPUInstance instance;
    WGPUQueue queue;
    uint32_t submitted_serial;
    uint32_t completed_serial;
} NativeDirectQueueCache;

typedef struct {
    WGPUInstance instance;
    WGPUBuffer buffer;
    uint64_t size;
    uint64_t usage;
    napi_ref queue_ref;
    napi_ref mapped_range_ref;
    size_t mapped_offset;
    size_t mapped_size;
    void* mapped_ptr;
} NativeDirectBufferCache;

static NativeDirectHandleCache* native_direct_get_handle_cache(napi_env env, napi_value obj);
static NativeDirectQueueCache* native_direct_get_queue_cache(napi_env env, napi_value obj);
static NativeDirectBufferCache* native_direct_get_buffer_cache(napi_env env, napi_value obj);
static void* native_direct_unwrap_external_prop(napi_env env, napi_value obj, const char* key);
static napi_ref native_direct_resolved_undefined_promise_ref;

/* ================================================================
 * Texture format u32 → string (inverse of texture_format_from_string)
 * Used by getPreferredCanvasFormat to convert the returned u32 to a JS string.
 * Only the canvas-candidate formats are mapped; unknown values fall back to
 * returning the u32 as a number (handled at call site).
 * ================================================================ */

static const char* texture_format_u32_to_string(uint32_t fmt) {
    switch (fmt) {
        case 0x00000001: return "r8unorm";
        case 0x00000002: return "r8snorm";
        case 0x00000003: return "r8uint";
        case 0x00000004: return "r8sint";
        case 0x00000007: return "r16uint";
        case 0x00000008: return "r16sint";
        case 0x00000009: return "r16float";
        case 0x0000000A: return "rg8unorm";
        case 0x0000000B: return "rg8snorm";
        case 0x0000000C: return "rg8uint";
        case 0x0000000D: return "rg8sint";
        case 0x0000000E: return "r32float";
        case 0x0000000F: return "r32uint";
        case 0x00000010: return "r32sint";
        case 0x00000013: return "rg16uint";
        case 0x00000014: return "rg16sint";
        case 0x00000015: return "rg16float";
        case 0x00000016: return "rgba8unorm";
        case 0x00000017: return "rgba8unorm-srgb";
        case 0x00000018: return "rgba8snorm";
        case 0x00000019: return "rgba8uint";
        case 0x0000001A: return "rgba8sint";
        case 0x0000001B: return "bgra8unorm";
        case 0x0000001C: return "bgra8unorm-srgb";
        case 0x0000001D: return "rgb10a2uint";
        case 0x0000001E: return "rgb10a2unorm";
        case 0x0000001F: return "rg11b10ufloat";
        case 0x00000020: return "rgb9e5ufloat";
        case 0x00000021: return "rg32float";
        case 0x00000022: return "rg32uint";
        case 0x00000023: return "rg32sint";
        case 0x00000024: return "rgba16uint";
        case 0x00000025: return "rgba16sint";
        case 0x00000026: return "rgba16float";
        case 0x00000027: return "rgba32float";
        case 0x00000028: return "rgba32uint";
        case 0x00000029: return "rgba32sint";
        default: return NULL; /* caller falls back to returning the u32 as a number */
    }
}

/* ================================================================
 * Group A: Adapter — getPreferredCanvasFormat
 * ================================================================ */

static napi_value native_direct_adapter_get_preferred_canvas_format(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    if (!pfn_doeNativeAdapterGetPreferredCanvasFormat) {
        /* Symbol not present yet — return the WebGPU preferred canvas format
         * for Apple Silicon (bgra8unorm is the Metal swapchain default). */
        napi_value result;
        napi_create_string_utf8(env, "bgra8unorm", NAPI_AUTO_LENGTH, &result);
        return result;
    }
    NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
    void* adapter = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    uint32_t fmt = pfn_doeNativeAdapterGetPreferredCanvasFormat(adapter);
    const char* name = texture_format_u32_to_string(fmt);
    if (name) {
        napi_value result;
        napi_create_string_utf8(env, name, NAPI_AUTO_LENGTH, &result);
        return result;
    }
    /* Unknown format — return the raw u32. TODO: extend texture_format_u32_to_string if needed. */
    napi_value result;
    napi_create_uint32(env, fmt, &result);
    return result;
}

/* ================================================================
 * Group A2: Adapter — getInfo
 * ================================================================ */

/* native_direct_adapter_get_info — implements GPUAdapter.info getter.
 * Returns a JS object with vendor, architecture, device, description,
 * subgroupMinSize, and subgroupMaxSize fields.
 * Invoked as a method on the adapter object (zero args, `this` is the
 * adapter).  When the native symbol is absent, returns empty-string fields
 * with Apple Silicon fixed subgroup sizes as conservative defaults. */
static napi_value native_direct_adapter_get_info(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);

    napi_value obj;
    napi_create_object(env, &obj);

    const char* vendor = "";
    const char* arch   = "";
    const char* device = "";
    const char* desc   = "";
    char* block = NULL;

    if (pfn_doeNativeAdapterGetInfo && pfn_doeNativeAdapterFreeInfo) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* adapter = cache ? cache->native
                              : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeAdapterGetInfo(adapter, &vendor, &arch, &device, &desc, &block);
        if (!vendor) vendor = "";
        if (!arch)   arch   = "";
        if (!device) device = "";
        if (!desc)   desc   = "";
    }

    napi_value v_vendor, v_arch, v_device, v_desc;
    napi_create_string_utf8(env, vendor, NAPI_AUTO_LENGTH, &v_vendor);
    napi_create_string_utf8(env, arch,   NAPI_AUTO_LENGTH, &v_arch);
    napi_create_string_utf8(env, device, NAPI_AUTO_LENGTH, &v_device);
    napi_create_string_utf8(env, desc,   NAPI_AUTO_LENGTH, &v_desc);
    napi_set_named_property(env, obj, "vendor",       v_vendor);
    napi_set_named_property(env, obj, "architecture", v_arch);
    napi_set_named_property(env, obj, "device",       v_device);
    napi_set_named_property(env, obj, "description",  v_desc);

    /* Apple Silicon SIMD-group size is fixed at 32 on all known variants. */
    napi_value v_sg_min, v_sg_max;
    napi_create_uint32(env, 32, &v_sg_min);
    napi_create_uint32(env, 32, &v_sg_max);
    napi_set_named_property(env, obj, "subgroupMinSize", v_sg_min);
    napi_set_named_property(env, obj, "subgroupMaxSize", v_sg_max);

    if (block && pfn_doeNativeAdapterFreeInfo) {
        pfn_doeNativeAdapterFreeInfo(block);
    }
    return obj;
}

/* ================================================================
 * Group A3: ShaderModule — getCompilationInfo
 * ================================================================ */

/* native_direct_shader_module_get_compilation_info — implements
 * GPUShaderModule.getCompilationInfo().
 * Returns a Promise resolved with a GPUCompilationInfo-shaped object whose
 * `messages` array is parsed from the JSON emitted by the native symbol.
 * When compilation succeeded the list is empty; on failure it holds a single
 * error entry with message, type, lineNum, linePos, offset, length. */
static napi_value native_direct_shader_module_get_compilation_info(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);

    NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
    void* module_raw = cache ? cache->native
                             : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);

    const char* json_str = "[]";
    if (pfn_doeNativeShaderModuleGetCompilationInfo) {
        const char* native_json = pfn_doeNativeShaderModuleGetCompilationInfo(module_raw);
        if (native_json) json_str = native_json;
    }

    /* Parse via JS JSON.parse — the Zig layer emits strict JSON. */
    napi_value global, json_obj, json_parse_fn, json_str_val, parse_args[1], parsed;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "JSON", &json_obj);
    napi_get_named_property(env, json_obj, "parse", &json_parse_fn);
    napi_create_string_utf8(env, json_str, NAPI_AUTO_LENGTH, &json_str_val);
    parse_args[0] = json_str_val;

    napi_value messages;
    napi_status parse_status = napi_call_function(env, json_obj, json_parse_fn, 1, parse_args, &parsed);
    if (parse_status != napi_ok) {
        napi_create_array_with_length(env, 0, &messages);
    } else {
        messages = parsed;
    }

    napi_value compilation_info;
    napi_create_object(env, &compilation_info);
    napi_set_named_property(env, compilation_info, "messages", messages);
    return native_direct_resolved_promise(env, compilation_info);
}

static napi_value doe_adapter_get_info_export(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUAdapter adapter = unwrap_ptr(env, _args[0]);
    if (!adapter) NAPI_THROW(env, "adapterGetInfo: null adapter");

    napi_value obj;
    napi_create_object(env, &obj);

    const char* vendor = "";
    const char* arch = "";
    const char* device = "";
    const char* desc = "";
    char* block = NULL;
    if (pfn_doeNativeAdapterGetInfo && pfn_doeNativeAdapterFreeInfo) {
        pfn_doeNativeAdapterGetInfo(adapter, &vendor, &arch, &device, &desc, &block);
        if (!vendor) vendor = "";
        if (!arch) arch = "";
        if (!device) device = "";
        if (!desc) desc = "";
    }

    napi_value v_vendor;
    napi_value v_arch;
    napi_value v_device;
    napi_value v_desc;
    napi_value v_sg_min;
    napi_value v_sg_max;
    napi_create_string_utf8(env, vendor, NAPI_AUTO_LENGTH, &v_vendor);
    napi_create_string_utf8(env, arch, NAPI_AUTO_LENGTH, &v_arch);
    napi_create_string_utf8(env, device, NAPI_AUTO_LENGTH, &v_device);
    napi_create_string_utf8(env, desc, NAPI_AUTO_LENGTH, &v_desc);
    napi_create_uint32(env, 32, &v_sg_min);
    napi_create_uint32(env, 32, &v_sg_max);
    napi_set_named_property(env, obj, "vendor", v_vendor);
    napi_set_named_property(env, obj, "architecture", v_arch);
    napi_set_named_property(env, obj, "device", v_device);
    napi_set_named_property(env, obj, "description", v_desc);
    napi_set_named_property(env, obj, "subgroupMinSize", v_sg_min);
    napi_set_named_property(env, obj, "subgroupMaxSize", v_sg_max);

    if (block && pfn_doeNativeAdapterFreeInfo) {
        pfn_doeNativeAdapterFreeInfo(block);
    }
    return obj;
}

static napi_value doe_shader_module_get_compilation_info_export(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUShaderModule module = unwrap_ptr(env, _args[0]);
    if (!module) NAPI_THROW(env, "shaderModuleGetCompilationInfo: null shader module");

    const char* json_str = "[]";
    if (pfn_doeNativeShaderModuleGetCompilationInfo) {
        const char* native_json = pfn_doeNativeShaderModuleGetCompilationInfo(module);
        if (native_json) json_str = native_json;
    }

    napi_value global;
    napi_value json_obj;
    napi_value json_parse_fn;
    napi_value json_str_val;
    napi_value parse_args[1];
    napi_value parsed;
    napi_value messages;
    napi_value compilation_info;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "JSON", &json_obj);
    napi_get_named_property(env, json_obj, "parse", &json_parse_fn);
    napi_create_string_utf8(env, json_str, NAPI_AUTO_LENGTH, &json_str_val);
    parse_args[0] = json_str_val;
    if (napi_call_function(env, json_obj, json_parse_fn, 1, parse_args, &parsed) != napi_ok) {
        napi_create_array_with_length(env, 0, &messages);
    } else {
        messages = parsed;
    }
    napi_create_object(env, &compilation_info);
    napi_set_named_property(env, compilation_info, "messages", messages);
    return native_direct_resolved_promise(env, compilation_info);
}

static napi_value doe_device_push_error_scope_export(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDevicePushErrorScope && !pfn_wgpuDevicePushErrorScope) NAPI_THROW(env, "devicePushErrorScope not available");
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "devicePushErrorScope: null device");
    uint32_t filter = 0;
    napi_get_value_uint32(env, _args[1], &filter);
    if (pfn_doeNativeDevicePushErrorScope) {
        pfn_doeNativeDevicePushErrorScope(device, filter);
    } else {
        pfn_wgpuDevicePushErrorScope(device, filter);
    }
    return NULL;
}

static napi_value doe_device_pop_error_scope_export(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (argc < 1 || argc > 2) NAPI_THROW(env, "devicePopErrorScope requires device and optional instance");
    if (!pfn_doeNativeDevicePopErrorScope && !pfn_wgpuDevicePopErrorScope) NAPI_THROW(env, "devicePopErrorScope not available");
    WGPUDevice device = unwrap_ptr(env, argv[0]);
    if (!device) NAPI_THROW(env, "devicePopErrorScope: null device");
    WGPUInstance inst = argc >= 2 ? unwrap_ptr(env, argv[1]) : NULL;

    DevicePopErrorScopeResult result = {0};
    WGPUPopErrorScopeCallbackInfo2 cb_info = {
        .next_in_chain = NULL,
        .mode = pfn_wgpuDevicePopErrorScope ? WGPU_CALLBACK_MODE_WAIT_ANY_ONLY : WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = pop_error_scope_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    if (pfn_doeNativeDevicePopErrorScope) {
        WGPUFuture future = pfn_doeNativeDevicePopErrorScope(device, cb_info);
        if (future.id == 0 || !result.done) {
            NAPI_THROW(env, "devicePopErrorScope future unavailable");
        }
    } else {
        if (!inst) NAPI_THROW(env, "devicePopErrorScope requires instance for public ABI fallback");
        WGPUFuture future = pfn_wgpuDevicePopErrorScope(device, cb_info);
        if (future.id == 0) NAPI_THROW(env, "devicePopErrorScope future unavailable");
        uint64_t start_ns = monotonic_now_ns();
        while (!result.done) {
            WGPUFutureWaitInfo wait_info = {
                .future = future,
                .completed = 0,
            };
            uint32_t wait_status = pfn_wgpuInstanceWaitAny(inst, 1, &wait_info, 0);
            if (wait_status == WGPU_WAIT_STATUS_SUCCESS) {
                if (!result.done) {
                    pfn_wgpuInstanceProcessEvents(inst);
                }
            } else if (wait_status == WGPU_WAIT_STATUS_TIMED_OUT) {
                pfn_wgpuInstanceProcessEvents(inst);
                if (monotonic_now_ns() - start_ns >= current_timeout_ns()) {
                    NAPI_THROW(env, "devicePopErrorScope timed out");
                }
                wait_slice();
            } else if (wait_status == WGPU_WAIT_STATUS_ERROR) {
                NAPI_THROW(env, "devicePopErrorScope wait failed");
            } else {
                NAPI_THROW(env, "devicePopErrorScope unsupported wait status");
            }
        }
    }

    if (result.error_type == 0x00000001) {
        napi_value null_value;
        napi_get_null(env, &null_value);
        return null_value;
    }

    napi_value out, type_val, message_val;
    napi_create_object(env, &out);
    napi_create_string_utf8(env, error_type_string(result.error_type), NAPI_AUTO_LENGTH, &type_val);
    napi_create_string_utf8(env, result.message, NAPI_AUTO_LENGTH, &message_val);
    napi_set_named_property(env, out, "type", type_val);
    napi_set_named_property(env, out, "message", message_val);
    return out;
}

static napi_value doe_device_set_uncaptured_error_callback_export(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceSetUncapturedErrorCallback) NAPI_THROW(env, "deviceSetUncapturedErrorCallback not available");
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "deviceSetUncapturedErrorCallback: null device");

    DeviceCallbackBinding* existing = binding_take(&g_uncaptured_bindings, device);
    release_binding(existing);

    napi_valuetype handler_type = napi_undefined;
    napi_typeof(env, _args[1], &handler_type);
    if (handler_type == napi_null || handler_type == napi_undefined) {
        pfn_doeNativeDeviceSetUncapturedErrorCallback(device, NULL, NULL, NULL);
        return NULL;
    }
    if (handler_type != napi_function) NAPI_THROW(env, "deviceSetUncapturedErrorCallback: handler must be a function or null");

    DeviceCallbackBinding* binding = create_device_callback_binding(
        env,
        device,
        _args[1],
        "doe-device-uncaptured-error",
        js_call_uncaptured_error,
        NULL
    );
    if (!binding) NAPI_THROW(env, "deviceSetUncapturedErrorCallback: callback binding allocation failed");
    binding_insert(&g_uncaptured_bindings, binding);
    pfn_doeNativeDeviceSetUncapturedErrorCallback(device, uncaptured_error_native_callback, binding, NULL);
    return NULL;
}

static napi_value doe_device_set_lost_callback_export(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceRegisterLostCallback) {
        napi_value result;
        napi_get_boolean(env, false, &result);
        return result;
    }
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "deviceSetLostCallback: null device");

    DeviceCallbackBinding* existing = binding_take(&g_lost_bindings, device);
    release_binding(existing);

    napi_valuetype handler_type = napi_undefined;
    napi_typeof(env, _args[1], &handler_type);
    if (handler_type == napi_null || handler_type == napi_undefined) {
        pfn_doeNativeDeviceRegisterLostCallback(device, NULL, NULL);
        return NULL;
    }
    if (handler_type != napi_function) NAPI_THROW(env, "deviceSetLostCallback: handler must be a function or null");

    DeviceCallbackBinding* binding = create_device_callback_binding(
        env,
        device,
        _args[1],
        "doe-device-lost",
        js_call_lost_callback,
        NULL
    );
    if (!binding) NAPI_THROW(env, "deviceSetLostCallback: callback binding allocation failed");
    binding_insert(&g_lost_bindings, binding);
    pfn_doeNativeDeviceRegisterLostCallback(device, lost_native_callback, binding);
    return NULL;
}

/* ================================================================
 * Group B: Device — addEventListener / removeEventListener (DOM stubs)
 * ================================================================ */

/* addEventListener is a DOM EventTarget stub required to prevent
 * "TypeError: device.addEventListener is not a function" in code that
 * attaches uncapturedError or devicelost listeners. The Doe runtime is
 * synchronous and surfaces errors through explicit return values, so
 * registration here is intentionally a no-op. */
static napi_value native_direct_device_add_event_listener(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    /* Consume type string and listener function to satisfy callers.
     * No forwarding to the C ABI — pfn_doeNativeDeviceAddEventListener would
     * also be a no-op and the symbol may not be present in the library yet. */
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_device_remove_event_listener(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* ================================================================
 * Group B: Device — importExternalTexture (explicitly unsupported)
 * ================================================================ */

static napi_value native_direct_device_import_external_texture(napi_env env, napi_callback_info info) {
    (void)info;
    /* External texture import requires platform video-frame OS APIs that are
     * not available in the Doe headless runtime. Throw a TypeError with a
     * clear unsupported message so callers get actionable feedback. */
    napi_throw_type_error(env, "DOE_UNSUPPORTED",
        "importExternalTexture is not supported in this runtime "
        "(external video frame import requires platform-specific OS APIs)");
    return NULL;
}

/* ================================================================
 * Group C: Encoder setImmediates (mixin + per-encoder variants)
 *
 * The C ABI functions log unsupported internally in Zig when the
 * capability is not available. All four variants share the same
 * argument shape: index (u32) + data (ArrayBuffer or TypedArray).
 * ================================================================ */

static void extract_buffer_data(napi_env env, napi_value val, void** out_ptr, size_t* out_len) {
    *out_ptr = NULL;
    *out_len = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, val, &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length = 0;
        void* ta_data = NULL;
        napi_value ta_ab;
        size_t ta_byte_offset = 0;
        napi_get_typedarray_info(env, val, &ta_type, &ta_length, &ta_data, &ta_ab, &ta_byte_offset);
        *out_ptr = ta_data;
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        *out_len = ta_length * elem_size;
        return;
    }
    bool is_ab = false;
    napi_is_arraybuffer(env, val, &is_ab);
    if (is_ab) {
        napi_get_arraybuffer_info(env, val, out_ptr, out_len);
        return;
    }
    bool is_buffer = false;
    napi_is_buffer(env, val, &is_buffer);
    if (is_buffer) {
        napi_get_buffer_info(env, val, out_ptr, out_len);
    }
}

/* GPUBindingCommandsMixin#setImmediates — registered on compute pass and render pass encoders */
static napi_value native_direct_compute_pass_set_immediates(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 2) NAPI_THROW(env, "setImmediates requires index and data");
    uint32_t index = 0;
    napi_get_value_uint32(env, argv[0], &index);
    void* data_ptr = NULL;
    size_t data_len = 0;
    extract_buffer_data(env, argv[1], &data_ptr, &data_len);
    if (pfn_doeNativeComputePassSetImmediates) {
        NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = pass_cache ? pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeComputePassSetImmediates(pass, index, (const uint8_t*)data_ptr, data_len);
    }
    /* When pfn is NULL the C side has not been delivered yet; silently no-op
     * so JS callers don't crash during the transition period. */
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#setImmediates */
static napi_value native_direct_render_pass_set_immediates(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 2) NAPI_THROW(env, "setImmediates requires index and data");
    uint32_t index = 0;
    napi_get_value_uint32(env, argv[0], &index);
    void* data_ptr = NULL;
    size_t data_len = 0;
    extract_buffer_data(env, argv[1], &data_ptr, &data_len);
    if (pfn_doeNativeRenderPassSetImmediates) {
        NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = pass_cache ? pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassSetImmediates(pass, index, (const uint8_t*)data_ptr, data_len);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#setViewport(x, y, width, height, minDepth, maxDepth) */
static napi_value native_direct_render_pass_set_viewport(napi_env env, napi_callback_info info) {
    size_t argc = 6;
    napi_value argv[6];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 6) NAPI_THROW(env, "setViewport requires x, y, width, height, minDepth, maxDepth");
    double x = 0, y = 0, width = 0, height = 0, min_depth = 0, max_depth = 1;
    napi_get_value_double(env, argv[0], &x);
    napi_get_value_double(env, argv[1], &y);
    napi_get_value_double(env, argv[2], &width);
    napi_get_value_double(env, argv[3], &height);
    napi_get_value_double(env, argv[4], &min_depth);
    napi_get_value_double(env, argv[5], &max_depth);
    if (pfn_doeNativeRenderPassSetViewport) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassSetViewport(pass, x, y, width, height, min_depth, max_depth);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#setScissorRect(x, y, width, height) */
static napi_value native_direct_render_pass_set_scissor_rect(napi_env env, napi_callback_info info) {
    size_t argc = 4;
    napi_value argv[4];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 4) NAPI_THROW(env, "setScissorRect requires x, y, width, height");
    uint32_t x = 0, y = 0, width = 0, height = 0;
    napi_get_value_uint32(env, argv[0], &x);
    napi_get_value_uint32(env, argv[1], &y);
    napi_get_value_uint32(env, argv[2], &width);
    napi_get_value_uint32(env, argv[3], &height);
    if (pfn_doeNativeRenderPassSetScissorRect) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassSetScissorRect(pass, x, y, width, height);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#setBlendConstant(color)
 * color: {r,g,b,a} object or [r,g,b,a] array */
static napi_value native_direct_render_pass_set_blend_constant(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "setBlendConstant requires a color argument");
    double r = 0, g = 0, b = 0, a = 1;
    napi_valuetype vt;
    napi_typeof(env, argv[0], &vt);
    if (vt == napi_object) {
        napi_value tmp;
        bool is_array = false;
        napi_is_array(env, argv[0], &is_array);
        if (is_array) {
            napi_get_element(env, argv[0], 0, &tmp); napi_get_value_double(env, tmp, &r);
            napi_get_element(env, argv[0], 1, &tmp); napi_get_value_double(env, tmp, &g);
            napi_get_element(env, argv[0], 2, &tmp); napi_get_value_double(env, tmp, &b);
            napi_get_element(env, argv[0], 3, &tmp); napi_get_value_double(env, tmp, &a);
        } else {
            if (napi_get_named_property(env, argv[0], "r", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &r);
            if (napi_get_named_property(env, argv[0], "g", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &g);
            if (napi_get_named_property(env, argv[0], "b", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &b);
            if (napi_get_named_property(env, argv[0], "a", &tmp) == napi_ok)
                napi_get_value_double(env, tmp, &a);
        }
    }
    if (pfn_doeNativeRenderPassSetBlendConstant) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassSetBlendConstant(pass, r, g, b, a);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#setStencilReference(reference) */
static napi_value native_direct_render_pass_set_stencil_reference(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "setStencilReference requires reference");
    uint32_t reference = 0;
    napi_get_value_uint32(env, argv[0], &reference);
    if (pfn_doeNativeRenderPassSetStencilReference) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassSetStencilReference(pass, reference);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#pushDebugGroup(groupLabel) */
static napi_value native_direct_render_pass_push_debug_group(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "pushDebugGroup requires groupLabel");
    size_t label_len = 0;
    napi_get_value_string_utf8(env, argv[0], NULL, 0, &label_len);
    char* label = (char*)malloc(label_len + 1);
    if (!label) return NULL;
    napi_get_value_string_utf8(env, argv[0], label, label_len + 1, &label_len);
    if (pfn_doeNativeRenderPassPushDebugGroup) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassPushDebugGroup(pass, label, label_len);
    }
    free(label);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#popDebugGroup() */
static napi_value native_direct_render_pass_pop_debug_group(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    if (pfn_doeNativeRenderPassPopDebugGroup) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassPopDebugGroup(pass);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderPassEncoder#insertDebugMarker(markerLabel) */
static napi_value native_direct_render_pass_insert_debug_marker(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "insertDebugMarker requires markerLabel");
    size_t label_len = 0;
    napi_get_value_string_utf8(env, argv[0], NULL, 0, &label_len);
    char* label = (char*)malloc(label_len + 1);
    if (!label) return NULL;
    napi_get_value_string_utf8(env, argv[0], label, label_len + 1, &label_len);
    if (pfn_doeNativeRenderPassInsertDebugMarker) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* pass = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderPassInsertDebugMarker(pass, label, label_len);
    }
    free(label);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPURenderBundleEncoder#setImmediates */
static napi_value native_direct_render_bundle_encoder_set_immediates(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 2) NAPI_THROW(env, "setImmediates requires index and data");
    uint32_t index = 0;
    napi_get_value_uint32(env, argv[0], &index);
    void* data_ptr = NULL;
    size_t data_len = 0;
    extract_buffer_data(env, argv[1], &data_ptr, &data_len);
    if (pfn_doeNativeRenderBundleEncoderSetImmediates) {
        NativeDirectHandleCache* enc_cache = native_direct_get_handle_cache(env, this_arg);
        void* enc = enc_cache ? enc_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeRenderBundleEncoderSetImmediates(enc, index, (const uint8_t*)data_ptr, data_len);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_resolved_promise(napi_env env, napi_value value) {
    napi_deferred deferred;
    napi_value promise;
    napi_create_promise(env, &deferred, &promise);
    napi_resolve_deferred(env, deferred, value);
    return promise;
}

static napi_value native_direct_resolved_undefined_promise(napi_env env) {
    napi_value promise;
    if (native_direct_resolved_undefined_promise_ref) {
        napi_get_reference_value(env, native_direct_resolved_undefined_promise_ref, &promise);
        return promise;
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    promise = native_direct_resolved_promise(env, undefined_value);
    napi_create_reference(env, promise, 1, &native_direct_resolved_undefined_promise_ref);
    return promise;
}

static void native_direct_set_external_prop(napi_env env, napi_value obj, const char* key, void* ptr) {
    napi_value value;
    if (ptr) {
        napi_create_external(env, ptr, NULL, NULL, &value);
    } else {
        napi_get_null(env, &value);
    }
    napi_set_named_property(env, obj, key, value);
}

static void native_direct_set_object_prop(napi_env env, napi_value obj, const char* key, napi_value value) {
    napi_set_named_property(env, obj, key, value);
}

static void native_direct_set_uint32_prop(napi_env env, napi_value obj, const char* key, uint32_t value) {
    napi_value prop;
    napi_create_uint32(env, value, &prop);
    napi_set_named_property(env, obj, key, prop);
}

static void native_direct_set_double_prop(napi_env env, napi_value obj, const char* key, double value) {
    napi_value prop;
    napi_create_double(env, value, &prop);
    napi_set_named_property(env, obj, key, prop);
}

static double native_direct_elapsed_ms(uint64_t started_ns) {
    const uint64_t ended_ns = monotonic_now_ns();
    if (ended_ns <= started_ns) return 0.0;
    return (double)(ended_ns - started_ns) / 1000000.0;
}

static void* native_direct_unwrap_external_prop(napi_env env, napi_value obj, const char* key) {
    if (!has_prop(env, obj, key)) return NULL;
    napi_value value = get_prop(env, obj, key);
    napi_valuetype vt;
    napi_typeof(env, value, &vt);
    if (vt != napi_external) return NULL;
    return unwrap_ptr(env, value);
}

static uint32_t native_direct_get_uint32_prop(napi_env env, napi_value obj, const char* key) {
    if (!has_prop(env, obj, key)) return 0;
    return get_uint32_prop(env, obj, key);
}

static bool native_direct_queue_has_pending(napi_env env, napi_value queue_obj) {
    NativeDirectQueueCache* cache = native_direct_get_queue_cache(env, queue_obj);
    if (cache) return cache->completed_serial < cache->submitted_serial;
    uint32_t submitted = native_direct_get_uint32_prop(env, queue_obj, DOE_DIRECT_SUBMITTED_SERIAL);
    uint32_t completed = native_direct_get_uint32_prop(env, queue_obj, DOE_DIRECT_COMPLETED_SERIAL);
    return completed < submitted;
}

static void native_direct_queue_mark_submitted(napi_env env, napi_value queue_obj) {
    NativeDirectQueueCache* cache = native_direct_get_queue_cache(env, queue_obj);
    if (cache) cache->submitted_serial += 1;
    uint32_t submitted = native_direct_get_uint32_prop(env, queue_obj, DOE_DIRECT_SUBMITTED_SERIAL);
    native_direct_set_uint32_prop(env, queue_obj, DOE_DIRECT_SUBMITTED_SERIAL, submitted + 1);
}

static void native_direct_queue_mark_done(napi_env env, napi_value queue_obj) {
    NativeDirectQueueCache* cache = native_direct_get_queue_cache(env, queue_obj);
    if (cache) cache->completed_serial = cache->submitted_serial;
    uint32_t submitted = native_direct_get_uint32_prop(env, queue_obj, DOE_DIRECT_SUBMITTED_SERIAL);
    native_direct_set_uint32_prop(env, queue_obj, DOE_DIRECT_COMPLETED_SERIAL, submitted);
}

static napi_value native_direct_create_empty_set(napi_env env) {
    napi_value global;
    napi_value ctor;
    napi_value result;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "Set", &ctor);
    napi_new_instance(env, ctor, 0, NULL, &result);
    return result;
}

static napi_value native_direct_create_empty_object(napi_env env) {
    napi_value obj;
    napi_create_object(env, &obj);
    return obj;
}

static void native_direct_add_cached_method(
    napi_env env,
    napi_value obj,
    const char* name,
    napi_callback fn,
    napi_ref* method_ref
) {
    napi_value method;
    if (*method_ref) {
        napi_get_reference_value(env, *method_ref, &method);
    } else {
        napi_create_function(env, name, NAPI_AUTO_LENGTH, fn, NULL, &method);
        napi_create_reference(env, method, 1, method_ref);
    }
    napi_set_named_property(env, obj, name, method);
}

static void native_direct_handle_cache_finalize(napi_env env, void* data, void* hint) {
    (void)env;
    (void)hint;
    if (data) free(data);
}

static void native_direct_queue_cache_finalize(napi_env env, void* data, void* hint) {
    (void)env;
    (void)hint;
    if (data) free(data);
}

static void native_direct_buffer_cache_finalize(napi_env env, void* data, void* hint) {
    NativeDirectBufferCache* cache = (NativeDirectBufferCache*)data;
    (void)hint;
    if (!cache) return;
    if (cache->queue_ref) napi_delete_reference(env, cache->queue_ref);
    if (cache->mapped_range_ref) napi_delete_reference(env, cache->mapped_range_ref);
    free(cache);
}

static void native_direct_wrap_handle_cache(napi_env env, napi_value obj, WGPUInstance instance, void* native) {
    NativeDirectHandleCache* cache = (NativeDirectHandleCache*)calloc(1, sizeof(NativeDirectHandleCache));
    if (!cache) {
        napi_throw_error(env, "DOE_ERROR", "nativeDirect: out of memory");
        return;
    }
    cache->instance = instance;
    cache->native = native;
    napi_wrap(env, obj, cache, native_direct_handle_cache_finalize, NULL, NULL);
}

static void native_direct_wrap_queue_cache(napi_env env, napi_value obj, WGPUInstance instance, WGPUQueue queue) {
    NativeDirectQueueCache* cache = (NativeDirectQueueCache*)calloc(1, sizeof(NativeDirectQueueCache));
    if (!cache) {
        napi_throw_error(env, "DOE_ERROR", "nativeDirect: out of memory");
        return;
    }
    cache->instance = instance;
    cache->queue = queue;
    napi_wrap(env, obj, cache, native_direct_queue_cache_finalize, NULL, NULL);
}

static void native_direct_wrap_buffer_cache(
    napi_env env,
    napi_value obj,
    WGPUInstance instance,
    WGPUBuffer buffer,
    uint64_t size,
    uint64_t usage,
    napi_value queue_obj
) {
    NativeDirectBufferCache* cache = (NativeDirectBufferCache*)calloc(1, sizeof(NativeDirectBufferCache));
    if (!cache) {
        napi_throw_error(env, "DOE_ERROR", "nativeDirect: out of memory");
        return;
    }
    cache->instance = instance;
    cache->buffer = buffer;
    cache->size = size;
    cache->usage = usage;
    napi_create_reference(env, queue_obj, 1, &cache->queue_ref);
    napi_wrap(env, obj, cache, native_direct_buffer_cache_finalize, NULL, NULL);
}

static NativeDirectHandleCache* native_direct_get_handle_cache(napi_env env, napi_value obj) {
    NativeDirectHandleCache* cache = NULL;
    napi_unwrap(env, obj, (void**)&cache);
    return cache;
}

static NativeDirectQueueCache* native_direct_get_queue_cache(napi_env env, napi_value obj) {
    NativeDirectQueueCache* cache = NULL;
    napi_unwrap(env, obj, (void**)&cache);
    return cache;
}

static NativeDirectBufferCache* native_direct_get_buffer_cache(napi_env env, napi_value obj) {
    NativeDirectBufferCache* cache = NULL;
    napi_unwrap(env, obj, (void**)&cache);
    return cache;
}

static void native_direct_invalidate_buffer_mapped_range_cache(napi_env env, NativeDirectBufferCache* cache) {
    if (!cache) return;
    if (cache->mapped_range_ref) {
        napi_delete_reference(env, cache->mapped_range_ref);
        cache->mapped_range_ref = NULL;
    }
    cache->mapped_offset = 0;
    cache->mapped_size = 0;
    cache->mapped_ptr = NULL;
}

static WGPUAdapter native_direct_request_adapter_sync(napi_env env, WGPUInstance inst) {
    if (!inst) NAPI_THROW(env, "nativeDirect.requestAdapter requires instance");

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
    if (!process_events_until(inst, &result.done, current_timeout_ns())) {
        throw_status_error(env, "DOE_REQUEST_ADAPTER_TIMEOUT", "requestAdapter timed out", result.status, result.message);
        return NULL;
    }
    if (result.status != WGPU_REQUEST_STATUS_SUCCESS || !result.adapter) {
        throw_status_error(env, "DOE_REQUEST_ADAPTER_ERROR", "requestAdapter failed", result.status, result.message);
        return NULL;
    }
    return result.adapter;
}

static WGPUDevice native_direct_request_device_sync(napi_env env, WGPUInstance inst, WGPUAdapter adapter) {
    if (!inst || !adapter) NAPI_THROW(env, "nativeDirect.requestDevice requires instance and adapter");

    DeviceRequestResult result = {0};
    const WGPURequestDeviceCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = device_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    WGPUFuture future = pfn_doeNativeAdapterRequestDevice
        ? pfn_doeNativeAdapterRequestDevice(adapter, NULL, cb_info)
        : pfn_wgpuAdapterRequestDevice(adapter, NULL, cb_info);
    if (future.id == 0) NAPI_THROW(env, "requestDevice future unavailable");
    if (!process_events_until(inst, &result.done, current_timeout_ns())) {
        throw_status_error(env, "DOE_REQUEST_DEVICE_TIMEOUT", "requestDevice timed out", result.status, result.message);
        return NULL;
    }
    if (result.status != WGPU_REQUEST_STATUS_SUCCESS || !result.device) {
        throw_status_error(env, "DOE_REQUEST_DEVICE_ERROR", "requestDevice failed", result.status, result.message);
        return NULL;
    }
    return result.device;
}

static WGPULimits native_direct_query_adapter_limits(WGPUAdapter adapter, bool* ok) {
    WGPULimits limits;
    memset(&limits, 0, sizeof(limits));
    *ok = false;
    uint32_t (*fn)(WGPUAdapter, void*) = pfn_doeNativeAdapterGetLimits ? pfn_doeNativeAdapterGetLimits : pfn_wgpuAdapterGetLimits;
    if (!fn) return limits;
    *ok = fn(adapter, &limits) == WGPU_STATUS_SUCCESS;
    return limits;
}

static WGPULimits native_direct_query_device_limits(WGPUDevice device, bool* ok) {
    WGPULimits limits;
    memset(&limits, 0, sizeof(limits));
    *ok = false;
    uint32_t (*fn)(WGPUDevice, void*) = pfn_doeNativeDeviceGetLimits ? pfn_doeNativeDeviceGetLimits : pfn_wgpuDeviceGetLimits;
    if (!fn) return limits;
    *ok = fn(device, &limits) == WGPU_STATUS_SUCCESS;
    return limits;
}

static napi_value native_direct_gpu_request_adapter(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    (void)argv;
    WGPUInstance inst = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUAdapter adapter = native_direct_request_adapter_sync(env, inst);
    if (!adapter) return NULL;
    return native_direct_resolved_promise(env, create_native_direct_adapter_object(env, inst, adapter));
}

static napi_value native_direct_adapter_request_device(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    (void)argv;
    WGPUInstance inst = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUAdapter adapter = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUDevice device = native_direct_request_device_sync(env, inst, adapter);
    if (!device) return NULL;
    return native_direct_resolved_promise(env, create_native_direct_device_object(env, inst, device));
}

static napi_value native_direct_adapter_destroy(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    WGPUAdapter adapter = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (adapter) {
        pfn_wgpuAdapterRelease(adapter);
        native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_device_create_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "createBuffer requires a descriptor");
    WGPUDevice device = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUInstance inst = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    napi_value queue_obj = get_prop(env, this_arg, "queue");
    if (!device) NAPI_THROW(env, "Invalid device");

    WGPUBufferDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.usage = (uint64_t)get_int64_prop(env, argv[0], "usage");
    desc.size = (uint64_t)get_int64_prop(env, argv[0], "size");
    desc.mappedAtCreation = get_bool_prop(env, argv[0], "mappedAtCreation") ? 1 : 0;

    WGPUBuffer buffer = pfn_wgpuDeviceCreateBuffer(device, &desc);
    if (!buffer) NAPI_THROW(env, "createBuffer failed");
    return create_native_direct_buffer_object(env, inst, queue_obj, buffer, desc.size, desc.usage);
}

static napi_value native_direct_device_create_shader_module(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "createShaderModule requires a descriptor");
    WGPUDevice device = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!device) NAPI_THROW(env, "Invalid device");
    napi_value code_value = has_prop(env, argv[0], "code") ? get_prop(env, argv[0], "code") : get_prop(env, argv[0], "source");
    size_t code_len = 0;
    napi_get_value_string_utf8(env, code_value, NULL, 0, &code_len);
    char* code = (char*)malloc(code_len + 1);
    if (!code) NAPI_THROW(env, "createShaderModule: out of memory");
    napi_get_value_string_utf8(env, code_value, code, code_len + 1, &code_len);

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
    if (!mod) {
        char msg[DOE_ERROR_BUF_CAP];
        char stage[64];
        char kind[64];
        copy_library_error_message(msg, sizeof(msg));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));
        if (msg[0] != '\0') {
            char full_msg[DOE_ERROR_BUF_CAP];
            if (stage[0] != '\0' && kind[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s/%s] %s", stage, kind, msg);
            } else if (stage[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s] %s", stage, msg);
            } else {
                snprintf(full_msg, sizeof(full_msg), "%s", msg);
            }
            napi_throw_error(env, "DOE_SHADER_MODULE_ERROR", full_msg);
        } else {
            napi_throw_error(env, "DOE_SHADER_MODULE_ERROR", "createShaderModule failed");
        }
        return NULL;
    }
    return create_native_direct_shader_module_object(env, mod);
}

static napi_value native_direct_device_create_compute_pipeline(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "createComputePipeline requires a descriptor");
    WGPUDevice device = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!device) NAPI_THROW(env, "Invalid device");

    napi_value compute = get_prop(env, argv[0], "compute");
    napi_value module_obj = get_prop(env, compute, "module");
    WGPUShaderModule shader = native_direct_unwrap_external_prop(env, module_obj, DOE_DIRECT_NATIVE);
    if (!shader) NAPI_THROW(env, "createComputePipeline: compute.module is required");
    napi_value entry_value = has_prop(env, compute, "entryPoint") ? get_prop(env, compute, "entryPoint") : NULL;
    char* entry_point = NULL;
    size_t entry_len = 0;
    if (entry_value) {
        entry_point = dup_string_value(env, entry_value, &entry_len);
    } else {
        entry_len = 4;
        entry_point = (char*)malloc(entry_len + 1);
        memcpy(entry_point, "main", entry_len + 1);
    }
    if (!entry_point) NAPI_THROW(env, "createComputePipeline: out of memory");

    WGPUPipelineLayout layout = NULL;
    if (has_prop(env, argv[0], "layout")) {
        layout = native_direct_unwrap_external_prop(env, get_prop(env, argv[0], "layout"), DOE_DIRECT_NATIVE);
    }

    /* Parse optional override constants from descriptor.compute.constants */
    WGPUConstantEntry* override_entries = NULL;
    size_t override_count = 0;
    if (has_prop(env, compute, "constants")) {
        napi_value constants_obj = get_prop(env, compute, "constants");
        override_count = parse_js_override_constants(env, constants_obj, &override_entries);
    }

    WGPUComputePipelineDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.layout = layout;
    desc.compute.module = shader;
    desc.compute.entryPoint.data = entry_point;
    desc.compute.entryPoint.length = entry_len;
    desc.compute.constantCount = override_count;
    desc.compute.constants = override_entries;

    WGPUComputePipeline pipeline = pfn_wgpuDeviceCreateComputePipeline(device, &desc);
    free(entry_point);
    free_override_constants(override_entries, override_count);
    if (!pipeline) {
        char msg[DOE_ERROR_BUF_CAP];
        char stage[64];
        char kind[64];
        copy_library_error_message(msg, sizeof(msg));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));
        if (msg[0] != '\0') {
            char full_msg[DOE_ERROR_BUF_CAP];
            if (stage[0] != '\0' && kind[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s/%s] %s", stage, kind, msg);
            } else if (stage[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s] %s", stage, msg);
            } else {
                snprintf(full_msg, sizeof(full_msg), "%s", msg);
            }
            napi_throw_error(env, "DOE_COMPUTE_PIPELINE_ERROR", full_msg);
        } else {
            napi_throw_error(env, "DOE_COMPUTE_PIPELINE_ERROR", "createComputePipeline failed");
        }
        return NULL;
    }
    return create_native_direct_compute_pipeline_object(env, pipeline);
}

static napi_value native_direct_device_create_compute_pipeline_async(napi_env env, napi_callback_info info) {
    napi_value result = native_direct_device_create_compute_pipeline(env, info);
    if (!result) return NULL;
    return native_direct_resolved_promise(env, result);
}

static napi_value native_direct_device_create_bind_group_layout(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "createBindGroupLayout requires a descriptor");
    WGPUDevice device = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!device) NAPI_THROW(env, "Invalid device");

    uint32_t entry_count = 0;
    napi_value entries_array = get_prop(env, argv[0], "entries");
    napi_get_array_length(env, entries_array, &entry_count);
    WGPUBindGroupLayoutEntry* entries = (WGPUBindGroupLayoutEntry*)calloc(entry_count, sizeof(WGPUBindGroupLayoutEntry));
    if (!entries && entry_count > 0) NAPI_THROW(env, "createBindGroupLayout: out of memory");

    for (uint32_t i = 0; i < entry_count; i++) {
        napi_value elem;
        napi_get_element(env, entries_array, i, &elem);
        entries[i].binding = get_uint32_prop(env, elem, "binding");
        entries[i].visibility = (uint64_t)get_int64_prop(env, elem, "visibility");
        if (has_prop(env, elem, "buffer") && prop_type(env, elem, "buffer") == napi_object) {
            napi_value buffer = get_prop(env, elem, "buffer");
            entries[i].buffer.type = buffer_binding_type_from_string(env, get_prop(env, buffer, "type"));
            if (has_prop(env, buffer, "hasDynamicOffset")) entries[i].buffer.hasDynamicOffset = get_bool_prop(env, buffer, "hasDynamicOffset") ? 1 : 0;
            if (has_prop(env, buffer, "minBindingSize")) entries[i].buffer.minBindingSize = (uint64_t)get_int64_prop(env, buffer, "minBindingSize");
        }
        if (has_prop(env, elem, "sampler") && prop_type(env, elem, "sampler") == napi_object) {
            napi_value sampler = get_prop(env, elem, "sampler");
            entries[i].sampler.type = sampler_binding_type_from_string(env, get_prop(env, sampler, "type"));
        }
        if (has_prop(env, elem, "texture") && prop_type(env, elem, "texture") == napi_object) {
            napi_value texture = get_prop(env, elem, "texture");
            entries[i].texture.sampleType = texture_sample_type_from_string(env, get_prop(env, texture, "sampleType"));
            entries[i].texture.viewDimension = texture_view_dimension_from_string(env, get_prop(env, texture, "viewDimension"));
            if (has_prop(env, texture, "multisampled")) entries[i].texture.multisampled = get_bool_prop(env, texture, "multisampled") ? 1 : 0;
        }
        if (has_prop(env, elem, "storageTexture") && prop_type(env, elem, "storageTexture") == napi_object) {
            napi_value storage_texture = get_prop(env, elem, "storageTexture");
            entries[i].storageTexture.access = storage_texture_access_from_string(env, get_prop(env, storage_texture, "access"));
            entries[i].storageTexture.format = texture_format_from_string(env, get_prop(env, storage_texture, "format"));
            entries[i].storageTexture.viewDimension = texture_view_dimension_from_string(env, get_prop(env, storage_texture, "viewDimension"));
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
    return create_native_direct_bind_group_layout_object(env, layout);
}

static napi_value native_direct_device_create_bind_group(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "createBindGroup requires a descriptor");
    WGPUDevice device = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUBindGroupLayout layout = native_direct_unwrap_external_prop(env, get_prop(env, argv[0], "layout"), DOE_DIRECT_NATIVE);
    if (!device || !layout) NAPI_THROW(env, "Invalid device or layout");

    napi_value entries_array = get_prop(env, argv[0], "entries");
    uint32_t entry_count = 0;
    napi_get_array_length(env, entries_array, &entry_count);
    WGPUBindGroupEntry* entries = (WGPUBindGroupEntry*)calloc(entry_count, sizeof(WGPUBindGroupEntry));
    if (!entries && entry_count > 0) NAPI_THROW(env, "createBindGroup: out of memory");

    for (uint32_t i = 0; i < entry_count; i++) {
        napi_value elem;
        napi_value resource;
        napi_get_element(env, entries_array, i, &elem);
        entries[i].binding = get_uint32_prop(env, elem, "binding");
        resource = get_prop(env, elem, "resource");
        if (has_prop(env, resource, "buffer")) entries[i].buffer = native_direct_unwrap_external_prop(env, get_prop(env, resource, "buffer"), DOE_DIRECT_NATIVE);
        if (has_prop(env, resource, "sampler")) entries[i].sampler = native_direct_unwrap_external_prop(env, get_prop(env, resource, "sampler"), DOE_DIRECT_NATIVE);
        if (has_prop(env, resource, "textureView")) entries[i].textureView = native_direct_unwrap_external_prop(env, get_prop(env, resource, "textureView"), DOE_DIRECT_NATIVE);
        if (has_prop(env, resource, "offset")) entries[i].offset = (uint64_t)get_int64_prop(env, resource, "offset");
        entries[i].size = has_prop(env, resource, "size") ? (uint64_t)get_int64_prop(env, resource, "size") : WGPU_WHOLE_SIZE;
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
    return create_native_direct_bind_group_object(env, group);
}

static napi_value native_direct_device_create_pipeline_layout(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "createPipelineLayout requires a descriptor");
    WGPUDevice device = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!device) NAPI_THROW(env, "Invalid device");

    napi_value layouts_array = get_prop(env, argv[0], "bindGroupLayouts");
    uint32_t layout_count = 0;
    napi_get_array_length(env, layouts_array, &layout_count);
    WGPUBindGroupLayout* layouts = (WGPUBindGroupLayout*)calloc(layout_count, sizeof(WGPUBindGroupLayout));
    if (!layouts && layout_count > 0) NAPI_THROW(env, "createPipelineLayout: out of memory");
    for (uint32_t i = 0; i < layout_count; i++) {
        napi_value elem;
        napi_get_element(env, layouts_array, i, &elem);
        layouts[i] = native_direct_unwrap_external_prop(env, elem, DOE_DIRECT_NATIVE);
    }

    WGPUPipelineLayoutDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
        .bindGroupLayoutCount = layout_count,
        .bindGroupLayouts = layouts,
        .immediateSize = 0,
    };
    WGPUPipelineLayout pipeline_layout = pfn_wgpuDeviceCreatePipelineLayout(device, &desc);
    free(layouts);
    if (!pipeline_layout) NAPI_THROW(env, "createPipelineLayout failed");
    return create_native_direct_pipeline_layout_object(env, pipeline_layout);
}

static napi_value native_direct_device_create_command_encoder(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    (void)argv;
    NativeDirectHandleCache* device_cache = native_direct_get_handle_cache(env, this_arg);
    WGPUDevice device = device_cache ? (WGPUDevice)device_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!device) NAPI_THROW(env, "Invalid device");
    WGPUCommandEncoderDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
    };
    WGPUCommandEncoder encoder = pfn_wgpuDeviceCreateCommandEncoder(device, &desc);
    if (!encoder) NAPI_THROW(env, "createCommandEncoder failed");
    return create_native_direct_command_encoder_object(env, encoder);
}

static napi_value native_direct_device_destroy(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectHandleCache* device_cache = native_direct_get_handle_cache(env, this_arg);
    WGPUDevice device = device_cache ? (WGPUDevice)device_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
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
        native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
        if (device_cache) device_cache->native = NULL;
    }
    if (has_prop(env, this_arg, "queue")) {
        napi_value queue_obj = get_prop(env, this_arg, "queue");
        NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, queue_obj);
        native_direct_set_external_prop(env, queue_obj, DOE_DIRECT_NATIVE, NULL);
        native_direct_set_external_prop(env, queue_obj, DOE_DIRECT_QUEUE_NATIVE, NULL);
        if (queue_cache) queue_cache->queue = NULL;
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_queue_submit(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "queue.submit requires command buffers");
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!queue) NAPI_THROW(env, "Invalid queue");
    uint32_t cmd_count = 0;
    napi_get_array_length(env, argv[0], &cmd_count);
    if (cmd_count == 1) {
        napi_value elem;
        WGPUCommandBuffer cmd = NULL;
        napi_get_element(env, argv[0], 0, &elem);
        {
            NativeDirectHandleCache* command_buffer_cache = native_direct_get_handle_cache(env, elem);
            cmd = command_buffer_cache ? (WGPUCommandBuffer)command_buffer_cache->native : native_direct_unwrap_external_prop(env, elem, DOE_DIRECT_NATIVE);
        }
        pfn_wgpuQueueSubmit(queue, 1, &cmd);
    } else {
        WGPUCommandBuffer* cmds = (WGPUCommandBuffer*)calloc(cmd_count, sizeof(WGPUCommandBuffer));
        if (!cmds && cmd_count > 0) NAPI_THROW(env, "queue.submit: out of memory");
        for (uint32_t i = 0; i < cmd_count; i++) {
            napi_value elem;
            napi_get_element(env, argv[0], i, &elem);
            {
                NativeDirectHandleCache* command_buffer_cache = native_direct_get_handle_cache(env, elem);
                cmds[i] = command_buffer_cache ? (WGPUCommandBuffer)command_buffer_cache->native : native_direct_unwrap_external_prop(env, elem, DOE_DIRECT_NATIVE);
            }
        }
        pfn_wgpuQueueSubmit(queue, cmd_count, cmds);
        free(cmds);
    }
    native_direct_queue_mark_submitted(env, this_arg);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_queue_write_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 5;
    napi_value argv[5];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 3) NAPI_THROW(env, "queue.writeBuffer requires buffer, offset, and data");
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, argv[0]);
    WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, argv[0], DOE_DIRECT_NATIVE);
    if (!queue || !buffer) NAPI_THROW(env, "queue.writeBuffer requires queue and buffer");
    int64_t offset = 0;
    napi_get_value_int64(env, argv[1], &offset);

    void* data = NULL;
    size_t byte_length = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, argv[2], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length;
        napi_value ab;
        size_t byte_offset;
        napi_get_typedarray_info(env, argv[2], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        byte_length = ta_length * elem_size;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, argv[2], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, argv[2], &data, &byte_length);
        } else {
            bool is_buffer = false;
            napi_is_buffer(env, argv[2], &is_buffer);
            if (is_buffer) {
                napi_get_buffer_info(env, argv[2], &data, &byte_length);
            } else {
                NAPI_THROW(env, "queue.writeBuffer data must be TypedArray, ArrayBuffer, or Buffer");
            }
        }
    }

    if (argc >= 4 && argv[3]) {
        uint32_t data_offset = 0;
        napi_get_value_uint32(env, argv[3], &data_offset);
        data = ((uint8_t*)data) + data_offset;
        byte_length = byte_length > data_offset ? byte_length - data_offset : 0;
    }
    if (argc >= 5 && argv[4]) {
        uint32_t size = 0;
        napi_get_value_uint32(env, argv[4], &size);
        if (size < byte_length) byte_length = size;
    }

    pfn_wgpuQueueWriteBuffer(queue, buffer, (uint64_t)offset, data, byte_length);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_queue_on_submitted_work_done(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    WGPUInstance inst = queue_cache ? queue_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!queue) NAPI_THROW(env, "Invalid queue");
    double queue_flush_ms = 0.0;
    const uint64_t submit_wait_started_ns = monotonic_now_ns();
    if (native_direct_queue_has_pending(env, this_arg)) {
        if (pfn_doeNativeQueueFlush) {
            const uint64_t flush_started_ns = monotonic_now_ns();
            pfn_doeNativeQueueFlush(queue);
            queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        } else {
            QueueWorkDoneResult result = {0};
            WGPUQueueWorkDoneCallbackInfo cb_info = {
                .nextInChain = NULL,
                .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
                .callback = queue_work_done_callback,
                .userdata1 = &result,
                .userdata2 = NULL,
            };
            WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
            if (future.id == 0) NAPI_THROW(env, "queue work-done future unavailable");
            const uint64_t flush_started_ns = monotonic_now_ns();
            uint64_t start_ns = monotonic_now_ns();
            while (!result.done) {
                WGPUFutureWaitInfo wait_info = {
                    .future = future,
                    .completed = 0,
                };
                uint32_t wait_status = pfn_wgpuInstanceWaitAny(inst, 1, &wait_info, 0);
                if (wait_status == WGPU_WAIT_STATUS_SUCCESS) {
                    if (!result.done) pfn_wgpuInstanceProcessEvents(inst);
                } else if (wait_status == WGPU_WAIT_STATUS_TIMED_OUT) {
                    pfn_wgpuInstanceProcessEvents(inst);
                    if (monotonic_now_ns() - start_ns >= current_timeout_ns()) {
                        napi_throw_error(env, "DOE_QUEUE_TIMEOUT", "queue wait timed out");
                        return NULL;
                    }
                    wait_slice();
                } else if (wait_status == WGPU_WAIT_STATUS_ERROR) {
                    napi_throw_error(env, "DOE_QUEUE_UNAVAILABLE", "queue wait failed");
                    return NULL;
                } else {
                    NAPI_THROW(env, "queue wait returned unsupported status");
                }
            }
            if (result.status != WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS) {
                return throw_status_error(env, "DOE_QUEUE_FLUSH_ERROR", "queue work did not complete", result.status, result.message);
            }
            queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        }
        native_direct_queue_mark_done(env, this_arg);
    }
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_QUEUE_FLUSH_MS, queue_flush_ms);
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_SUBMIT_WAIT_MS, native_direct_elapsed_ms(submit_wait_started_ns));
    return native_direct_resolved_undefined_promise(env);
}

static napi_value native_direct_buffer_map_async(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "buffer.mapAsync requires a mode");
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUInstance inst = buffer_cache ? buffer_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    napi_value queue_obj = NULL;
    if (buffer_cache && buffer_cache->queue_ref) {
        napi_get_reference_value(env, buffer_cache->queue_ref, &queue_obj);
    } else {
        queue_obj = get_prop(env, this_arg, DOE_DIRECT_QUEUE);
    }
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    uint32_t mode = 0;
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    napi_get_value_uint32(env, argv[0], &mode);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &offset);
    if (argc >= 3 && argv[2]) napi_get_value_int64(env, argv[2], &size);
    double map_queue_flush_ms = 0.0;
    if (native_direct_queue_has_pending(env, queue_obj)) {
        NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, queue_obj);
        WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, queue_obj, DOE_DIRECT_NATIVE);
        if (pfn_doeNativeQueueFlush) {
            const uint64_t flush_started_ns = monotonic_now_ns();
            pfn_doeNativeQueueFlush(queue);
            map_queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        } else {
            QueueWorkDoneResult result = {0};
            WGPUQueueWorkDoneCallbackInfo cb_info = {
                .nextInChain = NULL,
                .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
                .callback = queue_work_done_callback,
                .userdata1 = &result,
                .userdata2 = NULL,
            };
            WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
            if (future.id == 0) NAPI_THROW(env, "queue work-done future unavailable");
            const uint64_t flush_started_ns = monotonic_now_ns();
            if (!process_events_until(inst, &result.done, current_timeout_ns())) {
                return throw_status_error(env, "DOE_QUEUE_TIMEOUT", "queue wait timed out", result.status, result.message);
            }
            if (result.status != WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS) {
                return throw_status_error(env, "DOE_QUEUE_FLUSH_ERROR", "queue work did not complete", result.status, result.message);
            }
            map_queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        }
        native_direct_queue_mark_done(env, queue_obj);
    }

    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    const uint64_t map_started_ns = monotonic_now_ns();
    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0 || !result.done) NAPI_THROW(env, "doeNativeBufferMapAsync unavailable");
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS) {
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "doeNativeBufferMapAsync failed", result.status, result.message);
        }
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0) NAPI_THROW(env, "bufferMapAsync future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns())) {
            return throw_status_error(env, "DOE_BUFFER_MAP_TIMEOUT", "bufferMapAsync timed out", result.status, result.message);
        }
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS) {
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "bufferMapAsync failed", result.status, result.message);
        }
    }
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_MAP_QUEUE_FLUSH_MS, map_queue_flush_ms);
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_MAP_ASYNC_MS, native_direct_elapsed_ms(map_started_ns));
    return native_direct_resolved_undefined_promise(env);
}

static napi_value native_direct_buffer_get_mapped_range(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    if (argc >= 1 && argv[0]) napi_get_value_int64(env, argv[0], &offset);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &size);
    const uint64_t get_mapped_range_started_ns = monotonic_now_ns();
    void* data = pfn_wgpuBufferGetMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) data = (void*)pfn_wgpuBufferGetConstMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) NAPI_THROW(env, "getMappedRange returned NULL");
    if (buffer_cache &&
        buffer_cache->mapped_range_ref &&
        buffer_cache->mapped_ptr == data &&
        buffer_cache->mapped_offset == (size_t)offset &&
        buffer_cache->mapped_size == (size_t)size) {
        napi_value cached;
        native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS, native_direct_elapsed_ms(get_mapped_range_started_ns));
        napi_get_reference_value(env, buffer_cache->mapped_range_ref, &cached);
        return cached;
    }
    if (buffer_cache) native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    napi_value array_buffer;
    napi_create_external_arraybuffer(env, data, (size_t)size, NULL, NULL, &array_buffer);
    if (buffer_cache) {
        napi_create_reference(env, array_buffer, 1, &buffer_cache->mapped_range_ref);
        buffer_cache->mapped_offset = (size_t)offset;
        buffer_cache->mapped_size = (size_t)size;
        buffer_cache->mapped_ptr = data;
    }
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS, native_direct_elapsed_ms(get_mapped_range_started_ns));
    return array_buffer;
}

static napi_value native_direct_buffer_read_copy(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    if (argc >= 1 && argv[0]) napi_get_value_int64(env, argv[0], &offset);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &size);
    void* data = pfn_wgpuBufferGetMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) data = (void*)pfn_wgpuBufferGetConstMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) NAPI_THROW(env, "bufferReadCopy getMappedRange returned NULL");
    void* copy = NULL;
    napi_value array_buffer;
    napi_create_arraybuffer(env, (size_t)size, &copy, &array_buffer);
    if (copy && size > 0) memcpy(copy, data, (size_t)size);
    return array_buffer;
}

/* Combined map+copy+unmap in a single N-API call.
   Eliminates: mapAsync promise overhead, external arraybuffer from getMappedRange,
   .slice() copy in JS, and separate unmap call. Returns a V8-owned ArrayBuffer. */
static napi_value native_direct_buffer_map_read_copy_unmap(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    uint32_t mode = 0x0001; /* MAP_READ */
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    if (argc >= 1 && argv[0]) napi_get_value_uint32(env, argv[0], &mode);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &offset);
    if (argc >= 3 && argv[2]) napi_get_value_int64(env, argv[2], &size);

    /* flush queue if pending */
    napi_value queue_obj = NULL;
    if (buffer_cache && buffer_cache->queue_ref) {
        napi_get_reference_value(env, buffer_cache->queue_ref, &queue_obj);
    } else {
        queue_obj = get_prop(env, this_arg, DOE_DIRECT_QUEUE);
    }
    if (queue_obj && native_direct_queue_has_pending(env, queue_obj)) {
        NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, queue_obj);
        WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, queue_obj, DOE_DIRECT_NATIVE);
        if (pfn_doeNativeQueueFlush) {
            pfn_doeNativeQueueFlush(queue);
        } else {
            WGPUInstance inst = buffer_cache ? buffer_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
            QueueWorkDoneResult qresult = {0};
            WGPUQueueWorkDoneCallbackInfo cb_info = {
                .nextInChain = NULL,
                .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
                .callback = queue_work_done_callback,
                .userdata1 = &qresult,
                .userdata2 = NULL,
            };
            WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
            if (future.id == 0) NAPI_THROW(env, "queue work-done future unavailable");
            if (!process_events_until(inst, &qresult.done, current_timeout_ns())) {
                NAPI_THROW(env, "queue wait timed out in mapReadCopyUnmap");
            }
        }
        native_direct_queue_mark_done(env, queue_obj);
    }

    /* map */
    WGPUInstance inst = buffer_cache ? buffer_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0 || !result.done) NAPI_THROW(env, "mapReadCopyUnmap: map failed");
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0) NAPI_THROW(env, "mapReadCopyUnmap: map future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns())) {
            NAPI_THROW(env, "mapReadCopyUnmap: map timed out");
        }
    }
    if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS) {
        NAPI_THROW(env, "mapReadCopyUnmap: map failed");
    }

    /* copy mapped data into a V8-owned ArrayBuffer */
    void* data = pfn_wgpuBufferGetMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) data = (void*)pfn_wgpuBufferGetConstMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) {
        pfn_wgpuBufferUnmap(buffer);
        NAPI_THROW(env, "mapReadCopyUnmap: getMappedRange returned NULL");
    }
    void* copy = NULL;
    napi_value array_buffer;
    napi_create_arraybuffer(env, (size_t)size, &copy, &array_buffer);
    if (copy && size > 0) memcpy(copy, data, (size_t)size);

    /* unmap and invalidate cache */
    native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    pfn_wgpuBufferUnmap(buffer);

    return array_buffer;
}

static napi_value native_direct_buffer_unmap(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    if (buffer) pfn_wgpuBufferUnmap(buffer);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_buffer_destroy(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    if (buffer) {
        pfn_wgpuBufferRelease(buffer);
        native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
        if (buffer_cache) buffer_cache->buffer = NULL;
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_command_encoder_begin_compute_pass(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    (void)argv;
    NativeDirectHandleCache* encoder_cache = native_direct_get_handle_cache(env, this_arg);
    WGPUCommandEncoder encoder = encoder_cache ? (WGPUCommandEncoder)encoder_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!encoder) NAPI_THROW(env, "Invalid encoder");
    WGPUComputePassDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
        .timestampWrites = NULL,
    };
    WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(encoder, &desc);
    if (!pass) NAPI_THROW(env, "beginComputePass failed");
    return create_native_direct_compute_pass_object(env, pass);
}

static napi_value native_direct_command_encoder_copy_buffer_to_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 5;
    napi_value argv[5];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 5) NAPI_THROW(env, "copyBufferToBuffer requires source, sourceOffset, target, targetOffset, and size");
    NativeDirectHandleCache* encoder_cache = native_direct_get_handle_cache(env, this_arg);
    NativeDirectBufferCache* src_cache = native_direct_get_buffer_cache(env, argv[0]);
    NativeDirectBufferCache* dst_cache = native_direct_get_buffer_cache(env, argv[2]);
    WGPUCommandEncoder encoder = encoder_cache ? (WGPUCommandEncoder)encoder_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUBuffer src = src_cache ? src_cache->buffer : native_direct_unwrap_external_prop(env, argv[0], DOE_DIRECT_NATIVE);
    WGPUBuffer dst = dst_cache ? dst_cache->buffer : native_direct_unwrap_external_prop(env, argv[2], DOE_DIRECT_NATIVE);
    int64_t src_offset = 0;
    int64_t dst_offset = 0;
    int64_t size = 0;
    if (!encoder || !src || !dst) NAPI_THROW(env, "copyBufferToBuffer requires encoder and buffers");
    napi_get_value_int64(env, argv[1], &src_offset);
    napi_get_value_int64(env, argv[3], &dst_offset);
    napi_get_value_int64(env, argv[4], &size);
    pfn_wgpuCommandEncoderCopyBufferToBuffer(encoder, src, (uint64_t)src_offset, dst, (uint64_t)dst_offset, (uint64_t)size);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_command_encoder_finish(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectHandleCache* encoder_cache = native_direct_get_handle_cache(env, this_arg);
    WGPUCommandEncoder encoder = encoder_cache ? (WGPUCommandEncoder)encoder_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!encoder) NAPI_THROW(env, "Invalid encoder");
    WGPUCommandBufferDescriptor desc = {
        .nextInChain = NULL,
        .label = { .data = NULL, .length = 0 },
    };
    WGPUCommandBuffer command_buffer = pfn_wgpuCommandEncoderFinish(encoder, &desc);
    if (!command_buffer) NAPI_THROW(env, "commandEncoderFinish failed");
    native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
    if (encoder_cache) encoder_cache->native = NULL;
    return create_native_direct_command_buffer_object(env, command_buffer);
}

/* Helper: extract a uint32 from a named property of a JS object.
 * Returns 0 if the property is absent or not a number. */
static uint32_t get_u32_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    uint32_t out = 0;
    napi_get_value_uint32(env, val, &out);
    return out;
}

/* Helper: extract a GPUOrigin3D {x,y,z} from a JS object into three uint32 output args. */
static void get_origin_3d(napi_env env, napi_value obj, uint32_t* x, uint32_t* y, uint32_t* z) {
    *x = get_u32_prop(env, obj, "x");
    *y = get_u32_prop(env, obj, "y");
    *z = get_u32_prop(env, obj, "z");
}

/* Helper: extract a GPUExtent3D {width,height,depthOrArrayLayers} from a JS object. */
static void get_extent_3d(napi_env env, napi_value obj, uint32_t* w, uint32_t* h, uint32_t* d) {
    *w = get_u32_prop(env, obj, "width");
    *h = get_u32_prop(env, obj, "height");
    *d = get_u32_prop(env, obj, "depthOrArrayLayers");
    if (*d == 0) *d = 1; /* default per WebGPU spec */
}

/* GPUCommandEncoder.clearBuffer(buffer, offset?, size?)
 * argv[0]: GPUBuffer, argv[1]: offset (optional, default 0), argv[2]: size (optional, default WGPU_WHOLE_SIZE) */
static napi_value native_direct_command_encoder_clear_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "clearBuffer requires a buffer");
    NativeDirectHandleCache* enc_cache = native_direct_get_handle_cache(env, this_arg);
    NativeDirectBufferCache* buf_cache = native_direct_get_buffer_cache(env, argv[0]);
    void* encoder = enc_cache ? enc_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    void* buffer = buf_cache ? buf_cache->buffer : native_direct_unwrap_external_prop(env, argv[0], DOE_DIRECT_NATIVE);
    if (!encoder || !buffer) NAPI_THROW(env, "clearBuffer: invalid encoder or buffer");
    uint64_t offset = 0;
    uint64_t size = UINT64_MAX; /* WGPU_WHOLE_SIZE */
    if (argc >= 2 && argv[1]) {
        int64_t v = 0;
        napi_get_value_int64(env, argv[1], &v);
        if (v > 0) offset = (uint64_t)v;
    }
    if (argc >= 3 && argv[2]) {
        int64_t v = 0;
        napi_get_value_int64(env, argv[2], &v);
        if (v > 0) size = (uint64_t)v;
    }
    if (pfn_doeNativeCommandEncoderClearBuffer) {
        pfn_doeNativeCommandEncoderClearBuffer(encoder, buffer, offset, size);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPUCommandEncoder.copyTextureToTexture(source, destination, copySize)
 * argv[0]: {texture, mipLevel, origin: {x,y,z}}
 * argv[1]: {texture, mipLevel, origin: {x,y,z}}
 * argv[2]: {width, height, depthOrArrayLayers} */
static napi_value native_direct_command_encoder_copy_texture_to_texture(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 3) NAPI_THROW(env, "copyTextureToTexture requires source, destination, and copySize");
    NativeDirectHandleCache* enc_cache = native_direct_get_handle_cache(env, this_arg);
    void* encoder = enc_cache ? enc_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!encoder) NAPI_THROW(env, "copyTextureToTexture: invalid encoder");
    napi_value src_tex_obj = get_prop(env, argv[0], "texture");
    napi_value dst_tex_obj = get_prop(env, argv[1], "texture");
    void* src_texture = native_direct_unwrap_external_prop(env, src_tex_obj, DOE_DIRECT_NATIVE);
    void* dst_texture = native_direct_unwrap_external_prop(env, dst_tex_obj, DOE_DIRECT_NATIVE);
    if (!src_texture || !dst_texture) NAPI_THROW(env, "copyTextureToTexture: invalid source or destination texture");
    uint32_t src_mip = get_u32_prop(env, argv[0], "mipLevel");
    uint32_t dst_mip = get_u32_prop(env, argv[1], "mipLevel");
    uint32_t src_x = 0, src_y = 0, src_z = 0;
    uint32_t dst_x = 0, dst_y = 0, dst_z = 0;
    napi_value src_origin = get_prop(env, argv[0], "origin");
    napi_value dst_origin = get_prop(env, argv[1], "origin");
    napi_valuetype src_origin_type, dst_origin_type;
    napi_typeof(env, src_origin, &src_origin_type);
    napi_typeof(env, dst_origin, &dst_origin_type);
    if (src_origin_type == napi_object) get_origin_3d(env, src_origin, &src_x, &src_y, &src_z);
    if (dst_origin_type == napi_object) get_origin_3d(env, dst_origin, &dst_x, &dst_y, &dst_z);
    uint32_t width = 1, height = 1, depth_or_layers = 1;
    napi_valuetype size_type;
    napi_typeof(env, argv[2], &size_type);
    if (size_type == napi_object) get_extent_3d(env, argv[2], &width, &height, &depth_or_layers);
    if (pfn_wgpuCommandEncoderCopyTextureToTexture) {
        WGPUTexelCopyTextureInfo src;
        WGPUTexelCopyTextureInfo dst;
        WGPUExtent3D size;
        memset(&src, 0, sizeof(src));
        memset(&dst, 0, sizeof(dst));
        src.texture = src_texture;
        src.mipLevel = src_mip;
        src.origin.x = src_x;
        src.origin.y = src_y;
        src.origin.z = src_z;
        dst.texture = dst_texture;
        dst.mipLevel = dst_mip;
        dst.origin.x = dst_x;
        dst.origin.y = dst_y;
        dst.origin.z = dst_z;
        size.width = width;
        size.height = height;
        size.depthOrArrayLayers = depth_or_layers;
        pfn_wgpuCommandEncoderCopyTextureToTexture(encoder, &src, &dst, &size);
    } else if (pfn_doeNativeCommandEncoderCopyTextureToTexture) {
        pfn_doeNativeCommandEncoderCopyTextureToTexture(
            encoder,
            src_texture, src_mip, 0, src_x, src_y, src_z,
            dst_texture, dst_mip, 0, dst_x, dst_y, dst_z,
            width, height, depth_or_layers);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPUQueue.writeTexture(destination, data, dataLayout, size)
 * argv[0]: {texture, mipLevel, origin: {x,y,z}, aspect?}
 * argv[1]: ArrayBuffer | TypedArray — pixel data
 * argv[2]: {offset?, bytesPerRow, rowsPerImage?}
 * argv[3]: {width, height, depthOrArrayLayers} */
static napi_value native_direct_queue_write_texture(napi_env env, napi_callback_info info) {
    size_t argc = 4;
    napi_value argv[4];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 4) NAPI_THROW(env, "writeTexture requires destination, data, dataLayout, and size");
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    void* queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!queue) NAPI_THROW(env, "writeTexture: invalid queue");
    napi_value tex_obj = get_prop(env, argv[0], "texture");
    void* texture = native_direct_unwrap_external_prop(env, tex_obj, DOE_DIRECT_NATIVE);
    if (!texture) NAPI_THROW(env, "writeTexture: invalid destination texture");
    uint32_t dst_mip = get_u32_prop(env, argv[0], "mipLevel");
    uint32_t dst_x = 0, dst_y = 0, dst_z = 0;
    napi_value dst_origin = get_prop(env, argv[0], "origin");
    napi_valuetype dst_origin_type;
    napi_typeof(env, dst_origin, &dst_origin_type);
    if (dst_origin_type == napi_object) get_origin_3d(env, dst_origin, &dst_x, &dst_y, &dst_z);
    /* Extract pixel data pointer and byte length */
    void* data = NULL;
    size_t data_len = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, argv[1], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length;
        napi_value ab;
        size_t byte_offset;
        napi_get_typedarray_info(env, argv[1], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        data_len = ta_length * elem_size;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, argv[1], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, argv[1], &data, &data_len);
        } else {
            NAPI_THROW(env, "writeTexture: data must be TypedArray or ArrayBuffer");
        }
    }
    /* dataLayout: {offset?, bytesPerRow, rowsPerImage?} */
    uint32_t layout_offset = get_u32_prop(env, argv[2], "offset");
    uint32_t bytes_per_row = get_u32_prop(env, argv[2], "bytesPerRow");
    uint32_t rows_per_image = get_u32_prop(env, argv[2], "rowsPerImage");
    if (layout_offset > 0 && layout_offset < data_len) {
        data = ((uint8_t*)data) + layout_offset;
        data_len -= layout_offset;
    }
    /* copySize */
    uint32_t width = 1, height = 1, depth_or_layers = 1;
    napi_valuetype size_type;
    napi_typeof(env, argv[3], &size_type);
    if (size_type == napi_object) get_extent_3d(env, argv[3], &width, &height, &depth_or_layers);
    if (pfn_doeNativeQueueWriteTexture) {
        pfn_doeNativeQueueWriteTexture(
            queue, texture,
            data, data_len,
            bytes_per_row, rows_per_image,
            dst_x, dst_y, dst_z, dst_mip, 0,
            width, height, depth_or_layers);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value doe_command_encoder_clear_buffer_export(napi_env env, napi_callback_info info) {
    size_t argc = 4;
    napi_value argv[4];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeCommandEncoderClearBuffer) NAPI_THROW(env, "commandEncoderClearBuffer not available");
    if (argc < 2) NAPI_THROW(env, "commandEncoderClearBuffer requires encoder and buffer");

    WGPUCommandEncoder encoder = unwrap_ptr(env, argv[0]);
    WGPUBuffer buffer = unwrap_ptr(env, argv[1]);
    if (!encoder || !buffer) NAPI_THROW(env, "commandEncoderClearBuffer: invalid encoder or buffer");

    uint64_t offset = 0;
    uint64_t size = WGPU_WHOLE_SIZE;
    if (argc >= 3 && argv[2]) {
      napi_valuetype offset_type = napi_undefined;
      napi_typeof(env, argv[2], &offset_type);
      if (offset_type == napi_number) {
        int64_t value = 0;
        napi_get_value_int64(env, argv[2], &value);
        if (value > 0) offset = (uint64_t)value;
      }
    }
    if (argc >= 4 && argv[3]) {
      napi_valuetype size_type = napi_undefined;
      napi_typeof(env, argv[3], &size_type);
      if (size_type == napi_number) {
        int64_t value = 0;
        napi_get_value_int64(env, argv[3], &value);
        if (value >= 0) size = (uint64_t)value;
      }
    }
    pfn_doeNativeCommandEncoderClearBuffer(encoder, buffer, offset, size);
    return NULL;
}

static napi_value doe_command_encoder_copy_texture_to_texture_export(napi_env env, napi_callback_info info) {
    size_t argc = 15;
    napi_value argv[15];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (argc != 14 && argc != 15) {
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture requires 14 or 15 arguments");
    }
    if (!pfn_doeNativeCommandEncoderCopyTextureToTexture && !pfn_wgpuCommandEncoderCopyTextureToTexture) {
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture not available");
    }

    const size_t dst_index = argc == 15 ? 7 : 6;
    const size_t dst_mip_index = argc == 15 ? 8 : 7;
    const size_t dst_x_index = argc == 15 ? 9 : 8;
    const size_t dst_y_index = argc == 15 ? 10 : 9;
    const size_t dst_z_index = argc == 15 ? 11 : 10;
    const size_t width_index = argc == 15 ? 12 : 11;
    const size_t height_index = argc == 15 ? 13 : 12;
    const size_t depth_index = argc == 15 ? 14 : 13;

    WGPUCommandEncoder encoder = unwrap_ptr(env, argv[0]);
    WGPUTexture src_texture = unwrap_ptr(env, argv[1]);
    uint32_t src_mip = 0;
    uint32_t src_x = 0;
    uint32_t src_y = 0;
    uint32_t src_z = 0;
    WGPUTexture dst_texture = unwrap_ptr(env, argv[dst_index]);
    uint32_t dst_mip = 0;
    uint32_t dst_x = 0;
    uint32_t dst_y = 0;
    uint32_t dst_z = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t depth_or_layers = 0;

    if (!encoder || !src_texture || !dst_texture) NAPI_THROW(env, "commandEncoderCopyTextureToTexture: invalid encoder or textures");
    napi_get_value_uint32(env, argv[2], &src_mip);
    napi_get_value_uint32(env, argv[3], &src_x);
    napi_get_value_uint32(env, argv[4], &src_y);
    napi_get_value_uint32(env, argv[5], &src_z);
    napi_get_value_uint32(env, argv[dst_mip_index], &dst_mip);
    napi_get_value_uint32(env, argv[dst_x_index], &dst_x);
    napi_get_value_uint32(env, argv[dst_y_index], &dst_y);
    napi_get_value_uint32(env, argv[dst_z_index], &dst_z);
    napi_get_value_uint32(env, argv[width_index], &width);
    napi_get_value_uint32(env, argv[height_index], &height);
    napi_get_value_uint32(env, argv[depth_index], &depth_or_layers);

    if (pfn_doeNativeCommandEncoderCopyTextureToTexture) {
        pfn_doeNativeCommandEncoderCopyTextureToTexture(
            encoder,
            src_texture, src_mip, 0, src_x, src_y, src_z,
            dst_texture, dst_mip, 0, dst_x, dst_y, dst_z,
            width, height, depth_or_layers);
    } else {
        WGPUTexelCopyTextureInfo src;
        WGPUTexelCopyTextureInfo dst;
        WGPUExtent3D size;
        memset(&src, 0, sizeof(src));
        memset(&dst, 0, sizeof(dst));
        src.texture = src_texture;
        src.mipLevel = src_mip;
        src.origin.x = src_x;
        src.origin.y = src_y;
        src.origin.z = src_z;
        dst.texture = dst_texture;
        dst.mipLevel = dst_mip;
        dst.origin.x = dst_x;
        dst.origin.y = dst_y;
        dst.origin.z = dst_z;
        size.width = width;
        size.height = height;
        size.depthOrArrayLayers = depth_or_layers;
        pfn_wgpuCommandEncoderCopyTextureToTexture(encoder, &src, &dst, &size);
    }
    return NULL;
}

static napi_value native_direct_compute_pass_set_pipeline(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "setPipeline requires a pipeline");
    NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
    NativeDirectHandleCache* pipeline_cache = native_direct_get_handle_cache(env, argv[0]);
    WGPUComputePassEncoder pass = pass_cache ? (WGPUComputePassEncoder)pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUComputePipeline pipeline = pipeline_cache ? (WGPUComputePipeline)pipeline_cache->native : native_direct_unwrap_external_prop(env, argv[0], DOE_DIRECT_NATIVE);
    pfn_wgpuComputePassEncoderSetPipeline(pass, pipeline);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_compute_pass_set_bind_group(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 2) NAPI_THROW(env, "setBindGroup requires an index and bind group");
    NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
    NativeDirectHandleCache* bind_group_cache = native_direct_get_handle_cache(env, argv[1]);
    WGPUComputePassEncoder pass = pass_cache ? (WGPUComputePassEncoder)pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUBindGroup bind_group = bind_group_cache ? (WGPUBindGroup)bind_group_cache->native : native_direct_unwrap_external_prop(env, argv[1], DOE_DIRECT_NATIVE);
    uint32_t index = 0;
    napi_get_value_uint32(env, argv[0], &index);
    pfn_wgpuComputePassEncoderSetBindGroup(pass, index, bind_group, 0, NULL);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_compute_pass_dispatch_workgroups(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "dispatchWorkgroups requires x");
    NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
    WGPUComputePassEncoder pass = pass_cache ? (WGPUComputePassEncoder)pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    uint32_t x = 1;
    uint32_t y = 1;
    uint32_t z = 1;
    napi_get_value_uint32(env, argv[0], &x);
    if (argc >= 2 && argv[1]) napi_get_value_uint32(env, argv[1], &y);
    if (argc >= 3 && argv[2]) napi_get_value_uint32(env, argv[2], &z);
    pfn_wgpuComputePassEncoderDispatchWorkgroups(pass, x, y, z);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_compute_pass_dispatch_workgroups_indirect(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "dispatchWorkgroupsIndirect requires a buffer");
    NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, argv[0]);
    WGPUComputePassEncoder pass = pass_cache ? (WGPUComputePassEncoder)pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, argv[0], DOE_DIRECT_NATIVE);
    int64_t offset = 0;
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &offset);
    if (pfn_doeNativeComputePassDispatchIndirect) {
        pfn_doeNativeComputePassDispatchIndirect(pass, buffer, (uint64_t)offset);
    } else {
        pfn_wgpuComputePassEncoderDispatchWorkgroupsIndirect(pass, buffer, (uint64_t)offset);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value native_direct_compute_pass_end(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectHandleCache* pass_cache = native_direct_get_handle_cache(env, this_arg);
    WGPUComputePassEncoder pass = pass_cache ? (WGPUComputePassEncoder)pass_cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    pfn_wgpuComputePassEncoderEnd(pass);
    native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
    if (pass_cache) pass_cache->native = NULL;
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

static napi_value create_native_direct_gpu_object(napi_env env, WGPUInstance instance) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_wrap_handle_cache(env, obj, instance, NULL);
    native_direct_add_cached_method(env, obj, "requestAdapter", native_direct_gpu_request_adapter, &native_direct_method_gpu_request_adapter_ref);
    return obj;
}

static napi_value create_native_direct_adapter_object(napi_env env, WGPUInstance instance, WGPUAdapter adapter) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, adapter);
    native_direct_wrap_handle_cache(env, obj, instance, adapter);
    bool limits_ok = false;
    WGPULimits limits = native_direct_query_adapter_limits(adapter, &limits_ok);
    native_direct_set_object_prop(env, obj, "limits", limits_ok ? create_limits_object(env, &limits) : native_direct_create_empty_object(env));
    native_direct_set_object_prop(env, obj, "features", native_direct_create_empty_set(env));
    native_direct_add_cached_method(env, obj, "requestDevice", native_direct_adapter_request_device, &native_direct_method_adapter_request_device_ref);
    native_direct_add_cached_method(env, obj, "destroy", native_direct_adapter_destroy, &native_direct_method_adapter_destroy_ref);
    native_direct_add_cached_method(env, obj, "getPreferredCanvasFormat", native_direct_adapter_get_preferred_canvas_format, &native_direct_method_adapter_get_preferred_canvas_format_ref);
    /* GPUAdapter.info — method that returns the info object directly (not async). */
    native_direct_add_cached_method(env, obj, "getInfo", native_direct_adapter_get_info, &native_direct_method_adapter_get_info_ref);
    return obj;
}

static napi_value create_native_direct_queue_object(napi_env env, WGPUInstance instance, WGPUQueue queue) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, queue);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_QUEUE_NATIVE, queue);
    native_direct_set_uint32_prop(env, obj, DOE_DIRECT_SUBMITTED_SERIAL, 0);
    native_direct_set_uint32_prop(env, obj, DOE_DIRECT_COMPLETED_SERIAL, 0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_SUBMIT_WAIT_MS, 0.0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_QUEUE_FLUSH_MS, 0.0);
    native_direct_wrap_queue_cache(env, obj, instance, queue);
    native_direct_add_cached_method(env, obj, "submit", native_direct_queue_submit, &native_direct_method_queue_submit_ref);
    native_direct_add_cached_method(env, obj, "writeBuffer", native_direct_queue_write_buffer, &native_direct_method_queue_write_buffer_ref);
    native_direct_add_cached_method(env, obj, "writeTexture", native_direct_queue_write_texture, &native_direct_method_queue_write_texture_ref);
    native_direct_add_cached_method(env, obj, "onSubmittedWorkDone", native_direct_queue_on_submitted_work_done, &native_direct_method_queue_on_submitted_work_done_ref);
    return obj;
}

static napi_value create_native_direct_device_object(napi_env env, WGPUInstance instance, WGPUDevice device) {
    napi_value obj;
    WGPUQueue queue = pfn_wgpuDeviceGetQueue(device);
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, device);
    native_direct_wrap_handle_cache(env, obj, instance, device);
    bool limits_ok = false;
    WGPULimits limits = native_direct_query_device_limits(device, &limits_ok);
    native_direct_set_object_prop(env, obj, "limits", limits_ok ? create_limits_object(env, &limits) : native_direct_create_empty_object(env));
    native_direct_set_object_prop(env, obj, "features", native_direct_create_empty_set(env));
    native_direct_set_object_prop(env, obj, "queue", create_native_direct_queue_object(env, instance, queue));
    native_direct_add_cached_method(env, obj, "createBuffer", native_direct_device_create_buffer, &native_direct_method_device_create_buffer_ref);
    native_direct_add_cached_method(env, obj, "createShaderModule", native_direct_device_create_shader_module, &native_direct_method_device_create_shader_module_ref);
    native_direct_add_cached_method(env, obj, "createComputePipeline", native_direct_device_create_compute_pipeline, &native_direct_method_device_create_compute_pipeline_ref);
    native_direct_add_cached_method(env, obj, "createComputePipelineAsync", native_direct_device_create_compute_pipeline_async, &native_direct_method_device_create_compute_pipeline_async_ref);
    native_direct_add_cached_method(env, obj, "createBindGroupLayout", native_direct_device_create_bind_group_layout, &native_direct_method_device_create_bind_group_layout_ref);
    native_direct_add_cached_method(env, obj, "createBindGroup", native_direct_device_create_bind_group, &native_direct_method_device_create_bind_group_ref);
    native_direct_add_cached_method(env, obj, "createPipelineLayout", native_direct_device_create_pipeline_layout, &native_direct_method_device_create_pipeline_layout_ref);
    native_direct_add_cached_method(env, obj, "createCommandEncoder", native_direct_device_create_command_encoder, &native_direct_method_device_create_command_encoder_ref);
    native_direct_add_cached_method(env, obj, "destroy", native_direct_device_destroy, &native_direct_method_device_destroy_ref);
    native_direct_add_cached_method(env, obj, "addEventListener", native_direct_device_add_event_listener, &native_direct_method_device_add_event_listener_ref);
    native_direct_add_cached_method(env, obj, "removeEventListener", native_direct_device_remove_event_listener, &native_direct_method_device_remove_event_listener_ref);
    native_direct_add_cached_method(env, obj, "importExternalTexture", native_direct_device_import_external_texture, &native_direct_method_device_import_external_texture_ref);
    return obj;
}

static napi_value create_native_direct_buffer_object(napi_env env, WGPUInstance instance, napi_value queue_obj, WGPUBuffer buffer, uint64_t size, uint64_t usage) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, buffer);
    native_direct_set_object_prop(env, obj, DOE_DIRECT_QUEUE, queue_obj);
    native_direct_set_double_prop(env, obj, "size", (double)size);
    native_direct_set_double_prop(env, obj, "usage", (double)usage);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_MAP_ASYNC_MS, 0.0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_MAP_QUEUE_FLUSH_MS, 0.0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS, 0.0);
    native_direct_wrap_buffer_cache(env, obj, instance, buffer, size, usage, queue_obj);
    native_direct_add_cached_method(env, obj, "mapAsync", native_direct_buffer_map_async, &native_direct_method_buffer_map_async_ref);
    native_direct_add_cached_method(env, obj, "getMappedRange", native_direct_buffer_get_mapped_range, &native_direct_method_buffer_get_mapped_range_ref);
    native_direct_add_cached_method(env, obj, "_readCopy", native_direct_buffer_read_copy, &native_direct_method_buffer_read_copy_ref);
    native_direct_add_cached_method(env, obj, "_mapReadCopyUnmap", native_direct_buffer_map_read_copy_unmap, &native_direct_method_buffer_map_read_copy_unmap_ref);
    native_direct_add_cached_method(env, obj, "unmap", native_direct_buffer_unmap, &native_direct_method_buffer_unmap_ref);
    native_direct_add_cached_method(env, obj, "destroy", native_direct_buffer_destroy, &native_direct_method_buffer_destroy_ref);
    return obj;
}

static napi_value create_native_direct_bind_group_layout_object(napi_env env, WGPUBindGroupLayout layout) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, layout);
    native_direct_wrap_handle_cache(env, obj, NULL, layout);
    return obj;
}

static napi_value create_native_direct_bind_group_object(napi_env env, WGPUBindGroup group) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, group);
    native_direct_wrap_handle_cache(env, obj, NULL, group);
    return obj;
}

static napi_value create_native_direct_pipeline_layout_object(napi_env env, WGPUPipelineLayout layout) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, layout);
    native_direct_wrap_handle_cache(env, obj, NULL, layout);
    return obj;
}

static napi_value create_native_direct_shader_module_object(napi_env env, WGPUShaderModule shader_module) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, shader_module);
    native_direct_wrap_handle_cache(env, obj, NULL, shader_module);
    /* GPUShaderModule.getCompilationInfo() — returns a Promise<GPUCompilationInfo>. */
    native_direct_add_cached_method(env, obj, "getCompilationInfo", native_direct_shader_module_get_compilation_info, &native_direct_method_shader_module_get_compilation_info_ref);
    return obj;
}

static napi_value create_native_direct_compute_pipeline_object(napi_env env, WGPUComputePipeline pipeline) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, pipeline);
    native_direct_wrap_handle_cache(env, obj, NULL, pipeline);
    return obj;
}

static napi_value create_native_direct_command_buffer_object(napi_env env, WGPUCommandBuffer command_buffer) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, command_buffer);
    native_direct_wrap_handle_cache(env, obj, NULL, command_buffer);
    return obj;
}

static napi_value create_native_direct_command_encoder_object(napi_env env, WGPUCommandEncoder encoder) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, encoder);
    native_direct_wrap_handle_cache(env, obj, NULL, encoder);
    native_direct_add_cached_method(env, obj, "beginComputePass", native_direct_command_encoder_begin_compute_pass, &native_direct_method_command_encoder_begin_compute_pass_ref);
    native_direct_add_cached_method(env, obj, "copyBufferToBuffer", native_direct_command_encoder_copy_buffer_to_buffer, &native_direct_method_command_encoder_copy_buffer_to_buffer_ref);
    native_direct_add_cached_method(env, obj, "clearBuffer", native_direct_command_encoder_clear_buffer, &native_direct_method_command_encoder_clear_buffer_ref);
    native_direct_add_cached_method(env, obj, "copyTextureToTexture", native_direct_command_encoder_copy_texture_to_texture, &native_direct_method_command_encoder_copy_texture_to_texture_ref);
    native_direct_add_cached_method(env, obj, "finish", native_direct_command_encoder_finish, &native_direct_method_command_encoder_finish_ref);
    return obj;
}

static napi_value create_native_direct_compute_pass_object(napi_env env, WGPUComputePassEncoder pass) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, pass);
    native_direct_wrap_handle_cache(env, obj, NULL, pass);
    native_direct_add_cached_method(env, obj, "setPipeline", native_direct_compute_pass_set_pipeline, &native_direct_method_compute_pass_set_pipeline_ref);
    native_direct_add_cached_method(env, obj, "setBindGroup", native_direct_compute_pass_set_bind_group, &native_direct_method_compute_pass_set_bind_group_ref);
    native_direct_add_cached_method(env, obj, "dispatchWorkgroups", native_direct_compute_pass_dispatch_workgroups, &native_direct_method_compute_pass_dispatch_workgroups_ref);
    native_direct_add_cached_method(env, obj, "dispatchWorkgroupsIndirect", native_direct_compute_pass_dispatch_workgroups_indirect, &native_direct_method_compute_pass_dispatch_workgroups_indirect_ref);
    native_direct_add_cached_method(env, obj, "end", native_direct_compute_pass_end, &native_direct_method_compute_pass_end_ref);
    /* GPUBindingCommandsMixin#setImmediates — covers both mixin and compute-pass-specific contract */
    native_direct_add_cached_method(env, obj, "setImmediates", native_direct_compute_pass_set_immediates, &native_direct_method_compute_pass_set_immediates_ref);
    return obj;
}

/* create_native_direct_render_pass_object: wraps a WGPURenderPassEncoder as a JS
 * object with all GPURenderPassEncoder control methods registered. */
static napi_value
create_native_direct_render_pass_object(napi_env env, WGPURenderPassEncoder pass) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, pass);
    native_direct_wrap_handle_cache(env, obj, NULL, pass);
    /* GPURenderPassEncoder#setImmediates (GPUBindingCommandsMixin) */
    native_direct_add_cached_method(env, obj, "setImmediates", native_direct_render_pass_set_immediates, &native_direct_method_render_pass_set_immediates_ref);
    /* GPURenderPassEncoder dynamic state */
    native_direct_add_cached_method(env, obj, "setViewport", native_direct_render_pass_set_viewport, &native_direct_method_render_pass_set_viewport_ref);
    native_direct_add_cached_method(env, obj, "setScissorRect", native_direct_render_pass_set_scissor_rect, &native_direct_method_render_pass_set_scissor_rect_ref);
    native_direct_add_cached_method(env, obj, "setBlendConstant", native_direct_render_pass_set_blend_constant, &native_direct_method_render_pass_set_blend_constant_ref);
    native_direct_add_cached_method(env, obj, "setStencilReference", native_direct_render_pass_set_stencil_reference, &native_direct_method_render_pass_set_stencil_reference_ref);
    /* GPURenderPassEncoder debug markers */
    native_direct_add_cached_method(env, obj, "pushDebugGroup", native_direct_render_pass_push_debug_group, &native_direct_method_render_pass_push_debug_group_ref);
    native_direct_add_cached_method(env, obj, "popDebugGroup", native_direct_render_pass_pop_debug_group, &native_direct_method_render_pass_pop_debug_group_ref);
    native_direct_add_cached_method(env, obj, "insertDebugMarker", native_direct_render_pass_insert_debug_marker, &native_direct_method_render_pass_insert_debug_marker_ref);
    return obj;
}

/* create_native_direct_render_bundle_encoder_object: wraps a WGPURenderBundleEncoder
 * with setImmediates registered. The render bundle encoder is not yet plumbed through
 * the full native-direct object model; this creator is provided so that callers
 * constructing bundle encoders can attach setImmediates without special-casing. */
static napi_value __attribute__((unused))
create_native_direct_render_bundle_encoder_object(napi_env env, void* encoder) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, encoder);
    native_direct_wrap_handle_cache(env, obj, NULL, encoder);
    /* GPURenderBundleEncoder#setImmediates (GPUBindingCommandsMixin) */
    native_direct_add_cached_method(env, obj, "setImmediates", native_direct_render_bundle_encoder_set_immediates, &native_direct_method_render_bundle_encoder_set_immediates_ref);
    return obj;
}

static napi_value doe_native_direct_create(napi_env env, napi_callback_info info) {
    (void)info;
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = pfn_wgpuCreateInstance(NULL);
    if (!inst) NAPI_THROW(env, "wgpuCreateInstance returned NULL");
    return create_native_direct_gpu_object(env, inst);
}

/* ================================================================
 * Module initialization
 * ================================================================ */

#define EXPORT_FN(name, fn) { name, 0, fn, 0, 0, 0, napi_default, 0 }

static napi_value doe_module_init(napi_env env, napi_value exports) {
    napi_property_descriptor descriptors[] = {
        EXPORT_FN("loadLibrary", doe_load_library),
        EXPORT_FN("nativeDirectCreate", doe_native_direct_create),
        EXPORT_FN("createInstance", doe_create_instance),
        EXPORT_FN("instanceRelease", doe_instance_release),
        EXPORT_FN("requestAdapter", doe_request_adapter),
        EXPORT_FN("adapterRelease", doe_adapter_release),
        EXPORT_FN("adapterGetInfo", doe_adapter_get_info),
        EXPORT_FN("requestDevice", doe_request_device),
        EXPORT_FN("deviceRelease", doe_device_release),
        EXPORT_FN("deviceGetQueue", doe_device_get_queue),
        EXPORT_FN("devicePushErrorScope", doe_device_push_error_scope_export),
        EXPORT_FN("devicePopErrorScope", doe_device_pop_error_scope_export),
        EXPORT_FN("deviceSetUncapturedErrorCallback", doe_device_set_uncaptured_error_callback_export),
        EXPORT_FN("deviceRegisterLostCallback", doe_device_register_lost_callback),
        EXPORT_FN("createBuffer", doe_create_buffer),
        EXPORT_FN("bufferRelease", doe_buffer_release),
        EXPORT_FN("bufferUnmap", doe_buffer_unmap),
        EXPORT_FN("bufferMapSync", doe_buffer_map_sync),
        EXPORT_FN("bufferGetMappedRange", doe_buffer_get_mapped_range),
        EXPORT_FN("bufferGetStagedRange", doe_buffer_get_staged_range),
        EXPORT_FN("bufferFlushStagedRange", doe_buffer_flush_staged_range),
        EXPORT_FN("bufferReadCopy", doe_buffer_read_copy),
        EXPORT_FN("bufferWriteMappedRange", doe_buffer_write_mapped_range),
        EXPORT_FN("bufferReadIndirectCounts", doe_buffer_read_indirect_counts),
        EXPORT_FN("bufferAssertMappedPrefixF32", doe_buffer_assert_mapped_prefix_f32),
        EXPORT_FN("checkShaderSource", doe_check_shader_source),
        EXPORT_FN("createShaderModule", doe_create_shader_module),
        EXPORT_FN("shaderModuleRelease", doe_shader_module_release),
        EXPORT_FN("shaderModuleGetBindings", doe_shader_module_get_bindings),
        EXPORT_FN("shaderModuleGetCompilationInfo", doe_shader_module_get_compilation_info),
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
        EXPORT_FN("commandEncoderCopyBufferToTexture", doe_command_encoder_copy_buffer_to_texture),
        EXPORT_FN("commandEncoderCopyTextureToBuffer", doe_command_encoder_copy_texture_to_buffer),
        EXPORT_FN("commandEncoderClearBuffer", doe_command_encoder_clear_buffer_export),
        EXPORT_FN("commandEncoderCopyTextureToTexture", doe_command_encoder_copy_texture_to_texture_export),
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
        EXPORT_FN("queueWriteTexture", doe_queue_write_texture),
        EXPORT_FN("queueFlush", doe_queue_flush),
        EXPORT_FN("submitBatched", doe_submit_batched),
        EXPORT_FN("submitComputeDispatchCopy", doe_submit_compute_dispatch_copy),
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
        EXPORT_FN("renderPipelineGetBindGroupLayout", doe_render_pipeline_get_bind_group_layout),
        EXPORT_FN("beginRenderPass", doe_begin_render_pass),
        EXPORT_FN("renderPassSetPipeline", doe_render_pass_set_pipeline),
        EXPORT_FN("renderPassSetBindGroup", doe_render_pass_set_bind_group),
        EXPORT_FN("renderPassSetVertexBuffer", doe_render_pass_set_vertex_buffer),
        EXPORT_FN("renderPassSetIndexBuffer", doe_render_pass_set_index_buffer),
        EXPORT_FN("renderPassDraw", doe_render_pass_draw),
        EXPORT_FN("renderPassDrawIndexed", doe_render_pass_draw_indexed),
        EXPORT_FN("renderPassEnd", doe_render_pass_end),
        EXPORT_FN("renderPassRelease", doe_render_pass_release),
        EXPORT_FN("renderPassSetViewport", doe_render_pass_set_viewport),
        EXPORT_FN("renderPassSetScissorRect", doe_render_pass_set_scissor_rect),
        EXPORT_FN("renderPassSetBlendConstant", doe_render_pass_set_blend_constant),
        EXPORT_FN("renderPassSetStencilReference", doe_render_pass_set_stencil_reference),
        EXPORT_FN("renderPassPushDebugGroup", doe_render_pass_push_debug_group),
        EXPORT_FN("renderPassPopDebugGroup", doe_render_pass_pop_debug_group),
        EXPORT_FN("renderPassInsertDebugMarker", doe_render_pass_insert_debug_marker),
        EXPORT_FN("createRenderBundleEncoder", doe_create_render_bundle_encoder),
        EXPORT_FN("renderBundleEncoderSetPipeline", doe_render_bundle_encoder_set_pipeline),
        EXPORT_FN("renderBundleEncoderSetBindGroup", doe_render_bundle_encoder_set_bind_group),
        EXPORT_FN("renderBundleEncoderSetVertexBuffer", doe_render_bundle_encoder_set_vertex_buffer),
        EXPORT_FN("renderBundleEncoderSetIndexBuffer", doe_render_bundle_encoder_set_index_buffer),
        EXPORT_FN("renderBundleEncoderDraw", doe_render_bundle_encoder_draw),
        EXPORT_FN("renderBundleEncoderDrawIndexed", doe_render_bundle_encoder_draw_indexed),
        EXPORT_FN("renderBundleEncoderFinish", doe_render_bundle_encoder_finish),
        EXPORT_FN("renderBundleEncoderRelease", doe_render_bundle_encoder_release),
        EXPORT_FN("renderBundleRelease", doe_render_bundle_release),
        EXPORT_FN("adapterGetLimits", doe_adapter_get_limits),
        EXPORT_FN("adapterHasFeature", doe_adapter_has_feature),
        EXPORT_FN("deviceGetLimits", doe_device_get_limits),
        EXPORT_FN("deviceHasFeature", doe_device_has_feature),
        EXPORT_FN("deviceSetLostCallback", doe_device_set_lost_callback_export),
        EXPORT_FN("createQuerySet", doe_create_query_set),
        EXPORT_FN("commandEncoderWriteTimestamp", doe_command_encoder_write_timestamp),
        EXPORT_FN("commandEncoderResolveQuerySet", doe_command_encoder_resolve_query_set),
        EXPORT_FN("querySetDestroy", doe_query_set_destroy),
        EXPORT_FN("setTimeoutMs", doe_set_timeout_ms),
        EXPORT_FN("getLastErrorStage", doe_get_last_error_stage),
        EXPORT_FN("getLastErrorKind", doe_get_last_error_kind),
        EXPORT_FN("getLastErrorLine", doe_get_last_error_line),
        EXPORT_FN("getLastErrorColumn", doe_get_last_error_column),
    };

    size_t count = sizeof(descriptors) / sizeof(descriptors[0]);
    napi_define_properties(env, exports, count, descriptors);
    return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, doe_module_init)
