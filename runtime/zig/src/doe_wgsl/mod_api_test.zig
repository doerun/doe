// mod_api_test.zig — Public WGSL translation API smoke and cross-backend baseline tests.

const std = @import("std");
const mod = @import("mod.zig");
const lean_proof = @import("../lean_proof.zig");
const runtime_compile = @import("runtime_compile.zig");
const translateToMsl = mod.translateToMsl;
const translateToHlsl = mod.translateToHlsl;
const translateToSpirv = mod.translateToSpirv;
const analyzeToIr = mod.analyzeToIr;
const analyzeToIrWithConfig = mod.analyzeToIrWithConfig;
const ir = mod.ir;
const MAX_OUTPUT = mod.MAX_OUTPUT;
const MAX_HLSL_OUTPUT = mod.MAX_HLSL_OUTPUT;
const MAX_SPIRV_OUTPUT = mod.MAX_SPIRV_OUTPUT;

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
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], "?") != null);
    try std.testing.expect(std.mem.indexOf(u8, out[0..len], ".get_width(uint(") != null);
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

test "translate subgroup_size and subgroup_invocation_id builtins to MSL" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(32)
        \\fn main(@builtin(subgroup_size) sg_size: u32, @builtin(subgroup_invocation_id) sg_id: u32) {
        \\    data[sg_id] = f32(sg_size);
        \\}
    ;

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try translateToMsl(std.testing.allocator, source, &out);
    try std.testing.expect(len > 0);
    const msl = out[0..len];
    try std.testing.expect(std.mem.indexOf(u8, msl, "threads_per_simdgroup") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_index_in_simdgroup") != null);
}

test "translate subgroup_size and subgroup_invocation_id builtins to SPIR-V" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(32)
        \\fn main(@builtin(subgroup_size) sg_size: u32, @builtin(subgroup_invocation_id) sg_id: u32) {
        \\    data[sg_id] = f32(sg_size);
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

test "analyzeToIrWithConfig records byte-aware gid dispatch preconditions" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\@compute @workgroup_size(4)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    data[gid.x] = 1.0;
        \\}
    ;

    var module_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{
        .elide_proven_bounds = true,
    });
    defer module_ir.deinit();

    if (!lean_proof.boundsProven(.gid_1d_storage_buffer)) {
        try std.testing.expectEqual(@as(usize, 0), module_ir.dispatch_preconditions.items.len);
        return;
    }

    try std.testing.expectEqual(@as(usize, 1), module_ir.dispatch_preconditions.items.len);
    const precondition = module_ir.dispatch_preconditions.items[0];
    try std.testing.expectEqual(ir.DispatchPreconditionKind.gid_component, precondition.kind);
    try std.testing.expectEqual(@as(u8, 0), precondition.gid_axis);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_stride_bytes);
}

test "analyzeToIrWithConfig elides flat 2d dispatch-x indexing" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8, 2, 1)
        \\fn main(
        \\    @builtin(global_invocation_id) gid: vec3u,
        \\    @builtin(num_workgroups) num_wg: vec3u,
        \\) {
        \\    let width = num_wg.x * 8u;
        \\    let idx = gid.y * width + gid.x;
        \\    data[idx] = 1u;
        \\}
    ;

    var baseline_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{});
    defer baseline_ir.deinit();
    var baseline_has_min = false;
    for (baseline_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            baseline_has_min = true;
            break;
        }
    }
    try std.testing.expect(baseline_has_min);

    var elided_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{
        .elide_proven_bounds = true,
    });
    defer elided_ir.deinit();

    if (!lean_proof.boundsProven(.gid_2d_flat_storage_buffer)) {
        try std.testing.expectEqual(@as(usize, 0), elided_ir.dispatch_preconditions.items.len);
        return;
    }

    try std.testing.expectEqual(@as(usize, 1), elided_ir.dispatch_preconditions.items.len);
    const precondition = elided_ir.dispatch_preconditions.items[0];
    try std.testing.expectEqual(ir.DispatchPreconditionKind.flat_index_2d_dispatch_x, precondition.kind);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_stride_bytes);

    var elided_has_min = false;
    for (elided_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            elided_has_min = true;
            break;
        }
    }
    try std.testing.expect(!elided_has_min);
}

test "analyzeToIrWithConfig records affine gid offset preconditions" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    data[gid.x + 4u] = 1u;
        \\}
    ;

    var baseline_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{});
    defer baseline_ir.deinit();
    var baseline_has_min = false;
    for (baseline_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            baseline_has_min = true;
            break;
        }
    }
    try std.testing.expect(baseline_has_min);

    var elided_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{
        .elide_proven_bounds = true,
    });
    defer elided_ir.deinit();

    if (!lean_proof.boundsProven(.gid_1d_storage_buffer_offset)) {
        try std.testing.expectEqual(@as(usize, 0), elided_ir.dispatch_preconditions.items.len);
        return;
    }

    try std.testing.expectEqual(@as(usize, 1), elided_ir.dispatch_preconditions.items.len);
    const precondition = elided_ir.dispatch_preconditions.items[0];
    try std.testing.expectEqual(ir.DispatchPreconditionKind.gid_component, precondition.kind);
    try std.testing.expectEqual(@as(u8, 0), precondition.gid_axis);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_stride_bytes);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_offset);

    var elided_has_min = false;
    for (elided_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            elided_has_min = true;
            break;
        }
    }
    try std.testing.expect(!elided_has_min);
}

test "analyzeToIrWithConfig records affine gid stride preconditions" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    data[gid.x * 4u + 2u] = 1u;
        \\}
    ;

    var baseline_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{});
    defer baseline_ir.deinit();
    var baseline_has_min = false;
    for (baseline_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            baseline_has_min = true;
            break;
        }
    }
    try std.testing.expect(baseline_has_min);

    var elided_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{
        .elide_proven_bounds = true,
    });
    defer elided_ir.deinit();

    if (!lean_proof.boundsProven(.gid_1d_storage_buffer_stride)) {
        try std.testing.expectEqual(@as(usize, 0), elided_ir.dispatch_preconditions.items.len);
        return;
    }

    try std.testing.expectEqual(@as(usize, 1), elided_ir.dispatch_preconditions.items.len);
    const precondition = elided_ir.dispatch_preconditions.items[0];
    try std.testing.expectEqual(ir.DispatchPreconditionKind.gid_component, precondition.kind);
    try std.testing.expectEqual(@as(u8, 0), precondition.gid_axis);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_multiplier);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_stride_bytes);
    try std.testing.expectEqual(@as(u64, 2), precondition.element_offset);

    var elided_has_min = false;
    for (elided_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            elided_has_min = true;
            break;
        }
    }
    try std.testing.expect(!elided_has_min);
}

test "compute runtime translation drops _doe_sizes for proof-covered affine bounds only" {
    const affine_source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    data[gid.x + 4u] = 1u;
        \\}
    ;
    const direct_array_length_source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    if (gid.x < arrayLength(&data)) {
        \\        data[gid.x] = 1u;
        \\    }
        \\}
    ;

    var affine_out: [MAX_OUTPUT]u8 = undefined;
    var affine_translation = try runtime_compile.translateToMslForComputeRuntime(
        std.testing.allocator,
        affine_source,
        &affine_out,
        null,
        0,
    );
    defer affine_translation.info.deinit(std.testing.allocator);

    if (lean_proof.boundsProven(.gid_1d_storage_buffer_offset)) {
        try std.testing.expect(!affine_translation.info.needs_sizes_buf);
    } else {
        try std.testing.expect(affine_translation.info.needs_sizes_buf);
    }

    var direct_out: [MAX_OUTPUT]u8 = undefined;
    var direct_translation = try runtime_compile.translateToMslForComputeRuntime(
        std.testing.allocator,
        direct_array_length_source,
        &direct_out,
        null,
        0,
    );
    defer direct_translation.info.deinit(std.testing.allocator);
    try std.testing.expect(direct_translation.info.needs_sizes_buf);
}

test "compute runtime translation drops _doe_sizes for proof-covered strided affine bounds only" {
    const affine_source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    data[gid.x * 4u + 2u] = 1u;
        \\}
    ;

    var affine_out: [MAX_OUTPUT]u8 = undefined;
    var affine_translation = try runtime_compile.translateToMslForComputeRuntime(
        std.testing.allocator,
        affine_source,
        &affine_out,
        null,
        0,
    );
    defer affine_translation.info.deinit(std.testing.allocator);

    if (lean_proof.boundsProven(.gid_1d_storage_buffer_stride)) {
        try std.testing.expect(!affine_translation.info.needs_sizes_buf);
    } else {
        try std.testing.expect(affine_translation.info.needs_sizes_buf);
    }
}

test "analyzeToIrWithConfig records flat 2d offset preconditions" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<u32>;
        \\@compute @workgroup_size(8, 2, 1)
        \\fn main(
        \\    @builtin(global_invocation_id) gid: vec3u,
        \\    @builtin(num_workgroups) num_wg: vec3u,
        \\) {
        \\    let width = num_wg.x * 8u;
        \\    let idx = gid.y * width + gid.x + 16u;
        \\    data[idx] = 1u;
        \\}
    ;

    var baseline_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{});
    defer baseline_ir.deinit();
    var baseline_has_min = false;
    for (baseline_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            baseline_has_min = true;
            break;
        }
    }
    try std.testing.expect(baseline_has_min);

    var elided_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{
        .elide_proven_bounds = true,
    });
    defer elided_ir.deinit();

    if (!lean_proof.boundsProven(.gid_2d_flat_storage_buffer_offset)) {
        try std.testing.expectEqual(@as(usize, 0), elided_ir.dispatch_preconditions.items.len);
        return;
    }

    try std.testing.expectEqual(@as(usize, 1), elided_ir.dispatch_preconditions.items.len);
    const precondition = elided_ir.dispatch_preconditions.items[0];
    try std.testing.expectEqual(ir.DispatchPreconditionKind.flat_index_2d_dispatch_x, precondition.kind);
    try std.testing.expectEqual(@as(u64, 1), precondition.element_multiplier);
    try std.testing.expectEqual(@as(u64, 4), precondition.element_stride_bytes);
    try std.testing.expectEqual(@as(u64, 16), precondition.element_offset);

    var elided_has_min = false;
    for (elided_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "min")) {
            elided_has_min = true;
            break;
        }
    }
    try std.testing.expect(!elided_has_min);
}

test "analyzeToIrWithConfig records texture dispatch-fit preconditions" {
    const source =
        \\@group(0) @binding(0) var src_tex: texture_2d<f32>;
        \\@group(0) @binding(1) var dst_tex: texture_storage_2d<rgba8unorm, write>;
        \\@compute @workgroup_size(8, 8, 1)
        \\fn main(@builtin(global_invocation_id) gid: vec3u) {
        \\    let sample = textureLoad(src_tex, vec2u(gid.x, gid.y), 0);
        \\    textureStore(dst_tex, vec2u(gid.x, gid.y), sample);
        \\}
    ;

    var baseline_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{});
    defer baseline_ir.deinit();
    var baseline_has_clamp = false;
    for (baseline_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "clamp")) {
            baseline_has_clamp = true;
            break;
        }
    }
    try std.testing.expect(baseline_has_clamp);

    var elided_ir = try analyzeToIrWithConfig(std.testing.allocator, source, .{
        .elide_proven_texture_bounds = true,
    });
    defer elided_ir.deinit();

    const proofs_available = lean_proof.boundsProven(.gid_texture_2d_dispatch_fit);
    if (!proofs_available) {
        try std.testing.expectEqual(@as(usize, 0), elided_ir.texture_dispatch_preconditions.items.len);
        return;
    }

    try std.testing.expectEqual(@as(usize, 2), elided_ir.texture_dispatch_preconditions.items.len);
    try std.testing.expectEqual(ir.TextureDispatchPreconditionKind.gid_coords_2d, elided_ir.texture_dispatch_preconditions.items[0].kind);
    try std.testing.expectEqual(@as(u32, 0), elided_ir.texture_dispatch_preconditions.items[0].texture_binding.group);
    try std.testing.expectEqual(@as(u32, 0), elided_ir.texture_dispatch_preconditions.items[0].texture_binding.binding);
    try std.testing.expectEqual(@as(u32, 1), elided_ir.texture_dispatch_preconditions.items[1].texture_binding.binding);

    var elided_has_clamp = false;
    for (elided_ir.functions.items[0].exprs.items) |expr| {
        if (expr.data == .call and std.mem.eql(u8, expr.data.call.name, "clamp")) {
            elided_has_clamp = true;
            break;
        }
    }
    try std.testing.expect(!elided_has_clamp);
}

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
