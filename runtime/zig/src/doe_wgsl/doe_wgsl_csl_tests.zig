const std = @import("std");
const csl_spec = @import("csl_spec.zig");

pub fn expectArrayLengthInComparisonCompiles(
    allocator: std.mem.Allocator,
    comptime translateToMslFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    if (id.x < arrayLength(&buf)) { buf[id.x] = buf[id.x] * 2.0; }
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToMslFn(allocator, source, &out);
    try std.testing.expect(len > 0);
}

pub fn expectRuntimeSizedConstantIndexCoercesAbstractIntForMslMin(
    allocator: std.mem.Allocator,
    comptime translateToMslFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> buf: array<u32>;
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    buf[0] = 42u;
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToMslFn(allocator, source, &out);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "min(uint(0), (uint(_doe_sizes[0] / sizeof(uint)) - 1))") != null);
}

pub fn expectVertexArrayClampCoercesU32LiteralForMslMin(
    allocator: std.mem.Allocator,
    comptime translateToMslFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\@vertex
        \\fn main(@builtin(vertex_index) vid: u32) -> @builtin(position) vec4f {
        \\    var pos = array<vec2f, 3>(
        \\        vec2f( 0.0,  0.5),
        \\        vec2f(-0.5, -0.5),
        \\        vec2f( 0.5, -0.5),
        \\    );
        \\    return vec4f(pos[vid], 0.0, 1.0);
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToMslFn(allocator, source, &out);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "min(vid, uint(2))") != null);
}

pub fn expectArrayLengthOnStructMemberCompilesToMsl(
    allocator: std.mem.Allocator,
    comptime translateToMslFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\struct Storage {
        \\    count: u32,
        \\    data: array<f32>,
        \\}
        \\@group(0) @binding(0) var<storage, read_write> buf: Storage;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let len = arrayLength(&buf.data);
        \\    buf.data[0] = f32(len);
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToMslFn(allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "_doe_sizes[") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "- 4)") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "sizeof(float)") != null);
}

pub fn expectArrayLengthOnStructMemberCompilesToHlsl(
    allocator: std.mem.Allocator,
    comptime translateToHlslFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\struct Storage {
        \\    count: u32,
        \\    data: array<f32>,
        \\}
        \\@group(0) @binding(0) var<storage, read_write> buf: Storage;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let len = arrayLength(&buf.data);
        \\    buf.data[0] = f32(len);
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToHlslFn(allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_arrayLength_buf_data()") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "GetDimensions") != null);
}

pub fn expectArrayLengthOnStructMemberCompilesToSpirv(
    allocator: std.mem.Allocator,
    comptime translateToSpirvFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\struct Storage {
        \\    count: u32,
        \\    data: array<f32>,
        \\}
        \\@group(0) @binding(0) var<storage, read_write> buf: Storage;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let len = arrayLength(&buf.data);
        \\    buf.data[0] = f32(len);
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToSpirvFn(allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(len >= 20);
    const magic = std.mem.readInt(u32, @as(*const [4]u8, @ptrCast(out[0..4].ptr)), .little);
    try std.testing.expectEqual(@as(u32, 0x07230203), magic);
}

pub fn expectElementWiseComputeShaderCompilesToCsl(
    allocator: std.mem.Allocator,
    comptime translateToCslFn: anytype,
    comptime max_output: usize,
) !void {
    const source =
        \\struct Uniforms {
        \\    size: u32,
        \\    _pad0: u32,
        \\    _pad1: u32,
        \\    _pad2: u32,
        \\}
        \\@group(0) @binding(0) var<uniform> u: Uniforms;
        \\@group(0) @binding(1) var<storage, read> input: array<f32>;
        \\@group(0) @binding(2) var<storage, read_write> output: array<f32>;
        \\fn gelu(x: f32) -> f32 {
        \\    let inner = 0.7978845608 * (x + 0.044715 * x * x * x);
        \\    let inner_clamped = clamp(inner, -15.0, 15.0);
        \\    return 0.5 * x * (1.0 + tanh(inner_clamped));
        \\}
        \\@compute @workgroup_size(256)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let idx = gid.x;
        \\    if (idx >= u.size) { return; }
        \\    let x = input[idx];
        \\    output[idx] = gelu(x);
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const len = try translateToCslFn(allocator, source, &out);
    try std.testing.expect(len > 0);
    const csl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, csl, "layout.csl") != null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "pe_program.csl") != null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "@set_rectangle") != null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "memcpy") != null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "math") != null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "gelu") != null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "@export_symbol(compute)") != null);
    try std.testing.expect(csl_spec.validateOutput(csl) == null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "TODO") == null);
    try std.testing.expect(std.mem.indexOf(u8, csl, "gelu(") != null);
}

pub fn expectVertexShaderRejectedForCsl(
    allocator: std.mem.Allocator,
    comptime translateToCslFn: anytype,
    expected_error: anyerror,
    comptime max_output: usize,
) !void {
    const source =
        \\@vertex
        \\fn vs_main(@builtin(vertex_index) vid: u32) -> @builtin(position) vec4f {
        \\    return vec4f(0.0, 0.0, 0.0, 1.0);
        \\}
    ;
    var out: [max_output]u8 = undefined;
    const result = translateToCslFn(allocator, source, &out);
    try std.testing.expectError(expected_error, result);
}
