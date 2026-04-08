// mod_api_stage_and_pointer_test.zig - Shard of mod_api_test.zig covering stage IO and pointer-lowering coverage.

const support = @import("mod_api_test_support.zig");
const std = support.std;
const lean_proof = support.lean_proof;
const runtime_compile = support.runtime_compile;
const translateToMsl = support.translateToMsl;
const translateToHlsl = support.translateToHlsl;
const translateToSpirv = support.translateToSpirv;
const analyzeToIr = support.analyzeToIr;
const analyzeToIrWithConfig = support.analyzeToIrWithConfig;
const ir = support.ir;
const MAX_OUTPUT = support.MAX_OUTPUT;
const MAX_HLSL_OUTPUT = support.MAX_HLSL_OUTPUT;
const MAX_SPIRV_OUTPUT = support.MAX_SPIRV_OUTPUT;

test "translate inter-stage variables with centroid sampling to SPIR-V" {
    const source =
        \\struct VsOut {
        \\    @builtin(position) pos: vec4f,
        \\    @location(0) @interpolate(perspective, centroid) uv: vec2f,
        \\    @location(1) @interpolate(flat) flat_id: u32,
        \\    @location(2) @interpolate(linear, sample) sample_val: f32,
        \\}
        \\@vertex
        \\fn vs_main(@builtin(vertex_index) vid: u32) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(len >= 20);
    const magic = std.mem.readInt(u32, @as(*const [4]u8, @ptrCast(out[0..4].ptr)), .little);
    try std.testing.expectEqual(@as(u32, 0x07230203), magic);
}

test "translate MRT fragment output to all backends" {
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

    // MSL
    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    const msl = msl_out[0..msl_len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "color(0)") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "color(1)") != null);

    // HLSL
    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    const hlsl = hlsl_out[0..hlsl_len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "SV_Target0") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "SV_Target1") != null);

    // SPIR-V
    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);
}

test "translate interpolation with centroid sampling to MSL" {
    const source =
        \\struct VsOut {
        \\    @builtin(position) pos: vec4f,
        \\    @location(0) @interpolate(perspective, centroid) uv: vec2f,
        \\    @location(1) @interpolate(linear, centroid) linear_c: f32,
        \\}
        \\@vertex
        \\fn vs_main(@builtin(vertex_index) vid: u32) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "centroid_perspective") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "centroid_no_perspective") != null);
}

test "translate flat either interpolation to MSL" {
    const source =
        \\struct VsOut {
        \\    @builtin(position) pos: vec4f,
        \\    @location(0) @interpolate(flat, either) flat_id: u32,
        \\}
        \\@vertex
        \\fn vs_main(@builtin(vertex_index) vid: u32) -> VsOut {
        \\    var out: VsOut;
        \\    out.flat_id = vid;
        \\    return out;
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate benchmark-style vector and any/all constructs to MSL" {
    const source =
        \\struct RenderParams {
        \\  right : vec3<f32>,
        \\  up : vec3<f32>,
        \\};
        \\@binding(0) @group(0) var<uniform> render_params : RenderParams;
        \\@binding(1) @group(0) var tex : texture_2d<f32>;
        \\@binding(2) @group(0) var tex_out : texture_storage_2d<rgba8unorm, write>;
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) gid : vec3<u32>) {
        \\  let quad_pos = mat2x3<f32>(render_params.right, render_params.up) * vec2<f32>(1.0, 2.0);
        \\  let value = vec4<f32>(0.5);
        \\  let probs = vec4<f32>(0.0, 0.2, 0.4, 0.8);
        \\  let mask = (value >= vec4<f32>(0.0, probs.xyz)) & (value < probs);
        \\  if (all(gid.xy < vec2<u32>(textureDimensions(tex_out)))) {
        \\    let step = select(0u, 1u, any(mask.yw));
        \\    textureStore(tex_out, vec2<i32>(i32(step), i32(gid.y)), vec4<f32>(quad_pos, 1.0));
        \\  }
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate benchmark-style matrix constructors and scalar broadcasts to MSL" {
    const source =
        \\struct VertexInput {
        \\  @location(0) normal : vec3<f32>,
        \\  @location(1) instance0 : vec4<f32>,
        \\  @location(2) instance1 : vec4<f32>,
        \\  @location(3) instance2 : vec4<f32>,
        \\  @location(4) instance3 : vec4<f32>,
        \\}
        \\fn getInstanceMatrix(input : VertexInput) -> mat4x4<f32> {
        \\  return mat4x4(input.instance0, input.instance1, input.instance2, input.instance3);
        \\}
        \\@vertex
        \\fn main(input : VertexInput) -> @builtin(position) vec4<f32> {
        \\  let m = getInstanceMatrix(input);
        \\  let n = normalize((m * vec4f(input.normal, 0.0)).xyz);
        \\  let lit = min(0.2 + 0.5 * n, vec3<f32>(1.0));
        \\  return vec4<f32>(lit, 1.0);
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate nested bitcast generic call to MSL" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\  var a : vec3<i32>;
        \\  var b : vec4<u32>;
        \\  let c = (a.xyzz >= bitcast<vec4<i32>>(b.xyww)).xyz;
        \\  _ = c;
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate zero-arg value constructors to MSL" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\  let a = vec4<f32>();
        \\  let b = vec2<u32>();
        \\  let c = mat4x4<f32>();
        \\  _ = a;
        \\  _ = b;
        \\  _ = c;
        \\}
    ;
    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "compile shader with pointer output parameter to MSL" {
    const source =
        \\fn helper(p: ptr<function, f32>) {
        \\    *p = 1.0;
        \\}
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    var x: f32 = 0.0;
        \\    helper(&x);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "helper") != null);
}

test "compile shader with pointer output parameter to HLSL" {
    const source =
        \\fn helper(p: ptr<function, f32>) {
        \\    *p = 1.0;
        \\}
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    var x: f32 = 0.0;
        \\    helper(&x);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "inout") != null);
}

test "compile shader with pointer output parameter to SPIR-V" {
    const source =
        \\fn helper(p: ptr<function, f32>) {
        \\    *p = 1.0;
        \\}
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    var x: f32 = 0.0;
        \\    helper(&x);
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "compile shader with dereferenced pointer locals to MSL" {
    const source =
        \\fn read_back(p: ptr<function, i32>) -> i32 {
        \\    let x : i32 = *p;
        \\    return x;
        \\}
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    var x: i32 = 7;
        \\    let y = read_back(&x);
        \\    _ = y;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "compile shader with let-bound ref writes to MSL" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    var x: vec4<f32> = vec4<f32>(1.0);
        \\    let p = &(x);
        \\    *(p) = vec4<f32>(2.0);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "const thread float4& p = x;") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "p = float4(2.0);") != null);
}

test "compile shader using atomicAdd result as scalar value to MSL" {
    const source =
        \\struct OutBuf {
        \\    values: array<u32>,
        \\};
        \\
        \\@group(0) @binding(0) var<storage, read_write> counter: atomic<u32>;
        \\@group(0) @binding(1) var<storage, read_write> out_buf: OutBuf;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let old = atomicAdd(&(counter), 1u);
        \\    out_buf.values[0] = old + 1u;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "const uint old = atomic_fetch_add_explicit") != null);
}
