#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <QuartzCore/QuartzCore.h>
#include "metal_surface_bridge.h"
#include <string.h>

// CAMetalLayer surface management for Doe native Metal backend.
// Each surface wraps a CAMetalLayer and tracks the current drawable.
// Retained handles follow the same convention as metal_bridge.m:
// each returned MetalHandle is +1 retained; caller owns it.

// ============================================================
// Present mode constants (matching WGPUPresentMode values)
// ============================================================

#define DOE_PRESENT_MODE_IMMEDIATE 0x00000001
#define DOE_PRESENT_MODE_MAILBOX   0x00000002
#define DOE_PRESENT_MODE_FIFO      0x00000003
#define DOE_TONE_MAPPING_STANDARD  0x00000001
#define DOE_TONE_MAPPING_EXTENDED  0x00000002

// ============================================================
// Pixel format translation (shared with metal_bridge.m)
// ============================================================

static MTLPixelFormat doe_surface_wgpu_to_mtl_format(uint32_t wgpu) {
    switch (wgpu) {
        case 0x00000016: return MTLPixelFormatRGBA8Unorm;
        case 0x00000017: return MTLPixelFormatRGBA8Unorm_sRGB;
        case 0x0000001B: return MTLPixelFormatBGRA8Unorm;
        case 0x0000001C: return MTLPixelFormatBGRA8Unorm_sRGB;
        case 0x00000026: return MTLPixelFormatRGBA16Float;
        default:         return MTLPixelFormatBGRA8Unorm; // most common swapchain default
    }
}

// ============================================================
// Surface host: wraps CAMetalLayer for offscreen/embedded use
// ============================================================

@interface DoeSurfaceLayer : NSObject
@property(nonatomic, strong) CAMetalLayer*            layer;
@property(nonatomic, strong) NSWindow*                window;       // nil for canvas-embedded
@property(nonatomic, strong) NSView*                  view;         // nil for canvas-embedded
@property(nonatomic, strong) id<CAMetalDrawable>      current_drawable;
@property(nonatomic, assign) uint32_t                 configured_width;
@property(nonatomic, assign) uint32_t                 configured_height;
@property(nonatomic, assign) MTLPixelFormat           configured_format;
@property(nonatomic, assign) BOOL                     is_configured;
@end

@implementation DoeSurfaceLayer

- (instancetype)initOffscreen {
    self = [super init];
    if (self == nil) return nil;

    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];

    NSRect frame = NSMakeRect(0.0, 0.0, 64.0, 64.0);
    self.window = [[NSWindow alloc] initWithContentRect:frame
                                              styleMask:NSWindowStyleMaskBorderless
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    if (self.window == nil) return nil;
    [self.window setReleasedWhenClosed:NO];
    [self.window setOpaque:YES];
    [self.window setIgnoresMouseEvents:YES];

    self.view = [[NSView alloc] initWithFrame:frame];
    [self.view setWantsLayer:YES];

    self.layer = [CAMetalLayer layer];
    self.layer.opaque = YES;
    self.layer.contentsScale = 1.0;

    [self.view setLayer:self.layer];
    [self.window setContentView:self.view];
    [self.window orderFrontRegardless];

    self.configured_width  = 64;
    self.configured_height = 64;
    self.configured_format = MTLPixelFormatBGRA8Unorm;
    self.is_configured     = NO;
    return self;
}

// Canvas-embedded path: caller owns the CAMetalLayer.
// We retain a reference but do not create any window/view.
- (instancetype)initWithExternalLayer:(CAMetalLayer*)external_layer {
    self = [super init];
    if (self == nil) return nil;
    self.layer             = external_layer;
    self.configured_width  = 0;
    self.configured_height = 0;
    self.configured_format = MTLPixelFormatBGRA8Unorm;
    self.is_configured     = NO;
    return self;
}

@end

static BOOL doe_surface_apply_tone_mapping(
    DoeSurfaceLayer* surf,
    uint32_t         pixel_format,
    uint32_t         tone_mapping_mode)
{
    if (surf == nil || surf.layer == nil) return NO;

    CGColorSpaceRef color_space = NULL;
    if (tone_mapping_mode == DOE_TONE_MAPPING_EXTENDED) {
        if (pixel_format != 0x00000026) return NO;
        color_space = CGColorSpaceCreateWithName(kCGColorSpaceExtendedLinearSRGB);
        if (color_space == NULL) return NO;
    } else {
        color_space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    }

    if (color_space != NULL) {
        surf.layer.colorspace = color_space;
        CGColorSpaceRelease(color_space);
    }

    if (@available(macOS 13.0, *)) {
        surf.layer.wantsExtendedDynamicRangeContent = (tone_mapping_mode == DOE_TONE_MAPPING_EXTENDED);
    }
    return YES;
}

// ============================================================
// Create / destroy surface
// ============================================================

MetalHandle doe_surface_create_offscreen(void) {
    DoeSurfaceLayer* surf = [[DoeSurfaceLayer alloc] initOffscreen];
    if (surf == nil || surf.layer == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(surf);
}

MetalHandle doe_surface_create_from_layer(MetalHandle layer_h) {
    CAMetalLayer* external = (__bridge CAMetalLayer*)layer_h;
    if (external == nil) return NULL;
    DoeSurfaceLayer* surf = [[DoeSurfaceLayer alloc] initWithExternalLayer:external];
    if (surf == nil) return NULL;
    return (MetalHandle)CFBridgingRetain(surf);
}

void doe_surface_release(MetalHandle surf_h) {
    if (surf_h == NULL) return;
    CFRelease(surf_h);
}

// ============================================================
// Configure: set device, format, dimensions, present mode
// ============================================================

// present_mode: 0x1=immediate, 0x2=mailbox, 0x3=fifo.
// alpha_opaque: 1 = opaque layer (framebufferOnly=YES, no alpha).
// dpi_scale: contentsScale for HiDPI. Pass 1.0 for non-Retina.
int doe_surface_configure(
    MetalHandle surf_h,
    MetalHandle device_h,
    uint32_t    width,
    uint32_t    height,
    uint32_t    pixel_format,
    uint32_t    present_mode,
    uint32_t    tone_mapping_mode,
    int         alpha_opaque,
    float       dpi_scale)
{
    DoeSurfaceLayer* surf   = (__bridge DoeSurfaceLayer*)surf_h;
    id<MTLDevice>    device = (__bridge id<MTLDevice>)device_h;
    if (surf == nil || device == nil) return 0;

    MTLPixelFormat mtl_fmt = doe_surface_wgpu_to_mtl_format(pixel_format);

    // Apply configuration. Must happen on the main thread for AppKit layers.
    // For offscreen/headless benchmarking this is always the main thread.
    surf.layer.device          = device;
    surf.layer.pixelFormat     = mtl_fmt;
    surf.layer.drawableSize    = CGSizeMake((CGFloat)width, (CGFloat)height);
    surf.layer.contentsScale   = (dpi_scale > 0.0f) ? (CGFloat)dpi_scale : 1.0;
    surf.layer.opaque          = (alpha_opaque != 0);
    surf.layer.framebufferOnly = (alpha_opaque != 0);
    if (!doe_surface_apply_tone_mapping(surf, pixel_format, tone_mapping_mode)) {
        return 0;
    }

    // Display synchronization: fifo uses displaySyncEnabled=YES (vsync on).
    // Immediate and mailbox both disable vsync.
    surf.layer.displaySyncEnabled = (present_mode == DOE_PRESENT_MODE_FIFO);

    // Maximum drawable count: fifo=2 (double-buffer), mailbox/immediate=3 (triple-buffer).
    surf.layer.maximumDrawableCount =
        (present_mode == DOE_PRESENT_MODE_FIFO) ? 2 : 3;

    if (surf.window != nil) {
        NSRect frame = NSMakeRect(0.0, 0.0, (CGFloat)width, (CGFloat)height);
        [surf.window setFrame:frame display:NO];
        [surf.view   setFrame:NSMakeRect(0.0, 0.0, (CGFloat)width, (CGFloat)height)];
        [surf.layer  setFrame:CGRectMake(0.0, 0.0, (CGFloat)width, (CGFloat)height)];
        [CATransaction flush];
    }

    surf.configured_width  = width;
    surf.configured_height = height;
    surf.configured_format = mtl_fmt;
    surf.is_configured     = YES;
    return 1;
}

// ============================================================
// Capability query: report supported formats and present modes
// ============================================================

// Returns 1 if the given WGPU format is supported by CAMetalLayer, 0 otherwise.
// Only BGRA8Unorm and BGRA8UnormSrgb are universally supported on all macOS versions.
// RGBA8Unorm is supported on Apple Silicon and macOS 13+.
int doe_surface_supports_format(uint32_t wgpu_format) {
    switch (wgpu_format) {
        case 0x0000001B: return 1; // BGRA8Unorm — universal
        case 0x0000001C: return 1; // BGRA8UnormSrgb
        case 0x00000016: return 1; // RGBA8Unorm — Apple Silicon / macOS 13+
        case 0x00000017: return 1; // RGBA8UnormSrgb
        case 0x00000026: return 1; // RGBA16Float — extended tone mapping path
        default:         return 0;
    }
}

// ============================================================
// Acquire: get the next drawable from CAMetalLayer
// ============================================================

// Returns the CAMetalTexture (+1 retained) backing the next drawable.
// drawable_out receives the drawable handle (+1 retained) — caller must pass
// it to doe_surface_present() or doe_surface_discard_drawable().
// Returns NULL if no drawable is available (window minimized, layer not ready).
MetalHandle doe_surface_acquire_drawable(MetalHandle surf_h, MetalHandle* drawable_out) {
    DoeSurfaceLayer* surf = (__bridge DoeSurfaceLayer*)surf_h;
    if (surf == nil || !surf.is_configured) return NULL;
    if (drawable_out == NULL) return NULL;

    // nextDrawable blocks until a drawable becomes available.
    // This is the correct Metal presentation API — there is no timeout variant.
    id<CAMetalDrawable> drawable = [surf.layer nextDrawable];
    if (drawable == nil) {
        *drawable_out = NULL;
        return NULL;
    }

    // Retain drawable separately so Zig can hold it across the frame.
    *drawable_out = (MetalHandle)CFBridgingRetain(drawable);

    // Return the MTLTexture (+1 retained) for use as a render attachment.
    id<MTLTexture> texture = drawable.texture;
    if (texture == nil) {
        CFRelease(*drawable_out);
        *drawable_out = NULL;
        return NULL;
    }
    return (MetalHandle)CFBridgingRetain(texture);
}

// ============================================================
// Present: schedule drawable presentation and commit
// ============================================================

// Encodes a present-after-minimum-duration into the command buffer,
// then commits. The caller provides the command buffer (+1 retained)
// that encoded rendering into the drawable's texture.
// The command buffer is released by this function.
void doe_surface_present_drawable(
    MetalHandle cmd_buf_h,
    MetalHandle drawable_h)
{
    id<MTLCommandBuffer> cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<CAMetalDrawable>  drawable = (__bridge id<CAMetalDrawable>)drawable_h;
    if (cmd_buf == nil || drawable == nil) return;

    [cmd_buf presentDrawable:drawable];
    [cmd_buf commit];
}

// Commit without waiting. Presentation happens asynchronously.
// Used for fifo (vsync) where we do not want to block the CPU.
void doe_surface_present_drawable_async(
    MetalHandle cmd_buf_h,
    MetalHandle drawable_h)
{
    id<MTLCommandBuffer> cmd_buf  = (__bridge id<MTLCommandBuffer>)cmd_buf_h;
    id<CAMetalDrawable>  drawable = (__bridge id<CAMetalDrawable>)drawable_h;
    if (cmd_buf == nil || drawable == nil) return;

    [cmd_buf presentDrawable:drawable];
    [cmd_buf commit];
    // No waitUntilCompleted — frame pacing handled by CAMetalLayer.
}

// ============================================================
// Discard: release a drawable without presenting
// ============================================================

void doe_surface_discard_drawable(MetalHandle drawable_h) {
    if (drawable_h == NULL) return;
    CFRelease(drawable_h);
}

// ============================================================
// Resize: update drawableSize when window dimensions change
// ============================================================

void doe_surface_resize(MetalHandle surf_h, uint32_t width, uint32_t height, float dpi_scale) {
    DoeSurfaceLayer* surf = (__bridge DoeSurfaceLayer*)surf_h;
    if (surf == nil || surf.layer == nil) return;
    if (width == 0 || height == 0) return;

    CGFloat scale = (dpi_scale > 0.0f) ? (CGFloat)dpi_scale : surf.layer.contentsScale;
    surf.layer.drawableSize  = CGSizeMake((CGFloat)width * scale, (CGFloat)height * scale);
    surf.configured_width    = width;
    surf.configured_height   = height;

    if (surf.window != nil) {
        NSRect frame = NSMakeRect(0.0, 0.0, (CGFloat)width, (CGFloat)height);
        [surf.window setFrame:frame display:NO];
        [surf.view   setFrame:NSMakeRect(0.0, 0.0, (CGFloat)width, (CGFloat)height)];
        [surf.layer  setFrame:CGRectMake(0.0, 0.0, (CGFloat)width, (CGFloat)height)];
        [CATransaction flush];
    }
}

// ============================================================
// Dimension / format queries
// ============================================================

uint32_t doe_surface_drawable_width(MetalHandle surf_h) {
    DoeSurfaceLayer* surf = (__bridge DoeSurfaceLayer*)surf_h;
    if (surf == nil) return 0;
    return surf.configured_width;
}

uint32_t doe_surface_drawable_height(MetalHandle surf_h) {
    DoeSurfaceLayer* surf = (__bridge DoeSurfaceLayer*)surf_h;
    if (surf == nil) return 0;
    return surf.configured_height;
}

int doe_surface_is_configured(MetalHandle surf_h) {
    DoeSurfaceLayer* surf = (__bridge DoeSurfaceLayer*)surf_h;
    if (surf == nil) return 0;
    return surf.is_configured ? 1 : 0;
}

// ============================================================
// Release underlying CAMetalLayer configuration
// ============================================================

// Detaches the layer from the device, releasing swapchain resources.
// The surf handle itself remains valid until doe_surface_release().
void doe_surface_unconfigure(MetalHandle surf_h) {
    DoeSurfaceLayer* surf = (__bridge DoeSurfaceLayer*)surf_h;
    if (surf == nil) return;
    surf.layer.device  = nil;
    surf.is_configured = NO;
    // Discard any unreleased drawable.
    surf.current_drawable = nil;
}
