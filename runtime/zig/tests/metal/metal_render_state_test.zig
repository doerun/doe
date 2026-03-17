const std = @import("std");
const builtin = @import("builtin");
const rs = @import("../../src/backend/metal/render_state.zig");

// ============================================================
// Blend operation constants
// ============================================================

test "blend operation constants are sequential from 0 to 4" {
    try std.testing.expectEqual(@as(u32, 0), rs.BLEND_OP_ADD);
    try std.testing.expectEqual(@as(u32, 1), rs.BLEND_OP_SUBTRACT);
    try std.testing.expectEqual(@as(u32, 2), rs.BLEND_OP_REVERSE_SUBTRACT);
    try std.testing.expectEqual(@as(u32, 3), rs.BLEND_OP_MIN);
    try std.testing.expectEqual(@as(u32, 4), rs.BLEND_OP_MAX);
}

// ============================================================
// Blend factor constants
// ============================================================

test "blend factor constants are sequential from 0 to 16" {
    try std.testing.expectEqual(@as(u32, 0), rs.BLEND_FACTOR_ZERO);
    try std.testing.expectEqual(@as(u32, 1), rs.BLEND_FACTOR_ONE);
    try std.testing.expectEqual(@as(u32, 2), rs.BLEND_FACTOR_SRC);
    try std.testing.expectEqual(@as(u32, 3), rs.BLEND_FACTOR_ONE_MINUS_SRC);
    try std.testing.expectEqual(@as(u32, 4), rs.BLEND_FACTOR_SRC_ALPHA);
    try std.testing.expectEqual(@as(u32, 5), rs.BLEND_FACTOR_ONE_MINUS_SRC_ALPHA);
    try std.testing.expectEqual(@as(u32, 6), rs.BLEND_FACTOR_DST);
    try std.testing.expectEqual(@as(u32, 7), rs.BLEND_FACTOR_ONE_MINUS_DST);
    try std.testing.expectEqual(@as(u32, 8), rs.BLEND_FACTOR_DST_ALPHA);
    try std.testing.expectEqual(@as(u32, 9), rs.BLEND_FACTOR_ONE_MINUS_DST_ALPHA);
    try std.testing.expectEqual(@as(u32, 10), rs.BLEND_FACTOR_SRC_ALPHA_SATURATED);
    try std.testing.expectEqual(@as(u32, 11), rs.BLEND_FACTOR_CONSTANT);
    try std.testing.expectEqual(@as(u32, 12), rs.BLEND_FACTOR_ONE_MINUS_CONSTANT);
    try std.testing.expectEqual(@as(u32, 13), rs.BLEND_FACTOR_SRC1);
    try std.testing.expectEqual(@as(u32, 14), rs.BLEND_FACTOR_ONE_MINUS_SRC1);
    try std.testing.expectEqual(@as(u32, 15), rs.BLEND_FACTOR_SRC1_ALPHA);
    try std.testing.expectEqual(@as(u32, 16), rs.BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA);
}

// ============================================================
// Color write mask constants
// ============================================================

test "color write mask bits are non-overlapping powers of 2" {
    try std.testing.expectEqual(@as(u32, 0x1), rs.COLOR_WRITE_RED);
    try std.testing.expectEqual(@as(u32, 0x2), rs.COLOR_WRITE_GREEN);
    try std.testing.expectEqual(@as(u32, 0x4), rs.COLOR_WRITE_BLUE);
    try std.testing.expectEqual(@as(u32, 0x8), rs.COLOR_WRITE_ALPHA);

    // No overlap between individual bits
    try std.testing.expectEqual(@as(u32, 0), rs.COLOR_WRITE_RED & rs.COLOR_WRITE_GREEN);
    try std.testing.expectEqual(@as(u32, 0), rs.COLOR_WRITE_RED & rs.COLOR_WRITE_BLUE);
    try std.testing.expectEqual(@as(u32, 0), rs.COLOR_WRITE_RED & rs.COLOR_WRITE_ALPHA);
    try std.testing.expectEqual(@as(u32, 0), rs.COLOR_WRITE_GREEN & rs.COLOR_WRITE_BLUE);
    try std.testing.expectEqual(@as(u32, 0), rs.COLOR_WRITE_GREEN & rs.COLOR_WRITE_ALPHA);
    try std.testing.expectEqual(@as(u32, 0), rs.COLOR_WRITE_BLUE & rs.COLOR_WRITE_ALPHA);
}

test "COLOR_WRITE_ALL is the union of all four channels" {
    const all = rs.COLOR_WRITE_RED | rs.COLOR_WRITE_GREEN | rs.COLOR_WRITE_BLUE | rs.COLOR_WRITE_ALPHA;
    try std.testing.expectEqual(all, rs.COLOR_WRITE_ALL);
    try std.testing.expectEqual(@as(u32, 0xF), rs.COLOR_WRITE_ALL);
}

// ============================================================
// Compare function constants
// ============================================================

test "compare function constants are sequential from 0 to 8" {
    try std.testing.expectEqual(@as(u32, 0), rs.COMPARE_UNDEFINED);
    try std.testing.expectEqual(@as(u32, 1), rs.COMPARE_NEVER);
    try std.testing.expectEqual(@as(u32, 2), rs.COMPARE_LESS);
    try std.testing.expectEqual(@as(u32, 3), rs.COMPARE_EQUAL);
    try std.testing.expectEqual(@as(u32, 4), rs.COMPARE_LESS_EQUAL);
    try std.testing.expectEqual(@as(u32, 5), rs.COMPARE_GREATER);
    try std.testing.expectEqual(@as(u32, 6), rs.COMPARE_NOT_EQUAL);
    try std.testing.expectEqual(@as(u32, 7), rs.COMPARE_GREATER_EQUAL);
    try std.testing.expectEqual(@as(u32, 8), rs.COMPARE_ALWAYS);
}

// ============================================================
// Stencil operation constants
// ============================================================

test "stencil operation constants are sequential from 0 to 7" {
    try std.testing.expectEqual(@as(u32, 0), rs.STENCIL_OP_KEEP);
    try std.testing.expectEqual(@as(u32, 1), rs.STENCIL_OP_ZERO);
    try std.testing.expectEqual(@as(u32, 2), rs.STENCIL_OP_REPLACE);
    try std.testing.expectEqual(@as(u32, 3), rs.STENCIL_OP_INVERT);
    try std.testing.expectEqual(@as(u32, 4), rs.STENCIL_OP_INCREMENT_CLAMP);
    try std.testing.expectEqual(@as(u32, 5), rs.STENCIL_OP_DECREMENT_CLAMP);
    try std.testing.expectEqual(@as(u32, 6), rs.STENCIL_OP_INCREMENT_WRAP);
    try std.testing.expectEqual(@as(u32, 7), rs.STENCIL_OP_DECREMENT_WRAP);
}

test "stencil mask all has all bits set" {
    try std.testing.expectEqual(@as(u32, 0xFFFFFFFF), rs.STENCIL_MASK_ALL);
}

// ============================================================
// MSAA sample count constants
// ============================================================

test "MSAA sample count constants are powers of 2" {
    try std.testing.expectEqual(@as(u32, 1), rs.MSAA_SAMPLE_COUNT_1);
    try std.testing.expectEqual(@as(u32, 4), rs.MSAA_SAMPLE_COUNT_4);

    // Both must be powers of 2 (Metal requirement)
    try std.testing.expect(std.math.isPowerOfTwo(rs.MSAA_SAMPLE_COUNT_1));
    try std.testing.expect(std.math.isPowerOfTwo(rs.MSAA_SAMPLE_COUNT_4));
}

// ============================================================
// Pipeline error buffer capacity
// ============================================================

test "pipeline error cap is large enough for diagnostic messages" {
    try std.testing.expectEqual(@as(usize, 512), rs.PIPELINE_ERROR_CAP);
    try std.testing.expect(rs.PIPELINE_ERROR_CAP >= 256);
}

// ============================================================
// BlendComponent defaults
// ============================================================

test "BlendComponent default is additive no-op (src*1 + dst*0)" {
    const bc = rs.BlendComponent{};
    try std.testing.expectEqual(rs.BLEND_OP_ADD, bc.operation);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE, bc.src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ZERO, bc.dst_factor);
}

test "BlendComponent custom values override defaults" {
    const bc = rs.BlendComponent{
        .operation = rs.BLEND_OP_SUBTRACT,
        .src_factor = rs.BLEND_FACTOR_SRC_ALPHA,
        .dst_factor = rs.BLEND_FACTOR_ONE_MINUS_SRC_ALPHA,
    };
    try std.testing.expectEqual(rs.BLEND_OP_SUBTRACT, bc.operation);
    try std.testing.expectEqual(rs.BLEND_FACTOR_SRC_ALPHA, bc.src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE_MINUS_SRC_ALPHA, bc.dst_factor);
}

// ============================================================
// BlendState defaults
// ============================================================

test "BlendState default is disabled with write-all mask" {
    const bs = rs.BlendState{};
    try std.testing.expectEqual(false, bs.enabled);
    try std.testing.expectEqual(rs.COLOR_WRITE_ALL, bs.write_mask);

    // Color and alpha both use default BlendComponent
    try std.testing.expectEqual(rs.BLEND_OP_ADD, bs.color.operation);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE, bs.color.src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ZERO, bs.color.dst_factor);
    try std.testing.expectEqual(rs.BLEND_OP_ADD, bs.alpha.operation);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE, bs.alpha.src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ZERO, bs.alpha.dst_factor);
}

// ============================================================
// StencilFaceState defaults
// ============================================================

test "StencilFaceState default passes always and keeps on all outcomes" {
    const sf = rs.StencilFaceState{};
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, sf.compare);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, sf.fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, sf.depth_fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, sf.pass_op);
}

test "StencilFaceState custom stencil-test-replace configuration" {
    const sf = rs.StencilFaceState{
        .compare = rs.COMPARE_EQUAL,
        .fail_op = rs.STENCIL_OP_ZERO,
        .depth_fail_op = rs.STENCIL_OP_INVERT,
        .pass_op = rs.STENCIL_OP_REPLACE,
    };
    try std.testing.expectEqual(rs.COMPARE_EQUAL, sf.compare);
    try std.testing.expectEqual(rs.STENCIL_OP_ZERO, sf.fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_INVERT, sf.depth_fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_REPLACE, sf.pass_op);
}

// ============================================================
// DepthStencilState defaults
// ============================================================

test "DepthStencilState default has no depth attachment and all masks set" {
    const ds = rs.DepthStencilState{};
    try std.testing.expectEqual(@as(u32, 0), ds.format);
    try std.testing.expectEqual(false, ds.depth_write_enabled);
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, ds.depth_compare);
    try std.testing.expectEqual(rs.STENCIL_MASK_ALL, ds.stencil_read_mask);
    try std.testing.expectEqual(rs.STENCIL_MASK_ALL, ds.stencil_write_mask);

    // Front and back stencil both default to pass-always/keep
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, ds.stencil_front.compare);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, ds.stencil_front.fail_op);
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, ds.stencil_back.compare);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, ds.stencil_back.fail_op);
}

// ============================================================
// MultisampleState defaults
// ============================================================

test "MultisampleState default is 1 sample with no alpha-to-coverage" {
    const ms = rs.MultisampleState{};
    try std.testing.expectEqual(rs.MSAA_SAMPLE_COUNT_1, ms.sample_count);
    try std.testing.expectEqual(false, ms.alpha_to_coverage);
}

test "MultisampleState 4x MSAA with alpha-to-coverage" {
    const ms = rs.MultisampleState{
        .sample_count = rs.MSAA_SAMPLE_COUNT_4,
        .alpha_to_coverage = true,
    };
    try std.testing.expectEqual(rs.MSAA_SAMPLE_COUNT_4, ms.sample_count);
    try std.testing.expectEqual(true, ms.alpha_to_coverage);
}

// ============================================================
// ViewportRect construction
// ============================================================

test "ViewportRect explicit construction preserves all fields" {
    const vp = rs.ViewportRect{
        .x = 10.0,
        .y = 20.0,
        .width = 800.0,
        .height = 600.0,
        .min_depth = 0.0,
        .max_depth = 1.0,
    };
    try std.testing.expectEqual(@as(f64, 10.0), vp.x);
    try std.testing.expectEqual(@as(f64, 20.0), vp.y);
    try std.testing.expectEqual(@as(f64, 800.0), vp.width);
    try std.testing.expectEqual(@as(f64, 600.0), vp.height);
    try std.testing.expectEqual(@as(f64, 0.0), vp.min_depth);
    try std.testing.expectEqual(@as(f64, 1.0), vp.max_depth);
}

test "ViewportRect depth defaults are 0 to 1" {
    const vp = rs.ViewportRect{
        .x = 0.0,
        .y = 0.0,
        .width = 1920.0,
        .height = 1080.0,
    };
    try std.testing.expectEqual(@as(f64, 0.0), vp.min_depth);
    try std.testing.expectEqual(@as(f64, 1.0), vp.max_depth);
}

test "ViewportRect allows negative origin for Metal clipping" {
    const vp = rs.ViewportRect{
        .x = -100.0,
        .y = -50.0,
        .width = 400.0,
        .height = 300.0,
    };
    try std.testing.expect(vp.x < 0);
    try std.testing.expect(vp.y < 0);
    try std.testing.expect(vp.width > 0);
    try std.testing.expect(vp.height > 0);
}

test "ViewportRect custom depth range" {
    const vp = rs.ViewportRect{
        .x = 0.0,
        .y = 0.0,
        .width = 640.0,
        .height = 480.0,
        .min_depth = 0.25,
        .max_depth = 0.75,
    };
    try std.testing.expectEqual(@as(f64, 0.25), vp.min_depth);
    try std.testing.expectEqual(@as(f64, 0.75), vp.max_depth);
    try std.testing.expect(vp.max_depth > vp.min_depth);
}

// ============================================================
// ScissorRect construction
// ============================================================

test "ScissorRect stores origin and dimensions" {
    const rect = rs.ScissorRect{
        .x = 10,
        .y = 20,
        .width = 200,
        .height = 150,
    };
    try std.testing.expectEqual(@as(u32, 10), rect.x);
    try std.testing.expectEqual(@as(u32, 20), rect.y);
    try std.testing.expectEqual(@as(u32, 200), rect.width);
    try std.testing.expectEqual(@as(u32, 150), rect.height);
}

test "ScissorRect allows zero origin" {
    const rect = rs.ScissorRect{
        .x = 0,
        .y = 0,
        .width = 1920,
        .height = 1080,
    };
    try std.testing.expectEqual(@as(u32, 0), rect.x);
    try std.testing.expectEqual(@as(u32, 0), rect.y);
}

test "ScissorRect minimum valid dimensions" {
    const rect = rs.ScissorRect{
        .x = 0,
        .y = 0,
        .width = 1,
        .height = 1,
    };
    try std.testing.expect(rect.width > 0);
    try std.testing.expect(rect.height > 0);
}

// ============================================================
// blend_to_c conversion
// ============================================================

test "blend_to_c converts default BlendState to C layout" {
    const blend = rs.BlendState{};
    const c = rs.blend_to_c(&blend);
    try std.testing.expectEqual(rs.BLEND_OP_ADD, c.color_operation);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE, c.color_src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ZERO, c.color_dst_factor);
    try std.testing.expectEqual(rs.BLEND_OP_ADD, c.alpha_operation);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE, c.alpha_src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ZERO, c.alpha_dst_factor);
    try std.testing.expectEqual(rs.COLOR_WRITE_ALL, c.write_mask);
    try std.testing.expectEqual(@as(c_int, 0), c.blend_enabled);
}

test "blend_to_c converts enabled alpha blend to C layout" {
    const blend = rs.BlendState{
        .color = .{
            .operation = rs.BLEND_OP_ADD,
            .src_factor = rs.BLEND_FACTOR_SRC_ALPHA,
            .dst_factor = rs.BLEND_FACTOR_ONE_MINUS_SRC_ALPHA,
        },
        .alpha = .{
            .operation = rs.BLEND_OP_ADD,
            .src_factor = rs.BLEND_FACTOR_ONE,
            .dst_factor = rs.BLEND_FACTOR_ZERO,
        },
        .write_mask = rs.COLOR_WRITE_RED | rs.COLOR_WRITE_GREEN | rs.COLOR_WRITE_BLUE,
        .enabled = true,
    };
    const c = rs.blend_to_c(&blend);
    try std.testing.expectEqual(rs.BLEND_FACTOR_SRC_ALPHA, c.color_src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE_MINUS_SRC_ALPHA, c.color_dst_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ONE, c.alpha_src_factor);
    try std.testing.expectEqual(rs.BLEND_FACTOR_ZERO, c.alpha_dst_factor);
    try std.testing.expectEqual(@as(u32, 0x7), c.write_mask); // R|G|B without alpha
    try std.testing.expectEqual(@as(c_int, 1), c.blend_enabled);
}

test "blend_to_c maps enabled false to 0 and true to 1" {
    const disabled = rs.BlendState{ .enabled = false };
    const enabled = rs.BlendState{ .enabled = true };
    try std.testing.expectEqual(@as(c_int, 0), rs.blend_to_c(&disabled).blend_enabled);
    try std.testing.expectEqual(@as(c_int, 1), rs.blend_to_c(&enabled).blend_enabled);
}

// ============================================================
// depth_stencil_to_c conversion
// ============================================================

test "depth_stencil_to_c converts default DepthStencilState to C layout" {
    const ds = rs.DepthStencilState{};
    const c = rs.depth_stencil_to_c(&ds);
    try std.testing.expectEqual(@as(c_int, 0), c.depth_write_enabled);
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, c.depth_compare);
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, c.stencil_front_compare);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, c.stencil_front_fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, c.stencil_front_depth_fail);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, c.stencil_front_pass_op);
    try std.testing.expectEqual(rs.COMPARE_ALWAYS, c.stencil_back_compare);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, c.stencil_back_fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, c.stencil_back_depth_fail);
    try std.testing.expectEqual(rs.STENCIL_OP_KEEP, c.stencil_back_pass_op);
    try std.testing.expectEqual(rs.STENCIL_MASK_ALL, c.stencil_read_mask);
    try std.testing.expectEqual(rs.STENCIL_MASK_ALL, c.stencil_write_mask);
    try std.testing.expectEqual(@as(u32, 0), c.depth_stencil_format);
}

test "depth_stencil_to_c preserves asymmetric front/back stencil config" {
    const ds = rs.DepthStencilState{
        .format = 42,
        .depth_write_enabled = true,
        .depth_compare = rs.COMPARE_LESS,
        .stencil_front = .{
            .compare = rs.COMPARE_EQUAL,
            .fail_op = rs.STENCIL_OP_ZERO,
            .depth_fail_op = rs.STENCIL_OP_INVERT,
            .pass_op = rs.STENCIL_OP_REPLACE,
        },
        .stencil_back = .{
            .compare = rs.COMPARE_GREATER,
            .fail_op = rs.STENCIL_OP_INCREMENT_WRAP,
            .depth_fail_op = rs.STENCIL_OP_DECREMENT_WRAP,
            .pass_op = rs.STENCIL_OP_INCREMENT_CLAMP,
        },
        .stencil_read_mask = 0x0F,
        .stencil_write_mask = 0xF0,
    };
    const c = rs.depth_stencil_to_c(&ds);
    try std.testing.expectEqual(@as(c_int, 1), c.depth_write_enabled);
    try std.testing.expectEqual(rs.COMPARE_LESS, c.depth_compare);
    try std.testing.expectEqual(@as(u32, 42), c.depth_stencil_format);

    // Front face
    try std.testing.expectEqual(rs.COMPARE_EQUAL, c.stencil_front_compare);
    try std.testing.expectEqual(rs.STENCIL_OP_ZERO, c.stencil_front_fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_INVERT, c.stencil_front_depth_fail);
    try std.testing.expectEqual(rs.STENCIL_OP_REPLACE, c.stencil_front_pass_op);

    // Back face (different from front)
    try std.testing.expectEqual(rs.COMPARE_GREATER, c.stencil_back_compare);
    try std.testing.expectEqual(rs.STENCIL_OP_INCREMENT_WRAP, c.stencil_back_fail_op);
    try std.testing.expectEqual(rs.STENCIL_OP_DECREMENT_WRAP, c.stencil_back_depth_fail);
    try std.testing.expectEqual(rs.STENCIL_OP_INCREMENT_CLAMP, c.stencil_back_pass_op);

    // Masks
    try std.testing.expectEqual(@as(u32, 0x0F), c.stencil_read_mask);
    try std.testing.expectEqual(@as(u32, 0xF0), c.stencil_write_mask);
}

test "depth_stencil_to_c maps depth_write_enabled bool to c_int" {
    const enabled = rs.DepthStencilState{ .depth_write_enabled = true };
    const disabled = rs.DepthStencilState{ .depth_write_enabled = false };
    try std.testing.expectEqual(@as(c_int, 1), rs.depth_stencil_to_c(&enabled).depth_write_enabled);
    try std.testing.expectEqual(@as(c_int, 0), rs.depth_stencil_to_c(&disabled).depth_write_enabled);
}

// ============================================================
// C ABI export presence (comptime reference checks)
// ============================================================

test "C ABI render state exports are resolvable at comptime" {
    // Verify that each exported function exists and is callable by taking a reference.
    // This catches link-time regressions without needing a Metal runtime.
    comptime {
        _ = &rs.doeNativeRenderPassEncoderSetViewport;
        _ = &rs.doeNativeRenderPassEncoderSetScissorRect;
        _ = &rs.doeNativeRenderPassEncoderSetStencilReference;
        _ = &rs.doeNativeRenderPassEncoderSetBlendConstant;
        _ = &rs.doeNativeDeviceCreateRenderPipelineFull;
        _ = &rs.doeNativeDeviceCreateDepthStencilState;
        _ = &rs.doeNativeRenderPassEncoderSetDepthStencilState;
        _ = &rs.doeNativeDeviceCreateMsaaTexture;
        _ = &rs.doeNativeCmdBufMsaaRenderEncoder;
    }
}

// ============================================================
// Round-trip consistency: Zig -> C -> field equality
// ============================================================

test "blend_to_c round trip preserves all blend operations" {
    const ops = [_]u32{
        rs.BLEND_OP_ADD,
        rs.BLEND_OP_SUBTRACT,
        rs.BLEND_OP_REVERSE_SUBTRACT,
        rs.BLEND_OP_MIN,
        rs.BLEND_OP_MAX,
    };
    for (ops) |op| {
        const blend = rs.BlendState{
            .color = .{ .operation = op },
            .alpha = .{ .operation = op },
            .enabled = true,
        };
        const c = rs.blend_to_c(&blend);
        try std.testing.expectEqual(op, c.color_operation);
        try std.testing.expectEqual(op, c.alpha_operation);
    }
}

test "blend_to_c round trip preserves all blend factors" {
    var factor: u32 = rs.BLEND_FACTOR_ZERO;
    while (factor <= rs.BLEND_FACTOR_ONE_MINUS_SRC1_ALPHA) : (factor += 1) {
        const blend = rs.BlendState{
            .color = .{ .src_factor = factor, .dst_factor = factor },
            .alpha = .{ .src_factor = factor, .dst_factor = factor },
        };
        const c = rs.blend_to_c(&blend);
        try std.testing.expectEqual(factor, c.color_src_factor);
        try std.testing.expectEqual(factor, c.color_dst_factor);
        try std.testing.expectEqual(factor, c.alpha_src_factor);
        try std.testing.expectEqual(factor, c.alpha_dst_factor);
    }
}

test "depth_stencil_to_c round trip preserves all stencil ops" {
    const ops = [_]u32{
        rs.STENCIL_OP_KEEP,
        rs.STENCIL_OP_ZERO,
        rs.STENCIL_OP_REPLACE,
        rs.STENCIL_OP_INVERT,
        rs.STENCIL_OP_INCREMENT_CLAMP,
        rs.STENCIL_OP_DECREMENT_CLAMP,
        rs.STENCIL_OP_INCREMENT_WRAP,
        rs.STENCIL_OP_DECREMENT_WRAP,
    };
    for (ops) |op| {
        const ds = rs.DepthStencilState{
            .stencil_front = .{ .fail_op = op, .depth_fail_op = op, .pass_op = op },
            .stencil_back = .{ .fail_op = op, .depth_fail_op = op, .pass_op = op },
        };
        const c = rs.depth_stencil_to_c(&ds);
        try std.testing.expectEqual(op, c.stencil_front_fail_op);
        try std.testing.expectEqual(op, c.stencil_front_depth_fail);
        try std.testing.expectEqual(op, c.stencil_front_pass_op);
        try std.testing.expectEqual(op, c.stencil_back_fail_op);
        try std.testing.expectEqual(op, c.stencil_back_depth_fail);
        try std.testing.expectEqual(op, c.stencil_back_pass_op);
    }
}

test "depth_stencil_to_c round trip preserves all compare functions" {
    var cmp: u32 = rs.COMPARE_UNDEFINED;
    while (cmp <= rs.COMPARE_ALWAYS) : (cmp += 1) {
        const ds = rs.DepthStencilState{
            .depth_compare = cmp,
            .stencil_front = .{ .compare = cmp },
            .stencil_back = .{ .compare = cmp },
        };
        const c = rs.depth_stencil_to_c(&ds);
        try std.testing.expectEqual(cmp, c.depth_compare);
        try std.testing.expectEqual(cmp, c.stencil_front_compare);
        try std.testing.expectEqual(cmp, c.stencil_back_compare);
    }
}
