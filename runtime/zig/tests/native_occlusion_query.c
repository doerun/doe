#include "webgpu.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { WIDTH = 8, ROW_BYTES = 256, QUERY_BYTES = 256, READBACK_BYTES = QUERY_BYTES + WIDTH * ROW_BYTES };
static void adapter_ready(WGPURequestAdapterStatus s, WGPUAdapter a, WGPUStringView m, void *p, void *u) {
    (void)m; (void)u; if (s == WGPURequestAdapterStatus_Success) *(WGPUAdapter *)p = a;
}
static void device_ready(WGPURequestDeviceStatus s, WGPUDevice d, WGPUStringView m, void *p, void *u) {
    (void)m; (void)u; if (s == WGPURequestDeviceStatus_Success) *(WGPUDevice *)p = d;
}
static void map_ready(WGPUMapAsyncStatus s, WGPUStringView m, void *p, void *u) {
    (void)m; (void)u; *(bool *)p = s == WGPUMapAsyncStatus_Success;
}
static unsigned errors;
static void error_seen(WGPUDevice const *d, WGPUErrorType t, WGPUStringView m, void *p, void *u) {
    (void)d; (void)p; (void)u; ++errors;
    fprintf(stderr, "device error %u: %.*s\n", t, (int)m.length, m.data);
}
static WGPUStringView text(const char *s) { return (WGPUStringView){s, strlen(s)}; }

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "direct";
    const bool indexed = strcmp(mode, "indexed16") == 0 || strcmp(mode, "indexed32") == 0 || strcmp(mode, "indexed-indirect") == 0;
    const bool indirect = strcmp(mode, "indirect") == 0 || strcmp(mode, "indexed-indirect") == 0;
    const bool index16 = strcmp(mode, "indexed16") == 0;
    if (!indexed && !indirect && strcmp(mode, "direct") != 0) return 2;
    printf("mode=%s\n", mode);
    WGPUInstance instance = wgpuCreateInstance(NULL);
    WGPUAdapter adapter = NULL;
    WGPUDevice device = NULL;
    WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    options.backendType = WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo ac = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    ac.mode = WGPUCallbackMode_AllowSpontaneous; ac.callback = adapter_ready; ac.userdata1 = &adapter;
    wgpuInstanceRequestAdapter(instance, &options, ac); wgpuInstanceProcessEvents(instance);
    if (!adapter) return 1;
    WGPUAdapterInfo info = WGPU_ADAPTER_INFO_INIT;
    if (wgpuAdapterGetInfo(adapter, &info) != WGPUStatus_Success || info.adapterType == WGPUAdapterType_CPU) return 1;
    printf("adapter=%.*s driver=%.*s\n", (int)info.device.length, info.device.data, (int)info.description.length, info.description.data);
    wgpuAdapterInfoFreeMembers(info);
    WGPUDeviceDescriptor dd = WGPU_DEVICE_DESCRIPTOR_INIT;
    dd.uncapturedErrorCallbackInfo.callback = error_seen;
    WGPURequestDeviceCallbackInfo dc = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    dc.mode = WGPUCallbackMode_AllowSpontaneous; dc.callback = device_ready; dc.userdata1 = &device;
    wgpuAdapterRequestDevice(adapter, &dd, dc); wgpuInstanceProcessEvents(instance);
    if (!device) return 1;
    WGPUQueue queue = wgpuDeviceGetQueue(device);
    const char *wgsl =
        "@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {"
        "var p = array<vec2f,3>(vec2f(-1,-1),vec2f(3,-1),vec2f(-1,3)); return vec4f(p[i],0,1); }"
        "@fragment fn fs() -> @location(0) vec4f { return vec4f(1,0,0,1); }";
    WGPUShaderSourceWGSL source = WGPU_SHADER_SOURCE_WGSL_INIT; source.code = text(wgsl);
    WGPUShaderModuleDescriptor sd = WGPU_SHADER_MODULE_DESCRIPTOR_INIT; sd.nextInChain = &source.chain;
    WGPUShaderModule shader = wgpuDeviceCreateShaderModule(device, &sd);
    WGPUColorTargetState color = WGPU_COLOR_TARGET_STATE_INIT; color.format = WGPUTextureFormat_RGBA8Unorm;
    WGPUFragmentState fragment = WGPU_FRAGMENT_STATE_INIT;
    fragment.module = shader; fragment.entryPoint = text("fs"); fragment.targetCount = 1; fragment.targets = &color;
    WGPURenderPipelineDescriptor pd = WGPU_RENDER_PIPELINE_DESCRIPTOR_INIT;
    pd.vertex.module = shader; pd.vertex.entryPoint = text("vs"); pd.fragment = &fragment;
    WGPURenderPipeline pipeline = wgpuDeviceCreateRenderPipeline(device, &pd);
    WGPUTextureDescriptor td = WGPU_TEXTURE_DESCRIPTOR_INIT;
    td.dimension = WGPUTextureDimension_2D; td.size = (WGPUExtent3D){WIDTH, WIDTH, 1}; td.format = color.format;
    td.usage = WGPUTextureUsage_RenderAttachment | WGPUTextureUsage_CopySrc;
    WGPUTexture texture = wgpuDeviceCreateTexture(device, &td);
    WGPUTextureView view = wgpuTextureCreateView(texture, NULL);
    WGPUQuerySetDescriptor qd = WGPU_QUERY_SET_DESCRIPTOR_INIT; qd.type = WGPUQueryType_Occlusion; qd.count = 4;
    WGPUQuerySet queries = wgpuDeviceCreateQuerySet(device, &qd);
    WGPUBufferDescriptor bd = WGPU_BUFFER_DESCRIPTOR_INIT;
    bd.size = QUERY_BYTES; bd.usage = WGPUBufferUsage_QueryResolve | WGPUBufferUsage_CopySrc;
    WGPUBuffer resolved = wgpuDeviceCreateBuffer(device, &bd);
    bd.size = READBACK_BYTES; bd.usage = WGPUBufferUsage_MapRead | WGPUBufferUsage_CopyDst;
    WGPUBuffer readback = wgpuDeviceCreateBuffer(device, &bd);
    if (!pipeline || !view || !queries || !resolved || !readback) { fprintf(stderr, "creation failed: pipeline=%p view=%p queries=%p resolved=%p readback=%p\n", (void*)pipeline,(void*)view,(void*)queries,(void*)resolved,(void*)readback); return 1; }
    WGPUBuffer index_buffer = NULL;
    WGPUBuffer indirect_buffer = NULL;
    const uint16_t indices16[] = {999, 999, 0, 1, 2};
    const uint32_t indices32[] = {999, 999, 0, 1, 2};
    const size_t index_bytes = index16 ? sizeof(indices16) : sizeof(indices32);
    const size_t index_offset = index16 ? sizeof(uint16_t) : sizeof(uint32_t);
    bd.mappedAtCreation = WGPU_TRUE;
    if (indexed) {
        bd.size = (index_bytes + 3) & ~(size_t)3; bd.usage = WGPUBufferUsage_Index;
        index_buffer = wgpuDeviceCreateBuffer(device, &bd);
        void *mapped = wgpuBufferGetMappedRange(index_buffer, 0, bd.size);
        if (!mapped) return 1;
        memcpy(mapped, index16 ? (const void *)indices16 : (const void *)indices32, index_bytes);
        wgpuBufferUnmap(index_buffer);
    }
    if (indirect) {
        const uint32_t args[] = {3, 1, indexed ? 1 : 0, 0, 0};
        bd.size = sizeof(args); bd.usage = WGPUBufferUsage_Indirect;
        indirect_buffer = wgpuDeviceCreateBuffer(device, &bd);
        void *mapped = wgpuBufferGetMappedRange(indirect_buffer, 0, bd.size);
        if (!mapped) return 1;
        memcpy(mapped, args, sizeof(args));
        wgpuBufferUnmap(indirect_buffer);
    }
    bool passed = true;
    // Reuse the same queries. Empty queries in the next submission must erase
    // previous visibility; a later visible submission must work again.
    for (unsigned round = 0; round < 3; ++round) {
        const bool draw = round != 1;
        WGPUCommandEncoder enc = wgpuDeviceCreateCommandEncoder(device, NULL);
        WGPURenderPassColorAttachment attachment = WGPU_RENDER_PASS_COLOR_ATTACHMENT_INIT;
        attachment.view = view; attachment.loadOp = WGPULoadOp_Clear; attachment.storeOp = WGPUStoreOp_Store;
        attachment.clearValue = (WGPUColor){0,0,0,1};
        WGPURenderPassDescriptor rd = WGPU_RENDER_PASS_DESCRIPTOR_INIT;
        rd.colorAttachmentCount = 1; rd.colorAttachments = &attachment; rd.occlusionQuerySet = queries;
        WGPURenderPassEncoder pass = wgpuCommandEncoderBeginRenderPass(enc, &rd);
        wgpuRenderPassEncoderSetPipeline(pass, pipeline);
        if (indexed) wgpuRenderPassEncoderSetIndexBuffer(pass, index_buffer,
            index16 ? WGPUIndexFormat_Uint16 : WGPUIndexFormat_Uint32, index_offset, index_bytes - index_offset);
        for (unsigned query = 0; query < 3; ++query) {
            wgpuRenderPassEncoderBeginOcclusionQuery(pass, query);
            if (draw) {
                // q0: visible then invisible; q1: invisible then visible;
                // q2: both invisible. q3 has never been written.
                for (unsigned part = 0; part < 2; ++part) {
                    const bool visible = query < 2 && query == part;
                    wgpuRenderPassEncoderSetScissorRect(pass, 0, 0, visible ? WIDTH : 0, WIDTH);
                    if (indexed && indirect) wgpuRenderPassEncoderDrawIndexedIndirect(pass, indirect_buffer, 0);
                    else if (indirect) wgpuRenderPassEncoderDrawIndirect(pass, indirect_buffer, 0);
                    else if (indexed) wgpuRenderPassEncoderDrawIndexed(pass, 3, 1, 1, 0, 0);
                    else wgpuRenderPassEncoderDraw(pass, 3, 1, 0, 0);
                }
            }
            wgpuRenderPassEncoderEndOcclusionQuery(pass);
        }
        wgpuRenderPassEncoderEnd(pass); wgpuRenderPassEncoderRelease(pass);
        wgpuCommandEncoderResolveQuerySet(enc, queries, 0, 4, resolved, 0);
        wgpuCommandEncoderCopyBufferToBuffer(enc, resolved, 0, readback, 0, 4 * sizeof(uint64_t));
        // Re-resolve to the same target after the first copy, preserving its snapshot.
        wgpuCommandEncoderResolveQuerySet(enc, queries, 0, 4, resolved, 0);
        wgpuCommandEncoderCopyBufferToBuffer(enc, resolved, 0, readback, 32, 4 * sizeof(uint64_t));
        WGPUTexelCopyTextureInfo src = WGPU_TEXEL_COPY_TEXTURE_INFO_INIT; src.texture = texture;
        WGPUTexelCopyBufferInfo dst = WGPU_TEXEL_COPY_BUFFER_INFO_INIT;
        dst.buffer = readback; dst.layout.offset = QUERY_BYTES; dst.layout.bytesPerRow = ROW_BYTES; dst.layout.rowsPerImage = WIDTH;
        WGPUExtent3D extent = {WIDTH, WIDTH, 1}; wgpuCommandEncoderCopyTextureToBuffer(enc, &src, &dst, &extent);
        WGPUCommandBuffer command = wgpuCommandEncoderFinish(enc, NULL); wgpuCommandEncoderRelease(enc);
        if (round == 2) {
            wgpuQuerySetRelease(queries); queries = NULL;
            if (index_buffer) { wgpuBufferRelease(index_buffer); index_buffer = NULL; }
            if (indirect_buffer) { wgpuBufferRelease(indirect_buffer); indirect_buffer = NULL; }
        }
        wgpuQueueSubmit(queue, 1, &command); wgpuCommandBufferRelease(command);
        bool mapped = false;
        WGPUBufferMapCallbackInfo mc = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
        mc.mode = WGPUCallbackMode_AllowSpontaneous; mc.callback = map_ready; mc.userdata1 = &mapped;
        wgpuBufferMapAsync(readback, WGPUMapMode_Read, 0, READBACK_BYTES, mc); wgpuInstanceProcessEvents(instance);
        const uint8_t *bytes = wgpuBufferGetConstMappedRange(readback, 0, READBACK_BYTES);
        if (!mapped || !bytes) return 1;
        const uint64_t *result = (const uint64_t *)bytes;
        for (unsigned i = 0; i < 8; ++i) if ((result[i] != 0) != (draw && i % 4 < 2)) passed = false;
        for (unsigned y = 0; y < WIDTH; ++y) for (unsigned x = 0; x < WIDTH; ++x) {
            const uint8_t *pixel = bytes + QUERY_BYTES + y * ROW_BYTES + x * 4;
            if (pixel[0] != (draw ? 255 : 0) || pixel[1] || pixel[2] || pixel[3] != 255) passed = false;
        }
        printf("round=%u query=[%llu,%llu,%llu,%llu] query_and_pixel_oracles=%s\n", round,
            (unsigned long long)result[0], (unsigned long long)result[1], (unsigned long long)result[2], (unsigned long long)result[3], passed ? "pass" : "FAIL");
        wgpuBufferUnmap(readback);
    }
    wgpuBufferRelease(readback); wgpuBufferRelease(resolved); if (queries) wgpuQuerySetRelease(queries);
    wgpuTextureViewRelease(view); wgpuTextureRelease(texture); wgpuRenderPipelineRelease(pipeline); wgpuShaderModuleRelease(shader);
    wgpuQueueRelease(queue); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter); wgpuInstanceRelease(instance);
    return passed && errors == 0 ? 0 : 1;
}
