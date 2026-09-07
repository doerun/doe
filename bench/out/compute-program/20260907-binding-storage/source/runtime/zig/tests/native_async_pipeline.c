#define _POSIX_C_SOURCE 200809L
#include "webgpu.h"
#include <assert.h>
#include <dirent.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

enum {
    PIPELINE_REQUESTS = 32,
    VALIDATION_REQUESTS = 2,
    CALLBACK_DEADLINE_POLLS = 1000,
    CLEANUP_DEADLINE_POLLS = 100,
    POLL_NS = 10000000,
};
static atomic_int finished;
static atomic_int rejected;

static void adapter_ready(WGPURequestAdapterStatus status, WGPUAdapter adapter,
    WGPUStringView message, void* out, void* unused) {
    (void)message;
    (void)unused;
    assert(status == WGPURequestAdapterStatus_Success);
    *(WGPUAdapter*)out = adapter;
}

static void device_ready(WGPURequestDeviceStatus status, WGPUDevice device,
    WGPUStringView message, void* out, void* unused) {
    (void)message;
    (void)unused;
    assert(status == WGPURequestDeviceStatus_Success);
    *(WGPUDevice*)out = device;
}

static void pipeline_ready(WGPUCreatePipelineAsyncStatus status, WGPURenderPipeline pipeline,
    WGPUStringView message, void* unused1, void* unused2) {
    (void)unused1;
    (void)unused2;
    if (status != WGPUCreatePipelineAsyncStatus_Success) {
        fprintf(stderr, "pipeline failure: status=%u message=%.*s\n",
            status, (int)message.length, message.data);
    }
    assert(status == WGPUCreatePipelineAsyncStatus_Success && pipeline);
    wgpuRenderPipelineRelease(pipeline);
    atomic_fetch_add(&finished, 1);
}

static void pipeline_rejected(WGPUCreatePipelineAsyncStatus status, WGPURenderPipeline pipeline,
    WGPUStringView message, void* unused1, void* unused2) {
    (void)unused1;
    (void)unused2;
    assert(status == WGPUCreatePipelineAsyncStatus_ValidationError && !pipeline);
    assert(message.data && message.length);
    atomic_fetch_add(&rejected, 1);
}

static unsigned drm_descriptors(void) {
    DIR* fds = opendir("/proc/self/fdinfo");
    assert(fds);
    struct dirent* entry;
    char path[512], line[512];
    unsigned drm = 0;
    while ((entry = readdir(fds))) {
        snprintf(path, sizeof(path), "/proc/self/fdinfo/%s", entry->d_name);
        FILE* file = fopen(path, "r");
        if (!file) continue;
        while (fgets(line, sizeof(line), file)) {
            if (strstr(line, "drm-client-id:")) drm++;
        }
        fclose(file);
    }
    closedir(fds);
    return drm;
}

int main(void) {
    const unsigned initial_drm = drm_descriptors();
    const struct timespec pause = { .tv_nsec = POLL_NS };
    WGPUInstance instance = wgpuCreateInstance(NULL);
    WGPUAdapter adapter = NULL;
    WGPUDevice device = NULL;
    WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    options.backendType = WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo ac = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    ac.mode = WGPUCallbackMode_AllowSpontaneous;
    ac.callback = adapter_ready;
    ac.userdata1 = &adapter;
    wgpuInstanceRequestAdapter(instance, &options, ac);
    wgpuInstanceProcessEvents(instance);
    assert(adapter);
    WGPURequestDeviceCallbackInfo dc = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    dc.mode = WGPUCallbackMode_AllowSpontaneous;
    dc.callback = device_ready;
    dc.userdata1 = &device;
    wgpuAdapterRequestDevice(adapter, NULL, dc);
    wgpuInstanceProcessEvents(instance);
    assert(device);
    WGPUShaderSourceWGSL source = WGPU_SHADER_SOURCE_WGSL_INIT;
    source.code = (WGPUStringView){
        "@vertex fn vs(@builtin(vertex_index) v:u32)->@builtin(position) vec4f {"
        "return vec4f(f32(v),0.0,0.0,1.0); }"
        "@fragment fn fs()->@location(0) vec4f { return vec4f(1.0); }", WGPU_STRLEN,
    };
    WGPUShaderModuleDescriptor sd = WGPU_SHADER_MODULE_DESCRIPTOR_INIT;
    sd.nextInChain = &source.chain;
    WGPUShaderModule shader = wgpuDeviceCreateShaderModule(device, &sd);
    assert(shader);
    WGPUColorTargetState color = WGPU_COLOR_TARGET_STATE_INIT;
    color.format = WGPUTextureFormat_RGBA8Unorm;
    WGPUFragmentState fragment = WGPU_FRAGMENT_STATE_INIT;
    fragment.module = shader;
    fragment.entryPoint = (WGPUStringView){ "fs", WGPU_STRLEN };
    fragment.targetCount = 1;
    fragment.targets = &color;
    WGPURenderPipelineDescriptor desc = WGPU_RENDER_PIPELINE_DESCRIPTOR_INIT;
    desc.vertex.module = shader;
    desc.vertex.entryPoint = (WGPUStringView){ "vs", WGPU_STRLEN };
    desc.fragment = &fragment;
    WGPUCreateRenderPipelineAsyncCallbackInfo cb = WGPU_CREATE_RENDER_PIPELINE_ASYNC_CALLBACK_INFO_INIT;
    cb.mode = WGPUCallbackMode_AllowSpontaneous;
    cb.callback = pipeline_rejected;
    desc.vertex.constantCount = 1;
    wgpuDeviceCreateRenderPipelineAsync(device, &desc, cb);
    desc.vertex.constantCount = 0;
    WGPUChainedStruct unsupported = { .sType = WGPUSType_Force32 };
    desc.nextInChain = &unsupported;
    wgpuDeviceCreateRenderPipelineAsync(device, &desc, cb);
    desc.nextInChain = NULL;
    cb.callback = pipeline_ready;
    for (unsigned request = 0; request < PIPELINE_REQUESTS; request++) {
        wgpuDeviceCreateRenderPipelineAsync(device, &desc, cb);
    }
    wgpuShaderModuleRelease(shader);
    wgpuDeviceRelease(device);
    wgpuAdapterRelease(adapter);
    for (unsigned poll = 0; poll < CALLBACK_DEADLINE_POLLS; poll++) {
        wgpuInstanceProcessEvents(instance);
        if (atomic_load(&finished) == PIPELINE_REQUESTS &&
            atomic_load(&rejected) == VALIDATION_REQUESTS) break;
        nanosleep(&pause, NULL);
    }
    assert(atomic_load(&finished) == PIPELINE_REQUESTS);
    assert(atomic_load(&rejected) == VALIDATION_REQUESTS);
    wgpuInstanceRelease(instance);
    for (unsigned poll = 0; poll < CLEANUP_DEADLINE_POLLS; poll++) {
        if (drm_descriptors() == initial_drm) break;
        nanosleep(&pause, NULL);
    }
    assert(drm_descriptors() == initial_drm);
    puts("PASS: async validation, immediate callback release, shared requests, caller teardown, DRM cleanup");
}
