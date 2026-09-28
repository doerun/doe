#include "webgpu.h"
#include <xcb/xcb.h>
#include <stdlib.h>
#include <dlfcn.h>
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
static WGPUErrorType expected_error = WGPUErrorType_Validation;
static void error_seen(WGPUDevice const *d, WGPUErrorType t, WGPUStringView m, void *p, void *u) {
    (void)d; (void)p; (void)u; ++errors;
    fprintf(stderr, "device error %u: %.*s\n", t, (int)m.length, m.data);
}
static WGPUStringView text(const char *s) { return (WGPUStringView){s, strlen(s)}; }


static void scope_ready(WGPUPopErrorScopeStatus status, WGPUErrorType type, WGPUStringView message, void *p, void *u) {
    (void)u;
    *(bool *)p = status == WGPUPopErrorScopeStatus_Success && type == expected_error;
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
        WGPUTextureFormat format=wgpuTextureGetFormat(tex);
        bool bgra=format==WGPUTextureFormat_BGRA8Unorm || format==WGPUTextureFormat_BGRA8UnormSrgb;
        bool srgb=format==WGPUTextureFormat_BGRA8UnormSrgb || format==WGPUTextureFormat_RGBA8UnormSrgb;
        int expected=srgb ? 137 : 64;
        int actual=p[bgra ? 2 : 0];
        ok &= red && abs(actual-expected)<=1 && p[1]==0 && p[bgra ? 0 : 2]==0 && p[3]==255;
    }
    if (mapped) wgpuBufferUnmap(buffer);
    wgpuBufferRelease(buffer); return ok;
}

static void arm(const char *mode) {
    void (*hook)(const char *) = (void (*)(const char *))dlsym(RTLD_DEFAULT, "doe_surface_test_arm");
    if (hook) hook(mode);
}
int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "normal";
    if (!strcmp(mode,"unsupported")) arm(mode);
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
    int screen_index;
    xcb_connection_t *connection = xcb_connect(NULL, &screen_index);
    if (xcb_connection_has_error(connection)) return 2;
    xcb_screen_iterator_t it = xcb_setup_roots_iterator(xcb_get_setup(connection));
    for (int i=0; i<screen_index; ++i) xcb_screen_next(&it);
    xcb_screen_t *screen = it.data;
    xcb_window_t window = xcb_generate_id(connection);
    xcb_create_window(connection, XCB_COPY_FROM_PARENT, window, screen->root, 0,0, WIDTH,WIDTH,
        0, XCB_WINDOW_CLASS_INPUT_OUTPUT, screen->root_visual, 0, NULL);
    xcb_map_window(connection, window); xcb_flush(connection);
    WGPUSurfaceSourceXCBWindow source_window = WGPU_SURFACE_SOURCE_XCB_WINDOW_INIT;
    source_window.connection = connection; source_window.window = window;
    WGPUSurfaceDescriptor surface_desc = WGPU_SURFACE_DESCRIPTOR_INIT;
    surface_desc.nextInChain = &source_window.chain;
    WGPUSurface surface = wgpuInstanceCreateSurface(instance, &surface_desc);
    if (strcmp(mode,"unsupported")) {
        WGPUSurfaceCapabilities caps=WGPU_SURFACE_CAPABILITIES_INIT;
        if(wgpuSurfaceGetCapabilities(surface,adapter,&caps)!=WGPUStatus_Success) return 1;
        bool fifo=false, format=false;
        for(size_t i=0;i<caps.presentModeCount;++i) fifo |= caps.presentModes[i]==WGPUPresentMode_Fifo;
        for(size_t i=0;i<caps.formatCount;++i) format |= caps.formats[i]==WGPUTextureFormat_BGRA8Unorm;
        printf("capabilities formats=%zu modes=%zu alpha=%zu usages=%llu before-device=true\n",caps.formatCount,caps.presentModeCount,caps.alphaModeCount,(unsigned long long)caps.usages);
        bool valid=fifo && format && (caps.usages & WGPUTextureUsage_CopySrc);
        wgpuSurfaceCapabilitiesFreeMembers(caps);
        if(!valid) return 1;
        caps=(WGPUSurfaceCapabilities)WGPU_SURFACE_CAPABILITIES_INIT;
        if(wgpuSurfaceGetCapabilities(surface,NULL,&caps)!=WGPUStatus_Error || caps.formats) return 1;
        wgpuSurfaceCapabilitiesFreeMembers(caps);
    }
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
        "@fragment fn fs() -> @location(0) vec4f { return vec4f(0.25,0,0,1); }";
    WGPUShaderSourceWGSL source = WGPU_SHADER_SOURCE_WGSL_INIT; source.code = text(wgsl);
    WGPUShaderModuleDescriptor sd = WGPU_SHADER_MODULE_DESCRIPTOR_INIT; sd.nextInChain = &source.chain;
    WGPUShaderModule shader = wgpuDeviceCreateShaderModule(device, &sd);
    WGPUColorTargetState color = WGPU_COLOR_TARGET_STATE_INIT; color.format = !strcmp(mode,"srgb") ? WGPUTextureFormat_BGRA8UnormSrgb : WGPUTextureFormat_BGRA8Unorm;
    WGPUFragmentState fragment = WGPU_FRAGMENT_STATE_INIT;
    fragment.module = shader; fragment.entryPoint = text("fs"); fragment.targetCount = 1; fragment.targets = &color;
    WGPURenderPipelineDescriptor pd = WGPU_RENDER_PIPELINE_DESCRIPTOR_INIT;
    pd.vertex.module = shader; pd.vertex.entryPoint = text("vs"); pd.fragment = &fragment;
    WGPURenderPipeline pipeline = wgpuDeviceCreateRenderPipeline(device, &pd);

    WGPUSurfaceConfiguration config = WGPU_SURFACE_CONFIGURATION_INIT;
    config.device = device; config.format = color.format;
    config.usage = WGPUTextureUsage_RenderAttachment | WGPUTextureUsage_CopySrc;
    config.width = WIDTH; config.height = WIDTH;
    if(!strcmp(mode,"fifo")) config.presentMode=WGPUPresentMode_Fifo;
    if(!strcmp(mode,"relaxed")) config.presentMode=WGPUPresentMode_FifoRelaxed;
    if(!strcmp(mode,"immediate")) config.presentMode=WGPUPresentMode_Immediate;
    if(!strcmp(mode,"mailbox")) config.presentMode=WGPUPresentMode_Mailbox;
    if(!strcmp(mode,"opaque")) config.alphaMode=WGPUCompositeAlphaMode_Opaque;
    if(!strcmp(mode,"inherit")) config.alphaMode=WGPUCompositeAlphaMode_Inherit;
    if(!strcmp(mode,"usage")) config.usage |= WGPUTextureUsage_CopyDst | WGPUTextureUsage_TextureBinding;
    if(!strcmp(mode,"invalid-first")) {
        WGPUSurfaceConfiguration bad=config; bad.format=WGPUTextureFormat_RGBA16Float;
        wgpuDevicePushErrorScope(device,WGPUErrorFilter_Validation);
        wgpuSurfaceConfigure(surface,&bad);
        if(!validation(device,instance)) return 1;
        WGPUSurfaceTexture missing=WGPU_SURFACE_TEXTURE_INIT;
        wgpuSurfaceGetCurrentTexture(surface,&missing);
        if(missing.texture || missing.status!=WGPUSurfaceGetCurrentTextureStatus_Error) return 1;
    }
    if (strcmp(mode,"create-fence") == 0 || strcmp(mode,"create-semaphore") == 0 || strcmp(mode,"images") == 0) arm(mode);
    bool configure_failure=!strcmp(mode,"create-fence") || !strcmp(mode,"create-semaphore") || !strcmp(mode,"images") || !strcmp(mode,"unsupported");
    if(configure_failure) {
        expected_error=!strcmp(mode,"unsupported") ? WGPUErrorType_Validation : WGPUErrorType_OutOfMemory;
        wgpuDevicePushErrorScope(device,expected_error==WGPUErrorType_Validation ? WGPUErrorFilter_Validation : WGPUErrorFilter_OutOfMemory);
    }
    wgpuSurfaceConfigure(surface, &config);
    if(configure_failure) { if(!validation(device,instance)) return 1; expected_error=WGPUErrorType_Validation; }

    if (strcmp(mode,"create-fence") == 0 || strcmp(mode,"create-semaphore") == 0 || strcmp(mode,"images") == 0) {
        WGPUSurfaceTexture failed = WGPU_SURFACE_TEXTURE_INIT;
        wgpuSurfaceGetCurrentTexture(surface,&failed);
        if (failed.texture) return 1;
        wgpuSurfaceConfigure(surface,&config);
    }
    if (!strcmp(mode,"unsupported")) {
        WGPUSurfaceTexture failed = WGPU_SURFACE_TEXTURE_INIT;
        wgpuSurfaceGetCurrentTexture(surface,&failed);
        if (failed.texture) return 1;
        wgpuSurfaceRelease(surface); wgpuRenderPipelineRelease(pipeline); wgpuShaderModuleRelease(shader);
        wgpuQueueRelease(queue); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter); wgpuInstanceRelease(instance);
        xcb_destroy_window(connection,window); xcb_disconnect(connection); return 0;
    }
    for (unsigned frame=0; frame<8; ++frame) {
        WGPUSurfaceTexture current = WGPU_SURFACE_TEXTURE_INIT;
        if (frame==0 && (!strcmp(mode,"acquire-wait") || !strcmp(mode,"device-lost") || !strcmp(mode,"create-view"))) arm(mode);
        wgpuSurfaceGetCurrentTexture(surface, &current);
        if (frame==0 && !strcmp(mode,"create-view")) {
            if (current.texture) return 1;
            wgpuSurfaceGetCurrentTexture(surface,&current);
        }
        if (frame==0 && !strcmp(mode,"device-lost")) {
            if (current.texture) return 1;
            wgpuSurfaceUnconfigure(surface); wgpuSurfaceRelease(surface);
            wgpuRenderPipelineRelease(pipeline); wgpuShaderModuleRelease(shader);
            wgpuQueueRelease(queue); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter); wgpuInstanceRelease(instance);
            xcb_destroy_window(connection,window); xcb_disconnect(connection); return 0;
        }
        if (frame==0 && strcmp(mode,"acquire-wait") == 0) {
            if (current.status != WGPUSurfaceGetCurrentTextureStatus_Timeout) return 1;
            if (current.texture) return 1;
            wgpuSurfaceUnconfigure(surface);
            wgpuSurfaceConfigure(surface,&config);
            wgpuSurfaceGetCurrentTexture(surface,&current);
        }
        if (!current.texture) { fprintf(stderr,"acquire frame=%u status=%u\n",frame,current.status); return 1; }
        if (strcmp(mode,"baseline")) {
            WGPUSurfaceTexture same = WGPU_SURFACE_TEXTURE_INIT;
            wgpuSurfaceGetCurrentTexture(surface,&same);
            if (same.texture != current.texture) return 1;
            wgpuTextureRelease(same.texture);
        }
        if(wgpuTextureGetFormat(current.texture)!=config.format || wgpuTextureGetWidth(current.texture)!=WIDTH || wgpuTextureGetUsage(current.texture)!=config.usage) return 1;
        if(frame==0 && !strcmp(mode,"admission")) {
            for(unsigned reject=0;reject<11;++reject) {
                WGPUSurfaceConfiguration bad=config;
                WGPUChainedStruct chain={NULL,WGPUSType_ShaderSourceWGSL};
                WGPUTextureFormat view_format=WGPUTextureFormat_BGRA8UnormSrgb;
                switch(reject) {
                    case 0: bad.format=WGPUTextureFormat_RGBA16Float; break;
                    case 1: bad.format=WGPUTextureFormat_Undefined; break;
                    case 2: bad.usage |= UINT64_C(1)<<40; break;
                    case 3: bad.usage |= WGPUTextureUsage_StorageBinding; break;
                    case 4: bad.usage=0; break;
                    case 5: bad.presentMode=WGPUPresentMode_Force32; break;
                    case 6: bad.alphaMode=WGPUCompositeAlphaMode_Force32; break;
                    case 7: bad.nextInChain=&chain; break;
                    case 8: bad.viewFormatCount=1; bad.viewFormats=&view_format; break;
                    case 9: bad.width=0; break;
                    case 10: bad.device=NULL; break;
                }
                wgpuDevicePushErrorScope(device,WGPUErrorFilter_Validation);
                wgpuSurfaceConfigure(surface,&bad);
                if(!validation(device,instance)) return 1;
                WGPUSurfaceTexture retained=WGPU_SURFACE_TEXTURE_INIT;
                wgpuSurfaceGetCurrentTexture(surface,&retained);
                if(retained.texture!=current.texture) return 1;
                wgpuTextureRelease(retained.texture);
                printf("rejected=%u existing-texture=preserved\n",reject);
            }
        }
        WGPUTextureView view = wgpuTextureCreateView(current.texture, NULL);
        WGPUCommandEncoder enc = wgpuDeviceCreateCommandEncoder(device, NULL);
        draw(enc, view, pipeline, true); draw(enc, view, pipeline, true); draw(enc, view, pipeline, false);
        submit(queue, enc);
        if (errors || !pixels(device,instance,queue,current.texture,0,0,true)) {
            fprintf(stderr,"frame=%u errors=%u pixels failed\n",frame,errors); return 1;
        }
        if (frame==1) wgpuTextureRelease(current.texture);
        if (frame==0 && (strcmp(mode,"submit-reject") == 0 || strcmp(mode,"present-reject") == 0 || strcmp(mode,"outdated") == 0)) {
            arm(mode);
            if (wgpuSurfacePresent(surface) == WGPUStatus_Success) return 1;
            if (strcmp(mode,"outdated") == 0) {
                wgpuSurfaceConfigure(surface,&config);
            } else if (wgpuSurfacePresent(surface) != WGPUStatus_Success) return 1;
        } else if (wgpuSurfacePresent(surface) != WGPUStatus_Success) return 1;
        if (frame==3 && strcmp(mode,"present-wait") == 0) arm(mode);
        if (frame==2) {
            wgpuDevicePushErrorScope(device,WGPUErrorFilter_Validation);
            enc=wgpuDeviceCreateCommandEncoder(device,NULL);
            draw(enc,view,pipeline,false); submit(queue,enc);
            if (!validation(device,instance)) return 1;
        }
        if (frame==3) { wgpuSurfaceUnconfigure(surface); wgpuSurfaceConfigure(surface,&config); }
        wgpuTextureViewRelease(view); if (frame!=1) wgpuTextureRelease(current.texture);
        printf("frame=%u pixels=pass\n",frame);
    }
    if (!strcmp(mode,"empty")) {
        WGPUSurfaceTexture empty = WGPU_SURFACE_TEXTURE_INIT;
        wgpuSurfaceGetCurrentTexture(surface,&empty);
        if (!empty.texture || wgpuSurfacePresent(surface)!=WGPUStatus_Success) return 1;
        wgpuTextureRelease(empty.texture);
    }
    WGPUSurfaceCapabilities retained_caps=WGPU_SURFACE_CAPABILITIES_INIT;
    if(wgpuSurfaceGetCapabilities(surface,adapter,&retained_caps)!=WGPUStatus_Success || !retained_caps.formatCount) return 1;
    WGPUTextureFormat retained_format=retained_caps.formats[0];
    // Outstanding public references outlive the surface and caller's device ref.
    WGPUSurfaceTexture last = WGPU_SURFACE_TEXTURE_INIT;
    wgpuSurfaceGetCurrentTexture(surface,&last);
    if (!last.texture) return 1;
    WGPUTextureView last_view = wgpuTextureCreateView(last.texture,NULL);
    wgpuSurfaceUnconfigure(surface); wgpuSurfaceUnconfigure(surface); wgpuSurfaceRelease(surface);
    wgpuRenderPipelineRelease(pipeline); wgpuShaderModuleRelease(shader);
    wgpuQueueRelease(queue); wgpuDeviceRelease(device); wgpuAdapterRelease(adapter); wgpuInstanceRelease(instance);
    wgpuTextureViewRelease(last_view); wgpuTextureRelease(last.texture);
    if(retained_caps.formats[0]!=retained_format) return 1;
    wgpuSurfaceCapabilitiesFreeMembers(retained_caps);
    xcb_destroy_window(connection, window); xcb_disconnect(connection);
    return errors ? 1 : 0;
}
