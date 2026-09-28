#include "webgpu.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { WIDTH = 8, ROW_BYTES = 256, READBACK_BYTES = WIDTH * ROW_BYTES };
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


static void scope_ready(WGPUPopErrorScopeStatus status, WGPUErrorType type, WGPUStringView message, void *p, void *u) {
    (void)u;
    *(bool *)p = status == WGPUPopErrorScopeStatus_Success && type == WGPUErrorType_Validation;
    fprintf(stderr, "scope type=%u message=%.*s\n", type, (int)message.length, message.data);
}
static bool validation(WGPUDevice device, WGPUInstance instance) {
    bool seen = false;
    WGPUPopErrorScopeCallbackInfo cb = WGPU_POP_ERROR_SCOPE_CALLBACK_INFO_INIT;
    cb.mode = WGPUCallbackMode_AllowSpontaneous; cb.callback = scope_ready; cb.userdata1 = &seen;
    wgpuDevicePopErrorScope(device, cb); wgpuInstanceProcessEvents(instance);
    return seen;
}
static void draw(WGPUCommandEncoder enc, WGPUTextureView view, WGPURenderPipeline pipeline, bool clear_only) {
    WGPURenderPassColorAttachment att = WGPU_RENDER_PASS_COLOR_ATTACHMENT_INIT;
    att.view = view; att.loadOp = WGPULoadOp_Clear; att.storeOp = WGPUStoreOp_Store;
    att.clearValue = (WGPUColor){0,0,1,1};
    WGPURenderPassDescriptor desc = WGPU_RENDER_PASS_DESCRIPTOR_INIT;
    desc.colorAttachmentCount = 1; desc.colorAttachments = &att;
    WGPURenderPassEncoder pass = wgpuCommandEncoderBeginRenderPass(enc, &desc);
    if (!clear_only) { wgpuRenderPassEncoderSetPipeline(pass, pipeline); wgpuRenderPassEncoderDraw(pass, 3, 1, 0, 0); }
    wgpuRenderPassEncoderEnd(pass); wgpuRenderPassEncoderRelease(pass);
}
static void submit(WGPUQueue queue, WGPUCommandEncoder enc) {
    WGPUCommandBuffer cb = wgpuCommandEncoderFinish(enc, NULL);
    wgpuQueueSubmit(queue, 1, &cb); wgpuCommandBufferRelease(cb); wgpuCommandEncoderRelease(enc);
}
static bool pixels(WGPUDevice dev, WGPUInstance instance, WGPUQueue queue, WGPUTexture tex, unsigned mip, unsigned layer, bool red) {
    WGPUBufferDescriptor bd = WGPU_BUFFER_DESCRIPTOR_INIT;
    bd.size = READBACK_BYTES; bd.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_MapRead;
    WGPUBuffer buffer = wgpuDeviceCreateBuffer(dev, &bd);
    WGPUCommandEncoder enc = wgpuDeviceCreateCommandEncoder(dev, NULL);
    WGPUTexelCopyTextureInfo src = WGPU_TEXEL_COPY_TEXTURE_INFO_INIT;
    src.texture = tex; src.mipLevel = mip; src.origin.z = layer;
    WGPUTexelCopyBufferInfo dst = WGPU_TEXEL_COPY_BUFFER_INFO_INIT;
    dst.buffer = buffer; dst.layout.bytesPerRow = ROW_BYTES; dst.layout.rowsPerImage = WIDTH;
    WGPUExtent3D size = {WIDTH, WIDTH, 1};
    wgpuCommandEncoderCopyTextureToBuffer(enc, &src, &dst, &size); submit(queue, enc);
    bool mapped = false;
    WGPUBufferMapCallbackInfo cb = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
    cb.mode = WGPUCallbackMode_AllowSpontaneous; cb.callback = map_ready; cb.userdata1 = &mapped;
    wgpuBufferMapAsync(buffer, WGPUMapMode_Read, 0, READBACK_BYTES, cb); wgpuInstanceProcessEvents(instance);
    const unsigned char *bytes = mapped ? wgpuBufferGetConstMappedRange(buffer, 0, READBACK_BYTES) : NULL;
    bool ok = bytes != NULL;
    for (unsigned y=0; bytes && y<WIDTH; ++y) for (unsigned x=0; x<WIDTH; ++x) {
        const unsigned char *p = bytes + y*ROW_BYTES + x*4;
        ok &= p[0] == (red ? 255 : 0) && p[1] == 0 && p[2] == (red ? 0 : 255) && p[3] == 255;
    }
    if (mapped) wgpuBufferUnmap(buffer);
    wgpuBufferRelease(buffer); return ok;
}

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "samples";
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

    WGPUCommandEncoder enc = wgpuDeviceCreateCommandEncoder(device, NULL);
    draw(enc, view, pipeline, true); submit(queue, enc);
    if (!pixels(device, instance, queue, texture, 0, 0, false)) return 1;
    WGPUDevice other = NULL;
    WGPUTexture test_texture = NULL, depth_texture = NULL;
    WGPUTextureView test_view = view, depth_view = NULL;
    WGPURenderPipeline test_pipeline = pipeline;
    WGPUDepthStencilState depth_state = WGPU_DEPTH_STENCIL_STATE_INIT;
    depth_state.format = WGPUTextureFormat_Depth32Float; depth_state.depthCompare = WGPUCompareFunction_Always;
    WGPUTextureViewDescriptor vd = WGPU_TEXTURE_VIEW_DESCRIPTOR_INIT;
    WGPURenderPassColorAttachment attachments[2] = {WGPU_RENDER_PASS_COLOR_ATTACHMENT_INIT, WGPU_RENDER_PASS_COLOR_ATTACHMENT_INIT};
    WGPURenderPassDepthStencilAttachment da = WGPU_RENDER_PASS_DEPTH_STENCIL_ATTACHMENT_INIT;
    da.depthLoadOp = WGPULoadOp_Clear; da.depthStoreOp = WGPUStoreOp_Store; da.depthClearValue = 1;
    WGPURenderPassDescriptor rd = WGPU_RENDER_PASS_DESCRIPTOR_INIT;
    const bool valid_mip = strcmp(mode,"valid-mip-layer") == 0;
    const bool valid_depth = strcmp(mode,"valid-depth") == 0;
    if (strcmp(mode,"samples") == 0) { pd.multisample.count = 4; test_pipeline = wgpuDeviceCreateRenderPipeline(device, &pd); }
    else if (strcmp(mode,"format") == 0) { color.format = WGPUTextureFormat_BGRA8Unorm; test_pipeline = wgpuDeviceCreateRenderPipeline(device, &pd); }
    else if (strcmp(mode,"foreign-pipeline") == 0) {
        dc.userdata1 = &other; wgpuAdapterRequestDevice(adapter, &dd, dc); wgpuInstanceProcessEvents(instance);
        WGPUShaderModule other_shader = wgpuDeviceCreateShaderModule(other, &sd);
        pd.vertex.module = other_shader; fragment.module = other_shader;
        test_pipeline = wgpuDeviceCreateRenderPipeline(other, &pd); wgpuShaderModuleRelease(other_shader);
    }
    else if (strcmp(mode,"depth-extent") == 0 || strcmp(mode,"depth-samples") == 0 || strcmp(mode,"depth-format") == 0 || valid_depth) {
        td.format = WGPUTextureFormat_Depth32Float; td.usage = WGPUTextureUsage_RenderAttachment;
        if (strcmp(mode,"depth-extent") == 0) td.size.width = WIDTH/2;
        if (strcmp(mode,"depth-samples") == 0) td.sampleCount = 4;
        depth_texture = wgpuDeviceCreateTexture(device, &td); depth_view = wgpuTextureCreateView(depth_texture, NULL);
        da.view = depth_view; rd.depthStencilAttachment = &da;
        if (strcmp(mode,"depth-format") == 0) depth_state.format = WGPUTextureFormat_Depth24Plus;
        pd.depthStencil = &depth_state; test_pipeline = wgpuDeviceCreateRenderPipeline(device, &pd);
    }
    else if (strcmp(mode,"usage") == 0 || strcmp(mode,"mips") == 0 || strcmp(mode,"layers") == 0 || strcmp(mode,"foreign-view") == 0 || valid_mip) {
        WGPUDevice owner = device;
        if (strcmp(mode,"usage") == 0) td.usage = WGPUTextureUsage_TextureBinding;
        if (strcmp(mode,"mips") == 0) td.mipLevelCount = 2;
        if (strcmp(mode,"layers") == 0) { td.size.depthOrArrayLayers = 2; vd.dimension = WGPUTextureViewDimension_2DArray; }
        if (strcmp(mode,"foreign-view") == 0) {
            dc.userdata1 = &other; wgpuAdapterRequestDevice(adapter, &dd, dc); wgpuInstanceProcessEvents(instance); owner = other;
        }
        if (valid_mip) {
            td.size = (WGPUExtent3D){WIDTH*2,WIDTH*2,2}; td.mipLevelCount = 2;
            vd.dimension = WGPUTextureViewDimension_2D; vd.baseMipLevel = 1; vd.mipLevelCount = 1;
            vd.baseArrayLayer = 1; vd.arrayLayerCount = 1;
        }
        test_texture = wgpuDeviceCreateTexture(owner, &td); test_view = wgpuTextureCreateView(test_texture, &vd);
    }
    else if (strcmp(mode,"destroyed") == 0 || strcmp(mode,"destroy-after-record") == 0) {
        test_texture = wgpuDeviceCreateTexture(device, &td); test_view = wgpuTextureCreateView(test_texture, NULL);
        if (strcmp(mode,"destroyed") == 0) wgpuTextureDestroy(test_texture);
    }
    else if (strcmp(mode,"resolve") != 0 && strcmp(mode,"multiple") != 0 && strcmp(mode,"depth-only") != 0) return 2;
    if (!test_pipeline || !test_view || (rd.depthStencilAttachment && !depth_view)) return 1;
    for (unsigned i=0;i<2;++i) {
        attachments[i].view = test_view; attachments[i].loadOp = WGPULoadOp_Clear; attachments[i].storeOp = WGPUStoreOp_Store;
    }
    rd.colorAttachments = attachments; rd.colorAttachmentCount = strcmp(mode,"multiple") == 0 ? 2 : 1;
    if (strcmp(mode,"resolve") == 0) attachments[0].resolveTarget = view;
    if (strcmp(mode,"depth-only") == 0) rd.colorAttachmentCount = 0;
    fprintf(stderr,"invalid-window-begin\n");
    wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
    enc = wgpuDeviceCreateCommandEncoder(device, NULL);
    // Earlier valid work must also be abandoned when later admission fails.
    draw(enc, view, pipeline, false);
    WGPURenderPassEncoder pass = wgpuCommandEncoderBeginRenderPass(enc, &rd);
    wgpuRenderPassEncoderSetPipeline(pass, test_pipeline); wgpuRenderPassEncoderDraw(pass,3,1,0,0);
    wgpuRenderPassEncoderEnd(pass); wgpuRenderPassEncoderRelease(pass);
    if (strcmp(mode,"destroy-after-record") == 0) wgpuTextureDestroy(test_texture);
    if (test_view != view) { wgpuTextureViewRelease(test_view); test_view = NULL; }
    if (depth_view) { wgpuTextureViewRelease(depth_view); depth_view = NULL; }
    if (test_pipeline != pipeline) { wgpuRenderPipelineRelease(test_pipeline); test_pipeline = NULL; }
    const bool valid = valid_mip || valid_depth;
    if (strcmp(mode,"destroy-after-record") != 0 && !valid) {
        const bool rejected = validation(device,instance);
        if (!rejected) { fprintf(stderr,"FAIL missing recording validation\n"); wgpuCommandEncoderRelease(enc); return 1; }
        wgpuDevicePushErrorScope(device,WGPUErrorFilter_Validation);
    }
    submit(queue,enc);
    const bool rejected = validation(device,instance);
    fprintf(stderr,"invalid-window-end\n");
    bool ok = rejected != valid;
    if (valid_mip) ok &= pixels(device,instance,queue,test_texture,1,1,true);
    ok &= pixels(device,instance,queue,texture,0,0,valid);
    enc = wgpuDeviceCreateCommandEncoder(device,NULL); draw(enc,view,pipeline,false); submit(queue,enc);
    ok &= pixels(device,instance,queue,texture,0,0,true);
    if (test_texture) wgpuTextureRelease(test_texture);
    if (depth_texture) wgpuTextureRelease(depth_texture);
    wgpuTextureViewRelease(view); wgpuTextureRelease(texture); wgpuRenderPipelineRelease(pipeline); wgpuShaderModuleRelease(shader);
    if (other) wgpuDeviceRelease(other);
    wgpuQueueRelease(queue); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter); wgpuInstanceRelease(instance);
    printf("mode=%s rejection_and_recovery=%s uncaptured=%u\n",mode,ok?"pass":"FAIL",errors);
    return ok && errors == 0 ? 0 : 1;
}
