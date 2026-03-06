#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include "metal_bridge.h"
#include <string.h>

// CFBridging provides correct ARC-safe transfer across the void* boundary.
// Each returned MetalHandle is +1 retained and owned by the caller.
// metal_bridge_release() must be called to balance.

// ============================================================
// Cached render pass descriptor (avoids alloc per render command)
// ============================================================

static MTLRenderPassDescriptor* _cachedRenderPassDesc = nil;
static id<MTLTexture> _cachedRenderPassTarget = nil;

static MTLRenderPassDescriptor* cachedRenderPassDescriptor(id<MTLTexture> target) {
    if (_cachedRenderPassDesc == nil) {
        _cachedRenderPassDesc = [MTLRenderPassDescriptor new];
        _cachedRenderPassDesc.colorAttachments[0].loadAction  = MTLLoadActionDontCare;
        _cachedRenderPassDesc.colorAttachments[0].storeAction = MTLStoreActionDontCare;
    }
    if (_cachedRenderPassTarget != target) {
        _cachedRenderPassDesc.colorAttachments[0].texture = target;
        _cachedRenderPassTarget = target;
    }
    return _cachedRenderPassDesc;
}

// ============================================================
// Pixel format translation
// ============================================================

static MTLPixelFormat wgpu_to_mtl_format(uint32_t wgpu) {
    switch (wgpu) {
        case 0x00000016: return MTLPixelFormatRGBA8Unorm;
        case 0x00000017: return MTLPixelFormatRGBA8Unorm_sRGB;
        case 0x0000001B: return MTLPixelFormatBGRA8Unorm;
        case 0x0000001C: return MTLPixelFormatBGRA8Unorm_sRGB;
        case 0x00000030: return MTLPixelFormatDepth32Float;
        default:         return MTLPixelFormatRGBA8Unorm;
    }
}

// ============================================================
// Core device / buffer / blit
// ============================================================

MetalHandle metal_bridge_create_default_device(void) {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(device);
}

void metal_bridge_release(MetalHandle obj) {
    if (obj == NULL) return;
    CFRelease(obj);
}

MetalHandle metal_bridge_device_new_command_queue(MetalHandle device_h) {
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (queue == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(queue);
}

MetalHandle metal_bridge_device_new_buffer_shared(MetalHandle device_h, size_t length) {
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    id<MTLBuffer> buf = [device newBufferWithLength:length
                                           options:MTLResourceStorageModeShared
                                                   | MTLResourceHazardTrackingModeUntracked];
    if (buf == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(buf);
}

MetalHandle metal_bridge_device_new_buffer_private(MetalHandle device_h, size_t length) {
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    id<MTLBuffer> buf = [device newBufferWithLength:length
                                           options:MTLResourceStorageModePrivate
                                                   | MTLResourceHazardTrackingModeUntracked];
    if (buf == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(buf);
}

void* metal_bridge_buffer_contents(MetalHandle buffer_h) {
    id<MTLBuffer> buf = (__bridge id<MTLBuffer>)buffer_h;
    return [buf contents];
}

MetalHandle metal_bridge_encode_blit_copy(
    MetalHandle queue_h,
    MetalHandle src_h,
    MetalHandle dst_h,
    size_t      byte_count)
{
    id<MTLCommandQueue> queue   = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLBuffer>       src_buf = (__bridge id<MTLBuffer>)src_h;
    id<MTLBuffer>       dst_buf = (__bridge id<MTLBuffer>)dst_h;

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    id<MTLBlitCommandEncoder> encoder = [cmd_buf blitCommandEncoder];
    [encoder copyFromBuffer:src_buf
               sourceOffset:0
                   toBuffer:dst_buf
          destinationOffset:0
                       size:byte_count];
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

void metal_bridge_command_buffer_commit(MetalHandle cmd_buf_h) {
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    [cmd_buf commit];
}

void metal_bridge_command_buffer_wait_completed(MetalHandle cmd_buf_h) {
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    [cmd_buf waitUntilCompleted];
}

MetalHandle metal_bridge_encode_blit_batch(
    MetalHandle  queue_h,
    MetalHandle* src_bufs,
    MetalHandle* dst_bufs,
    size_t*      byte_counts,
    uint32_t     count)
{
    if (count == 0) return NULL;
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)queue_h;

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    id<MTLBlitCommandEncoder> encoder = [cmd_buf blitCommandEncoder];
    for (uint32_t i = 0; i < count; i++) {
        id<MTLBuffer> src = (__bridge id<MTLBuffer>)src_bufs[i];
        id<MTLBuffer> dst = (__bridge id<MTLBuffer>)dst_bufs[i];
        [encoder copyFromBuffer:src sourceOffset:0
                       toBuffer:dst destinationOffset:0
                           size:byte_counts[i]];
    }
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

// ============================================================
// Compute Pipeline
// ============================================================

static void write_error(NSError* err, char* buf, size_t cap) {
    if (buf == NULL || cap == 0) return;
    const char* msg = err ? [[err localizedDescription] UTF8String] : "unknown error";
    strncpy(buf, msg, cap - 1);
    buf[cap - 1] = '\0';
}

MetalHandle metal_bridge_device_new_library_msl(
    MetalHandle device_h,
    const char* src,
    size_t      src_len,
    char*       error_buf,
    size_t      error_cap)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    NSString* source = [[NSString alloc] initWithBytes:src length:src_len encoding:NSUTF8StringEncoding];
    if (source == nil) {
        if (error_buf && error_cap) strncpy(error_buf, "invalid MSL source encoding", error_cap - 1);
        return NULL;
    }
    NSError* err = nil;
    id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&err];
    if (library == nil) {
        write_error(err, error_buf, error_cap);
        return NULL;
    }
    return (MetalHandle)CFBridgingRetain(library);
}

MetalHandle metal_bridge_library_new_function(MetalHandle library_h, const char* name) {
    id<MTLLibrary> library = (__bridge id<MTLLibrary>)library_h;
    NSString* fname = [NSString stringWithUTF8String:name];
    id<MTLFunction> fn = [library newFunctionWithName:fname];
    if (fn == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(fn);
}

MetalHandle metal_bridge_device_new_compute_pipeline(
    MetalHandle device_h,
    MetalHandle function_h,
    char*       error_buf,
    size_t      error_cap)
{
    id<MTLDevice>   device   = (__bridge id<MTLDevice>)device_h;
    id<MTLFunction> function = (__bridge id<MTLFunction>)function_h;
    NSError* err = nil;
    id<MTLComputePipelineState> pso = [device newComputePipelineStateWithFunction:function error:&err];
    if (pso == nil) {
        write_error(err, error_buf, error_cap);
        return NULL;
    }
    return (MetalHandle)CFBridgingRetain(pso);
}

MetalHandle metal_bridge_encode_compute_dispatch(
    MetalHandle  queue_h,
    MetalHandle  pipeline_h,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    uint32_t     x,
    uint32_t     y,
    uint32_t     z)
{
    id<MTLCommandQueue>          queue    = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLComputePipelineState>  pipeline = (__bridge id<MTLComputePipelineState>)pipeline_h;

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];
    [encoder setComputePipelineState:pipeline];

    for (uint32_t i = 0; i < buffer_count; i++) {
        if (buffers[i] != NULL) {
            id<MTLBuffer> buf = (__bridge id<MTLBuffer>)buffers[i];
            [encoder setBuffer:buf offset:0 atIndex:i];
        }
    }

    MTLSize tg_size    = MTLSizeMake(pipeline.maxTotalThreadsPerThreadgroup > 0
                                     ? (NSUInteger)pipeline.maxTotalThreadsPerThreadgroup
                                     : 256, 1, 1);
    MTLSize grid_size  = MTLSizeMake(x, y, z);
    [encoder dispatchThreadgroups:grid_size threadsPerThreadgroup:tg_size];
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

MetalHandle metal_bridge_encode_compute_dispatch_batch(
    MetalHandle  queue_h,
    MetalHandle  pipeline_h,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    uint32_t     x,
    uint32_t     y,
    uint32_t     z,
    uint32_t     repeat_count)
{
    id<MTLCommandQueue>          queue    = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLComputePipelineState>  pipeline = (__bridge id<MTLComputePipelineState>)pipeline_h;

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    MTLSize tg_size   = MTLSizeMake(pipeline.maxTotalThreadsPerThreadgroup > 0
                                    ? (NSUInteger)pipeline.maxTotalThreadsPerThreadgroup
                                    : 256, 1, 1);
    MTLSize grid_size = MTLSizeMake(x, y, z);

    // Single encoder for all repeats: set pipeline/buffers once, dispatch N times.
    id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];
    [encoder setComputePipelineState:pipeline];
    for (uint32_t i = 0; i < buffer_count; i++) {
        if (buffers[i] != NULL) {
            id<MTLBuffer> buf = (__bridge id<MTLBuffer>)buffers[i];
            [encoder setBuffer:buf offset:0 atIndex:i];
        }
    }
    for (uint32_t r = 0; r < repeat_count; r++) {
        [encoder dispatchThreadgroups:grid_size threadsPerThreadgroup:tg_size];
    }
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

// ============================================================
// Texture
// ============================================================

MetalHandle metal_bridge_device_new_texture(
    MetalHandle device_h,
    uint32_t    width,
    uint32_t    height,
    uint32_t    mip_levels,
    uint32_t    pixel_format,
    uint32_t    usage)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    MTLTextureDescriptor* desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:wgpu_to_mtl_format(pixel_format)
                                                                                    width:width
                                                                                   height:height
                                                                                mipmapped:(mip_levels > 1)];
    desc.mipmapLevelCount = mip_levels > 0 ? mip_levels : 1;

    MTLTextureUsage mtl_usage = MTLTextureUsageShaderRead;
    if (usage & 0x02) mtl_usage |= MTLTextureUsageShaderWrite; // CopyDst
    if (usage & 0x08) mtl_usage |= MTLTextureUsageShaderWrite; // StorageBinding
    if (usage & 0x10) mtl_usage |= MTLTextureUsageRenderTarget; // RenderAttachment
    desc.usage = mtl_usage;
    desc.storageMode = MTLStorageModeShared;

    id<MTLTexture> tex = [device newTextureWithDescriptor:desc];
    if (tex == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(tex);
}

void metal_bridge_texture_replace_region(
    MetalHandle  texture_h,
    uint32_t     width,
    uint32_t     height,
    const void*  data,
    uint32_t     bytes_per_row,
    uint32_t     mip_level)
{
    id<MTLTexture> tex = (__bridge id<MTLTexture>)texture_h;
    MTLRegion region = MTLRegionMake2D(0, 0, width, height);
    [tex replaceRegion:region mipmapLevel:mip_level withBytes:data bytesPerRow:bytes_per_row];
}

uint32_t metal_bridge_texture_width(MetalHandle h)           { return (uint32_t)[(__bridge id<MTLTexture>)h width]; }
uint32_t metal_bridge_texture_height(MetalHandle h)          { return (uint32_t)[(__bridge id<MTLTexture>)h height]; }
uint32_t metal_bridge_texture_depth(MetalHandle h)           { return (uint32_t)[(__bridge id<MTLTexture>)h depth]; }
uint32_t metal_bridge_texture_pixel_format(MetalHandle h)    { return (uint32_t)[(__bridge id<MTLTexture>)h pixelFormat]; }
uint32_t metal_bridge_texture_mip_level_count(MetalHandle h) { return (uint32_t)[(__bridge id<MTLTexture>)h mipmapLevelCount]; }
uint32_t metal_bridge_texture_sample_count(MetalHandle h)    { return (uint32_t)[(__bridge id<MTLTexture>)h sampleCount]; }

// ============================================================
// Sampler
// ============================================================

static MTLSamplerMinMagFilter wgpu_to_mtl_filter(uint32_t f) {
    return (f == 1) ? MTLSamplerMinMagFilterLinear : MTLSamplerMinMagFilterNearest;
}

static MTLSamplerMipFilter wgpu_to_mtl_mip_filter(uint32_t f) {
    return (f == 1) ? MTLSamplerMipFilterLinear : MTLSamplerMipFilterNearest;
}

static MTLSamplerAddressMode wgpu_to_mtl_addr(uint32_t a) {
    switch (a) {
        case 0: return MTLSamplerAddressModeClampToEdge;
        case 1: return MTLSamplerAddressModeMirrorClampToEdge;
        case 3: return MTLSamplerAddressModeMirrorRepeat;
        default: return MTLSamplerAddressModeRepeat;
    }
}

static MTLSamplerDescriptor* _cachedSamplerDesc = nil;

MetalHandle metal_bridge_device_new_sampler(
    MetalHandle device_h,
    uint32_t    min_filter,
    uint32_t    mag_filter,
    uint32_t    mipmap_filter,
    uint32_t    addr_u,
    uint32_t    addr_v,
    uint32_t    addr_w,
    float       lod_min,
    float       lod_max,
    uint16_t    max_aniso)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    if (_cachedSamplerDesc == nil) {
        _cachedSamplerDesc = [MTLSamplerDescriptor new];
    }
    _cachedSamplerDesc.minFilter       = wgpu_to_mtl_filter(min_filter);
    _cachedSamplerDesc.magFilter       = wgpu_to_mtl_filter(mag_filter);
    _cachedSamplerDesc.mipFilter       = wgpu_to_mtl_mip_filter(mipmap_filter);
    _cachedSamplerDesc.sAddressMode    = wgpu_to_mtl_addr(addr_u);
    _cachedSamplerDesc.tAddressMode    = wgpu_to_mtl_addr(addr_v);
    _cachedSamplerDesc.rAddressMode    = wgpu_to_mtl_addr(addr_w);
    _cachedSamplerDesc.lodMinClamp     = lod_min;
    _cachedSamplerDesc.lodMaxClamp     = lod_max;
    _cachedSamplerDesc.maxAnisotropy   = max_aniso > 0 ? max_aniso : 1;

    id<MTLSamplerState> sampler = [device newSamplerStateWithDescriptor:_cachedSamplerDesc];
    if (sampler == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(sampler);
}

// ============================================================
// Render Pipeline — built-in noop shaders
// ============================================================

// Degenerate vertex shader: all vertices collapse to the same clip-space point,
// producing zero-area triangles that the GPU culls before rasterization.
// This matches Dawn's noop render pipeline behavior for draw-call benchmarks.
static const char* k_render_msl =
    "#include <metal_stdlib>\n"
    "using namespace metal;\n"
    "vertex float4 v_noop(uint vid [[vertex_id]]) {\n"
    "    (void)vid;\n"
    "    return float4(0.0f, 0.0f, 0.0f, 1.0f);\n"
    "}\n"
    "fragment float4 f_noop(float4 pos [[position]]) {\n"
    "    return float4(0.0f);\n"
    "}\n";

MetalHandle metal_bridge_device_new_render_pipeline(
    MetalHandle device_h,
    uint32_t    pixel_format,
    int         support_icb,
    char*       error_buf,
    size_t      error_cap)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;

    NSError* err = nil;
    NSString* src = [NSString stringWithUTF8String:k_render_msl];
    id<MTLLibrary> lib = [device newLibraryWithSource:src options:nil error:&err];
    if (lib == nil) { write_error(err, error_buf, error_cap); return NULL; }

    id<MTLFunction> vert_fn = [lib newFunctionWithName:@"v_noop"];
    id<MTLFunction> frag_fn = [lib newFunctionWithName:@"f_noop"];
    if (vert_fn == nil || frag_fn == nil) {
        if (error_buf && error_cap) strncpy(error_buf, "failed to get render functions", error_cap - 1);
        return NULL;
    }

    MTLRenderPipelineDescriptor* desc = [MTLRenderPipelineDescriptor new];
    desc.vertexFunction   = vert_fn;
    desc.fragmentFunction = frag_fn;
    desc.colorAttachments[0].pixelFormat = wgpu_to_mtl_format(pixel_format);
    if (support_icb) {
        desc.supportIndirectCommandBuffers = YES;
    }

    id<MTLRenderPipelineState> pso = [device newRenderPipelineStateWithDescriptor:desc error:&err];
    if (pso == nil) { write_error(err, error_buf, error_cap); return NULL; }
    return (MetalHandle)CFBridgingRetain(pso);
}

MetalHandle metal_bridge_device_new_render_target(
    MetalHandle device_h,
    uint32_t    width,
    uint32_t    height,
    uint32_t    pixel_format)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    MTLTextureDescriptor* desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:wgpu_to_mtl_format(pixel_format)
                                                                                    width:width
                                                                                   height:height
                                                                                mipmapped:NO];
    desc.usage       = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
    desc.storageMode = MTLStorageModePrivate;
    desc.hazardTrackingMode = MTLHazardTrackingModeUntracked;
    id<MTLTexture> tex = [device newTextureWithDescriptor:desc];
    if (tex == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(tex);
}

MetalHandle metal_bridge_encode_render_pass(
    MetalHandle queue_h,
    MetalHandle pipeline_h,
    MetalHandle target_h,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    int         redundant_pipeline,
    int         redundant_bindgroup)
{
    (void)redundant_bindgroup; // Metal has no bind-group abstraction; deviation documented.

    id<MTLCommandQueue>         queue    = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLRenderPipelineState>  pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    id<MTLTexture>              target   = (__bridge id<MTLTexture>)target_h;

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target);

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    id<MTLRenderCommandEncoder> encoder = [cmd_buf renderCommandEncoderWithDescriptor:pass];
    [encoder setRenderPipelineState:pipeline];

    for (uint32_t i = 0; i < draw_count; i++) {
        if (redundant_pipeline) {
            [encoder setRenderPipelineState:pipeline];
        }
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle
                    vertexStart:0
                    vertexCount:vertex_count
                  instanceCount:instance_count];
    }
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

// ============================================================
// Indirect Command Buffer (render bundle emulation)
// ============================================================

MetalHandle metal_bridge_device_new_icb(
    MetalHandle device_h,
    MetalHandle pipeline_h,
    uint32_t    command_count,
    int         redundant_pipeline)
{
    id<MTLDevice>              device   = (__bridge id<MTLDevice>)device_h;
    id<MTLRenderPipelineState> pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    (void)pipeline;
    (void)redundant_pipeline;

    // inheritPipelineState = NO: per-command setRenderPipelineState: is called during CPU
    // ICB encoding. This is faster on Apple Silicon than NO+inheritance because the CPU
    // encode path for ICB with inheritPipelineState=YES has higher per-command overhead.
    MTLIndirectCommandBufferDescriptor* desc = [MTLIndirectCommandBufferDescriptor new];
    desc.commandTypes               = MTLIndirectCommandTypeDraw;
    desc.inheritPipelineState       = NO;
    desc.inheritBuffers             = YES;
    desc.maxVertexBufferBindCount   = 0;
    desc.maxFragmentBufferBindCount = 0;

    id<MTLIndirectCommandBuffer> icb = [device newIndirectCommandBufferWithDescriptor:desc
                                                                      maxCommandCount:command_count
                                                                              options:0];
    if (icb == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(icb);
}

void metal_bridge_icb_encode_draws(
    MetalHandle icb_h,
    MetalHandle pipeline_h,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    int         redundant_pipeline)
{
    id<MTLIndirectCommandBuffer> icb      = (__bridge id<MTLIndirectCommandBuffer>)icb_h;
    id<MTLRenderPipelineState>   pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;

    for (uint32_t i = 0; i < draw_count; i++) {
        id<MTLIndirectRenderCommand> cmd = [icb indirectRenderCommandAtIndex:i];
        // inheritPipelineState = NO requires setRenderPipelineState: per command.
        // Called unconditionally; redundant_pipeline flag only signals the workload type.
        [cmd setRenderPipelineState:pipeline];
        [cmd drawPrimitives:MTLPrimitiveTypeTriangle
                vertexStart:0
                vertexCount:vertex_count
              instanceCount:instance_count
               baseInstance:0];
    }
}

MetalHandle metal_bridge_encode_icb_render_pass(
    MetalHandle queue_h,
    MetalHandle pipeline_h,
    MetalHandle icb_h,
    MetalHandle target_h,
    uint32_t    draw_count)
{
    id<MTLCommandQueue>          queue    = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLRenderPipelineState>   pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    id<MTLIndirectCommandBuffer> icb      = (__bridge id<MTLIndirectCommandBuffer>)icb_h;
    id<MTLTexture>               target   = (__bridge id<MTLTexture>)target_h;

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target);

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    id<MTLRenderCommandEncoder> encoder = [cmd_buf renderCommandEncoderWithDescriptor:pass];
    [encoder setRenderPipelineState:pipeline];
    [encoder executeCommandsInBuffer:icb withRange:NSMakeRange(0, draw_count)];
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}
