// render_state.zig — Viewport, scissor, blend, MSAA, stencil, depth pipeline state
// for the Metal backend. Provides:
//   - Zig type definitions mirroring WebGPU render state descriptors
//   - Metal-boundary C extern declarations
//   - C ABI exports for all dynamic state setters and pipeline creation

const std = @import("std");

// ============================================================
// Constants
// ============================================================

// WebGPU blend operation values (wgpu.h-compatible)
pub const BLEND_OP_ADD: u32             = 0;
pub const BLEND_OP_SUBTRACT: u32        = 1;
pub const BLEND_OP_REVERSE_SUBTRACT: u32 = 2;
pub const BLEND_OP_MIN: u32             = 3;
pub const BLEND_OP_MAX: u32             = 4;

// WebGPU blend factor values
pub const BLEND_FACTOR_ZERO: u32                  = 0;
pub const BLEND_FACTOR_ONE: u32                   = 1;
pub const BLEND_FACTOR_SRC: u32                   = 2;
pub const BLEND_FACTOR_ONE_MINUS_SRC: u32         = 3;
pub const BLEND_FACTOR_SRC_ALPHA: u32             = 4;
pub const BLEND_FACTOR_ONE_MINUS_SRC_ALPHA: u32   = 5;
pub const BLEND_FACTOR_DST: u32                   = 6;
pub const BLEND_FACTOR_ONE_MINUS_DST: u32         = 7;
pub const BLEND_FACTOR_DST_ALPHA: u32             = 8;
pub const BLEND_FACTOR_ONE_MINUS_DST_ALPHA: u32   = 9;
pub const BLEND_FACTOR_SRC_ALPHA_SATURATED: u32   = 10;
pub const BLEND_FACTOR_CONSTANT: u32              = 11;
pub const BLEND_FACTOR_ONE_MINUS_CONSTANT: u32    = 12;
pub const BLEND_FACTOR_SRC1: u32                  = 13;
pub const BLEND_FACTOR_ONE_MINUS_SRC1: u32        = 14;
pub const BLEND_FACTOR_SRC1_ALPHA: u32            = 15;
pub const BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA: u32  = 16;

// WebGPU color write mask bits
pub const COLOR_WRITE_RED: u32   = 0x1;
pub const COLOR_WRITE_GREEN: u32 = 0x2;
pub const COLOR_WRITE_BLUE: u32  = 0x4;
pub const COLOR_WRITE_ALPHA: u32 = 0x8;
pub const COLOR_WRITE_ALL: u32   = 0xF;

// WebGPU compare function values
pub const COMPARE_UNDEFINED: u32     = 0;
pub const COMPARE_NEVER: u32         = 1;
pub const COMPARE_LESS: u32          = 2;
pub const COMPARE_EQUAL: u32         = 3;
pub const COMPARE_LESS_EQUAL: u32    = 4;
pub const COMPARE_GREATER: u32       = 5;
pub const COMPARE_NOT_EQUAL: u32     = 6;
pub const COMPARE_GREATER_EQUAL: u32 = 7;
pub const COMPARE_ALWAYS: u32        = 8;

// WebGPU stencil operation values
pub const STENCIL_OP_KEEP: u32             = 0;
pub const STENCIL_OP_ZERO: u32             = 1;
pub const STENCIL_OP_REPLACE: u32          = 2;
pub const STENCIL_OP_INVERT: u32           = 3;
pub const STENCIL_OP_INCREMENT_CLAMP: u32  = 4;
pub const STENCIL_OP_DECREMENT_CLAMP: u32  = 5;
pub const STENCIL_OP_INCREMENT_WRAP: u32   = 6;
pub const STENCIL_OP_DECREMENT_WRAP: u32   = 7;

// Default stencil mask (all bits active)
pub const STENCIL_MASK_ALL: u32 = 0xFFFFFFFF;

// Supported MSAA sample counts
pub const MSAA_SAMPLE_COUNT_1: u32 = 1;
pub const MSAA_SAMPLE_COUNT_4: u32 = 4;

// Pipeline creation error buffer capacity
pub const PIPELINE_ERROR_CAP: usize = 512;

// ============================================================
// Zig descriptor types
// ============================================================

pub const BlendComponent = struct {
    operation: u32 = BLEND_OP_ADD,
    src_factor: u32 = BLEND_FACTOR_ONE,
    dst_factor: u32 = BLEND_FACTOR_ZERO,
};

pub const BlendState = struct {
    color: BlendComponent = .{},
    alpha: BlendComponent = .{},
    write_mask: u32 = COLOR_WRITE_ALL,
    enabled: bool = false,
};

pub const StencilFaceState = struct {
    compare: u32 = COMPARE_ALWAYS,
    fail_op: u32 = STENCIL_OP_KEEP,
    depth_fail_op: u32 = STENCIL_OP_KEEP,
    pass_op: u32 = STENCIL_OP_KEEP,
};

pub const DepthStencilState = struct {
    format: u32 = 0,               // WGPUTextureFormat; 0 = no attachment
    depth_write_enabled: bool = false,
    depth_compare: u32 = COMPARE_ALWAYS,
    stencil_front: StencilFaceState = .{},
    stencil_back: StencilFaceState = .{},
    stencil_read_mask: u32 = STENCIL_MASK_ALL,
    stencil_write_mask: u32 = STENCIL_MASK_ALL,
};

pub const MultisampleState = struct {
    sample_count: u32 = MSAA_SAMPLE_COUNT_1,
    alpha_to_coverage: bool = false,
};

pub const ViewportRect = struct {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64 = 0.0,
    max_depth: f64 = 1.0,
};

pub const ScissorRect = struct {
    x: u32,
    y: u32,
    width: u32,
    height: u32,
};

// ============================================================
// C extern declarations (resolved from metal_render_state_bridge.m)
// ============================================================

extern fn metal_render_state_set_viewport(
    encoder: ?*anyopaque,
    x: f64, y: f64, width: f64, height: f64,
    depth_min: f64, depth_max: f64,
) callconv(.c) void;

extern fn metal_render_state_set_scissor_rect(
    encoder: ?*anyopaque,
    x: u32, y: u32, width: u32, height: u32,
) callconv(.c) void;

extern fn metal_render_state_set_stencil_reference(
    encoder: ?*anyopaque,
    value: u32,
) callconv(.c) void;

extern fn metal_render_state_set_blend_color(
    encoder: ?*anyopaque,
    r: f32, g: f32, b: f32, a: f32,
) callconv(.c) void;

extern fn metal_render_state_new_pipeline(
    device: ?*anyopaque,
    vertex_msl: ?[*:0]const u8,
    fragment_msl: ?[*:0]const u8,
    pixel_format: u32,
    sample_count: u32,
    alpha_to_coverage: c_int,
    blend: ?*const CBlendAttachment,
    depth_stencil: ?*const CDepthStencilConfig,
    support_icb: c_int,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

extern fn metal_render_state_new_depth_stencil_state(
    device: ?*anyopaque,
    cfg: ?*const CDepthStencilConfig,
) callconv(.c) ?*anyopaque;

extern fn metal_render_state_set_depth_stencil_state(
    encoder: ?*anyopaque,
    ds_state: ?*anyopaque,
) callconv(.c) void;

extern fn metal_render_state_new_msaa_texture(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    pixel_format: u32,
    sample_count: u32,
) callconv(.c) ?*anyopaque;

extern fn metal_render_state_cmd_buf_msaa_render_encoder(
    cmd_buf: ?*anyopaque,
    pipeline: ?*anyopaque,
    msaa_texture: ?*anyopaque,
    resolve_target: ?*anyopaque,
) callconv(.c) ?*anyopaque;

// ============================================================
// C-layout structs matching metal_render_state_bridge.h
// ============================================================

// Must match MetalBlendAttachment in metal_render_state_bridge.h exactly.
const CBlendAttachment = extern struct {
    color_operation: u32,
    color_src_factor: u32,
    color_dst_factor: u32,
    alpha_operation: u32,
    alpha_src_factor: u32,
    alpha_dst_factor: u32,
    write_mask: u32,
    blend_enabled: c_int,
};

// Must match MetalDepthStencilConfig in metal_render_state_bridge.h exactly.
const CDepthStencilConfig = extern struct {
    depth_write_enabled: c_int,
    depth_compare: u32,
    stencil_front_compare: u32,
    stencil_front_fail_op: u32,
    stencil_front_depth_fail: u32,
    stencil_front_pass_op: u32,
    stencil_back_compare: u32,
    stencil_back_fail_op: u32,
    stencil_back_depth_fail: u32,
    stencil_back_pass_op: u32,
    stencil_read_mask: u32,
    stencil_write_mask: u32,
    depth_stencil_format: u32,
};

// ============================================================
// Public helpers: convert Zig descriptors to C structs
// ============================================================

pub fn blend_to_c(blend: *const BlendState) CBlendAttachment {
    return .{
        .color_operation  = blend.color.operation,
        .color_src_factor = blend.color.src_factor,
        .color_dst_factor = blend.color.dst_factor,
        .alpha_operation  = blend.alpha.operation,
        .alpha_src_factor = blend.alpha.src_factor,
        .alpha_dst_factor = blend.alpha.dst_factor,
        .write_mask       = blend.write_mask,
        .blend_enabled    = if (blend.enabled) 1 else 0,
    };
}

pub fn depth_stencil_to_c(ds: *const DepthStencilState) CDepthStencilConfig {
    return .{
        .depth_write_enabled      = if (ds.depth_write_enabled) 1 else 0,
        .depth_compare            = ds.depth_compare,
        .stencil_front_compare    = ds.stencil_front.compare,
        .stencil_front_fail_op    = ds.stencil_front.fail_op,
        .stencil_front_depth_fail = ds.stencil_front.depth_fail_op,
        .stencil_front_pass_op    = ds.stencil_front.pass_op,
        .stencil_back_compare     = ds.stencil_back.compare,
        .stencil_back_fail_op     = ds.stencil_back.fail_op,
        .stencil_back_depth_fail  = ds.stencil_back.depth_fail_op,
        .stencil_back_pass_op     = ds.stencil_back.pass_op,
        .stencil_read_mask        = ds.stencil_read_mask,
        .stencil_write_mask       = ds.stencil_write_mask,
        .depth_stencil_format     = ds.format,
    };
}

// ============================================================
// Public dispatch functions: thin wrappers over C bridge
// ============================================================

pub fn set_viewport(encoder: ?*anyopaque, vp: ViewportRect) void {
    metal_render_state_set_viewport(
        encoder,
        vp.x, vp.y, vp.width, vp.height,
        vp.min_depth, vp.max_depth,
    );
}

pub fn set_scissor_rect(encoder: ?*anyopaque, rect: ScissorRect) void {
    metal_render_state_set_scissor_rect(encoder, rect.x, rect.y, rect.width, rect.height);
}

pub fn set_stencil_reference(encoder: ?*anyopaque, value: u32) void {
    metal_render_state_set_stencil_reference(encoder, value);
}

pub fn set_blend_color(encoder: ?*anyopaque, r: f32, g: f32, b: f32, a: f32) void {
    metal_render_state_set_blend_color(encoder, r, g, b, a);
}

pub fn set_depth_stencil_state(encoder: ?*anyopaque, ds_state: ?*anyopaque) void {
    metal_render_state_set_depth_stencil_state(encoder, ds_state);
}

// Create a render pipeline with full blend + MSAA + depth/stencil support.
// Returns an opaque Metal pipeline handle (+1 retained) or null on failure.
pub fn create_pipeline(
    device: ?*anyopaque,
    vertex_msl: ?[*:0]const u8,
    fragment_msl: ?[*:0]const u8,
    pixel_format: u32,
    msaa: MultisampleState,
    blend: ?*const BlendState,
    ds: ?*const DepthStencilState,
    support_icb: bool,
    error_buf: []u8,
) ?*anyopaque {
    var c_blend: CBlendAttachment = undefined;
    var c_ds: CDepthStencilConfig = undefined;
    const c_blend_ptr: ?*const CBlendAttachment = if (blend) |b| blk: {
        c_blend = blend_to_c(b);
        break :blk &c_blend;
    } else null;
    const c_ds_ptr: ?*const CDepthStencilConfig = if (ds) |d| blk: {
        c_ds = depth_stencil_to_c(d);
        break :blk &c_ds;
    } else null;

    return metal_render_state_new_pipeline(
        device,
        vertex_msl,
        fragment_msl,
        pixel_format,
        msaa.sample_count,
        if (msaa.alpha_to_coverage) @as(c_int, 1) else @as(c_int, 0),
        c_blend_ptr,
        c_ds_ptr,
        if (support_icb) @as(c_int, 1) else @as(c_int, 0),
        error_buf.ptr,
        error_buf.len,
    );
}

// Create a MTLDepthStencilState object from a DepthStencilState descriptor.
// Returns an opaque handle (+1 retained) or null on failure.
pub fn create_depth_stencil_state(
    device: ?*anyopaque,
    ds: *const DepthStencilState,
) ?*anyopaque {
    const c_ds = depth_stencil_to_c(ds);
    return metal_render_state_new_depth_stencil_state(device, &c_ds);
}

// Create an MSAA render target texture.
pub fn create_msaa_texture(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    pixel_format: u32,
    sample_count: u32,
) ?*anyopaque {
    return metal_render_state_new_msaa_texture(device, width, height, pixel_format, sample_count);
}

// Open an MSAA render encoder that resolves into resolve_target.
// Returns the encoder (+1 retained). Caller must end encoding and release.
pub fn open_msaa_render_encoder(
    cmd_buf: ?*anyopaque,
    pipeline: ?*anyopaque,
    msaa_texture: ?*anyopaque,
    resolve_target: ?*anyopaque,
) ?*anyopaque {
    return metal_render_state_cmd_buf_msaa_render_encoder(
        cmd_buf, pipeline, msaa_texture, resolve_target,
    );
}

// ============================================================
// C ABI exports — callable from doe_napi.c or external harnesses
// ============================================================

// Set viewport on an open render pass encoder.
pub export fn doeNativeRenderPassEncoderSetViewport(
    encoder: ?*anyopaque,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64,
    max_depth: f64,
) callconv(.c) void {
    metal_render_state_set_viewport(encoder, x, y, width, height, min_depth, max_depth);
}

// Set scissor rect on an open render pass encoder.
pub export fn doeNativeRenderPassEncoderSetScissorRect(
    encoder: ?*anyopaque,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) callconv(.c) void {
    metal_render_state_set_scissor_rect(encoder, x, y, width, height);
}

// Set stencil reference value on an open render pass encoder.
pub export fn doeNativeRenderPassEncoderSetStencilReference(
    encoder: ?*anyopaque,
    reference: u32,
) callconv(.c) void {
    metal_render_state_set_stencil_reference(encoder, reference);
}

// Set blend constant color on an open render pass encoder.
pub export fn doeNativeRenderPassEncoderSetBlendConstant(
    encoder: ?*anyopaque,
    r: f64,
    g: f64,
    b: f64,
    a: f64,
) callconv(.c) void {
    // Metal expects f32; the WebGPU spec uses f64 for color values.
    metal_render_state_set_blend_color(
        encoder,
        @floatCast(r),
        @floatCast(g),
        @floatCast(b),
        @floatCast(a),
    );
}

// Create a full render pipeline with blend/MSAA/depth-stencil support.
// vertex_msl and fragment_msl are NUL-terminated MSL strings (or NULL for noop).
// Returns the pipeline handle (+1 retained) or null on failure.
pub export fn doeNativeDeviceCreateRenderPipelineFull(
    device: ?*anyopaque,
    vertex_msl: ?[*:0]const u8,
    fragment_msl: ?[*:0]const u8,
    pixel_format: u32,
    sample_count: u32,
    alpha_to_coverage: u32,
    // Blend state fields (flat — avoids ABI struct complexity across C boundary)
    blend_enabled: u32,
    blend_color_op: u32,
    blend_color_src: u32,
    blend_color_dst: u32,
    blend_alpha_op: u32,
    blend_alpha_src: u32,
    blend_alpha_dst: u32,
    blend_write_mask: u32,
    // Depth/stencil fields
    depth_stencil_format: u32,
    depth_write_enabled: u32,
    depth_compare: u32,
    stencil_front_compare: u32,
    stencil_front_fail: u32,
    stencil_front_depth_fail: u32,
    stencil_front_pass: u32,
    stencil_back_compare: u32,
    stencil_back_fail: u32,
    stencil_back_depth_fail: u32,
    stencil_back_pass: u32,
    stencil_read_mask: u32,
    stencil_write_mask: u32,
) callconv(.c) ?*anyopaque {
    var err_buf: [PIPELINE_ERROR_CAP]u8 = undefined;

    const blend_desc = BlendState{
        .color = .{
            .operation  = blend_color_op,
            .src_factor = blend_color_src,
            .dst_factor = blend_color_dst,
        },
        .alpha = .{
            .operation  = blend_alpha_op,
            .src_factor = blend_alpha_src,
            .dst_factor = blend_alpha_dst,
        },
        .write_mask = blend_write_mask,
        .enabled    = blend_enabled != 0,
    };

    const ds_desc = DepthStencilState{
        .format              = depth_stencil_format,
        .depth_write_enabled = depth_write_enabled != 0,
        .depth_compare       = depth_compare,
        .stencil_front = .{
            .compare     = stencil_front_compare,
            .fail_op     = stencil_front_fail,
            .depth_fail_op = stencil_front_depth_fail,
            .pass_op     = stencil_front_pass,
        },
        .stencil_back = .{
            .compare     = stencil_back_compare,
            .fail_op     = stencil_back_fail,
            .depth_fail_op = stencil_back_depth_fail,
            .pass_op     = stencil_back_pass,
        },
        .stencil_read_mask  = stencil_read_mask,
        .stencil_write_mask = stencil_write_mask,
    };

    const msaa = MultisampleState{
        .sample_count      = if (sample_count > 0) sample_count else MSAA_SAMPLE_COUNT_1,
        .alpha_to_coverage = alpha_to_coverage != 0,
    };

    // Only pass depth/stencil descriptor if a format was specified.
    const ds_ptr: ?*const DepthStencilState = if (depth_stencil_format != 0) &ds_desc else null;

    return create_pipeline(
        device,
        vertex_msl,
        fragment_msl,
        pixel_format,
        msaa,
        &blend_desc,
        ds_ptr,
        false,
        &err_buf,
    );
}

// Create a depth/stencil state object. Returns opaque handle (+1 retained) or null.
pub export fn doeNativeDeviceCreateDepthStencilState(
    device: ?*anyopaque,
    format: u32,
    depth_write_enabled: u32,
    depth_compare: u32,
    stencil_front_compare: u32,
    stencil_front_fail: u32,
    stencil_front_depth_fail: u32,
    stencil_front_pass: u32,
    stencil_back_compare: u32,
    stencil_back_fail: u32,
    stencil_back_depth_fail: u32,
    stencil_back_pass: u32,
    stencil_read_mask: u32,
    stencil_write_mask: u32,
) callconv(.c) ?*anyopaque {
    const ds = DepthStencilState{
        .format              = format,
        .depth_write_enabled = depth_write_enabled != 0,
        .depth_compare       = depth_compare,
        .stencil_front = .{
            .compare       = stencil_front_compare,
            .fail_op       = stencil_front_fail,
            .depth_fail_op = stencil_front_depth_fail,
            .pass_op       = stencil_front_pass,
        },
        .stencil_back = .{
            .compare       = stencil_back_compare,
            .fail_op       = stencil_back_fail,
            .depth_fail_op = stencil_back_depth_fail,
            .pass_op       = stencil_back_pass,
        },
        .stencil_read_mask  = stencil_read_mask,
        .stencil_write_mask = stencil_write_mask,
    };
    return create_depth_stencil_state(device, &ds);
}

// Attach a depth/stencil state to an open render pass encoder.
pub export fn doeNativeRenderPassEncoderSetDepthStencilState(
    encoder: ?*anyopaque,
    ds_state: ?*anyopaque,
) callconv(.c) void {
    if (ds_state == null) return;
    metal_render_state_set_depth_stencil_state(encoder, ds_state);
}

// Create an MSAA render target texture.
// sample_count should be 1 or 4.
pub export fn doeNativeDeviceCreateMsaaTexture(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    pixel_format: u32,
    sample_count: u32,
) callconv(.c) ?*anyopaque {
    const sc = if (sample_count < 2) MSAA_SAMPLE_COUNT_4 else sample_count;
    return create_msaa_texture(device, width, height, pixel_format, sc);
}

// Open an MSAA render encoder that resolves into resolve_target.
// Returns the encoder (+1 retained). Caller must endEncoding and release.
pub export fn doeNativeCmdBufMsaaRenderEncoder(
    cmd_buf: ?*anyopaque,
    pipeline: ?*anyopaque,
    msaa_texture: ?*anyopaque,
    resolve_target: ?*anyopaque,
) callconv(.c) ?*anyopaque {
    return open_msaa_render_encoder(cmd_buf, pipeline, msaa_texture, resolve_target);
}
