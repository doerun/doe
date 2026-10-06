#include "dawn/dawn_proc_table.h"
#include <stddef.h>
#include <stdint.h>

typedef struct ContextRequest {
    void* handle;
    uint32_t status;
} ContextRequest;

typedef struct ContextIdentity {
    uint32_t backend;
    uint32_t vendor;
    uint32_t device;
    uint32_t adapter_type;
} ContextIdentity;

static void adapter_ready(WGPURequestAdapterStatus status, WGPUAdapter adapter,
    WGPUStringView message, void* out, void* unused) {
    (void)message;
    (void)unused;
    ContextRequest* request = out;
    request->handle = adapter;
    request->status = status;
}

static void device_ready(WGPURequestDeviceStatus status, WGPUDevice device,
    WGPUStringView message, void* out, void* unused) {
    (void)message;
    (void)unused;
    ContextRequest* request = out;
    request->handle = device;
    request->status = status;
}

int doeExternalContextCreate(const DawnProcTable* table,
    WGPUInstance* instance_out, WGPUDevice* device_out, ContextIdentity* identity_out) {
    const WGPUInstanceFeatureName timed_wait = WGPUInstanceFeatureName_TimedWaitAny;
    WGPUInstanceDescriptor descriptor = {0};
    descriptor.requiredFeatureCount = 1;
    descriptor.requiredFeatures = &timed_wait;
    WGPUInstance instance = table->createInstance(&descriptor);
    if (!instance) return 1;
    *instance_out = instance;
    ContextRequest adapter = {0};
    WGPURequestAdapterOptions options = {0};
    options.backendType = WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo callback = {0};
    callback.mode = WGPUCallbackMode_WaitAnyOnly;
    callback.callback = adapter_ready;
    callback.userdata1 = &adapter;
    WGPUFutureWaitInfo wait = {0};
    wait.future = table->instanceRequestAdapter(instance, &options, callback);
    if (table->instanceWaitAny(instance, 1, &wait, UINT64_MAX) != WGPUWaitStatus_Success ||
        adapter.status != WGPURequestAdapterStatus_Success || !adapter.handle) return 2;
    WGPUAdapterInfo info = {0};
    WGPUStatus info_status = table->adapterGetInfo(adapter.handle, &info);
    *identity_out = (ContextIdentity){info.backendType, info.vendorID, info.deviceID, info.adapterType};
    table->adapterInfoFreeMembers(info);
    if (info_status != WGPUStatus_Success || identity_out->backend != WGPUBackendType_Vulkan ||
        identity_out->vendor != 0x1002 || identity_out->adapter_type == WGPUAdapterType_CPU) {
        table->adapterRelease(adapter.handle);
        return 4;
    }
    WGPUFeatureName features[3];
    size_t count = 0;
    const WGPUFeatureName candidates[] = {
        WGPUFeatureName_ShaderF16, WGPUFeatureName_Subgroups, WGPUFeatureName_TimestampQuery,
    };
    for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); ++i) {
        if (table->adapterHasFeature(adapter.handle, candidates[i])) features[count++] = candidates[i];
    }
    WGPUDeviceDescriptor device_descriptor = {0};
    device_descriptor.requiredFeatureCount = count;
    device_descriptor.requiredFeatures = features;
    ContextRequest device = {0};
    WGPURequestDeviceCallbackInfo device_callback = {0};
    device_callback.mode = WGPUCallbackMode_WaitAnyOnly;
    device_callback.callback = device_ready;
    device_callback.userdata1 = &device;
    wait = (WGPUFutureWaitInfo){0};
    wait.future = table->adapterRequestDevice(adapter.handle, &device_descriptor, device_callback);
    WGPUWaitStatus status = table->instanceWaitAny(instance, 1, &wait, UINT64_MAX);
    table->adapterRelease(adapter.handle);
    if (status != WGPUWaitStatus_Success || device.status != WGPURequestDeviceStatus_Success ||
        !device.handle) return 3;
    *device_out = device.handle;
    return 0;
}

void doeExternalContextRelease(const DawnProcTable* table,
    WGPUInstance instance, WGPUDevice device) {
    if (device) {
        table->deviceDestroy(device);
        table->deviceRelease(device);
    }
    if (instance) table->instanceRelease(instance);
}

/* The deliberately blocked callback establishes that WaitAny cannot retire its
 * caller-owned data while delivery is still in progress. */
#include <pthread.h>
typedef struct PipelineControl {
    pthread_mutex_t mutex;
    pthread_cond_t condition;
    int entered;
    int release;
    int returned;
    WGPUCreatePipelineAsyncStatus status;
    WGPUComputePipeline pipeline;
} PipelineControl;

static void pipeline_ready(WGPUCreatePipelineAsyncStatus status,
    WGPUComputePipeline pipeline, WGPUStringView message, void* out, void* unused) {
    (void)message;
    (void)unused;
    PipelineControl* control = out;
    pthread_mutex_lock(&control->mutex);
    control->status = status;
    control->pipeline = pipeline;
    control->entered = 1;
    pthread_cond_broadcast(&control->condition);
    while (!control->release) pthread_cond_wait(&control->condition, &control->mutex);
    control->returned = 1;
    pthread_cond_broadcast(&control->condition);
    pthread_mutex_unlock(&control->mutex);
}

int doeExternalFutureControl(const DawnProcTable* table,
    WGPUInstance instance, WGPUDevice device) {
    PipelineControl control = {0};
    pthread_mutex_init(&control.mutex, NULL);
    pthread_cond_init(&control.condition, NULL);
    WGPUShaderSourceWGSL wgsl = {0};
    wgsl.chain.sType = WGPUSType_ShaderSourceWGSL;
    wgsl.code = (WGPUStringView){"@compute @workgroup_size(1) fn main() {}", WGPU_STRLEN};
    WGPUShaderModuleDescriptor shader_descriptor = {0};
    shader_descriptor.nextInChain = &wgsl.chain;
    WGPUShaderModule shader = table->deviceCreateShaderModule(device, &shader_descriptor);
    WGPUComputePipelineDescriptor descriptor = {0};
    descriptor.compute.module = shader;
    descriptor.compute.entryPoint = (WGPUStringView){"main", WGPU_STRLEN};
    WGPUCreateComputePipelineAsyncCallbackInfo callback = {0};
    callback.mode = WGPUCallbackMode_AllowSpontaneous;
    callback.callback = pipeline_ready;
    callback.userdata1 = &control;
    WGPUFutureWaitInfo wait = {0};
    wait.future = table->deviceCreateComputePipelineAsync(device, &descriptor, callback);
    pthread_mutex_lock(&control.mutex);
    while (!control.entered) pthread_cond_wait(&control.condition, &control.mutex);
    pthread_mutex_unlock(&control.mutex);
    WGPUWaitStatus pending = table->instanceWaitAny(instance, 1, &wait, 0);
    int premature = pending != WGPUWaitStatus_TimedOut || wait.completed;
    pthread_mutex_lock(&control.mutex);
    control.release = 1;
    pthread_cond_broadcast(&control.condition);
    pthread_mutex_unlock(&control.mutex);
    WGPUWaitStatus settled = table->instanceWaitAny(instance, 1, &wait, UINT64_MAX);
    pthread_mutex_lock(&control.mutex);
    while (!control.returned) pthread_cond_wait(&control.condition, &control.mutex);
    pthread_mutex_unlock(&control.mutex);
    int failed = premature || settled != WGPUWaitStatus_Success || !wait.completed ||
        control.status != WGPUCreatePipelineAsyncStatus_Success || !control.pipeline;
    if (control.pipeline) table->computePipelineRelease(control.pipeline);
    table->shaderModuleRelease(shader);
    pthread_cond_destroy(&control.condition);
    pthread_mutex_destroy(&control.mutex);
    return failed;
}
