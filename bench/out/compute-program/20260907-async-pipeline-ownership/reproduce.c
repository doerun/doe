#define _POSIX_C_SOURCE 200809L
#include "webgpu.h"
#include <assert.h>
#include <dirent.h>
#include <string.h>
#include <stdatomic.h>
#include <stdio.h>
#include <time.h>
static atomic_int finished;
static void adapter_ready(WGPURequestAdapterStatus status, WGPUAdapter adapter, WGPUStringView message, void* out, void* unused) {
    (void)message; (void)unused; assert(status == WGPURequestAdapterStatus_Success); *(WGPUAdapter*)out = adapter;
}
static void device_ready(WGPURequestDeviceStatus status, WGPUDevice device, WGPUStringView message, void* out, void* unused) {
    (void)message; (void)unused; assert(status == WGPURequestDeviceStatus_Success); *(WGPUDevice*)out = device;
}
static void pipeline_ready(WGPUCreatePipelineAsyncStatus status, WGPURenderPipeline pipeline, WGPUStringView message, void* a, void* b) {
    (void)a; (void)b;
    fprintf(stderr, "callback status=%u pipeline=%p message=%.*s\n", status, (void*)pipeline, (int)message.length, message.data);
    assert(status == WGPUCreatePipelineAsyncStatus_Success && pipeline);
    wgpuRenderPipelineRelease(pipeline);
    atomic_fetch_add(&finished, 1);
}
int main(void) {
    WGPUInstance instance = wgpuCreateInstance(NULL);
    WGPUAdapter adapter = NULL; WGPUDevice device = NULL;
    WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    options.backendType = WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo ac = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    ac.mode = WGPUCallbackMode_AllowSpontaneous; ac.callback = adapter_ready; ac.userdata1 = &adapter;
    wgpuInstanceRequestAdapter(instance, &options, ac); wgpuInstanceProcessEvents(instance); assert(adapter);
    WGPURequestDeviceCallbackInfo dc = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    dc.mode = WGPUCallbackMode_AllowSpontaneous; dc.callback = device_ready; dc.userdata1 = &device;
    wgpuAdapterRequestDevice(adapter, NULL, dc); wgpuInstanceProcessEvents(instance); assert(device);
    WGPUShaderSourceWGSL source = WGPU_SHADER_SOURCE_WGSL_INIT;
    source.code = (WGPUStringView){"@vertex fn vs(@builtin(vertex_index) v:u32)->@builtin(position) vec4f { return vec4f(f32(v),0.0,0.0,1.0); } @fragment fn fs()->@location(0) vec4f { return vec4f(1.0); }", WGPU_STRLEN};
    WGPUShaderModuleDescriptor sd = WGPU_SHADER_MODULE_DESCRIPTOR_INIT; sd.nextInChain = &source.chain;
    WGPUShaderModule shader = wgpuDeviceCreateShaderModule(device, &sd); assert(shader);
    WGPUColorTargetState color = WGPU_COLOR_TARGET_STATE_INIT; color.format = WGPUTextureFormat_RGBA8Unorm;
    WGPUFragmentState fragment = WGPU_FRAGMENT_STATE_INIT; fragment.module = shader; fragment.entryPoint = (WGPUStringView){"fs",2}; fragment.targetCount=1; fragment.targets=&color;
    WGPURenderPipelineDescriptor desc = WGPU_RENDER_PIPELINE_DESCRIPTOR_INIT; desc.vertex.module=shader; desc.vertex.entryPoint=(WGPUStringView){"vs",2}; desc.fragment=&fragment;
    WGPUCreateRenderPipelineAsyncCallbackInfo cb = WGPU_CREATE_RENDER_PIPELINE_ASYNC_CALLBACK_INFO_INIT;
    cb.mode=WGPUCallbackMode_AllowSpontaneous; cb.callback=pipeline_ready;
    wgpuDeviceCreateRenderPipelineAsync(device,&desc,cb);
    wgpuShaderModuleRelease(shader);
    struct timespec delay={.tv_nsec=10000000};
    for (int i=0;i<1000 && !atomic_load(&finished);i++) nanosleep(&delay,NULL);
    assert(atomic_load(&finished)==1);
    for (int i=0;i<10;i++) nanosleep(&delay,NULL);
    wgpuDeviceDestroy(device); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter); wgpuInstanceRelease(instance);
    DIR* fds = opendir("/proc/self/fdinfo"); assert(fds);
    struct dirent* entry; char path[512], line[512]; int drm = 0;
    while ((entry = readdir(fds))) {
        snprintf(path, sizeof(path), "/proc/self/fdinfo/%s", entry->d_name);
        FILE* file = fopen(path, "r"); if (!file) continue;
        while (fgets(line, sizeof(line), file)) if (strstr(line, "drm-client-id:")) drm++;
        fclose(file);
    }
    closedir(fds); fprintf(stderr, "remaining DRM descriptors=%d\n", drm); assert(drm == 0);
    puts("PASS: asynchronous render callback and final cleanup");
}
