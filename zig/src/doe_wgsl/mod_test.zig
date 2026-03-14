const builtin = @import("builtin");
const std = @import("std");
const mod = @import("mod.zig");
const translateToMsl = mod.translateToMsl;
const translateToHlsl = mod.translateToHlsl;
const translateToDxil = mod.translateToDxil;
const translateToDxilWithToolchainConfig = mod.translateToDxilWithToolchainConfig;
const translateToSpirv = mod.translateToSpirv;
const analyzeToIr = mod.analyzeToIr;
const TranslateError = mod.TranslateError;
const CompilationStage = mod.CompilationStage;
const DxilToolchainConfig = mod.DxilToolchainConfig;
const DXIL_DXC_ENV_VAR = mod.DXIL_DXC_ENV_VAR;
const lastErrorStage = mod.lastErrorStage;
const lastErrorKind = mod.lastErrorKind;
const lastErrorContext = mod.lastErrorContext;
const lastErrorInfo = mod.lastErrorInfo;
const lastErrorMessage = mod.lastErrorMessage;
const MAX_OUTPUT = mod.MAX_OUTPUT;
const MAX_HLSL_OUTPUT = mod.MAX_HLSL_OUTPUT;
const MAX_SPIRV_OUTPUT = mod.MAX_SPIRV_OUTPUT;
const MAX_DXIL_OUTPUT = mod.MAX_DXIL_OUTPUT;
const ir = mod.ir;

test "translate simple compute shader with builtin vector member access to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = data[id.x] * 2.0;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "main_kernel") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_position_in_grid") != null);
}

test "translate vertex shader with struct input to SPIR-V" {
    const source =
        \\struct VsIn {
        \\    @builtin(vertex_index) vertex_index: u32,
        \\    @location(0) uv: vec2f,
        \\};
        \\
        \\struct VsOut {
        \\    @builtin(position) position: vec4f,
        \\    @location(0) uv: vec2f,
        \\};
        \\
        \\@vertex
        \\fn main(input: VsIn) -> VsOut {
        \\    var out: VsOut;
        \\    return out;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate fragment shader with struct input to SPIR-V" {
    const source =
        \\struct FsIn {
        \\    @location(0) uv: vec2f,
        \\};
        \\
        \\struct FsOut {
        \\    @location(0) color: vec4f,
        \\};
        \\
        \\@fragment
        \\fn main(input: FsIn) -> FsOut {
        \\    var out: FsOut;
        \\    return out;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate simple vertex shader to MSL" {
    const source =
        \\@vertex
        \\fn main(@location(0) uv: vec2f) -> @builtin(position) vec4f {
        \\    return vec4f(uv, 0.0, 1.0);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "vertex") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "[[stage_in]]") != null);
}

test "translate simple fragment shader to MSL" {
    const source =
        \\@fragment
        \\fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
        \\    return vec4f(uv, 0.0, 1.0);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "fragment") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "[[color(0)]]") != null);
}

test "translate fragment shader with uniform binding to MSL" {
    const source =
        \\@group(0) @binding(0) var<uniform> tint: vec4f;
        \\
        \\@fragment
        \\fn main() -> @location(0) vec4f {
        \\    return tint;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "constant float4& tint [[buffer(0)]]") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "main_impl(tint)") != null);
}

test "translate simple vertex shader to HLSL" {
    const source =
        \\@vertex
        \\fn main(@location(0) uv: vec2f) -> @builtin(position) vec4f {
        \\    return vec4f(uv, 0.0, 1.0);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "_stage_out") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "SV_Position") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "TEXCOORD0") != null);
}

test "translate simple fragment shader to HLSL" {
    const source =
        \\@fragment
        \\fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
        \\    return vec4f(uv, 0.0, 1.0);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "_stage_out") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "SV_Target0") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "TEXCOORD0") != null);
}

test "translate vec4f constructor to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = vec4f(1.0, 2.0, 3.0, 4.0);
        \\    data[id.x] = value.x;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate vec4 generic constructor to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = vec4<f32>(1.0, 2.0, 3.0, 4.0);
        \\    data[id.x] = value.x;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate shader with suffixed integer and float literals to MSL" {
    const source =
        \\struct Dims {
        \\    m: u32,
        \\    n: u32,
        \\    _pad0: u32,
        \\    _pad1: u32,
        \\};
        \\
        \\@group(0) @binding(0) var<uniform> dims: Dims;
        \\@group(0) @binding(1) var<storage, read> src: array<f32>;
        \\@group(0) @binding(2) var<storage, read_write> dst: array<f32>;
        \\
        \\@compute @workgroup_size(8u, 8u, 1u)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    if (gid.x >= dims.n || gid.y >= dims.m) {
        \\        return;
        \\    }
        \\    let index = gid.y * dims.n + gid.x;
        \\    dst[index] = src[index] * 2.0f + 1.0f;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "analyze WGSL with suffixed attrs and array sizes" {
    const source =
        \\@group(0u) @binding(1u) var<storage, read_write> data: array<f32, 4u>;
        \\const size: u32 = 4u;
        \\override gain: f32 = 1f;
        \\
        \\@compute @workgroup_size(8u, 1u, 1u)
        \\fn main() {
        \\    let value: i32 = -2i;
        \\}
    ;

    var module_ir = try analyzeToIr(std.testing.allocator, source);
    defer module_ir.deinit();

    try std.testing.expectEqual(@as(u32, 1), module_ir.globals.items[0].binding.?.binding);
    try std.testing.expectEqual(@as(u32, 8), module_ir.entry_points.items[0].workgroup_size[0]);
    try std.testing.expectEqual(@as(u64, 4), module_ir.globals.items[1].initializer.?.int);
    try std.testing.expectEqual(@as(f64, 1), module_ir.globals.items[2].initializer.?.float);
}

test "translate multi-element vector swizzle to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = vec4f(1.0, 2.0, 3.0, 4.0);
        \\    let swizzled = value.yxwz;
        \\    data[id.x] = swizzled.z;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate bitcast generic call to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = bitcast<u32>(1.0f);
        \\    data[id.x] = value;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "as_type<uint>(") != null);
}

test "translate bitcast generic call to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = bitcast<u32>(1.0f);
        \\    data[id.x] = value;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate pack and unpack half builtins to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let packed = pack2x16float(vec2f(1.0, 2.0));
        \\    let unpacked = unpack2x16float(packed);
        \\    if (unpacked.x > 0.0) {
        \\        data[id.x] = packed;
        \\    }
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "as_type<uint>(half2(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "float2(as_type<half2>(") != null);
}

test "translate msl math builtins keeps scalar float literals explicit" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = clamp(cos(1.0), 0.0, 1.0);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "cos(1.0)") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "0.0") != null);
}

test "translate MSL-only math builtin mappings explicitly" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = degrees(1.0) + radians(180.0) + inverseSqrt(4.0);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "57.29577951308232") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "0.017453292519943295") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "rsqrt(") != null);
}

test "translate texture builtins to MSL explicitly" {
    const source =
        \\@group(0) @binding(0) var tex: texture_2d<f32>;
        \\@group(0) @binding(1) var out_tex: texture_storage_2d<rgba8unorm, write>;
        \\@group(0) @binding(2) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let sample = textureLoad(tex, vec2u(id.xy), 0);
        \\    textureStore(out_tex, vec2u(id.xy), sample);
        \\    data[id.x] = sample.x;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], ".read(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], ".write(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "texture2d<float, access::write>") != null);
}

test "translate atomic builtins to MSL explicitly" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> value: atomic<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let old = atomicAdd(value, 1u);
        \\    atomicStore(value, old);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "atomic_fetch_add_explicit") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "atomic_store_explicit") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "memory_order_relaxed") != null);
}

test "translate pack and unpack half builtins to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let packed = pack2x16float(vec2f(1.0, 2.0));
        \\    let unpacked = unpack2x16float(packed);
        \\    if (unpacked.x > 0.0) {
        \\        data[id.x] = packed;
        \\    }
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate pack and unpack 4x8 normalized builtins to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let packed_u = pack4x8unorm(vec4f(0.0, 0.5, 1.0, 0.25));
        \\    let packed_s = pack4x8snorm(vec4f(-1.0, -0.5, 0.5, 1.0));
        \\    let unpacked_u = unpack4x8unorm(packed_u);
        \\    let unpacked_s = unpack4x8snorm(packed_s);
        \\    if (unpacked_u.y >= 0.0 && unpacked_s.z >= -1.0) {
        \\        data[id.x] = packed_u ^ packed_s;
        \\    }
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "as_type<uint>(uchar4(round(clamp(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "as_type<uint>(char4(round(clamp(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "float4(as_type<uchar4>(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "float4(as_type<char4>(") != null);
}

test "translate pack and unpack 4x8 normalized builtins to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let packed_u = pack4x8unorm(vec4f(0.0, 0.5, 1.0, 0.25));
        \\    let packed_s = pack4x8snorm(vec4f(-1.0, -0.5, 0.5, 1.0));
        \\    let unpacked_u = unpack4x8unorm(packed_u);
        \\    let unpacked_s = unpack4x8snorm(packed_s);
        \\    if (unpacked_u.y >= 0.0 && unpacked_s.z >= -1.0) {
        \\        data[id.x] = packed_u ^ packed_s;
        \\    }
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate common subgroup builtins to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(32)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let base = data[id.x];
        \\    let reduced = subgroupAdd(base);
        \\    let prefix = subgroupExclusiveAdd(base);
        \\    let lane = subgroupBroadcast(base, 0u);
        \\    let shuffled = subgroupShuffle(base, 1u);
        \\    let mixed = subgroupShuffleXor(base, 1u);
        \\    data[id.x] = reduced + prefix + lane + shuffled + mixed;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "simd_sum(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "simd_prefix_exclusive_sum(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "simd_broadcast(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "simd_shuffle(") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "simd_shuffle_xor(") != null);
}

test "translate common subgroup builtins to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(32)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let base = data[id.x];
        \\    let reduced = subgroupAdd(base);
        \\    let prefix = subgroupExclusiveAdd(base);
        \\    let lane = subgroupBroadcast(base, 0u);
        \\    let shuffled = subgroupShuffle(base, 1u);
        \\    let mixed = subgroupShuffleXor(base, 1u);
        \\    data[id.x] = reduced + prefix + lane + shuffled + mixed;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate common math builtins to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let value = clamp(cos(1.0), 0.0, 1.0) + sqrt(4.0) + exp2(1.0) + floor(1.5);
        \\    data[id.x] = value;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate f16 shader to SPIR-V" {
    const source =
        \\enable f16;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let value: f16 = 1.0h;
        \\    if (value > 0.0h) {
        \\    }
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate storage struct with matrix to SPIR-V" {
    const source =
        \\struct Params {
        \\    transform: mat4x4f,
        \\};
        \\
        \\@group(0) @binding(0) var<uniform> params: Params;
        \\@group(0) @binding(1) var<storage, read_write> out_data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    out_data[id.x] = 1.0;
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "semantic type mismatch preserves stage kind and source context" {
    try std.testing.expectError(TranslateError.UnexpectedToken, analyzeToIr(std.testing.allocator, "fn main("));
    try std.testing.expectEqual(CompilationStage.parser, lastErrorStage());
    try std.testing.expectEqual(TranslateError.UnexpectedToken, lastErrorKind().?);
    try std.testing.expect(std.mem.startsWith(u8, lastErrorMessage(), "parser:"));

    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let value: bool = 1u;
        \\}
    ;
    try std.testing.expectError(TranslateError.TypeMismatch, analyzeToIr(std.testing.allocator, source));
    const info = lastErrorInfo();
    try std.testing.expectEqual(CompilationStage.sema, info.stage);
    try std.testing.expectEqual(TranslateError.TypeMismatch, info.kind.?);
    try std.testing.expect(info.location != null);
    try std.testing.expect(std.mem.indexOf(u8, info.context, "let value: bool = 1u;") != null);
    try std.testing.expect(std.mem.startsWith(u8, lastErrorMessage(), "sema: TypeMismatch"));
}

test "semantic unsupported builtin preserves specific error contract" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let value = transpose(1.0);
        \\}
    ;

    try std.testing.expectError(TranslateError.UnsupportedBuiltin, analyzeToIr(std.testing.allocator, source));
    try std.testing.expectEqual(CompilationStage.sema, lastErrorStage());
    try std.testing.expectEqual(TranslateError.UnsupportedBuiltin, lastErrorKind().?);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorContext(), "transpose(1.0)") != null);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorMessage(), "UnsupportedBuiltin") != null);
}

test "ir builder unsupported construct preserves specific error contract" {
    const source =
        \\const FLAG: bool = !true;
        \\@compute @workgroup_size(1)
        \\fn main() {}
    ;

    try std.testing.expectError(TranslateError.UnsupportedConstruct, analyzeToIr(std.testing.allocator, source));
    try std.testing.expectEqual(CompilationStage.ir_builder, lastErrorStage());
    try std.testing.expectEqual(TranslateError.UnsupportedConstruct, lastErrorKind().?);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorContext(), "const FLAG: bool = !true;") != null);
    try std.testing.expect(std.mem.startsWith(u8, lastErrorMessage(), "ir_builder: UnsupportedConstruct"));
}

test "analyze WGSL folds scalar const binary expressions" {
    const source =
        \\const MASK: u32 = 0xFFu & 0x0Fu;
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = MASK;
        \\}
    ;

    var module_ir = try analyzeToIr(std.testing.allocator, source);
    defer module_ir.deinit();

    try std.testing.expectEqual(@as(usize, 2), module_ir.globals.items.len);
    try std.testing.expect(module_ir.globals.items[0].initializer != null);
    try std.testing.expectEqual(ir.ConstantValue{ .int = 0x0F }, module_ir.globals.items[0].initializer.?);
}

test "translate bitcast to HLSL uses asuint and asfloat" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let as_uint = bitcast<u32>(1.0f);
        \\    let as_float = bitcast<f32>(as_uint);
        \\    data[id.x] = bitcast<u32>(as_float);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "asuint(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "asfloat(") != null);
}

test "translate subgroup builtins to HLSL Wave intrinsics" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(32)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let base = data[id.x];
        \\    let reduced = subgroupAdd(base);
        \\    let prefix = subgroupExclusiveAdd(base);
        \\    let lane = subgroupBroadcast(base, 0u);
        \\    let shuffled = subgroupShuffle(base, 1u);
        \\    let mixed = subgroupShuffleXor(base, 1u);
        \\    data[id.x] = reduced + prefix + lane + shuffled + mixed;
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "WaveActiveSum(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "WavePrefixSum(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "WaveReadLaneAt(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "WaveGetLaneIndex()") != null);
}

test "translate atomic builtins to HLSL helpers" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> value: atomic<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let old = atomicAdd(value, 1u);
        \\    atomicStore(value, old);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_atomicAdd(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_atomicStore(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "InterlockedAdd(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "InterlockedExchange(") != null);
}

test "translate signed atomic builtins to HLSL helpers" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> value: atomic<i32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\    let old = atomicAdd(value, 1);
        \\    atomicStore(value, old);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "int doe_atomicAdd(inout int v, int a)") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "void doe_atomicStore(inout int value, int next)") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_atomicAdd(value, 1)") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_atomicStore(value, old)") != null);
}

test "translate pack and unpack builtins to HLSL helpers" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let packed = pack2x16float(vec2f(1.0, 2.0));
        \\    let unpacked = unpack2x16float(packed);
        \\    if (unpacked.x > 0.0) {
        \\        data[id.x] = packed;
        \\    }
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_pack2x16float(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_unpack2x16float(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "f16tof32(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "f32tof16(") != null);
}

test "translate HLSL math name remapping fract mix inverseSqrt" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = fract(1.5) + inverseSqrt(4.0) + mix(0.0, 1.0, 0.5);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "frac(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "rsqrt(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "lerp(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "fract") == null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "inverseSqrt") == null);
}

test "translate degrees radians to HLSL inline multiply" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = degrees(1.0) + radians(180.0);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "57.29577951308232") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "0.017453292519943295") != null);
}

test "translate compound assignment with inferred f32 local to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read> lhs: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> out: array<f32>;
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    var acc = 0.0;
        \\    acc += lhs[id.x];
        \\    out[id.x] = acc;
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate select builtin to HLSL ternary" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = select(0.0, 1.0, data[id.x] > 0.5);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "?") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, ":") != null);
}

test "translate select builtin to MSL ternary" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = select(0.0, 1.0, data[id.x] > 0.5);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "?") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, ":") != null);
}

test "translate select builtin to SPIR-V OpSelect" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = select(0.0, 1.0, data[id.x] > 0.5);
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate pack and unpack 4x8 normalized builtins to HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let packed_u = pack4x8unorm(vec4f(0.0, 0.5, 1.0, 0.25));
        \\    let packed_s = pack4x8snorm(vec4f(-1.0, -0.5, 0.5, 1.0));
        \\    let unpacked_u = unpack4x8unorm(packed_u);
        \\    let unpacked_s = unpack4x8snorm(packed_s);
        \\    if (unpacked_u.y >= 0.0 && unpacked_s.z >= -1.0) {
        \\        data[id.x] = packed_u ^ packed_s;
        \\    }
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_pack4x8unorm(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_pack4x8snorm(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_unpack4x8unorm(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_unpack4x8snorm(") != null);
}

test "translate texture builtins to HLSL" {
    const source =
        \\@group(0) @binding(0) var tex: texture_2d<f32>;
        \\@group(0) @binding(1) var out_tex: texture_storage_2d<rgba8unorm, write>;
        \\@group(0) @binding(2) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let sample = textureLoad(tex, vec2u(id.xy), 0);
        \\    textureStore(out_tex, vec2u(id.xy), sample);
        \\    data[id.x] = sample.x;
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, ".Load(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "RWTexture2D<float4>") != null);
}

test "translate newly accepted math builtins end-to-end to HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = tan(1.0) + acos(0.5) + asin(0.5) + atan(1.0) + cosh(1.0) + sinh(1.0) + sign(1.0);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "tan(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "acos(") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "sign(") != null);
}

test "translate newly accepted math builtins end-to-end to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = tan(1.0) + acos(0.5) + asin(0.5) + atan(1.0) + cosh(1.0) + sinh(1.0) + sign(1.0);
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate atan2 and ldexp to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = atan2(1.0, 2.0) + ldexp(1.0, 2);
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

test "translate arrayLength to HLSL helper" {
    const source =
        \\@group(0) @binding(0) var<storage, read> data: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> out_data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    out_data[id.x] = arrayLength(data);
        \\}
    ;

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const hlsl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "uint doe_arrayLength_data()") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "data.GetDimensions(count, stride);") != null);
    try std.testing.expect(std.mem.indexOf(u8, hlsl, "doe_arrayLength_data()") != null);
}

test "translate arrayLength to MSL buffer-size helper" {
    const source =
        \\@group(0) @binding(0) var<storage, read> data: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> out: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    out[id.x] = arrayLength(data);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "data_size [[buffer_size(0)]]") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "uint(data_size / sizeof(float))") != null);
}

test "translate arrayLength to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read> data: array<f32>;
        \\@group(0) @binding(1) var<storage, read_write> out_data: array<u32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    out_data[id.x] = arrayLength(data);
        \\}
    ;

    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
}

fn writeFakeDxcScript(dir: std.fs.Dir, sub_path: []const u8) !void {
    var file = try dir.createFile(sub_path, .{ .read = true, .truncate = true });
    defer file.close();
    try file.writeAll(
        \\#!/bin/sh
        \\out=""
        \\while [ "$#" -gt 0 ]; do
        \\  if [ "$1" = "-Fo" ]; then
        \\    shift
        \\    out="$1"
        \\  fi
        \\  shift
        \\done
        \\if [ -z "$out" ]; then
        \\  echo "missing -Fo output path" >&2
        \\  exit 91
        \\fi
        \\printf 'FAKE-DXIL' > "$out"
        \\
    );
    try file.chmod(0o755);
}

test "translate DXIL with explicit fake toolchain config" {
    if (builtin.os.tag == .windows) return error.SkipZigTest;

    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = 1.0;
        \\}
    ;

    var tmp_dir = std.testing.tmpDir(.{});
    defer tmp_dir.cleanup();
    try writeFakeDxcScript(tmp_dir.dir, "fake_dxc.sh");

    const script_path = try std.fs.path.join(std.testing.allocator, &.{
        ".zig-cache",
        "tmp",
        tmp_dir.sub_path[0..],
        "fake_dxc.sh",
    });
    defer std.testing.allocator.free(script_path);

    var out: [MAX_DXIL_OUTPUT]u8 = undefined;
    const len = try translateToDxilWithToolchainConfig(std.testing.allocator, source, &out, DxilToolchainConfig{
        .executable = script_path,
        .discovery = .explicit_config,
    });
    try std.testing.expectEqualStrings("FAKE-DXIL", out[0..len]);
}

test "translate DXIL reports explicit missing toolchain config path" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = 1.0;
        \\}
    ;

    var out: [MAX_DXIL_OUTPUT]u8 = undefined;
    try std.testing.expectError(TranslateError.ShaderToolchainUnavailable, translateToDxilWithToolchainConfig(
        std.testing.allocator,
        source,
        &out,
        DxilToolchainConfig{
            .executable = "zig-out/does-not-exist/dxc",
            .discovery = .explicit_config,
        },
    ));
    try std.testing.expectEqual(CompilationStage.dxil_emit, lastErrorStage());
    try std.testing.expect(std.mem.indexOf(u8, lastErrorMessage(), "zig-out/does-not-exist/dxc") != null);
    try std.testing.expect(std.mem.indexOf(u8, lastErrorMessage(), DXIL_DXC_ENV_VAR) != null);
}

test "translate compute shader to DXIL or report missing toolchain" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = 1.0;
        \\}
    ;

    var out: [MAX_DXIL_OUTPUT]u8 = undefined;
    const len = translateToDxil(std.testing.allocator, source, &out) catch |err| switch (err) {
        TranslateError.ShaderToolchainUnavailable => {
            try std.testing.expectEqual(CompilationStage.dxil_emit, lastErrorStage());
            try std.testing.expect(std.mem.indexOf(u8, lastErrorMessage(), DXIL_DXC_ENV_VAR) != null);
            return;
        },
        else => return err,
    };
    try std.testing.expect(len > 0);
}

test "translate vertex shader to DXIL or report missing toolchain" {
    const source =
        \\@vertex
        \\fn main(@location(0) uv: vec2f) -> @builtin(position) vec4f {
        \\    return vec4f(uv, 0.0, 1.0);
        \\}
    ;

    var out: [MAX_DXIL_OUTPUT]u8 = undefined;
    const len = translateToDxil(std.testing.allocator, source, &out) catch |err| switch (err) {
        TranslateError.ShaderToolchainUnavailable => {
            try std.testing.expectEqual(CompilationStage.dxil_emit, lastErrorStage());
            try std.testing.expect(std.mem.indexOf(u8, lastErrorMessage(), DXIL_DXC_ENV_VAR) != null);
            return;
        },
        else => return err,
    };
    try std.testing.expect(len > 0);
}

test "translate workgroupBarrier builtin to MSL SPIR-V and HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = 1.0;
        \\    workgroupBarrier();
        \\    data[id.x] = data[id.x] + 1.0;
        \\}
    ;

    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, msl_out[0..msl_len], "threadgroup_barrier(mem_flags::mem_threadgroup)") != null);

    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);

    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, hlsl_out[0..hlsl_len], "GroupMemoryBarrierWithGroupSync()") != null);
}

test "translate storageBarrier builtin to MSL SPIR-V and HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = 1.0;
        \\    storageBarrier();
        \\    data[id.x] = data[id.x] + 1.0;
        \\}
    ;

    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, msl_out[0..msl_len], "threadgroup_barrier(mem_flags::mem_device)") != null);

    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);

    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, hlsl_out[0..hlsl_len], "AllMemoryBarrierWithGroupSync()") != null);
}

test "translate fma builtin to MSL SPIR-V and HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let a = data[id.x];
        \\    let b = data[id.x + 1u];
        \\    let c = data[id.x + 2u];
        \\    data[id.x] = fma(a, b, c);
        \\}
    ;

    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, msl_out[0..msl_len], "fma(") != null);

    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);

    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, hlsl_out[0..hlsl_len], "fma(") != null);
}

test "translate smoothstep builtin to MSL SPIR-V and HLSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = smoothstep(0.0, 1.0, data[id.x]);
        \\}
    ;

    var msl_out: [MAX_OUTPUT]u8 = undefined;
    const msl_len = try translateToMsl(std.testing.allocator, source, &msl_out);
    try std.testing.expect(msl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, msl_out[0..msl_len], "smoothstep(") != null);

    var spirv_out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const spirv_len = try translateToSpirv(std.testing.allocator, source, &spirv_out);
    try std.testing.expect(spirv_len > 0);

    var hlsl_out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const hlsl_len = try translateToHlsl(std.testing.allocator, source, &hlsl_out);
    try std.testing.expect(hlsl_len > 0);
    try std.testing.expect(std.mem.indexOf(u8, hlsl_out[0..hlsl_len], "smoothstep(") != null);
}

test "ptr parameter codegen is unsupported" {
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
    const result = translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(result == error.InvalidWgsl or result == error.UnsupportedConstruct or result == error.InvalidIr or result == error.UnexpectedToken);
}

test "texture_3d type is unsupported" {
    const source =
        \\@group(0) @binding(0) var tex: texture_3d<f32>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const result = translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(result == error.UnknownType or result == error.InvalidType or result == error.UnsupportedConstruct);
}

test "textureSample builtin is unsupported" {
    const source =
        \\@group(0) @binding(0) var tex: texture_2d<f32>;
        \\@group(0) @binding(1) var samp: sampler;
        \\
        \\@fragment
        \\fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
        \\    return textureSample(tex, samp, uv);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const result = translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(result == error.UnsupportedBuiltin or result == error.UnsupportedConstruct);
}

test "texture_depth_2d type is unsupported" {
    const source =
        \\@group(0) @binding(0) var depth: texture_depth_2d;
        \\
        \\@compute @workgroup_size(1)
        \\fn main() {
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const result = translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(result == error.UnknownType or result == error.InvalidType or result == error.UnsupportedConstruct);
}
