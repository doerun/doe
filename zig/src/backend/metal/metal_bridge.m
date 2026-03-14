#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <QuartzCore/QuartzCore.h>
#include "metal_bridge.h"
#include <string.h>
#include <sched.h>

// CFBridging provides correct ARC-safe transfer across the void* boundary.
// Each returned MetalHandle is +1 retained and owned by the caller.
// metal_bridge_release() must be called to balance.

// ============================================================
// Cached render pass descriptor (avoids alloc per render command)
// ============================================================

static MTLRenderPassDescriptor* _cachedRenderPassDesc = nil;
static id<MTLTexture> _cachedRenderPassTarget = nil;
static id<MTLTexture> _cachedDepthTarget = nil;

static MTLRenderPassDescriptor* cachedRenderPassDescriptor(id<MTLTexture> target, id<MTLTexture> depth_target, BOOL use_depth_store) {
    if (_cachedRenderPassDesc == nil) {
        _cachedRenderPassDesc = [MTLRenderPassDescriptor new];
        _cachedRenderPassDesc.colorAttachments[0].loadAction  = MTLLoadActionDontCare;
        _cachedRenderPassDesc.colorAttachments[0].storeAction = MTLStoreActionDontCare;
    }
    if (_cachedRenderPassTarget != target) {
        _cachedRenderPassDesc.colorAttachments[0].texture = target;
        _cachedRenderPassTarget = target;
    }
    if (_cachedDepthTarget != depth_target) {
        _cachedRenderPassDesc.depthAttachment.texture = depth_target;
        _cachedDepthTarget = depth_target;
    }
    if (depth_target != nil) {
        _cachedRenderPassDesc.depthAttachment.loadAction = MTLLoadActionClear;
        _cachedRenderPassDesc.depthAttachment.storeAction = use_depth_store ? MTLStoreActionStore : MTLStoreActionDontCare;
        _cachedRenderPassDesc.depthAttachment.clearDepth = 1.0;
    } else {
        _cachedRenderPassDesc.depthAttachment.texture = nil;
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
        case 0x0000002F: return MTLPixelFormatDepth32Float;
        case 0x00000030: return MTLPixelFormatDepth32Float;
        default:         return MTLPixelFormatRGBA8Unorm;
    }
}

static MTLPrimitiveType wgpu_to_mtl_primitive(uint32_t topology) {
    switch (topology) {
        case 0x00000001: return MTLPrimitiveTypePoint;
        case 0x00000002: return MTLPrimitiveTypeLine;
        case 0x00000003: return MTLPrimitiveTypeLineStrip;
        case 0x00000005: return MTLPrimitiveTypeTriangleStrip;
        case 0x00000004:
        default: return MTLPrimitiveTypeTriangle;
    }
}

static MTLWinding wgpu_to_mtl_winding(uint32_t front_face) {
    return front_face == 0x00000002 ? MTLWindingClockwise : MTLWindingCounterClockwise;
}

static MTLCullMode wgpu_to_mtl_cull(uint32_t cull_mode) {
    switch (cull_mode) {
        case 0x00000002: return MTLCullModeFront;
        case 0x00000003: return MTLCullModeBack;
        case 0x00000001:
        default: return MTLCullModeNone;
    }
}

static MTLCompareFunction wgpu_to_mtl_compare(uint32_t compare_fn) {
    switch (compare_fn) {
        case 0x00000001: return MTLCompareFunctionNever;
        case 0x00000002: return MTLCompareFunctionLess;
        case 0x00000003: return MTLCompareFunctionEqual;
        case 0x00000004: return MTLCompareFunctionLessEqual;
        case 0x00000005: return MTLCompareFunctionGreater;
        case 0x00000006: return MTLCompareFunctionNotEqual;
        case 0x00000007: return MTLCompareFunctionGreaterEqual;
        case 0x00000008: return MTLCompareFunctionAlways;
        default: return MTLCompareFunctionAlways;
    }
}

static MTLVertexFormat wgpu_to_mtl_vertex_format(uint32_t format) {
    switch (format) {
        case 0x00000019: return MTLVertexFormatFloat;
        case 0x0000001A: return MTLVertexFormatFloat2;
        case 0x0000001B: return MTLVertexFormatFloat3;
        case 0x0000001C: return MTLVertexFormatFloat4;
        case 0x00000001: return MTLVertexFormatUChar2Normalized;
        case 0x00000002: return MTLVertexFormatUChar4Normalized;
        case 0x00000003: return MTLVertexFormatChar2Normalized;
        case 0x00000004: return MTLVertexFormatChar4Normalized;
        case 0x0000000D: return MTLVertexFormatUShort2Normalized;
        case 0x0000000E: return MTLVertexFormatUShort4Normalized;
        case 0x0000000F: return MTLVertexFormatShort2Normalized;
        case 0x00000010: return MTLVertexFormatShort4Normalized;
        case 0x00000015: return MTLVertexFormatHalf2;
        case 0x00000016: return MTLVertexFormatHalf4;
        case 0x00000021: return MTLVertexFormatUInt;
        case 0x00000022: return MTLVertexFormatUInt2;
        case 0x00000023: return MTLVertexFormatUInt3;
        case 0x00000024: return MTLVertexFormatUInt4;
        case 0x00000025: return MTLVertexFormatInt;
        case 0x00000026: return MTLVertexFormatInt2;
        case 0x00000027: return MTLVertexFormatInt3;
        case 0x00000028: return MTLVertexFormatInt4;
        default: return MTLVertexFormatInvalid;
    }
}

static MTLIndexType wgpu_to_mtl_index_type(uint32_t format) {
    return format == 0x00000002 ? MTLIndexTypeUInt32 : MTLIndexTypeUInt16;
}

// ============================================================
// Core device / buffer / blit
// ============================================================

@interface MetalSurfaceHost : NSObject
@property(nonatomic, strong) NSWindow* window;
@property(nonatomic, strong) NSView* view;
@property(nonatomic, strong) CAMetalLayer* layer;
- (instancetype)initOffscreen;
- (void)configureWithWidth:(uint32_t)width height:(uint32_t)height;
@end

@implementation MetalSurfaceHost

- (instancetype)initOffscreen {
    self = [super init];
    if (self == nil) {
        return nil;
    }

    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];

    NSRect frame = NSMakeRect(0.0, 0.0, 64.0, 64.0);
    self.window = [[NSWindow alloc] initWithContentRect:frame
                                              styleMask:NSWindowStyleMaskBorderless
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    if (self.window == nil) {
        return nil;
    }
    [self.window setReleasedWhenClosed:NO];
    [self.window setOpaque:YES];
    [self.window setAlphaValue:1.0];
    [self.window setIgnoresMouseEvents:YES];

    self.view = [[NSView alloc] initWithFrame:frame];
    [self.view setWantsLayer:YES];

    self.layer = [CAMetalLayer layer];
    [self.layer setContentsScale:1.0];
    [self.layer setOpaque:YES];

    [self.view setLayer:self.layer];
    [self.window setContentView:self.view];
    [self.window orderFrontRegardless];
    return self;
}

- (void)configureWithWidth:(uint32_t)width height:(uint32_t)height {
    CGFloat w = (CGFloat)width;
    CGFloat h = (CGFloat)height;
    NSRect frame = NSMakeRect(0.0, 0.0, w, h);
    [self.window setFrame:frame display:NO];
    [self.view setFrame:NSMakeRect(0.0, 0.0, w, h)];
    [self.layer setFrame:CGRectMake(0.0, 0.0, w, h)];
    [self.layer setBounds:CGRectMake(0.0, 0.0, w, h)];
    [self.layer setDrawableSize:CGSizeMake(w, h)];
    [self.window orderFrontRegardless];
    [self.window displayIfNeeded];
    [self.view displayIfNeeded];
    [CATransaction flush];
}

@end

MetalHandle metal_bridge_create_default_device(void) {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(device);
}

MetalHandle metal_bridge_create_surface_host(MetalHandle* layer_out) {
    MetalSurfaceHost* host = [[MetalSurfaceHost alloc] initOffscreen];
    if (host == nil || host.layer == nil) return NULL;
    if (layer_out != NULL) {
        *layer_out = (__bridge MetalHandle)host.layer;
    }
    return (MetalHandle)CFBridgingRetain(host);
}

void metal_bridge_configure_surface_host(MetalHandle host_h, uint32_t width, uint32_t height) {
    MetalSurfaceHost* host = (__bridge MetalSurfaceHost*)host_h;
    if (host == nil) return;
    [host configureWithWidth:width height:height];
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

void metal_bridge_command_buffer_spin_wait(MetalHandle cmd_buf_h) {
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    while ([cmd_buf status] < MTLCommandBufferStatusCompleted) {
        /* spin */
    }
}

static volatile int32_t _atomic_done = 0;
void metal_bridge_command_buffer_setup_atomic_wait(MetalHandle cmd_buf_h) {
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    __atomic_store_n(&_atomic_done, 0, __ATOMIC_RELEASE);
    [cmd_buf addCompletedHandler:^(id<MTLCommandBuffer> _Nonnull cb) {
        __atomic_store_n(&_atomic_done, 1, __ATOMIC_RELEASE);
    }];
}

void metal_bridge_command_buffer_atomic_wait(void) {
    while (!__atomic_load_n(&_atomic_done, __ATOMIC_ACQUIRE)) {
        /* spin — no kernel call */
    }
}

// ============================================================
// Streaming Blit Encoder
// ============================================================

MetalHandle metal_bridge_begin_blit_encoding(MetalHandle queue_h, MetalHandle* encoder_out) {
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;
    id<MTLBlitCommandEncoder> encoder = [cmd_buf blitCommandEncoder];
    if (encoder == nil) return NULL;
    *encoder_out = (__bridge MetalHandle)encoder; // unretained — lifetime tied to cmd_buf
    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

void metal_bridge_blit_encoder_copy(
    MetalHandle encoder_h,
    MetalHandle src_h,
    MetalHandle dst_h,
    size_t      byte_count)
{
    id<MTLBlitCommandEncoder> encoder = (__bridge id<MTLBlitCommandEncoder>)encoder_h;
    id<MTLBuffer> src = (__bridge id<MTLBuffer>)src_h;
    id<MTLBuffer> dst = (__bridge id<MTLBuffer>)dst_h;
    [encoder copyFromBuffer:src sourceOffset:0
                   toBuffer:dst destinationOffset:0
                       size:byte_count];
}

void metal_bridge_blit_encoder_copy_region(
    MetalHandle encoder_h,
    MetalHandle src_h,
    uint64_t    src_offset,
    MetalHandle dst_h,
    uint64_t    dst_offset,
    uint64_t    size)
{
    id<MTLBlitCommandEncoder> encoder = (__bridge id<MTLBlitCommandEncoder>)encoder_h;
    id<MTLBuffer> src = (__bridge id<MTLBuffer>)src_h;
    id<MTLBuffer> dst = (__bridge id<MTLBuffer>)dst_h;
    [encoder copyFromBuffer:src
               sourceOffset:(NSUInteger)src_offset
                   toBuffer:dst
          destinationOffset:(NSUInteger)dst_offset
                       size:(NSUInteger)size];
}

void metal_bridge_blit_encoder_copy_buffer_to_texture(
    MetalHandle encoder_h,
    MetalHandle src_h,
    uint64_t    src_offset,
    uint32_t    src_bytes_per_row,
    uint32_t    src_rows_per_image,
    MetalHandle dst_texture_h,
    uint32_t    dst_mip_level,
    uint32_t    width,
    uint32_t    height,
    uint32_t    depth_or_array_layers)
{
    id<MTLBlitCommandEncoder> encoder = (__bridge id<MTLBlitCommandEncoder>)encoder_h;
    id<MTLBuffer> src = (__bridge id<MTLBuffer>)src_h;
    id<MTLTexture> dst = (__bridge id<MTLTexture>)dst_texture_h;
    MTLSize copy_size = MTLSizeMake(width, height, depth_or_array_layers);
    [encoder copyFromBuffer:src
               sourceOffset:(NSUInteger)src_offset
          sourceBytesPerRow:(NSUInteger)src_bytes_per_row
        sourceBytesPerImage:(NSUInteger)src_rows_per_image * (NSUInteger)src_bytes_per_row
                 sourceSize:copy_size
                  toTexture:dst
           destinationSlice:0
           destinationLevel:(NSUInteger)dst_mip_level
          destinationOrigin:MTLOriginMake(0, 0, 0)];
}

void metal_bridge_blit_encoder_copy_texture_to_buffer(
    MetalHandle encoder_h,
    MetalHandle src_texture_h,
    uint32_t    src_mip_level,
    MetalHandle dst_h,
    uint64_t    dst_offset,
    uint32_t    dst_bytes_per_row,
    uint32_t    dst_rows_per_image,
    uint32_t    width,
    uint32_t    height,
    uint32_t    depth_or_array_layers)
{
    id<MTLBlitCommandEncoder> encoder = (__bridge id<MTLBlitCommandEncoder>)encoder_h;
    id<MTLTexture> src = (__bridge id<MTLTexture>)src_texture_h;
    id<MTLBuffer> dst = (__bridge id<MTLBuffer>)dst_h;
    MTLSize copy_size = MTLSizeMake(width, height, depth_or_array_layers);
    [encoder copyFromTexture:src
                 sourceSlice:0
                 sourceLevel:(NSUInteger)src_mip_level
                sourceOrigin:MTLOriginMake(0, 0, 0)
                  sourceSize:copy_size
                    toBuffer:dst
           destinationOffset:(NSUInteger)dst_offset
      destinationBytesPerRow:(NSUInteger)dst_bytes_per_row
    destinationBytesPerImage:(NSUInteger)dst_rows_per_image * (NSUInteger)dst_bytes_per_row];
}

void metal_bridge_blit_encoder_copy_texture_to_texture(
    MetalHandle encoder_h,
    MetalHandle src_texture_h,
    uint32_t    src_mip_level,
    MetalHandle dst_texture_h,
    uint32_t    dst_mip_level,
    uint32_t    width,
    uint32_t    height,
    uint32_t    depth_or_array_layers)
{
    id<MTLBlitCommandEncoder> encoder = (__bridge id<MTLBlitCommandEncoder>)encoder_h;
    id<MTLTexture> src = (__bridge id<MTLTexture>)src_texture_h;
    id<MTLTexture> dst = (__bridge id<MTLTexture>)dst_texture_h;
    MTLSize copy_size = MTLSizeMake(width, height, depth_or_array_layers);
    [encoder copyFromTexture:src
                 sourceSlice:0
                 sourceLevel:(NSUInteger)src_mip_level
                sourceOrigin:MTLOriginMake(0, 0, 0)
                  sourceSize:copy_size
                   toTexture:dst
            destinationSlice:0
            destinationLevel:(NSUInteger)dst_mip_level
           destinationOrigin:MTLOriginMake(0, 0, 0)];
}

void metal_bridge_end_blit_encoding(MetalHandle encoder_h) {
    id<MTLBlitCommandEncoder> encoder = (__bridge id<MTLBlitCommandEncoder>)encoder_h;
    [encoder endEncoding];
}

// ============================================================
// Shared Event (lightweight GPU fence)
// ============================================================

MetalHandle metal_bridge_device_new_shared_event(MetalHandle device_h) {
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    id<MTLSharedEvent> event = [device newSharedEvent];
    if (event == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(event);
}

uint64_t metal_bridge_shared_event_signaled_value(MetalHandle event_h) {
    id<MTLSharedEvent> event = (__bridge id<MTLSharedEvent>)event_h;
    return event.signaledValue;
}

void metal_bridge_command_buffer_encode_signal_event(
    MetalHandle cmd_buf_h,
    MetalHandle event_h,
    uint64_t    value)
{
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLSharedEvent>   event   = (__bridge id<MTLSharedEvent>)event_h;
    [cmd_buf encodeSignalEvent:event value:value];
}

void metal_bridge_shared_event_wait(MetalHandle event_h, uint64_t value) {
    id<MTLSharedEvent> event = (__bridge id<MTLSharedEvent>)event_h;
    // Quick check: often the GPU has already completed by the time we get here.
    if (event.signaledValue >= value) return;
    // Spin with ARM yield hint. Covers ~500us of GPU scheduling delay at ~5ns/iter.
    // Most dispatches complete within 50-200us; extended spin avoids sched_yield tail.
    for (int i = 0; i < 100000; i++) {
        if (event.signaledValue >= value) return;
#if defined(__aarch64__) || defined(__arm64__)
        __asm__ volatile ("yield");
#endif
    }
    // Fallback: yield to OS scheduler for truly long waits.
    while (event.signaledValue < value) {
        sched_yield();
    }
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
// Streaming Command Buffer (shared across blit/render/compute)
// ============================================================

MetalHandle metal_bridge_create_command_buffer(MetalHandle queue_h) {
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

MetalHandle metal_bridge_cmd_buf_blit_encoder(MetalHandle cmd_buf_h) {
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLBlitCommandEncoder> encoder = [cmd_buf blitCommandEncoder];
    if (encoder == nil) return NULL;
    return (__bridge MetalHandle)encoder; // unretained — lifetime tied to cmd_buf
}

void metal_bridge_cmd_buf_encode_render_pass(
    MetalHandle cmd_buf_h,
    MetalHandle pipeline_h,
    MetalHandle target_h,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    int         redundant_pipeline,
    int         redundant_bindgroup)
{
    (void)redundant_bindgroup;
    id<MTLCommandBuffer>        cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLRenderPipelineState>  pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    id<MTLTexture>              target   = (__bridge id<MTLTexture>)target_h;

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target, nil, NO);
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
}

void metal_bridge_cmd_buf_encode_icb_render_pass(
    MetalHandle cmd_buf_h,
    MetalHandle pipeline_h,
    MetalHandle icb_h,
    MetalHandle target_h,
    uint32_t    draw_count)
{
    id<MTLCommandBuffer>         cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLRenderPipelineState>   pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    id<MTLIndirectCommandBuffer> icb      = (__bridge id<MTLIndirectCommandBuffer>)icb_h;
    id<MTLTexture>               target   = (__bridge id<MTLTexture>)target_h;

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target, nil, NO);
    id<MTLRenderCommandEncoder> encoder = [cmd_buf renderCommandEncoderWithDescriptor:pass];
    [encoder setRenderPipelineState:pipeline];
    [encoder executeCommandsInBuffer:icb withRange:NSMakeRange(0, draw_count)];
    [encoder endEncoding];
}

// === Cached render encoder (kept open across render_draw calls) ===

MetalHandle metal_bridge_cmd_buf_render_encoder(
    MetalHandle cmd_buf_h,
    MetalHandle pipeline_h,
    MetalHandle target_h,
    MetalHandle depth_target_h,
    int         use_depth_store)
{
    id<MTLCommandBuffer>        cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLRenderPipelineState>  pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    id<MTLTexture>              target   = (__bridge id<MTLTexture>)target_h;
    id<MTLTexture>              depth_target = (__bridge id<MTLTexture>)depth_target_h;

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target, depth_target, use_depth_store ? YES : NO);
    id<MTLRenderCommandEncoder> encoder = [cmd_buf renderCommandEncoderWithDescriptor:pass];
    if (encoder == nil) return NULL;
    [encoder setRenderPipelineState:pipeline];
    return (MetalHandle)CFBridgingRetain(encoder); // +1 retained; caller must release
}

void metal_bridge_render_encoder_set_bind_buffer(
    MetalHandle encoder_h,
    uint32_t    slot,
    MetalHandle buffer_h,
    uint64_t    offset)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLBuffer> buffer = (__bridge id<MTLBuffer>)buffer_h;
    [encoder setVertexBuffer:buffer offset:(NSUInteger)offset atIndex:slot];
    [encoder setFragmentBuffer:buffer offset:(NSUInteger)offset atIndex:slot];
}

void metal_bridge_render_encoder_set_bind_texture(
    MetalHandle encoder_h,
    uint32_t    slot,
    MetalHandle texture_h)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLTexture> texture = (__bridge id<MTLTexture>)texture_h;
    [encoder setVertexTexture:texture atIndex:slot];
    [encoder setFragmentTexture:texture atIndex:slot];
}

void metal_bridge_render_encoder_set_bind_sampler(
    MetalHandle encoder_h,
    uint32_t    slot,
    MetalHandle sampler_h)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLSamplerState> sampler = (__bridge id<MTLSamplerState>)sampler_h;
    [encoder setVertexSamplerState:sampler atIndex:slot];
    [encoder setFragmentSamplerState:sampler atIndex:slot];
}

void metal_bridge_render_encoder_set_vertex_buffer(
    MetalHandle encoder_h,
    uint32_t    slot,
    MetalHandle buffer_h,
    uint64_t    offset)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLBuffer> buffer = (__bridge id<MTLBuffer>)buffer_h;
    [encoder setVertexBuffer:buffer offset:(NSUInteger)offset atIndex:slot];
}

void metal_bridge_render_encoder_set_depth_stencil_state(
    MetalHandle encoder_h,
    MetalHandle depth_state_h)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLDepthStencilState> depth_state = (__bridge id<MTLDepthStencilState>)depth_state_h;
    [encoder setDepthStencilState:depth_state];
}

void metal_bridge_render_encoder_set_depth_stencil_values(
    MetalHandle encoder_h,
    uint32_t    compare_fn,
    int         write_enabled)
{
    (void)encoder_h;
    (void)compare_fn;
    (void)write_enabled;
}

void metal_bridge_render_encoder_set_front_facing(
    MetalHandle encoder_h,
    uint32_t    front_face)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    [encoder setFrontFacingWinding:wgpu_to_mtl_winding(front_face)];
}

void metal_bridge_render_encoder_set_cull_mode(
    MetalHandle encoder_h,
    uint32_t    cull_mode)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    [encoder setCullMode:wgpu_to_mtl_cull(cull_mode)];
}

void metal_bridge_render_encoder_draw(
    MetalHandle encoder_h,
    uint32_t    topology,
    uint32_t    draw_count,
    uint32_t    vertex_count,
    uint32_t    instance_count,
    uint32_t    first_vertex,
    uint32_t    first_instance,
    int         redundant_pipeline,
    MetalHandle pipeline_h)
{
    id<MTLRenderCommandEncoder> encoder  = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLRenderPipelineState>  pipeline = (__bridge id<MTLRenderPipelineState>)pipeline_h;
    const MTLPrimitiveType primitive = wgpu_to_mtl_primitive(topology);

    for (uint32_t i = 0; i < draw_count; i++) {
        if (redundant_pipeline) {
            [encoder setRenderPipelineState:pipeline];
        }
        [encoder drawPrimitives:primitive
                    vertexStart:first_vertex
                    vertexCount:vertex_count
                  instanceCount:instance_count
                    baseInstance:first_instance];
    }
}

void metal_bridge_render_encoder_draw_indexed(
    MetalHandle encoder_h,
    uint32_t    topology,
    uint32_t    draw_count,
    uint32_t    index_count,
    uint32_t    instance_count,
    MetalHandle index_buffer_h,
    uint64_t    index_offset,
    uint32_t    index_format,
    int32_t     base_vertex,
    uint32_t    first_instance)
{
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLBuffer> index_buffer = (__bridge id<MTLBuffer>)index_buffer_h;
    const MTLPrimitiveType primitive = wgpu_to_mtl_primitive(topology);
    const MTLIndexType index_type = wgpu_to_mtl_index_type(index_format);
    for (uint32_t i = 0; i < draw_count; i++) {
        [encoder drawIndexedPrimitives:primitive
                            indexCount:index_count
                             indexType:index_type
                           indexBuffer:index_buffer
                     indexBufferOffset:(NSUInteger)index_offset
                         instanceCount:instance_count
                            baseVertex:base_vertex
                          baseInstance:first_instance];
    }
}

void metal_bridge_render_encoder_execute_icb(
    MetalHandle encoder_h,
    MetalHandle icb_h,
    uint32_t    draw_count)
{
    id<MTLRenderCommandEncoder>  encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    id<MTLIndirectCommandBuffer> icb     = (__bridge id<MTLIndirectCommandBuffer>)icb_h;
    [encoder executeCommandsInBuffer:icb withRange:NSMakeRange(0, draw_count)];
}

void metal_bridge_render_encoder_end(MetalHandle encoder_h) {
    id<MTLRenderCommandEncoder> encoder = (__bridge id<MTLRenderCommandEncoder>)encoder_h;
    [encoder endEncoding];
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

    NSUInteger max_tg = pipeline.maxTotalThreadsPerThreadgroup;
    if (max_tg == 0) max_tg = 256;
    MTLSize tg_size;
    if (y > 1) {
        NSUInteger tg_x = (NSUInteger)sqrt((double)max_tg);
        while (tg_x > 1 && max_tg % tg_x != 0) tg_x--;
        tg_size = MTLSizeMake(tg_x, max_tg / tg_x, 1);
    } else {
        tg_size = MTLSizeMake(max_tg, 1, 1);
    }
    MTLSize grid_size  = MTLSizeMake(x, y, z);
    [encoder dispatchThreadgroups:grid_size threadsPerThreadgroup:tg_size];
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

void metal_bridge_cmd_buf_encode_blit_copy(
    MetalHandle cmd_buf_h,
    MetalHandle src_h,
    uint64_t    src_offset,
    MetalHandle dst_h,
    uint64_t    dst_offset,
    uint64_t    size)
{
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLBuffer> src = (__bridge id<MTLBuffer>)src_h;
    id<MTLBuffer> dst = (__bridge id<MTLBuffer>)dst_h;
    id<MTLBlitCommandEncoder> encoder = [cmd_buf blitCommandEncoder];
    [encoder copyFromBuffer:src sourceOffset:(NSUInteger)src_offset
                   toBuffer:dst destinationOffset:(NSUInteger)dst_offset
                       size:(NSUInteger)size];
    [encoder endEncoding];
}

void metal_bridge_cmd_buf_encode_compute_dispatch(
    MetalHandle  cmd_buf_h,
    MetalHandle  pipeline_h,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    uint32_t     x,
    uint32_t     y,
    uint32_t     z,
    uint32_t     wg_x,
    uint32_t     wg_y,
    uint32_t     wg_z)
{
    id<MTLCommandBuffer>         cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLComputePipelineState>  pipeline = (__bridge id<MTLComputePipelineState>)pipeline_h;

    id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];
    [encoder setComputePipelineState:pipeline];

    for (uint32_t i = 0; i < buffer_count; i++) {
        if (buffers[i] != NULL) {
            id<MTLBuffer> buf = (__bridge id<MTLBuffer>)buffers[i];
            [encoder setBuffer:buf offset:0 atIndex:i];
        }
    }

    // Use shader-declared workgroup size when available; fall back to pipeline max.
    MTLSize tg_size;
    if (wg_x > 0) {
        tg_size = MTLSizeMake(wg_x, wg_y > 0 ? wg_y : 1, wg_z > 0 ? wg_z : 1);
    } else {
        NSUInteger max_tg = pipeline.maxTotalThreadsPerThreadgroup;
        if (max_tg == 0) max_tg = 256;
        tg_size = MTLSizeMake(max_tg, 1, 1);
    }
    MTLSize grid_size = MTLSizeMake(x, y, z);
    [encoder dispatchThreadgroups:grid_size threadsPerThreadgroup:tg_size];
    [encoder endEncoding];
}

void metal_bridge_cmd_buf_encode_compute_dispatch_indirect(
    MetalHandle  cmd_buf_h,
    MetalHandle  pipeline_h,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    MetalHandle  indirect_buffer_h,
    uint64_t     indirect_offset,
    uint32_t     wg_x,
    uint32_t     wg_y,
    uint32_t     wg_z)
{
    id<MTLCommandBuffer>         cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<MTLComputePipelineState>  pipeline = (__bridge id<MTLComputePipelineState>)pipeline_h;
    id<MTLBuffer>                indirect = (__bridge id<MTLBuffer>)indirect_buffer_h;

    id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];
    [encoder setComputePipelineState:pipeline];

    for (uint32_t i = 0; i < buffer_count; i++) {
        if (buffers[i] != NULL) {
            id<MTLBuffer> buf = (__bridge id<MTLBuffer>)buffers[i];
            [encoder setBuffer:buf offset:0 atIndex:i];
        }
    }

    MTLSize tg_size;
    if (wg_x > 0) {
        tg_size = MTLSizeMake(wg_x, wg_y > 0 ? wg_y : 1, wg_z > 0 ? wg_z : 1);
    } else {
        NSUInteger max_tg = pipeline.maxTotalThreadsPerThreadgroup;
        if (max_tg == 0) max_tg = 256;
        tg_size = MTLSizeMake(max_tg, 1, 1);
    }
    [encoder dispatchThreadgroupsWithIndirectBuffer:indirect
                               indirectBufferOffset:(NSUInteger)indirect_offset
                              threadsPerThreadgroup:tg_size];
    [encoder endEncoding];
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

    NSUInteger max_tg = pipeline.maxTotalThreadsPerThreadgroup;
    if (max_tg == 0) max_tg = 256;
    MTLSize tg_size;
    if (y > 1) {
        // 2D grid: distribute threadgroup threads across X and Y.
        NSUInteger tg_x = (NSUInteger)sqrt((double)max_tg);
        while (tg_x > 1 && max_tg % tg_x != 0) tg_x--;
        tg_size = MTLSizeMake(tg_x, max_tg / tg_x, 1);
    } else {
        tg_size = MTLSizeMake(max_tg, 1, 1);
    }
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

MetalHandle metal_bridge_device_new_render_pipeline_functions(
    MetalHandle device_h,
    MetalHandle vertex_function_h,
    MetalHandle fragment_function_h,
    uint32_t    pixel_format,
    char*       error_buf,
    size_t      error_cap)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    id<MTLFunction> vert_fn = (__bridge id<MTLFunction>)vertex_function_h;
    id<MTLFunction> frag_fn = (__bridge id<MTLFunction>)fragment_function_h;
    if (device == nil || vert_fn == nil || frag_fn == nil) {
        if (error_buf && error_cap) {
            strncpy(error_buf, "render pipeline requires valid vertex and fragment functions", error_cap - 1);
            error_buf[error_cap - 1] = '\0';
        }
        return NULL;
    }

    NSError* err = nil;
    MTLRenderPipelineDescriptor* desc = [MTLRenderPipelineDescriptor new];
    desc.vertexFunction = vert_fn;
    desc.fragmentFunction = frag_fn;
    desc.colorAttachments[0].pixelFormat = wgpu_to_mtl_format(pixel_format);

    id<MTLRenderPipelineState> pso = [device newRenderPipelineStateWithDescriptor:desc error:&err];
    if (pso == nil) { write_error(err, error_buf, error_cap); return NULL; }
    return (MetalHandle)CFBridgingRetain(pso);
}

MetalHandle metal_bridge_device_new_render_pipeline_full(
    MetalHandle                     device_h,
    MetalHandle                     vertex_function_h,
    MetalHandle                     fragment_function_h,
    uint32_t                        pixel_format,
    uint32_t                        depth_format,
    const MetalVertexBufferLayout*  vertex_layouts,
    uint32_t                        vertex_layout_count,
    const MetalVertexAttributeDesc* vertex_attributes,
    uint32_t                        vertex_attribute_count,
    char*                           error_buf,
    size_t                          error_cap)
{
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    id<MTLFunction> vert_fn = (__bridge id<MTLFunction>)vertex_function_h;
    id<MTLFunction> frag_fn = (__bridge id<MTLFunction>)fragment_function_h;
    if (device == nil || vert_fn == nil || frag_fn == nil) {
        if (error_buf && error_cap) {
            strncpy(error_buf, "render pipeline requires valid vertex and fragment functions", error_cap - 1);
            error_buf[error_cap - 1] = '\0';
        }
        return NULL;
    }

    NSError* err = nil;
    MTLRenderPipelineDescriptor* desc = [MTLRenderPipelineDescriptor new];
    desc.vertexFunction = vert_fn;
    desc.fragmentFunction = frag_fn;
    desc.colorAttachments[0].pixelFormat = wgpu_to_mtl_format(pixel_format);
    if (depth_format != 0) {
        desc.depthAttachmentPixelFormat = wgpu_to_mtl_format(depth_format);
    }
    if (vertex_layout_count > 0 || vertex_attribute_count > 0) {
        MTLVertexDescriptor* vertex_desc = [MTLVertexDescriptor vertexDescriptor];
        for (uint32_t i = 0; i < vertex_layout_count; i++) {
            const MetalVertexBufferLayout layout = vertex_layouts[i];
            vertex_desc.layouts[layout.buffer_index].stride = (NSUInteger)layout.array_stride;
            vertex_desc.layouts[layout.buffer_index].stepFunction =
                layout.step_mode == 0x00000002 ? MTLVertexStepFunctionPerInstance : MTLVertexStepFunctionPerVertex;
            vertex_desc.layouts[layout.buffer_index].stepRate = 1;
        }
        for (uint32_t i = 0; i < vertex_attribute_count; i++) {
            const MetalVertexAttributeDesc attr = vertex_attributes[i];
            const MTLVertexFormat format = wgpu_to_mtl_vertex_format(attr.format);
            if (format == MTLVertexFormatInvalid) {
                if (error_buf && error_cap) {
                    strncpy(error_buf, "unsupported vertex attribute format", error_cap - 1);
                    error_buf[error_cap - 1] = '\0';
                }
                return NULL;
            }
            vertex_desc.attributes[attr.shader_location].format = format;
            vertex_desc.attributes[attr.shader_location].offset = (NSUInteger)attr.offset;
            vertex_desc.attributes[attr.shader_location].bufferIndex = attr.buffer_index;
        }
        desc.vertexDescriptor = vertex_desc;
    }

    id<MTLRenderPipelineState> pso = [device newRenderPipelineStateWithDescriptor:desc error:&err];
    if (pso == nil) { write_error(err, error_buf, error_cap); return NULL; }
    return (MetalHandle)CFBridgingRetain(pso);
}

MetalHandle metal_bridge_device_new_depth_stencil_state(
    MetalHandle device_h,
    uint32_t    compare_fn,
    int         write_enabled,
    char*       error_buf,
    size_t      error_cap)
{
    (void)error_buf;
    (void)error_cap;
    id<MTLDevice> device = (__bridge id<MTLDevice>)device_h;
    if (device == nil) return NULL;
    MTLDepthStencilDescriptor* desc = [MTLDepthStencilDescriptor new];
    desc.depthCompareFunction = wgpu_to_mtl_compare(compare_fn);
    desc.depthWriteEnabled = write_enabled ? YES : NO;
    id<MTLDepthStencilState> state = [device newDepthStencilStateWithDescriptor:desc];
    if (state == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(state);
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

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target, nil, NO);

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

// ============================================================
// Combined compute dispatch + blit copy + event signal + commit
// Single ObjC call eliminates per-step bridge overhead.
// ============================================================

MetalHandle metal_bridge_compute_dispatch_copy_signal_commit(
    MetalHandle  queue_h,
    MetalHandle  pipeline_h,
    MetalHandle* buffers,
    uint32_t     buffer_count,
    uint32_t     x,
    uint32_t     y,
    uint32_t     z,
    uint32_t     wg_x,
    uint32_t     wg_y,
    uint32_t     wg_z,
    MetalHandle  copy_src_h,
    uint64_t     copy_src_off,
    MetalHandle  copy_dst_h,
    uint64_t     copy_dst_off,
    uint64_t     copy_size,
    MetalHandle  event_h,
    uint64_t     event_value)
{
    id<MTLCommandQueue>         queue    = (__bridge id<MTLCommandQueue>)queue_h;
    id<MTLComputePipelineState> pipeline = (__bridge id<MTLComputePipelineState>)pipeline_h;

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    // Compute dispatch
    id<MTLComputeCommandEncoder> encoder = [cmd_buf computeCommandEncoder];
    [encoder setComputePipelineState:pipeline];
    for (uint32_t i = 0; i < buffer_count; i++) {
        if (buffers[i] != NULL) {
            id<MTLBuffer> buf = (__bridge id<MTLBuffer>)buffers[i];
            [encoder setBuffer:buf offset:0 atIndex:i];
        }
    }
    MTLSize tg_size;
    if (wg_x > 0) {
        tg_size = MTLSizeMake(wg_x, wg_y > 0 ? wg_y : 1, wg_z > 0 ? wg_z : 1);
    } else {
        NSUInteger max_tg = pipeline.maxTotalThreadsPerThreadgroup;
        if (max_tg == 0) max_tg = 256;
        tg_size = MTLSizeMake(max_tg, 1, 1);
    }
    [encoder dispatchThreadgroups:MTLSizeMake(x, y, z) threadsPerThreadgroup:tg_size];
    [encoder endEncoding];

    // Blit copy (if requested)
    if (copy_size > 0 && copy_src_h != NULL && copy_dst_h != NULL) {
        id<MTLBuffer> src = (__bridge id<MTLBuffer>)copy_src_h;
        id<MTLBuffer> dst = (__bridge id<MTLBuffer>)copy_dst_h;
        id<MTLBlitCommandEncoder> blit = [cmd_buf blitCommandEncoder];
        [blit copyFromBuffer:src sourceOffset:(NSUInteger)copy_src_off
                    toBuffer:dst destinationOffset:(NSUInteger)copy_dst_off
                        size:(NSUInteger)copy_size];
        [blit endEncoding];
    }

    // Signal event + commit
    if (event_h != NULL) {
        id<MTLSharedEvent> event = (__bridge id<MTLSharedEvent>)event_h;
        [cmd_buf encodeSignalEvent:event value:event_value];
    }
    [cmd_buf commit];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}

// ============================================================
// Semaphore-based completion (faster than waitUntilCompleted)
// ============================================================

static dispatch_semaphore_t _completion_sem = NULL;

void metal_bridge_command_buffer_setup_fast_wait(MetalHandle cmd_buf_h) {
    id<MTLCommandBuffer> cmd_buf = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    if (_completion_sem == NULL) {
        _completion_sem = dispatch_semaphore_create(0);
    }
    [cmd_buf addCompletedHandler:^(id<MTLCommandBuffer> _Nonnull cb) {
        dispatch_semaphore_signal(_completion_sem);
    }];
}

void metal_bridge_command_buffer_wait_fast(void) {
    if (_completion_sem == NULL) return;
    dispatch_semaphore_wait(_completion_sem, DISPATCH_TIME_FOREVER);
}

// ============================================================
// Indirect Command Buffer (render bundle emulation)
// ============================================================

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

    MTLRenderPassDescriptor* pass = cachedRenderPassDescriptor(target, nil, NO);

    id<MTLCommandBuffer> cmd_buf = [queue commandBufferWithUnretainedReferences];
    if (cmd_buf == nil) return NULL;

    id<MTLRenderCommandEncoder> encoder = [cmd_buf renderCommandEncoderWithDescriptor:pass];
    [encoder setRenderPipelineState:pipeline];
    [encoder executeCommandsInBuffer:icb withRange:NSMakeRange(0, draw_count)];
    [encoder endEncoding];

    return (MetalHandle)CFBridgingRetain(cmd_buf);
}
