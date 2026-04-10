pub extern fn metal_render_state_set_viewport(
    encoder: ?*anyopaque,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64,
    max_depth: f64,
) callconv(.c) void;

pub extern fn metal_render_state_set_scissor_rect(
    encoder: ?*anyopaque,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) callconv(.c) void;

pub extern fn metal_render_state_set_stencil_reference(
    encoder: ?*anyopaque,
    reference: u32,
) callconv(.c) void;

pub extern fn metal_render_state_set_blend_color(
    encoder: ?*anyopaque,
    r: f32,
    g: f32,
    b: f32,
    a: f32,
) callconv(.c) void;

pub const MetalBlendAttachment = extern struct {
    color_operation: u32,
    color_src_factor: u32,
    color_dst_factor: u32,
    alpha_operation: u32,
    alpha_src_factor: u32,
    alpha_dst_factor: u32,
    write_mask: u32,
    blend_enabled: c_int,
};

pub const MetalDepthStencilConfig = extern struct {
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

pub extern fn metal_render_state_new_pipeline(
    device: ?*anyopaque,
    vertex_msl: ?[*:0]const u8,
    fragment_msl: ?[*:0]const u8,
    pixel_format: u32,
    sample_count: u32,
    alpha_to_coverage: c_int,
    blend: ?*const MetalBlendAttachment,
    depth_stencil: ?*const MetalDepthStencilConfig,
    support_icb: c_int,
    error_buf: ?[*]u8,
    error_cap: usize,
) callconv(.c) ?*anyopaque;

pub extern fn metal_render_state_new_depth_stencil_state(
    device: ?*anyopaque,
    cfg: ?*const MetalDepthStencilConfig,
) callconv(.c) ?*anyopaque;

pub extern fn metal_render_state_set_depth_stencil_state(
    encoder: ?*anyopaque,
    state: ?*anyopaque,
) callconv(.c) void;

pub extern fn metal_render_state_new_msaa_texture(
    device: ?*anyopaque,
    width: u32,
    height: u32,
    pixel_format: u32,
    sample_count: u32,
) callconv(.c) ?*anyopaque;

pub extern fn metal_render_state_cmd_buf_msaa_render_encoder(
    cmd_buf: ?*anyopaque,
    pipeline: ?*anyopaque,
    msaa_texture: ?*anyopaque,
    resolve_texture: ?*anyopaque,
) callconv(.c) ?*anyopaque;

pub extern fn metal_render_state_push_debug_group(
    encoder: ?*anyopaque,
    label_ptr: ?[*]const u8,
    label_len: usize,
) callconv(.c) void;

pub extern fn metal_render_state_pop_debug_group(encoder: ?*anyopaque) callconv(.c) void;

pub extern fn metal_render_state_insert_debug_marker(
    encoder: ?*anyopaque,
    label_ptr: ?[*]const u8,
    label_len: usize,
) callconv(.c) void;
