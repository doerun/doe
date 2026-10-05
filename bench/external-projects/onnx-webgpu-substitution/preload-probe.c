/* Observe whether the unchanged native WebGPU EP reaches external WebGPU symbols. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <webgpu.h>

static _Atomic uint64_t instance_calls;
static _Atomic uint64_t shader_calls;
static _Atomic uint64_t submission_calls;

uint64_t doeProbeInstanceCalls(void) { return atomic_load(&instance_calls); }
uint64_t doeProbeShaderCalls(void) { return atomic_load(&shader_calls); }
uint64_t doeProbeSubmissionCalls(void) { return atomic_load(&submission_calls); }

WGPUInstance wgpuCreateInstance(const WGPUInstanceDescriptor* descriptor) {
    instance_calls++;
    WGPUProcCreateInstance next = (WGPUProcCreateInstance)dlsym(RTLD_NEXT, "wgpuCreateInstance");
    if (!next) abort();
    return next(descriptor);
}

WGPUShaderModule wgpuDeviceCreateShaderModule(WGPUDevice device,
                                             const WGPUShaderModuleDescriptor* descriptor) {
    shader_calls++;
    WGPUProcDeviceCreateShaderModule next =
        (WGPUProcDeviceCreateShaderModule)dlsym(RTLD_NEXT, "wgpuDeviceCreateShaderModule");
    if (!next) abort();
    return next(device, descriptor);
}

void wgpuQueueSubmit(WGPUQueue queue, size_t count, const WGPUCommandBuffer* commands) {
    submission_calls++;
    WGPUProcQueueSubmit next = (WGPUProcQueueSubmit)dlsym(RTLD_NEXT, "wgpuQueueSubmit");
    if (!next) abort();
    next(queue, count, commands);
}
