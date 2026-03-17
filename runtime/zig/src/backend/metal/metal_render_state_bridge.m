#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include "metal_render_state_bridge.h"
#include <string.h>

// ============================================================
// Internal translation helpers
// ============================================================

// WebGPU blend operation values → MTLBlendOperation
static MTLBlendOperation wgpu_blend_op(uint32_t v) {
    switch (v) {
        case 1: return MTLBlendOperationSubtract;
        case 2: return MTLBlendOperationReverseSubtract;
        case 3: return MTLBlendOperationMin;
        case 4: return MTLBlendOperationMax;
        default: return MTLBlendOperationAdd;
    }
}

// WebGPU blend factor values → MTLBlendFactor
static MTLBlendFactor wgpu_blend_factor(uint32_t v) {
    switch (v) {
        case  0: return MTLBlendFactorZero;
        case  1: return MTLBlendFactorOne;
        case  2: return MTLBlendFactorSourceColor;
        case  3: return MTLBlendFactorOneMinusSourceColor;
        case  4: return MTLBlendFactorSourceAlpha;
        case  5: return MTLBlendFactorOneMinusSourceAlpha;
        case  6: return MTLBlendFactorDestinationColor;
        case  7: return MTLBlendFactorOneMinusDestinationColor;
        case  8: return MTLBlendFactorDestinationAlpha;
        case  9: return MTLBlendFactorOneMinusDestinationAlpha;
        case 10: return MTLBlendFactorSourceAlphaSaturated;
        case 11: return MTLBlendFactorBlendColor;
        case 12: return MTLBlendFactorOneMinusBlendColor;
        case 13: return MTLBlendFactorSource1Color;
        case 14: return MTLBlendFactorOneMinusSource1Color;
        case 15: return MTLBlendFactorSource1Alpha;
        case 16: return MTLBlendFactorOneMinusSource1Alpha;
        default: return MTLBlendFactorOne;
    }
}

// WebGPU write mask bits → MTLColorWriteMask
// WebGPU: red=1 green=2 blue=4 alpha=8 all=0xF
static MTLColorWriteMask wgpu_write_mask(uint32_t m) {
    MTLColorWriteMask out = MTLColorWriteMaskNone;
    if (m & 0x1) out |= MTLColorWriteMaskRed;
    if (m & 0x2) out |= MTLColorWriteMaskGreen;
    if (m & 0x4) out |= MTLColorWriteMaskBlue;
    if (m & 0x8) out |= MTLColorWriteMaskAlpha;
    return out;
}

// WebGPU compare function → MTLCompareFunction
// 0=undefined→always, 1=never, 2=less, 3=equal, 4=less_equal,
// 5=greater, 6=not_equal, 7=greater_equal, 8=always
static MTLCompareFunction wgpu_compare(uint32_t v) {
    switch (v) {
        case 1: return MTLCompareFunctionNever;
        case 2: return MTLCompareFunctionLess;
        case 3: return MTLCompareFunctionEqual;
        case 4: return MTLCompareFunctionLessEqual;
        case 5: return MTLCompareFunctionGreater;
        case 6: return MTLCompareFunctionNotEqual;
        case 7: return MTLCompareFunctionGreaterEqual;
        case 8: return MTLCompareFunctionAlways;
        default: return MTLCompareFunctionAlways;
    }
}

// WebGPU stencil operation → MTLStencilOperation
// 0=keep, 1=zero, 2=replace, 3=invert,
// 4=increment_clamp, 5=decrement_clamp, 6=increment_wrap, 7=decrement_wrap
static MTLStencilOperation wgpu_stencil_op(uint32_t v) {
    switch (v) {
        case 0: return MTLStencilOperationKeep;
        case 1: return MTLStencilOperationZero;
        case 2: return MTLStencilOperationReplace;
        case 3: return MTLStencilOperationInvert;
        case 4: return MTLStencilOperationIncrementClamp;
        case 5: return MTLStencilOperationDecrementClamp;
        case 6: return MTLStencilOperationIncrementWrap;
        case 7: return MTLStencilOperationDecrementWrap;
        default: return MTLStencilOperationKeep;
    }
}

// WebGPU texture format → MTLPixelFormat (matching metal_bridge.m + depth formats)
static MTLPixelFormat wgpu_format(uint32_t wgpu) {
    switch (wgpu) {
        case 0x00000001: return MTLPixelFormatR8Unorm;
        case 0x00000016: return MTLPixelFormatRGBA8Unorm;
        case 0x00000017: return MTLPixelFormatRGBA8Unorm_sRGB;
        case 0x0000001B: return MTLPixelFormatBGRA8Unorm;
        case 0x0000001C: return MTLPixelFormatBGRA8Unorm_sRGB;
        case 0x00000024: return MTLPixelFormatRGBA16Float;
        case 0x00000025: return MTLPixelFormatRGBA32Float;
        case 0x00000030: return MTLPixelFormatDepth32Float;
        case 0x00000031: return MTLPixelFormatStencil8;
        case 0x00000032: return MTLPixelFormatDepth32Float_Stencil8;
        case 0x00000033: return MTLPixelFormatDepth16Unorm;
        default:         return MTLPixelFormatRGBA8Unorm;
    }
}

static void write_err(NSError* err, char* buf, size_t cap) {
    if (buf == NULL || cap == 0) return;
    const char* msg = err ? [[err localizedDescription] UTF8String] : "unknown error";
    strncpy(buf, msg, cap - 1);
    buf[cap - 1] = '\0';
}

// ============================================================
// Viewport / Scissor / Stencil reference / Blend color
// ============================================================

void metal_render_state_set_viewport(
    MetalHandle encoder_h,
    double      x,
    double      y,
    double      width,
    double      height,
    double      depth_min,
    double      depth_max)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    MTLViewport vp;
    vp.originX = x;
    vp.originY = y;
    vp.width   = width;
    vp.height  = height;
    vp.znear   = depth_min;
    vp.zfar    = depth_max;
    [encoder setViewport:vp];
}

void metal_render_state_set_scissor_rect(
    MetalHandle encoder_h,
    uint32_t    x,
    uint32_t    y,
    uint32_t    width,
    uint32_t    height)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    MTLScissorRect rect;
    rect.x      = (NSUInteger)x;
    rect.y      = (NSUInteger)y;
    rect.width  = (NSUInteger)width;
    rect.height = (NSUInteger)height;
    [encoder setScissorRect:rect];
}

void metal_render_state_set_stencil_reference(
    MetalHandle encoder_h,
    uint32_t    value)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    [encoder setStencilReferenceValue:(uint32_t)value];
}

void metal_render_state_set_blend_color(
    MetalHandle encoder_h,
    float       r,
    float       g,
    float       b,
    float       a)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    [encoder setBlendColorRed:r green:g blue:b alpha:a];
}

// ============================================================
// Full render pipeline with blend, MSAA, depth/stencil
// ============================================================

// Noop shaders used when vertex_msl/fragment_msl are NULL.
// Degenerate vertex shader collapses all vertices to one point (zero-area triangles).
static const char* k_noop_msl =
    "#include <metal_stdlib>\n"
    "using namespace metal;\n"
    "vertex float4 v_noop(uint vid [[vertex_id]]) {\n"
    "    (void)vid; return float4(0.0f,0.0f,0.0f,1.0f);\n"
    "}\n"
    "fragment float4 f_noop(float4 pos [[position]]) {\n"
    "    return float4(0.0f);\n"
    "}\n";

static id<MTLLibrary> compile_library(
    id<MTLDevice> device,
    const char*   msl_src,
    char*         error_buf,
    size_t        error_cap)
{
    NSString* src = [NSString stringWithUTF8String:msl_src];
    if (src == nil) {
        if (error_buf && error_cap) strncpy(error_buf, "invalid MSL encoding", error_cap - 1);
        return nil;
    }
    NSError* err = nil;
    id<MTLLibrary> lib = [device newLibraryWithSource:src options:nil error:&err];
    if (lib == nil) write_err(err, error_buf, error_cap);
    return lib;
}

MetalHandle metal_render_state_new_pipeline(
    MetalHandle                    device_h,
    const char*                    vertex_msl,
    const char*                    fragment_msl,
    uint32_t                       pixel_format,
    uint32_t                       sample_count,
    int                            alpha_to_coverage,
    const MetalBlendAttachment*    blend,
    const MetalDepthStencilConfig* depth_stencil,
    int                            support_icb,
    char*                          error_buf,
    size_t                         error_cap)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;

    // Compile vertex and fragment shaders.
    // Both can be provided as separate MSL strings, or NULL for noop.
    const char* vert_src = (vertex_msl   != NULL) ? vertex_msl   : k_noop_msl;
    const char* frag_src = (fragment_msl != NULL) ? fragment_msl : k_noop_msl;

    id<MTLLibrary> vert_lib = compile_library(device, vert_src, error_buf, error_cap);
    if (vert_lib == nil) return NULL;

    // When both shaders come from the same source string, reuse the library.
    id<MTLLibrary> frag_lib;
    if (fragment_msl == vertex_msl || frag_src == vert_src) {
        frag_lib = vert_lib;
    } else {
        frag_lib = compile_library(device, frag_src, error_buf, error_cap);
        if (frag_lib == nil) return NULL;
    }

    // Prefer "vertexMain"/"fragmentMain" then fall back to first function in library.
    id<MTLFunction> vert_fn = [vert_lib newFunctionWithName:@"vertexMain"];
    if (vert_fn == nil) vert_fn = [vert_lib newFunctionWithName:@"v_noop"];
    id<MTLFunction> frag_fn = [frag_lib newFunctionWithName:@"fragmentMain"];
    if (frag_fn == nil) frag_fn = [frag_lib newFunctionWithName:@"f_noop"];

    if (vert_fn == nil || frag_fn == nil) {
        if (error_buf && error_cap) strncpy(error_buf, "render shader functions not found", error_cap - 1);
        return NULL;
    }

    MTLRenderPipelineDescriptor* desc = [MTLRenderPipelineDescriptor new];
    desc.vertexFunction   = vert_fn;
    desc.fragmentFunction = frag_fn;

    // Sample count (MSAA).
    uint32_t sc = (sample_count > 1) ? sample_count : 1;
    desc.rasterSampleCount = sc;

    // Alpha-to-coverage.
    desc.alphaToCoverageEnabled = (alpha_to_coverage != 0) ? YES : NO;

    // Color attachment 0 — pixel format and blend state.
    MTLRenderPipelineColorAttachmentDescriptor* ca = desc.colorAttachments[0];
    ca.pixelFormat = wgpu_format(pixel_format);

    if (blend != NULL && blend->blend_enabled) {
        ca.blendingEnabled             = YES;
        ca.rgbBlendOperation           = wgpu_blend_op(blend->color_operation);
        ca.sourceRGBBlendFactor        = wgpu_blend_factor(blend->color_src_factor);
        ca.destinationRGBBlendFactor   = wgpu_blend_factor(blend->color_dst_factor);
        ca.alphaBlendOperation         = wgpu_blend_op(blend->alpha_operation);
        ca.sourceAlphaBlendFactor      = wgpu_blend_factor(blend->alpha_src_factor);
        ca.destinationAlphaBlendFactor = wgpu_blend_factor(blend->alpha_dst_factor);
        ca.writeMask                   = wgpu_write_mask(blend->write_mask);
    } else {
        ca.blendingEnabled = NO;
        // Default: all channels written.
        ca.writeMask = (blend != NULL)
            ? wgpu_write_mask(blend->write_mask)
            : MTLColorWriteMaskAll;
    }

    // Depth/stencil attachment pixel format (pipeline-side declaration only).
    if (depth_stencil != NULL && depth_stencil->depth_stencil_format != 0) {
        MTLPixelFormat ds_fmt = wgpu_format(depth_stencil->depth_stencil_format);
        // Separate depth vs combined depth+stencil.
        switch (ds_fmt) {
            case MTLPixelFormatDepth32Float:
            case MTLPixelFormatDepth16Unorm:
                desc.depthAttachmentPixelFormat = ds_fmt;
                break;
            case MTLPixelFormatStencil8:
                desc.stencilAttachmentPixelFormat = ds_fmt;
                break;
            case MTLPixelFormatDepth32Float_Stencil8:
                desc.depthAttachmentPixelFormat   = ds_fmt;
                desc.stencilAttachmentPixelFormat = ds_fmt;
                break;
            default:
                desc.depthAttachmentPixelFormat = ds_fmt;
                break;
        }
    }

    if (support_icb) {
        desc.supportIndirectCommandBuffers = YES;
    }

    NSError* err = nil;
    id<MTLRenderPipelineState> pso = [device newRenderPipelineStateWithDescriptor:desc error:&err];
    if (pso == nil) {
        write_err(err, error_buf, error_cap);
        return NULL;
    }
    return (MetalHandle)CFBridgingRetain(pso);
}

// ============================================================
// Depth/stencil state object
// ============================================================

MetalHandle metal_render_state_new_depth_stencil_state(
    MetalHandle                    device_h,
    const MetalDepthStencilConfig* cfg)
{
    if (cfg == NULL) return NULL;
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;

    MTLDepthStencilDescriptor* desc = [MTLDepthStencilDescriptor new];
    desc.depthWriteEnabled = (cfg->depth_write_enabled != 0) ? YES : NO;
    desc.depthCompareFunction = wgpu_compare(cfg->depth_compare);

    // Front face stencil
    MTLStencilDescriptor* front = [MTLStencilDescriptor new];
    front.stencilCompareFunction = wgpu_compare(cfg->stencil_front_compare);
    front.stencilFailureOperation    = wgpu_stencil_op(cfg->stencil_front_fail_op);
    front.depthFailureOperation      = wgpu_stencil_op(cfg->stencil_front_depth_fail);
    front.depthStencilPassOperation  = wgpu_stencil_op(cfg->stencil_front_pass_op);
    front.readMask  = cfg->stencil_read_mask;
    front.writeMask = cfg->stencil_write_mask;
    desc.frontFaceStencil = front;

    // Back face stencil
    MTLStencilDescriptor* back = [MTLStencilDescriptor new];
    back.stencilCompareFunction = wgpu_compare(cfg->stencil_back_compare);
    back.stencilFailureOperation    = wgpu_stencil_op(cfg->stencil_back_fail_op);
    back.depthFailureOperation      = wgpu_stencil_op(cfg->stencil_back_depth_fail);
    back.depthStencilPassOperation  = wgpu_stencil_op(cfg->stencil_back_pass_op);
    back.readMask  = cfg->stencil_read_mask;
    back.writeMask = cfg->stencil_write_mask;
    desc.backFaceStencil = back;

    id<MTLDepthStencilState> state = [device newDepthStencilStateWithDescriptor:desc];
    if (state == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(state);
}

void metal_render_state_set_depth_stencil_state(
    MetalHandle encoder_h,
    MetalHandle ds_state_h)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLDepthStencilState>    state   = (__bridge id<MTLDepthStencilState>)ds_state_h;
    [encoder setDepthStencilState:state];
}

// ============================================================
// MSAA texture and MSAA render pass
// ============================================================

MetalHandle metal_render_state_new_msaa_texture(
    MetalHandle device_h,
    uint32_t    width,
    uint32_t    height,
    uint32_t    pixel_format,
    uint32_t    sample_count)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;

    MTLTextureDescriptor* desc = [MTLTextureDescriptor new];
    desc.textureType    = MTLTextureType2DMultisample;
    desc.pixelFormat    = wgpu_format(pixel_format);
    desc.width          = (NSUInteger)width;
    desc.height         = (NSUInteger)height;
    desc.sampleCount    = (NSUInteger)(sample_count > 1 ? sample_count : 4);
    desc.mipmapLevelCount = 1;
    desc.usage          = MTLTextureUsageRenderTarget;
    // Memoryless is preferred for transient MSAA surfaces on Apple Silicon:
    // the GPU resolves before the tile data is ever flushed to DRAM.
    desc.storageMode    = MTLStorageModeMemoryless;
    desc.hazardTrackingMode = MTLHazardTrackingModeUntracked;

    id<MTLTexture> tex = [device newTextureWithDescriptor:desc];
    if (tex == nil) {
        // Fall back to private storage if memoryless allocation fails.
        desc.storageMode = MTLStorageModePrivate;
        tex = [device newTextureWithDescriptor:desc];
    }
    if (tex == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(tex);
}

MetalHandle metal_render_state_cmd_buf_msaa_render_encoder(
    MetalHandle cmd_buf_h,
    MetalHandle pipeline_h,
    MetalHandle msaa_texture_h,
    MetalHandle resolve_target_h)
{
    id<MTLCommandBuffer>        cmd_buf        = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLRenderPipelineState>  pipeline       = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    id<MTLTexture>              msaa_texture   = (__bridge id<MTLTexture>)msaa_texture_h;
    id<MTLTexture>              resolve_target = (__bridge id<MTLTexture>)resolve_target_h;

    MTLRenderPassDescriptor* pass = [MTLRenderPassDescriptor new];
    pass.colorAttachments[0].texture       = msaa_texture;
    pass.colorAttachments[0].resolveTexture = resolve_target;
    // StoreAndMultisampleResolve: resolve the MSAA surface into the resolve target
    // in one pass — no explicit blit needed.
    pass.colorAttachments[0].loadAction   = MTLLoadActionDontCare;
    pass.colorAttachments[0].storeAction  = MTLStoreActionMultisampleResolve;

    id<MTLRenderCommandEncoder> encoder = [cmd_buf renderCommandEncoderWithDescriptor:pass];
    if (encoder == nil) return NULL;
    [encoder setRenderPipelineState:pipeline];
    // Return +1 retained; caller must call endEncoding then metal_bridge_release.
    return (MetalHandle)CFBridgingRetain(encoder);
}
