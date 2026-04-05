#pragma once
#include <stdint.h>

// CAMetalLayer surface bridge for Doe native Metal backend.
// Handles are +1 retained; caller owns and must release via doe_surface_release()
// or metal_bridge_release() (same CFRelease semantics).
typedef void* MetalHandle;

// ============================================================
// Surface lifecycle
// ============================================================

// Create an offscreen surface backed by a borderless NSWindow/CAMetalLayer.
// Suitable for headless benchmarking and non-embedded use.
MetalHandle doe_surface_create_offscreen(void);

// Wrap an externally-owned CAMetalLayer (e.g. from Chromium's compositor).
// The caller retains ownership of the layer; this surface holds an additional ref.
MetalHandle doe_surface_create_from_layer(MetalHandle layer_h);

// Release the surface. Balances doe_surface_create_offscreen or
// doe_surface_create_from_layer. Does not present any pending drawable.
void doe_surface_release(MetalHandle surf_h);

// ============================================================
// Configuration
// ============================================================

// Configure the CAMetalLayer swapchain.
// present_mode: 0x1=immediate, 0x2=mailbox, 0x3=fifo.
// tone_mapping_mode: 0x1=standard, 0x2=extended (RGBA16Float only).
// alpha_opaque: 1 = opaque (no alpha blending with compositor).
// dpi_scale: pass 1.0 for standard DPI; 2.0 for Retina.
int doe_surface_configure(
    MetalHandle surf_h,
    MetalHandle device_h,
    uint32_t    width,
    uint32_t    height,
    uint32_t    pixel_format,
    uint32_t    present_mode,
    uint32_t    tone_mapping_mode,
    int         alpha_opaque,
    float       dpi_scale);

// Detach the device from the layer; release swapchain resources.
// Surface handle remains valid; call doe_surface_release() when done.
void doe_surface_unconfigure(MetalHandle surf_h);

// ============================================================
// Capability query
// ============================================================

// Returns 1 if the WGPU texture format is supported by CAMetalLayer on this system.
int doe_surface_supports_format(uint32_t wgpu_format);

// ============================================================
// Acquire / present
// ============================================================

// Acquire the next CAMetalDrawable from the layer.
// Returns the MTLTexture (+1 retained) for render attachment.
// drawable_out receives the drawable (+1 retained) for presentation.
// Returns NULL on failure (minimized window, unconfigured, no drawable available).
MetalHandle doe_surface_acquire_drawable(MetalHandle surf_h, MetalHandle* drawable_out);

// Present a drawable synchronously (encodes presentDrawable: then commits).
// Releases cmd_buf_h via commit semantics (does not CFRelease the handle;
// the caller still owns the Zig-side ref and must call metal_bridge_release).
void doe_surface_present_drawable(MetalHandle cmd_buf_h, MetalHandle drawable_h);

// Present without blocking. Frame pacing handled by CAMetalLayer.
void doe_surface_present_drawable_async(MetalHandle cmd_buf_h, MetalHandle drawable_h);

// Discard a drawable without presenting (e.g. on device lost).
void doe_surface_discard_drawable(MetalHandle drawable_h);

// ============================================================
// Resize
// ============================================================

// Update drawableSize when the window or canvas element resizes.
// dpi_scale: pass 0.0 to preserve the existing contentsScale.
void doe_surface_resize(MetalHandle surf_h, uint32_t width, uint32_t height, float dpi_scale);

// ============================================================
// Queries
// ============================================================

uint32_t doe_surface_drawable_width(MetalHandle surf_h);
uint32_t doe_surface_drawable_height(MetalHandle surf_h);
int      doe_surface_is_configured(MetalHandle surf_h);
