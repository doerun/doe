// emit_spirv_stage_test.zig — SPIR-V vertex and fragment stage emission tests.

const std = @import("std");
const spirv = @import("spirv_builder.zig");
const mod = @import("mod.zig");

const testing = std.testing;
const allocator = testing.allocator;

const MAX_SPIRV_OUTPUT = mod.MAX_SPIRV_OUTPUT;
const translateToSpirv = mod.translateToSpirv;

fn read_u32_le(bytes: []const u8, offset: usize) u32 {
    return std.mem.readInt(u32, @as(*const [4]u8, @ptrCast(bytes[offset .. offset + 4].ptr)), .little);
}

// ============================================================
// HLSL type mapping tests (via IR construction)
// ============================================================

test "spirv vertex: produces valid binary with vertex entry point" {
    const source =
        \\struct VsOut {
        \\    @builtin(position) position: vec4f,
        \\    @location(0) uv: vec2f,
        \\}
        \\
        \\@vertex
        \\fn main(@builtin(vertex_index) vid: u32) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // OpEntryPoint Vertex (ExecutionModel = 0) should appear
    var found_vertex = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 15 and wc >= 3) {
            const exec_model = read_u32_le(binary, (i + 1) * 4);
            if (exec_model == 0) { // Vertex
                found_vertex = true;
                break;
            }
        }
        i += wc;
    }
    try testing.expect(found_vertex);
}

test "spirv fragment: produces valid binary with fragment entry point" {
    const source =
        \\@fragment
        \\fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
        \\    return vec4f(uv, 0.0, 1.0);
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // OpEntryPoint Fragment (ExecutionModel = 4)
    var found_fragment = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 15 and wc >= 3) {
            const exec_model = read_u32_le(binary, (i + 1) * 4);
            if (exec_model == 4) { // Fragment
                found_fragment = true;
                break;
            }
        }
        i += wc;
    }
    try testing.expect(found_fragment);
}

test "spirv vertex: struct return with position and location" {
    const source =
        \\struct VsOut {
        \\    @builtin(position) clip_pos: vec4f,
        \\    @location(0) uv: vec2f,
        \\}
        \\
        \\@vertex
        \\fn vs_main(@builtin(vertex_index) vid: u32) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // Verify Vertex execution model and at least one OpDecorate for Location
    var found_vertex = false;
    var found_location = false;
    var found_builtin = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 15 and wc >= 3) { // OpEntryPoint
            const exec_model = read_u32_le(binary, (i + 1) * 4);
            if (exec_model == 0) found_vertex = true; // Vertex
        }
        if (op == 71 and wc >= 3) { // OpDecorate
            const decoration = read_u32_le(binary, (i + 2) * 4);
            if (decoration == 30) found_location = true; // Location
            if (decoration == 11) found_builtin = true; // BuiltIn
        }
        i += wc;
    }
    try testing.expect(found_vertex);
    try testing.expect(found_location);
    try testing.expect(found_builtin);
}

test "spirv vertex: struct input parameter" {
    const source =
        \\struct VertIn {
        \\    @location(0) pos: vec4f,
        \\    @location(1) uv: vec2f,
        \\}
        \\struct VertOut {
        \\    @builtin(position) clip_pos: vec4f,
        \\    @location(0) uv: vec2f,
        \\}
        \\@vertex
        \\fn vs_main(in: VertIn) -> VertOut {
        \\    var out: VertOut;
        \\    out.clip_pos = in.pos;
        \\    out.uv = in.uv;
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // Count Location decorations: should have at least 3
    // (2 input locations + 1 output location)
    var location_count: u32 = 0;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 71 and wc >= 3) { // OpDecorate
            const decoration = read_u32_le(binary, (i + 2) * 4);
            if (decoration == 30) location_count += 1; // Location
        }
        i += wc;
    }
    try testing.expect(location_count >= 3);
}

test "spirv fragment: struct return with MRT outputs" {
    const source =
        \\struct FragOut {
        \\    @location(0) color0: vec4f,
        \\    @location(1) color1: vec4f,
        \\}
        \\@fragment
        \\fn fs_main(@location(0) uv: vec2f) -> FragOut {
        \\    var out: FragOut;
        \\    out.color0 = vec4f(uv, 0.0, 1.0);
        \\    out.color1 = vec4f(1.0, 0.0, 0.0, 1.0);
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // Verify Fragment execution model and OriginUpperLeft execution mode
    var found_fragment = false;
    var found_origin_upper_left = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 15 and wc >= 3) { // OpEntryPoint
            const exec_model = read_u32_le(binary, (i + 1) * 4);
            if (exec_model == 4) found_fragment = true;
        }
        if (op == 16 and wc >= 3) { // OpExecutionMode
            const mode = read_u32_le(binary, (i + 2) * 4);
            if (mode == 7) found_origin_upper_left = true;
        }
        i += wc;
    }
    try testing.expect(found_fragment);
    try testing.expect(found_origin_upper_left);
}

test "spirv fragment: frag_depth output with DepthReplacing" {
    const source =
        \\struct FragOut {
        \\    @location(0) color: vec4f,
        \\    @builtin(frag_depth) depth: f32,
        \\}
        \\@fragment
        \\fn fs_main(@location(0) uv: vec2f) -> FragOut {
        \\    var out: FragOut;
        \\    out.color = vec4f(uv, 0.0, 1.0);
        \\    out.depth = 0.5;
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // Verify DepthReplacing execution mode (12)
    var found_depth_replacing = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 16 and wc >= 3) { // OpExecutionMode
            const mode = read_u32_le(binary, (i + 2) * 4);
            if (mode == 12) found_depth_replacing = true;
        }
        i += wc;
    }
    try testing.expect(found_depth_replacing);
}

test "spirv vertex: interpolation decorations on outputs" {
    const source =
        \\struct VsOut {
        \\    @builtin(position) pos: vec4f,
        \\    @location(0) @interpolate(flat) flat_val: f32,
        \\    @location(1) @interpolate(linear) linear_val: vec2f,
        \\}
        \\@vertex
        \\fn vs_main(@builtin(vertex_index) vid: u32) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(binary, 0));

    // Verify Flat (14) and NoPerspective (13) decorations
    var found_flat = false;
    var found_noperspective = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 71 and wc >= 3) { // OpDecorate
            const decoration = read_u32_le(binary, (i + 2) * 4);
            if (decoration == 14) found_flat = true;
            if (decoration == 13) found_noperspective = true;
        }
        i += wc;
    }
    try testing.expect(found_flat);
    try testing.expect(found_noperspective);
}
