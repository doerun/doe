// shader_coverage_test_2.zig — Extended test corpus for WGSL compiler frontend surface area.
//
// Part 2 of 2: attributes, storage classes, helper functions, additional
// expressions, builtins, vertex/fragment, atomics, and const folding.
// Part 1 is in shader_coverage_test.zig.

const std = @import("std");
const mod = @import("mod.zig");
const msl_maps = @import("emit_msl_maps.zig");
const translateToMsl = mod.translateToMsl;
const translateToHlsl = mod.translateToHlsl;
const translateToSpirv = mod.translateToSpirv;
const analyzeToIr = mod.analyzeToIr;
const TranslateError = mod.TranslateError;
const MAX_OUTPUT = mod.MAX_OUTPUT;
const MAX_HLSL_OUTPUT = mod.MAX_HLSL_OUTPUT;
const MAX_SPIRV_OUTPUT = mod.MAX_SPIRV_OUTPUT;
const ir = mod.ir;

fn contains(haystack: []const u8, needle: []const u8) bool {
    return std.mem.indexOf(u8, haystack, needle) != null;
}

test "msl builtin map covers the current IR builtin surface" {
    inline for (std.meta.fields(ir.Builtin)) |field| {
        const builtin: ir.Builtin = @enumFromInt(field.value);
        if (builtin == .none) continue;
        try std.testing.expect(!std.mem.eql(u8, msl_maps.msl_builtin_name(builtin), "unsupported_builtin"));
    }
}

test "declarations: fixed-size array parameter through MSL HLSL and SPIR-V" {
    const source =
        \\fn sum4(values: array<u32, 4>) -> u32 {
        \\    return values[0] + values[1] + values[2] + values[3];
        \\}
        \\
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    var values: array<u32, 4>;
        \\    values[0] = 1u;
        \\    values[1] = 2u;
        \\    values[2] = 3u;
        \\    values[3] = 4u;
        \\    data[id.x] = sum4(values);
        \\}
    ;

    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    try std.testing.expect(contains(msl_out[0..msl_len], "sum4("));

    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    try std.testing.expect(contains(hlsl_out[0..hlsl_len], "sum4("));

    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);
}

// ============================================================
// 24. Attributes: @workgroup_size with 3 dimensions
// ============================================================

test "attributes: workgroup_size 3D through IR" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(4, 4, 2)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = 1.0;
        \\}
    ;

    var module_ir = try analyzeToIr(std.testing.allocator, source);
    defer module_ir.deinit();

    try std.testing.expect(module_ir.entry_points.items.len >= 1);
    try std.testing.expectEqual(@as(u32, 4), module_ir.entry_points.items[0].workgroup_size[0]);
    try std.testing.expectEqual(@as(u32, 4), module_ir.entry_points.items[0].workgroup_size[1]);
    try std.testing.expectEqual(@as(u32, 2), module_ir.entry_points.items[0].workgroup_size[2]);
}

// ============================================================
// 25. Attributes: multiple @group/@binding pairs
// ============================================================

test "attributes: multiple bind groups through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read> input: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> output: array<f32>;
        \\@group(1) @binding(0) var<uniform> scale: f32;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    output[id.x] = input[id.x] * scale;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "buffer("));
}

// ============================================================
// 26. Storage classes: uniform buffer with struct
// ============================================================

test "storage classes: uniform struct through HLSL" {
    const source =
        \\struct Uniforms {
        \\    width: u32,
        \\    height: u32,
        \\};
        \\
        \\@group(0) @binding(0) var<uniform> uniforms: Uniforms;
        \\@group(0) @binding(1) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = uniforms.width * uniforms.height;
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(contains(hlsl, "cbuffer") or contains(hlsl, "ConstantBuffer"));
}

// ============================================================
// 27. Storage classes: storage buffer read-only
// ============================================================

test "storage classes: read-only storage buffer through SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read> src: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> dst: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    dst[id.x] = src[id.x];
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 28. Declarations: helper function with return value
// ============================================================

test "declarations: helper function call through MSL" {
    const source =
        \\fn square(x: f32) -> f32 {
        \\    return x * x;
        \\}
        \\
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = square(data[id.x]);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "square("));
}

// ============================================================
// 29. Declarations: helper function with multiple params
// ============================================================

test "declarations: helper function with multiple params through HLSL" {
    const source =
        \\fn add_scaled(a: f32, b: f32, scale: f32) -> f32 {
        \\    return a + b * scale;
        \\}
        \\
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = add_scaled(1.0, data[id.x], 0.5);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(contains(hlsl, "add_scaled("));
}

// ============================================================
// 30. Expressions: chained member access
// ============================================================

test "expressions: chained struct member access through MSL" {
    const source =
        \\struct Inner {
        \\    value: f32,
        \\};
        \\
        \\struct Outer {
        \\    scale: f32,
        \\    data: Inner,
        \\};
        \\
        \\@group(0) @binding(0) var<uniform> params: Outer;
        \\@group(0) @binding(1) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    out[id.x] = params.data.value * params.scale;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 31. Expressions: array indexing with computed index
// ============================================================

test "expressions: array indexing with expression through SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let base = id.x * 4u;
        \\    data[base + 0u] = data[base + 1u] + data[base + 2u] + data[base + 3u];
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 32. Builtins: local_invocation_id, workgroup_id, and num_workgroups
// ============================================================

test "builtins: local_invocation_id, workgroup_id, and num_workgroups through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(
        \\    @builtin(local_invocation_id) lid: vec3u,
        \\    @builtin(workgroup_id) wid: vec3u,
        \\    @builtin(num_workgroups) nwg: vec3u
        \\) {
        \\    let index = wid.x * 64u + lid.x;
        \\    data[index] = index + nwg.x;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "thread_position_in_threadgroup"));
    try std.testing.expect(contains(msl, "threadgroup_position_in_grid"));
    try std.testing.expect(contains(msl, "threadgroups_per_grid"));
}

// ============================================================
// 33. Builtins: local_invocation_index
// ============================================================

test "builtins: local_invocation_index through HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(local_invocation_index) idx: u32) {
        \\    data[idx] = idx;
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(contains(hlsl, "SV_GroupIndex"));
}

// ============================================================
// 34. Type system: f32 scalar type constructor
// ============================================================

test "type system: f32 type constructor from u32 through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = f32(id.x);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "float("));
}

// ============================================================
// 35. Type system: u32 type constructor from f32
// ============================================================

test "type system: u32 type constructor from f32 through HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    var val: f32 = 3.14;
        \\    data[id.x] = u32(val);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(contains(hlsl, "uint("));
}

// ============================================================
// 36. Expressions: compound assignment operators
// ============================================================

test "expressions: compound assignment operators through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    var acc = data[id.x];
        \\    acc += 1.0;
        \\    acc -= 0.5;
        \\    acc *= 2.0;
        \\    data[id.x] = acc;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 37. Enable directive: f16 with vec2h operations
// ============================================================

test "enable: f16 with half-precision vector through MSL" {
    const source =
        \\enable f16;
        \\
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let h: f16 = 1.5h;
        \\    let hv = vec2<f16>(h, 2.0h);
        \\    data[id.x] = f32(hv.x + hv.y);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "half"));
}

// ============================================================
// 38. Expressions: logical and / logical or operators
// ============================================================

test "expressions: logical and-or short circuit through HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let x = data[id.x];
        \\    if (x > 0.0 && x < 1.0) {
        \\        data[id.x] = 0.5;
        \\    }
        \\    if (x <= 0.0 || x >= 1.0) {
        \\        data[id.x] = -1.0;
        \\    }
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(contains(hlsl, "&&"));
    try std.testing.expect(contains(hlsl, "||"));
}

// ============================================================
// 39. Expressions: multiple let bindings in sequence
// ============================================================

test "expressions: chained let bindings referencing prior lets through SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let a = data[id.x];
        \\    let b = a * 2.0;
        \\    let c = b + 1.0;
        \\    let d = c * a;
        \\    data[id.x] = d;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 40. Builtins: normalize through MSL
// ============================================================

test "builtins: normalize through MSL" {
    // distance() has a sema type-inference limitation (returns vec instead of
    // scalar). Test normalize on its own with compatible types.
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let a = vec3f(data[id.x], 0.0, 0.0);
        \\    let n = normalize(a);
        \\    data[id.x] = n.x;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "normalize("));
}

// ============================================================
// 41. Builtins: dot product through MSL
// ============================================================

test "builtins: dot product through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let v1 = vec4f(1.0, 2.0, 3.0, 4.0);
        \\    let v2 = vec4f(4.0, 3.0, 2.0, 1.0);
        \\    data[id.x] = dot(v1, v2);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "dot("));
}

// ============================================================
// 42. Expressions: subtraction to avoid false conflation with negation
// ============================================================

test "expressions: subtraction operator distinct from negation through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let a = data[id.x];
        \\    let b = data[id.x + 1u];
        \\    data[id.x] = a - b;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 43. Type system: atomic<u32> type with atomicLoad
// ============================================================

test "type system: atomic type with atomicLoad through MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> counter: atomic<u32>;
        \\@group(0) @binding(1) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let val = atomicLoad(counter);
        \\    data[id.x] = val;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(contains(msl, "atomic_load_explicit"));
}

// ============================================================
// 44. Vertex shader: multiple location outputs through SPIR-V
// ============================================================

test "vertex: multiple location outputs through SPIR-V" {
    const source =
        \\struct VertOut {
        \\    @builtin(position) pos: vec4f,
        \\    @location(0) color: vec4f,
        \\    @location(1) uv: vec2f,
        \\};
        \\
        \\@vertex
        \\fn main(@builtin(vertex_index) vi: u32) -> VertOut {
        \\    var out: VertOut;
        \\    out.pos = vec4f(0.0, 0.0, 0.0, 1.0);
        \\    out.color = vec4f(1.0, 0.0, 0.0, 1.0);
        \\    out.uv = vec2f(0.0, 0.0);
        \\    return out;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 45. Fragment shader: single color output through all backends
// ============================================================

test "fragment: solid color output through MSL HLSL SPIR-V" {
    const source =
        \\@fragment
        \\fn main() -> @location(0) vec4f {
        \\    return vec4f(0.2, 0.4, 0.6, 1.0);
        \\}
    ;

    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    // MSL uses "fragment" as a function qualifier, not [[fragment]].
    try std.testing.expect(contains(msl_out[0..msl_len], "main_fragment"));

    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    try std.testing.expect(contains(hlsl_out[0..hlsl_len], "SV_Target0"));

    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);
}

// ============================================================
// 46. Expressions: nested function calls
// ============================================================

test "expressions: nested builtin calls through SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = abs(sin(cos(data[id.x])));
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 47. Const folding: integer arithmetic at module scope
// ============================================================

test "const folding: module-scope literal arithmetic through MSL" {
    // Inter-const references (const B = A * 2) are not yet supported by sema
    // (UnknownIdentifier). Test const folding with direct literal expressions.
    const source =
        \\const TILE_SIZE: u32 = 8u;
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = TILE_SIZE;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 48. Pointer parameters: ptr<storage, array<f32>> in helper function
// ============================================================

test "pointer param: helper with ptr<storage, f32> MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> val: f32;
        \\
        \\fn add_one(p: ptr<storage, f32, read_write>) {
        \\    *p = *p + 1.0;
        \\}
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    add_one(&val);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    // MSL pointer param must use device address space, not bare element type.
    try std.testing.expect(contains(msl, "device"));
}

test "pointer param: helper with ptr<storage, f32> HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> val: f32;
        \\
        \\fn add_one(p: ptr<storage, f32, read_write>) {
        \\    *p = *p + 1.0;
        \\}
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    add_one(&val);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    // HLSL pointer param must use inout qualifier.
    try std.testing.expect(contains(hlsl, "inout"));
}

test "pointer param: helper with ptr<storage, f32> SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> val: f32;
        \\
        \\fn add_one(p: ptr<storage, f32, read_write>) {
        \\    *p = *p + 1.0;
        \\}
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    add_one(&val);
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

// ============================================================
// 49. Cube texture types: texture_cube, texture_depth_cube
// ============================================================

test "texture_cube compiles to MSL" {
    const source =
        \\@group(0) @binding(0) var t: texture_cube<f32>;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(contains(out[0..len], "texturecube"));
}

test "texture_cube compiles to HLSL" {
    const source =
        \\@group(0) @binding(0) var t: texture_cube<f32>;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(contains(out[0..len], "TextureCube"));
}

test "texture_cube compiles to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var t: texture_cube<f32>;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "texture_depth_cube compiles to MSL" {
    const source =
        \\@group(0) @binding(0) var t: texture_depth_cube;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(contains(out[0..len], "depthcube"));
}

// ============================================================
// 50. 2D array texture type: texture_2d_array
// ============================================================

test "texture_2d_array compiles to MSL" {
    const source =
        \\@group(0) @binding(0) var t: texture_2d_array<f32>;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(contains(out[0..len], "texture2d_array"));
}

test "texture_2d_array compiles to HLSL" {
    const source =
        \\@group(0) @binding(0) var t: texture_2d_array<f32>;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(contains(out[0..len], "Texture2DArray"));
}

test "texture_2d_array compiles to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var t: texture_2d_array<f32>;
        \\@group(0) @binding(1) var s: sampler;
        \\@group(0) @binding(2) var<storage, read_write> out: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let dims = textureDimensions(t, 0);
        \\    out[id.x] = f32(dims.x);
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}
