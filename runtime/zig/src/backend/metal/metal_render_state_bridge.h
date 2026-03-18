#pragma once
#include <stddef.h>
#include <stdint.h>

// Opaque handle convention matches metal_bridge.h: every returned handle is
// +1 retained; call metal_bridge_release() to decrement.
typedef void* MetalHandle;

// ============================================================
// Viewport dynamic state
// ============================================================

// Set viewport on an open render command encoder.
// depth_min and depth_max are in [0.0, 1.0].
void metal_render_state_set_viewport(
    MetalHandle encoder,
    double      x,
    double      y,
    double      width,
    double      height,
    double      depth_min,
    double      depth_max);

// ============================================================
// Scissor rect dynamic state
// ============================================================

// Set scissor rect on an open render command encoder.
// All coords in pixels, clipped to render target bounds by Metal.
void metal_render_state_set_scissor_rect(
    MetalHandle encoder,
    uint32_t    x,
    uint32_t    y,
    uint32_t    width,
    uint32_t    height);

// ============================================================
// Stencil reference dynamic state
// ============================================================

// Set the stencil reference value on an open render command encoder.
void metal_render_state_set_stencil_reference(
    MetalHandle encoder,
    uint32_t    value);

// ============================================================
// Blend color dynamic state
// ============================================================

// Set the blend constant color on an open render command encoder.
void metal_render_state_set_blend_color(
    MetalHandle encoder,
    float       r,
    float       g,
    float       b,
    float       a);

// ============================================================
// Full render pipeline with blend, MSAA, depth/stencil
// ============================================================

// WGPUBlendOperation values (matching webgpu.h)
// 0=add, 1=subtract, 2=reverse_subtract, 3=min, 4=max
// WGPUBlendFactor values:
// 0=zero, 1=one, 2=src, 3=one_minus_src, 4=src_alpha,
// 5=one_minus_src_alpha, 6=dst, 7=one_minus_dst, 8=dst_alpha,
// 9=one_minus_dst_alpha, 10=src_alpha_saturated, 11=constant,
// 12=one_minus_constant, 13=src1, 14=one_minus_src1,
// 15=src1_alpha, 16=one_minus_src1_alpha

// WGPUCompareFunction values:
// 0=undefined, 1=never, 2=less, 3=equal, 4=less_equal,
// 5=greater, 6=not_equal, 7=greater_equal, 8=always

// WGPUStencilOperation values:
// 0=keep, 1=zero, 2=replace, 3=invert, 4=increment_clamp,
// 5=decrement_clamp, 6=increment_wrap, 7=decrement_wrap

// Per-target blend state packed into scalars for C-boundary clarity.
typedef struct {
    uint32_t color_operation;     // WGPUBlendOperation
    uint32_t color_src_factor;    // WGPUBlendFactor
    uint32_t color_dst_factor;    // WGPUBlendFactor
    uint32_t alpha_operation;     // WGPUBlendOperation
    uint32_t alpha_src_factor;    // WGPUBlendFactor
    uint32_t alpha_dst_factor;    // WGPUBlendFactor
    uint32_t write_mask;          // WGPUColorWriteMask bits: r=1 g=2 b=4 a=8
    int      blend_enabled;       // non-zero = enable blending
} MetalBlendAttachment;

typedef struct {
    // Depth
    int      depth_write_enabled; // non-zero = write depth
    uint32_t depth_compare;       // WGPUCompareFunction; 0 = always
    // Stencil front face
    uint32_t stencil_front_compare;    // WGPUCompareFunction
    uint32_t stencil_front_fail_op;    // WGPUStencilOperation
    uint32_t stencil_front_depth_fail; // WGPUStencilOperation
    uint32_t stencil_front_pass_op;    // WGPUStencilOperation
    // Stencil back face
    uint32_t stencil_back_compare;
    uint32_t stencil_back_fail_op;
    uint32_t stencil_back_depth_fail;
    uint32_t stencil_back_pass_op;
    // Masks
    uint32_t stencil_read_mask;
    uint32_t stencil_write_mask;
    // Depth format
    uint32_t depth_stencil_format; // WGPUTextureFormat; 0 = no depth/stencil
} MetalDepthStencilConfig;

// Create a full render pipeline state supporting blend, MSAA, and depth/stencil.
// vertex_msl / fragment_msl: NUL-terminated MSL shader source (may be NULL for noop).
// pixel_format: WGPUTextureFormat for the color attachment.
// sample_count: 1 for non-MSAA, 4 for 4x MSAA.
// alpha_to_coverage: non-zero to enable alphaToCoverageEnabled.
// blend: per-target blend config (may be NULL = no blending, full write mask).
// depth_stencil: depth/stencil config (may be NULL = no depth/stencil attachment).
// support_icb: non-zero to enable indirect command buffer use.
// Returns NULL on failure; writes error into error_buf.
MetalHandle metal_render_state_new_pipeline(
    MetalHandle                  device,
    const char*                  vertex_msl,
    const char*                  fragment_msl,
    uint32_t                     pixel_format,
    uint32_t                     sample_count,
    int                          alpha_to_coverage,
    const MetalBlendAttachment*  blend,
    const MetalDepthStencilConfig* depth_stencil,
    int                          support_icb,
    char*                        error_buf,
    size_t                       error_cap);

// Create a depth/stencil state object from a MetalDepthStencilConfig.
// Returns NULL on failure. The returned handle is +1 retained.
MetalHandle metal_render_state_new_depth_stencil_state(
    MetalHandle                    device,
    const MetalDepthStencilConfig* cfg);

// Attach a depth/stencil state to an open render command encoder.
void metal_render_state_set_depth_stencil_state(
    MetalHandle encoder,
    MetalHandle depth_stencil_state);

// ============================================================
// Debug group / marker dynamic state
// ============================================================

// Push a named debug group onto the render command encoder's debug stack.
// label_len bytes are read from label (no NUL terminator required).
void metal_render_state_push_debug_group(
    MetalHandle encoder,
    const char* label,
    size_t      label_len);

// Pop the most recently pushed debug group from the render command encoder.
void metal_render_state_pop_debug_group(MetalHandle encoder);

// Insert a single-point debug marker on the render command encoder.
// label_len bytes are read from label (no NUL terminator required).
void metal_render_state_insert_debug_marker(
    MetalHandle encoder,
    const char* label,
    size_t      label_len);

// Create a multisample render target texture.
// Returns NULL on failure.
MetalHandle metal_render_state_new_msaa_texture(
    MetalHandle device,
    uint32_t    width,
    uint32_t    height,
    uint32_t    pixel_format,
    uint32_t    sample_count);

// Encode a render pass with an MSAA texture and a resolve target.
// The MSAA texture is the rendering surface; resolve_target receives the resolved output.
// Both textures must already exist. encoder_out receives the open render command encoder
// (+1 retained via CFBridgingRetain); caller must end encoding and release.
MetalHandle metal_render_state_cmd_buf_msaa_render_encoder(
    MetalHandle cmd_buf,
    MetalHandle pipeline,
    MetalHandle msaa_texture,
    MetalHandle resolve_target);
