// doe_render_pass_controls_native.zig — RenderPassEncoder control method C-ABI exports.
// Implements: setViewport, setScissorRect, setBlendConstant, setStencilReference,
//             pushDebugGroup, popDebugGroup, insertDebugMarker.
//
// These exports accept an opaque render encoder handle (a +1-retained MTL render
// command encoder returned by metal_bridge_cmd_buf_render_encoder or equivalent).
// They forward directly to the metal_render_state_bridge functions without any
// Zig-side state — the encoder carries all GPU state.

const builtin = @import("builtin");
const render_state_native = @import("doe_render_state_native.zig");

extern fn doeNativeRenderPassRecordViewportState(
    pass_raw: ?*anyopaque,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64,
    max_depth: f64,
) callconv(.c) void;
extern fn doeNativeRenderPassRecordScissorState(
    pass_raw: ?*anyopaque,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) callconv(.c) void;
extern fn doeNativeRenderPassRecordBlendConstantState(
    pass_raw: ?*anyopaque,
    r: f64,
    g: f64,
    b: f64,
    a: f64,
) callconv(.c) void;
extern fn doeNativeRenderPassRecordStencilReferenceState(
    pass_raw: ?*anyopaque,
    reference: u32,
) callconv(.c) void;

// ============================================================
// setViewport
// ============================================================

pub export fn doeNativeRenderPassSetViewport(
    encoder_raw: ?*anyopaque,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    min_depth: f64,
    max_depth: f64,
) callconv(.c) void {
    if (builtin.os.tag == .macos) {
        render_state_native.doeNativeRenderPassEncoderSetViewport(
            encoder_raw, x, y, width, height, min_depth, max_depth,
        );
        return;
    }
    doeNativeRenderPassRecordViewportState(
        encoder_raw, x, y, width, height, min_depth, max_depth,
    );
}

// ============================================================
// setScissorRect
// ============================================================

pub export fn doeNativeRenderPassSetScissorRect(
    encoder_raw: ?*anyopaque,
    x: u32,
    y: u32,
    width: u32,
    height: u32,
) callconv(.c) void {
    if (builtin.os.tag == .macos) {
        render_state_native.doeNativeRenderPassEncoderSetScissorRect(
            encoder_raw, x, y, width, height,
        );
        return;
    }
    doeNativeRenderPassRecordScissorState(encoder_raw, x, y, width, height);
}

// ============================================================
// setBlendConstant — color is {r,g,b,a} f64 components
// ============================================================

pub export fn doeNativeRenderPassSetBlendConstant(
    encoder_raw: ?*anyopaque,
    r: f64,
    g: f64,
    b: f64,
    a: f64,
) callconv(.c) void {
    if (builtin.os.tag == .macos) {
        render_state_native.doeNativeRenderPassEncoderSetBlendConstant(
            encoder_raw, r, g, b, a,
        );
        return;
    }
    doeNativeRenderPassRecordBlendConstantState(encoder_raw, r, g, b, a);
}

// ============================================================
// setStencilReference
// ============================================================

pub export fn doeNativeRenderPassSetStencilReference(
    encoder_raw: ?*anyopaque,
    reference: u32,
) callconv(.c) void {
    if (builtin.os.tag == .macos) {
        render_state_native.doeNativeRenderPassEncoderSetStencilReference(
            encoder_raw, reference,
        );
        return;
    }
    doeNativeRenderPassRecordStencilReferenceState(encoder_raw, reference);
}

// ============================================================
// pushDebugGroup — label_ptr / label_len: UTF-8 byte span
// ============================================================

pub export fn doeNativeRenderPassPushDebugGroup(
    encoder_raw: ?*anyopaque,
    label_ptr: ?[*]const u8,
    label_len: usize,
) callconv(.c) void {
    render_state_native.doeNativeRenderPassEncoderPushDebugGroup(
        encoder_raw, label_ptr, label_len,
    );
}

// ============================================================
// popDebugGroup
// ============================================================

pub export fn doeNativeRenderPassPopDebugGroup(
    encoder_raw: ?*anyopaque,
) callconv(.c) void {
    render_state_native.doeNativeRenderPassEncoderPopDebugGroup(encoder_raw);
}

// ============================================================
// insertDebugMarker — label_ptr / label_len: UTF-8 byte span
// ============================================================

pub export fn doeNativeRenderPassInsertDebugMarker(
    encoder_raw: ?*anyopaque,
    label_ptr: ?[*]const u8,
    label_len: usize,
) callconv(.c) void {
    render_state_native.doeNativeRenderPassEncoderInsertDebugMarker(
        encoder_raw, label_ptr, label_len,
    );
}
