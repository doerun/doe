#define _GNU_SOURCE
#include "webgpu.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <time.h>

enum { DISPATCHES = 32, WARMUPS = 256, SAMPLES = 2048, BUFFER_BYTES = 256 };
static double now(clockid_t clock) {
    struct timespec t;
    assert(clock_gettime(clock, &t) == 0);
    return (double)t.tv_sec * 1000.0 + (double)t.tv_nsec / 1000000.0;
}
static void adapter_ready(WGPURequestAdapterStatus status, WGPUAdapter adapter,
    WGPUStringView message, void* out, void* unused) {
    (void)message; (void)unused;
    assert(status == WGPURequestAdapterStatus_Success);
    *(WGPUAdapter*)out = adapter;
}
static void device_ready(WGPURequestDeviceStatus status, WGPUDevice device,
    WGPUStringView message, void* out, void* unused) {
    (void)message; (void)unused;
    assert(status == WGPURequestDeviceStatus_Success);
    *(WGPUDevice*)out = device;
}
static void map_ready(WGPUMapAsyncStatus status, WGPUStringView message, void* out, void* unused) {
    (void)message; (void)unused;
    assert(status == WGPUMapAsyncStatus_Success);
    *(bool*)out = true;
}
int main(void) {
    Dl_info identity;
    assert(dladdr((void*)&wgpuCreateInstance, &identity));
    fprintf(stderr, "native-library: %s\n", identity.dli_fname);
    WGPUInstance instance = wgpuCreateInstance(NULL);
    WGPUAdapter adapter = NULL;
    WGPUDevice device = NULL;
    WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    options.backendType = WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo ac = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    ac.mode = WGPUCallbackMode_AllowSpontaneous;
    ac.callback = adapter_ready; ac.userdata1 = &adapter;
    wgpuInstanceRequestAdapter(instance, &options, ac);
    wgpuInstanceProcessEvents(instance); assert(adapter);
    WGPURequestDeviceCallbackInfo dc = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    dc.mode = WGPUCallbackMode_AllowSpontaneous;
    dc.callback = device_ready; dc.userdata1 = &device;
    wgpuAdapterRequestDevice(adapter, NULL, dc);
    wgpuInstanceProcessEvents(instance); assert(device);
    WGPUShaderSourceWGSL source = WGPU_SHADER_SOURCE_WGSL_INIT;
    source.code = (WGPUStringView){
        "@group(0) @binding(0) var<storage,read_write> values:array<u32>;"
        "@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) i:vec3u) {"
        "values[i.x] = values[i.x] + 1u; }", WGPU_STRLEN };
    WGPUShaderModuleDescriptor sd = WGPU_SHADER_MODULE_DESCRIPTOR_INIT;
    sd.nextInChain = &source.chain;
    WGPUShaderModule shader = wgpuDeviceCreateShaderModule(device, &sd); assert(shader);
    WGPUComputePipelineDescriptor pd = WGPU_COMPUTE_PIPELINE_DESCRIPTOR_INIT;
    pd.compute.module = shader;
    pd.compute.entryPoint = (WGPUStringView){"main", WGPU_STRLEN};
    WGPUComputePipeline pipeline = wgpuDeviceCreateComputePipeline(device, &pd); assert(pipeline);
    WGPUBindGroupLayout layout = wgpuComputePipelineGetBindGroupLayout(pipeline, 0); assert(layout);
    WGPUBuffer buffers[2]; WGPUBindGroup groups[2];
    for (unsigned i = 0; i < 2; i++) {
        WGPUBufferDescriptor bd = WGPU_BUFFER_DESCRIPTOR_INIT;
        bd.size = BUFFER_BYTES; bd.usage = WGPUBufferUsage_Storage | WGPUBufferUsage_CopySrc | WGPUBufferUsage_CopyDst;
        buffers[i] = wgpuDeviceCreateBuffer(device, &bd); assert(buffers[i]);
        WGPUBindGroupEntry entry = WGPU_BIND_GROUP_ENTRY_INIT;
        entry.buffer = buffers[i]; entry.size = BUFFER_BYTES;
        WGPUBindGroupDescriptor gd = WGPU_BIND_GROUP_DESCRIPTOR_INIT;
        gd.layout = layout; gd.entryCount = 1; gd.entries = &entry;
        groups[i] = wgpuDeviceCreateBindGroup(device, &gd); assert(groups[i]);
    }
    puts("sample\trecordWallMs\trecordCpuMs\tfinishAndCleanupMs");
    for (unsigned sample = 0; sample < WARMUPS + SAMPLES; sample++) {
        double cpu = now(CLOCK_PROCESS_CPUTIME_ID), start = now(CLOCK_MONOTONIC);
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL); assert(encoder);
        WGPUComputePassEncoder pass = wgpuCommandEncoderBeginComputePass(encoder, NULL); assert(pass);
        wgpuComputePassEncoderSetPipeline(pass, pipeline);
        for (unsigned dispatch = 0; dispatch < DISPATCHES; dispatch++) {
            wgpuComputePassEncoderSetBindGroup(pass, 0, groups[dispatch % 2], 0, NULL);
            wgpuComputePassEncoderDispatchWorkgroups(pass, BUFFER_BYTES / sizeof(uint32_t), 1, 1);
        }
        wgpuComputePassEncoderEnd(pass);
        double record = now(CLOCK_MONOTONIC) - start, record_cpu = now(CLOCK_PROCESS_CPUTIME_ID) - cpu;
        start = now(CLOCK_MONOTONIC);
        wgpuComputePassEncoderRelease(pass);
        WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL); assert(commands);
        wgpuCommandEncoderRelease(encoder);
        wgpuCommandBufferRelease(commands);
        double cleanup = now(CLOCK_MONOTONIC) - start;
        if (sample >= WARMUPS) printf("%u\t%.9f\t%.9f\t%.9f\n", sample-WARMUPS, record, record_cpu, cleanup);
    }
    WGPUQueue queue = wgpuDeviceGetQueue(device); assert(queue);
    const uint32_t zeros[BUFFER_BYTES / sizeof(uint32_t)] = {0};
    for (unsigned i = 0; i < 2; i++) wgpuQueueWriteBuffer(queue, buffers[i], 0, zeros, sizeof(zeros));
    WGPUBufferDescriptor readback_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    readback_desc.size = 2 * BUFFER_BYTES;
    readback_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_MapRead;
    WGPUBuffer readback = wgpuDeviceCreateBuffer(device, &readback_desc); assert(readback);
    WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL); assert(encoder);
    WGPUComputePassEncoder pass = wgpuCommandEncoderBeginComputePass(encoder, NULL); assert(pass);
    wgpuComputePassEncoderSetPipeline(pass, pipeline);
    for (unsigned dispatch = 0; dispatch < DISPATCHES; dispatch++) {
        wgpuComputePassEncoderSetBindGroup(pass, 0, groups[dispatch % 2], 0, NULL);
        wgpuComputePassEncoderDispatchWorkgroups(pass, BUFFER_BYTES / sizeof(uint32_t), 1, 1);
    }
    wgpuComputePassEncoderEnd(pass); wgpuComputePassEncoderRelease(pass);
    for (unsigned i = 0; i < 2; i++)
        wgpuCommandEncoderCopyBufferToBuffer(encoder, buffers[i], 0, readback, i * BUFFER_BYTES, BUFFER_BYTES);
    WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL); assert(commands);
    wgpuCommandEncoderRelease(encoder);
    wgpuQueueSubmit(queue, 1, &commands); wgpuCommandBufferRelease(commands);
    bool mapped = false;
    WGPUBufferMapCallbackInfo callback = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowSpontaneous;
    callback.callback = map_ready; callback.userdata1 = &mapped;
    wgpuBufferMapAsync(readback, WGPUMapMode_Read, 0, 2 * BUFFER_BYTES, callback);
    wgpuInstanceProcessEvents(instance); assert(mapped);
    const uint32_t* output = wgpuBufferGetConstMappedRange(readback, 0, 2 * BUFFER_BYTES); assert(output);
    for (unsigned i = 0; i < 2 * BUFFER_BYTES / sizeof(uint32_t); i++) assert(output[i] == DISPATCHES / 2);
    wgpuBufferUnmap(readback); wgpuBufferRelease(readback); wgpuQueueRelease(queue);
    fputs("PASS: untimed GPU check confirms every alternating dispatch and integer output.\n", stderr);
    for (unsigned i = 0; i < 2; i++) { wgpuBindGroupRelease(groups[i]); wgpuBufferRelease(buffers[i]); }
    wgpuBindGroupLayoutRelease(layout); wgpuComputePipelineRelease(pipeline);
    wgpuShaderModuleRelease(shader); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter);
    wgpuInstanceRelease(instance);
    fputs("Timed region records CPU commands only; untimed GPU oracle passes; no application speed claim.\n", stderr);
}
