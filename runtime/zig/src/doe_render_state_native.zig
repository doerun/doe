// doe_render_state_native.zig — C ABI re-exports for full render state support:
// viewport, scissor, blend, MSAA, stencil, and depth/stencil pipeline.
//
// The implementations live in backend/metal/render_state.zig.  On non-macOS
// targets, this file exposes deterministic no-op fallbacks so builds that do
// not link Metal still produce a valid shared library.

const builtin = @import("builtin");

const impl = if (builtin.os.tag == .macos)
    @import("backend/metal/render_state.zig")
else
    struct {
        pub fn doeNativeRenderPassEncoderSetViewport(
            encoder: ?*anyopaque,
            x: f64,
            y: f64,
            width: f64,
            height: f64,
            min_depth: f64,
            max_depth: f64,
        ) void {
            _ = encoder;
            _ = x;
            _ = y;
            _ = width;
            _ = height;
            _ = min_depth;
            _ = max_depth;
        }

        pub fn doeNativeRenderPassEncoderSetScissorRect(
            encoder: ?*anyopaque,
            x: u32,
            y: u32,
            width: u32,
            height: u32,
        ) void {
            _ = encoder;
            _ = x;
            _ = y;
            _ = width;
            _ = height;
        }

        pub fn doeNativeRenderPassEncoderSetStencilReference(
            encoder: ?*anyopaque,
            reference: u32,
        ) void {
            _ = encoder;
            _ = reference;
        }

        pub fn doeNativeRenderPassEncoderSetBlendConstant(
            encoder: ?*anyopaque,
            r: f64,
            g: f64,
            b: f64,
            a: f64,
        ) void {
            _ = encoder;
            _ = r;
            _ = g;
            _ = b;
            _ = a;
        }

        pub fn doeNativeDeviceCreateRenderPipelineFull(
            device: ?*anyopaque,
            vertex_msl: ?[*:0]const u8,
            fragment_msl: ?[*:0]const u8,
            pixel_format: u32,
            sample_count: u32,
            alpha_to_coverage: u32,
            blend_enabled: u32,
            blend_color_op: u32,
            blend_color_src: u32,
            blend_color_dst: u32,
            blend_alpha_op: u32,
            blend_alpha_src: u32,
            blend_alpha_dst: u32,
            blend_write_mask: u32,
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
        ) ?*anyopaque {
            _ = device;
            _ = vertex_msl;
            _ = fragment_msl;
            _ = pixel_format;
            _ = sample_count;
            _ = alpha_to_coverage;
            _ = blend_enabled;
            _ = blend_color_op;
            _ = blend_color_src;
            _ = blend_color_dst;
            _ = blend_alpha_op;
            _ = blend_alpha_src;
            _ = blend_alpha_dst;
            _ = blend_write_mask;
            _ = depth_stencil_format;
            _ = depth_write_enabled;
            _ = depth_compare;
            _ = stencil_front_compare;
            _ = stencil_front_fail;
            _ = stencil_front_depth_fail;
            _ = stencil_front_pass;
            _ = stencil_back_compare;
            _ = stencil_back_fail;
            _ = stencil_back_depth_fail;
            _ = stencil_back_pass;
            _ = stencil_read_mask;
            _ = stencil_write_mask;
            return null;
        }

        pub fn doeNativeDeviceCreateDepthStencilState(
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
        ) ?*anyopaque {
            _ = device;
            _ = format;
            _ = depth_write_enabled;
            _ = depth_compare;
            _ = stencil_front_compare;
            _ = stencil_front_fail;
            _ = stencil_front_depth_fail;
            _ = stencil_front_pass;
            _ = stencil_back_compare;
            _ = stencil_back_fail;
            _ = stencil_back_depth_fail;
            _ = stencil_back_pass;
            _ = stencil_read_mask;
            _ = stencil_write_mask;
            return null;
        }

        pub fn doeNativeRenderPassEncoderSetDepthStencilState(
            encoder: ?*anyopaque,
            ds_state: ?*anyopaque,
        ) void {
            _ = encoder;
            _ = ds_state;
        }

        pub fn doeNativeDeviceCreateMsaaTexture(
            device: ?*anyopaque,
            width: u32,
            height: u32,
            pixel_format: u32,
            sample_count: u32,
        ) ?*anyopaque {
            _ = device;
            _ = width;
            _ = height;
            _ = pixel_format;
            _ = sample_count;
            return null;
        }

        pub fn doeNativeCmdBufMsaaRenderEncoder(
            cmd_buf: ?*anyopaque,
            pipeline: ?*anyopaque,
            msaa_texture: ?*anyopaque,
            resolve_target: ?*anyopaque,
        ) ?*anyopaque {
            _ = cmd_buf;
            _ = pipeline;
            _ = msaa_texture;
            _ = resolve_target;
            return null;
        }
    };

comptime {
    _ = impl;
}

pub const doeNativeRenderPassEncoderSetViewport = impl.doeNativeRenderPassEncoderSetViewport;
pub const doeNativeRenderPassEncoderSetScissorRect = impl.doeNativeRenderPassEncoderSetScissorRect;
pub const doeNativeRenderPassEncoderSetStencilReference = impl.doeNativeRenderPassEncoderSetStencilReference;
pub const doeNativeRenderPassEncoderSetBlendConstant = impl.doeNativeRenderPassEncoderSetBlendConstant;
pub const doeNativeDeviceCreateRenderPipelineFull = impl.doeNativeDeviceCreateRenderPipelineFull;
pub const doeNativeDeviceCreateDepthStencilState = impl.doeNativeDeviceCreateDepthStencilState;
pub const doeNativeRenderPassEncoderSetDepthStencilState = impl.doeNativeRenderPassEncoderSetDepthStencilState;
pub const doeNativeDeviceCreateMsaaTexture = impl.doeNativeDeviceCreateMsaaTexture;
pub const doeNativeCmdBufMsaaRenderEncoder = impl.doeNativeCmdBufMsaaRenderEncoder;
