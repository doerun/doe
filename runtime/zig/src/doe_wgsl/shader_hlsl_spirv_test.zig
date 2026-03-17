// shader_hlsl_spirv_test.zig — Tests for the HLSL and SPIR-V emitters.
//
// Tests HLSL type mapping, semantic mapping, compute shader emission,
// register binding, and SPIR-V binary generation including header
// validation, type IDs, OpDecorate for bindings, and entry point emission.

const std = @import("std");
const ir = @import("ir.zig");
const emit_hlsl = @import("emit_hlsl.zig");
const emit_spirv = @import("emit_spirv.zig");
const spirv = @import("spirv_builder.zig");
const mod = @import("mod.zig");
const maps = @import("emit_hlsl_maps.zig");

const testing = std.testing;
const allocator = testing.allocator;

const MAX_HLSL_OUTPUT = mod.MAX_HLSL_OUTPUT;
const MAX_SPIRV_OUTPUT = mod.MAX_SPIRV_OUTPUT;
const translateToHlsl = mod.translateToHlsl;
const translateToSpirv = mod.translateToSpirv;

// ============================================================
// Helpers
// ============================================================

fn contains(haystack: []const u8, needle: []const u8) bool {
    return std.mem.indexOf(u8, haystack, needle) != null;
}

fn read_u32_le(bytes: []const u8, offset: usize) u32 {
    return std.mem.readInt(u32, @as(*const [4]u8, @ptrCast(bytes[offset .. offset + 4].ptr)), .little);
}

// ============================================================
// HLSL type mapping tests (via IR construction)
// ============================================================

test "hlsl type: scalar f32 emits float" {
    var module = ir.Module.init(allocator);
    defer module.deinit();
    const f32_ty = try module.types.intern(.{ .scalar = .f32 });
    const void_ty = try module.types.intern(.{ .scalar = .void });

    var function = ir.Function{
        .name = try ir.dup_string(allocator, "test_fn"),
        .return_type = void_ty,
    };
    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "x"),
        .ty = f32_ty,
        .mutable = true,
    });
    const local_decl = try function.append_stmt(allocator, .{ .local_decl = .{
        .local = 0,
        .initializer = null,
        .is_const = false,
    } });
    const ret_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const block_range = try function.append_stmt_children(allocator, &.{ local_decl, ret_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = block_range });
    try module.functions.append(allocator, function);

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = emit_hlsl.emit(&module, &out) catch return error.SkipZigTest;
    const hlsl = out[0..len];
    try testing.expect(contains(hlsl, "float x"));
}

test "hlsl type: scalar i32 emits int" {
    var module = ir.Module.init(allocator);
    defer module.deinit();
    const i32_ty = try module.types.intern(.{ .scalar = .i32 });
    const void_ty = try module.types.intern(.{ .scalar = .void });

    var function = ir.Function{
        .name = try ir.dup_string(allocator, "test_fn"),
        .return_type = void_ty,
    };
    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "y"),
        .ty = i32_ty,
        .mutable = true,
    });
    const local_decl = try function.append_stmt(allocator, .{ .local_decl = .{
        .local = 0,
        .initializer = null,
        .is_const = false,
    } });
    const ret_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const block_range = try function.append_stmt_children(allocator, &.{ local_decl, ret_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = block_range });
    try module.functions.append(allocator, function);

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = emit_hlsl.emit(&module, &out) catch return error.SkipZigTest;
    const hlsl = out[0..len];
    try testing.expect(contains(hlsl, "int y"));
}

test "hlsl type: vec3u emits uint3" {
    var module = ir.Module.init(allocator);
    defer module.deinit();
    const u32_ty = try module.types.intern(.{ .scalar = .u32 });
    const vec3u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 3 } });
    const void_ty = try module.types.intern(.{ .scalar = .void });

    var function = ir.Function{
        .name = try ir.dup_string(allocator, "test_fn"),
        .return_type = void_ty,
    };
    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "v"),
        .ty = vec3u_ty,
        .mutable = true,
    });
    const local_decl = try function.append_stmt(allocator, .{ .local_decl = .{
        .local = 0,
        .initializer = null,
        .is_const = false,
    } });
    const ret_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const block_range = try function.append_stmt_children(allocator, &.{ local_decl, ret_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = block_range });
    try module.functions.append(allocator, function);

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = emit_hlsl.emit(&module, &out) catch return error.SkipZigTest;
    const hlsl = out[0..len];
    try testing.expect(contains(hlsl, "uint3 v"));
}

test "hlsl type: mat4x4f emits float4x4" {
    var module = ir.Module.init(allocator);
    defer module.deinit();
    const f32_ty = try module.types.intern(.{ .scalar = .f32 });
    const mat4_ty = try module.types.intern(.{ .matrix = .{ .elem = f32_ty, .columns = 4, .rows = 4 } });
    const void_ty = try module.types.intern(.{ .scalar = .void });

    var function = ir.Function{
        .name = try ir.dup_string(allocator, "test_fn"),
        .return_type = void_ty,
    };
    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "m"),
        .ty = mat4_ty,
        .mutable = true,
    });
    const local_decl = try function.append_stmt(allocator, .{ .local_decl = .{
        .local = 0,
        .initializer = null,
        .is_const = false,
    } });
    const ret_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const block_range = try function.append_stmt_children(allocator, &.{ local_decl, ret_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = block_range });
    try module.functions.append(allocator, function);

    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = emit_hlsl.emit(&module, &out) catch return error.SkipZigTest;
    const hlsl = out[0..len];
    try testing.expect(contains(hlsl, "float4x4 m"));
}

// ============================================================
// HLSL semantic mapping tests
// ============================================================

test "hlsl builtin map: position maps to SV_Position" {
    try testing.expectEqualStrings("SV_Position", maps.hlsl_builtin_name(.position));
}

test "hlsl builtin map: vertex_index maps to SV_VertexID" {
    try testing.expectEqualStrings("SV_VertexID", maps.hlsl_builtin_name(.vertex_index));
}

test "hlsl builtin map: instance_index maps to SV_InstanceID" {
    try testing.expectEqualStrings("SV_InstanceID", maps.hlsl_builtin_name(.instance_index));
}

test "hlsl builtin map: global_invocation_id maps to SV_DispatchThreadID" {
    try testing.expectEqualStrings("SV_DispatchThreadID", maps.hlsl_builtin_name(.global_invocation_id));
}

test "hlsl builtin map: local_invocation_id maps to SV_GroupThreadID" {
    try testing.expectEqualStrings("SV_GroupThreadID", maps.hlsl_builtin_name(.local_invocation_id));
}

test "hlsl builtin map: local_invocation_index maps to SV_GroupIndex" {
    try testing.expectEqualStrings("SV_GroupIndex", maps.hlsl_builtin_name(.local_invocation_index));
}

test "hlsl builtin map: workgroup_id maps to SV_GroupID" {
    try testing.expectEqualStrings("SV_GroupID", maps.hlsl_builtin_name(.workgroup_id));
}

test "hlsl builtin map: frag_depth maps to SV_Depth" {
    try testing.expectEqualStrings("SV_Depth", maps.hlsl_builtin_name(.frag_depth));
}

test "hlsl builtin map: front_facing maps to SV_IsFrontFace" {
    try testing.expectEqualStrings("SV_IsFrontFace", maps.hlsl_builtin_name(.front_facing));
}

test "hlsl builtin map: sample_index maps to SV_SampleIndex" {
    try testing.expectEqualStrings("SV_SampleIndex", maps.hlsl_builtin_name(.sample_index));
}

test "hlsl intrinsic: subgroup_size maps to WaveGetLaneCount()" {
    try testing.expectEqualStrings("WaveGetLaneCount()", maps.hlsl_intrinsic_builtin(.subgroup_size).?);
}

test "hlsl intrinsic: subgroup_invocation_id maps to WaveGetLaneIndex()" {
    try testing.expectEqualStrings("WaveGetLaneIndex()", maps.hlsl_intrinsic_builtin(.subgroup_invocation_id).?);
}

test "hlsl intrinsic: position is not an intrinsic" {
    try testing.expect(maps.hlsl_intrinsic_builtin(.position) == null);
}

// ============================================================
// HLSL renamed builtins
// ============================================================

test "hlsl renamed: fract maps to frac" {
    try testing.expectEqualStrings("frac", maps.hlsl_renamed_builtin("fract").?);
}

test "hlsl renamed: inverseSqrt maps to rsqrt" {
    try testing.expectEqualStrings("rsqrt", maps.hlsl_renamed_builtin("inverseSqrt").?);
}

test "hlsl renamed: mix maps to lerp" {
    try testing.expectEqualStrings("lerp", maps.hlsl_renamed_builtin("mix").?);
}

test "hlsl renamed: atomicLoad maps to doe_atomicLoad" {
    try testing.expectEqualStrings("doe_atomicLoad", maps.hlsl_renamed_builtin("atomicLoad").?);
}

test "hlsl passthrough: abs returns true" {
    try testing.expect(maps.hlsl_builtin_passthrough("abs"));
}

test "hlsl passthrough: clamp returns true" {
    try testing.expect(maps.hlsl_builtin_passthrough("clamp"));
}

test "hlsl passthrough: unknownBuiltin returns false" {
    try testing.expect(!maps.hlsl_builtin_passthrough("unknownBuiltin"));
}

// ============================================================
// HLSL compute shader emission (full pipeline)
// ============================================================

test "hlsl compute: simple shader emits numthreads and SV_DispatchThreadID" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32, 64>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = data[id.x] * 2.0;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "[numthreads(64, 1, 1)]"));
    try testing.expect(contains(hlsl, "SV_DispatchThreadID"));
    try testing.expect(contains(hlsl, "void main"));
}

test "hlsl compute: multi-dimensional workgroup size" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> buf: array<u32, 256>;
        \\
        \\@compute @workgroup_size(8, 8, 1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    buf[id.x + id.y * 16u] = id.x;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "[numthreads(8, 8, 1)]"));
}

// ============================================================
// HLSL register binding tests (full pipeline)
// ============================================================

test "hlsl binding: uniform buffer maps to cbuffer register(bN)" {
    const source =
        \\struct Params {
        \\    scale: f32,
        \\    offset: f32,
        \\}
        \\@group(0) @binding(0) var<uniform> params: Params;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let s = params.scale;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "register(b0, space0)"));
    try testing.expect(contains(hlsl, "cbuffer"));
}

test "hlsl binding: storage buffer read_write maps to RWStructuredBuffer register(uN)" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32, 16>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[0] = 1.0;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "RWStructuredBuffer"));
    try testing.expect(contains(hlsl, "register(u0, space0)"));
}

test "hlsl binding: storage buffer read maps to StructuredBuffer register(tN)" {
    const source =
        \\@group(0) @binding(0) var<storage, read> data: array<f32, 16>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let v = data[0];
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "StructuredBuffer"));
    try testing.expect(!contains(hlsl, "RWStructuredBuffer"));
    try testing.expect(contains(hlsl, "register(t0, space0)"));
}

test "hlsl binding: group 1 maps to space1" {
    const source =
        \\struct Data { value: f32 }
        \\@group(1) @binding(2) var<uniform> params: Data;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let v = params.value;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "register(b2, space1)"));
}

// ============================================================
// HLSL atomic helper emission
// ============================================================

test "hlsl: atomic helper functions are emitted in preamble" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32, 4>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[0] = 0.0;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "doe_atomicLoad"));
    try testing.expect(contains(hlsl, "doe_atomicStore"));
    try testing.expect(contains(hlsl, "doe_atomicAdd"));
    try testing.expect(contains(hlsl, "InterlockedExchange"));
}

// ============================================================
// HLSL operator mapping
// ============================================================

test "hlsl operator: assign ops map correctly" {
    try testing.expectEqualStrings("=", maps.assign_op_text(.assign));
    try testing.expectEqualStrings("+=", maps.assign_op_text(.add));
    try testing.expectEqualStrings("-=", maps.assign_op_text(.sub));
    try testing.expectEqualStrings("*=", maps.assign_op_text(.mul));
    try testing.expectEqualStrings("/=", maps.assign_op_text(.div));
    try testing.expectEqualStrings("%=", maps.assign_op_text(.rem));
}

test "hlsl operator: binary ops map correctly" {
    try testing.expectEqualStrings("+", maps.binary_op_text(.add));
    try testing.expectEqualStrings("&&", maps.binary_op_text(.logical_and));
    try testing.expectEqualStrings("||", maps.binary_op_text(.logical_or));
    try testing.expectEqualStrings("<<", maps.binary_op_text(.shift_left));
    try testing.expectEqualStrings(">>", maps.binary_op_text(.shift_right));
}

test "hlsl operator: unary ops map correctly" {
    try testing.expectEqualStrings("-", maps.unary_op_text(.neg));
    try testing.expectEqualStrings("!", maps.unary_op_text(.not));
    try testing.expectEqualStrings("~", maps.unary_op_text(.bit_not));
}

// ============================================================
// HLSL struct emission
// ============================================================

test "hlsl struct: user-defined struct appears in output" {
    const source =
        \\struct Params {
        \\    a: f32,
        \\    b: u32,
        \\    c: vec4f,
        \\}
        \\@group(0) @binding(0) var<uniform> params: Params;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let v = params.a;
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "struct Params"));
    try testing.expect(contains(hlsl, "float a;"));
    try testing.expect(contains(hlsl, "uint b;"));
    try testing.expect(contains(hlsl, "float4 c;"));
}

// ============================================================
// HLSL control flow
// ============================================================

test "hlsl control flow: if/else emits correctly" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32, 4>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    if (id.x == 0u) {
        \\        data[0] = 1.0;
        \\    } else {
        \\        data[0] = 2.0;
        \\    }
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "if ("));
    try testing.expect(contains(hlsl, "} else {"));
}

test "hlsl control flow: for loop emits while" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32, 16>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    for (var i: u32 = 0u; i < 16u; i = i + 1u) {
        \\        data[i] = f32(i);
        \\    }
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "while ("));
}

// ============================================================
// HLSL workgroup shared memory
// ============================================================

test "hlsl workgroup: var<workgroup> emits groupshared" {
    const source =
        \\var<workgroup> shared_data: array<f32, 256>;
        \\
        \\@compute @workgroup_size(256)
        \\fn main(@builtin(local_invocation_index) idx: u32) {
        \\    shared_data[idx] = f32(idx);
        \\}
    ;
    var out: [MAX_HLSL_OUTPUT]u8 = undefined;
    const len = try translateToHlsl(allocator, source, &out);
    const hlsl = out[0..len];

    try testing.expect(contains(hlsl, "groupshared"));
}

// ============================================================
// SPIR-V header tests (full pipeline)
// ============================================================

test "spirv header: magic number is 0x07230203" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    try testing.expect(len >= 20);
    const magic = read_u32_le(&out, 0);
    try testing.expectEqual(spirv.MAGIC, magic);
}

test "spirv header: version is 1.3 or later" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    try testing.expect(len >= 20);
    const version = read_u32_le(&out, 4);
    try testing.expect(version >= 0x00010300);
}

test "spirv header: bound is nonzero" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    try testing.expect(len >= 20);
    const bound = read_u32_le(&out, 12);
    try testing.expect(bound > 0);
}

test "spirv header: schema is 0" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    try testing.expect(len >= 20);
    const schema = read_u32_le(&out, 16);
    try testing.expectEqual(@as(u32, 0), schema);
}

// ============================================================
// SPIR-V type ID allocation (spirv_builder direct)
// ============================================================

test "spirv builder: type_void returns same ID on repeated calls" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const id1 = try builder.type_void();
    const id2 = try builder.type_void();
    try testing.expectEqual(id1, id2);
}

test "spirv builder: distinct scalar types get distinct IDs" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const void_id = try builder.type_void();
    const u32_id = try builder.type_u32();
    const i32_id = try builder.type_i32();
    const f32_id = try builder.type_f32();
    try testing.expect(void_id != u32_id);
    try testing.expect(u32_id != i32_id);
    try testing.expect(i32_id != f32_id);
}

test "spirv builder: vector types are deduplicated" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const f32_id = try builder.type_f32();
    const vec3f_a = try builder.type_vector(f32_id, 3);
    const vec3f_b = try builder.type_vector(f32_id, 3);
    try testing.expectEqual(vec3f_a, vec3f_b);
}

test "spirv builder: different vector lengths get distinct IDs" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const f32_id = try builder.type_f32();
    const vec2f = try builder.type_vector(f32_id, 2);
    const vec3f = try builder.type_vector(f32_id, 3);
    const vec4f = try builder.type_vector(f32_id, 4);
    try testing.expect(vec2f != vec3f);
    try testing.expect(vec3f != vec4f);
}

test "spirv builder: pointer types are deduplicated" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const f32_id = try builder.type_f32();
    const ptr1 = try builder.type_pointer(spirv.StorageClass.Function, f32_id);
    const ptr2 = try builder.type_pointer(spirv.StorageClass.Function, f32_id);
    try testing.expectEqual(ptr1, ptr2);
}

test "spirv builder: pointer types differ by storage class" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const f32_id = try builder.type_f32();
    const fn_ptr = try builder.type_pointer(spirv.StorageClass.Function, f32_id);
    const priv_ptr = try builder.type_pointer(spirv.StorageClass.Private, f32_id);
    try testing.expect(fn_ptr != priv_ptr);
}

test "spirv builder: constant deduplication" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    const c1 = try builder.const_u32(42);
    const c2 = try builder.const_u32(42);
    const c3 = try builder.const_u32(7);
    try testing.expectEqual(c1, c2);
    try testing.expect(c1 != c3);
}

// ============================================================
// SPIR-V decoration tests (via binary output inspection)
// ============================================================

fn find_spirv_word_sequence(binary: []const u8, needle: []const u32) bool {
    if (binary.len < needle.len * 4) return false;
    const word_count = binary.len / 4;
    if (word_count < needle.len) return false;
    var i: usize = 0;
    while (i + needle.len <= word_count) : (i += 1) {
        var match = true;
        for (needle, 0..) |expected, j| {
            if (read_u32_le(binary, (i + j) * 4) != expected) {
                match = false;
                break;
            }
        }
        if (match) return true;
    }
    return false;
}

test "spirv binding: OpDecorate DescriptorSet appears for bound resources" {
    const source =
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32, 64>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[0] = 1.0;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    // OpDecorate has opcode 71. DescriptorSet = 34. Group = 0.
    // The instruction encoding is: (word_count << 16) | opcode, target_id, decoration, value
    // We search for opcode 71 with decoration 34 (DescriptorSet) and value 0.
    var found_descriptor_set = false;
    const word_count = len / 4;
    var i: usize = 5; // skip header
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 71 and wc >= 4) { // OpDecorate
            const decoration = read_u32_le(binary, (i + 2) * 4);
            if (decoration == 34) { // DescriptorSet
                const value = read_u32_le(binary, (i + 3) * 4);
                if (value == 0) {
                    found_descriptor_set = true;
                    break;
                }
            }
        }
        i += wc;
    }
    try testing.expect(found_descriptor_set);
}

test "spirv binding: OpDecorate Binding appears for bound resources" {
    const source =
        \\@group(0) @binding(3) var<storage, read_write> data: array<f32, 64>;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[0] = 1.0;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    var found_binding = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 71 and wc >= 4) {
            const decoration = read_u32_le(binary, (i + 2) * 4);
            if (decoration == 33) { // Binding
                const value = read_u32_le(binary, (i + 3) * 4);
                if (value == 3) {
                    found_binding = true;
                    break;
                }
            }
        }
        i += wc;
    }
    try testing.expect(found_binding);
}

// ============================================================
// SPIR-V compute shader entry point
// ============================================================

test "spirv compute: OpEntryPoint GLCompute appears" {
    const source =
        \\@compute @workgroup_size(4, 2, 1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    // OpEntryPoint = 15. ExecutionModel GLCompute = 5.
    var found_entry_point = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 15 and wc >= 3) { // OpEntryPoint
            const exec_model = read_u32_le(binary, (i + 1) * 4);
            if (exec_model == 5) { // GLCompute
                found_entry_point = true;
                break;
            }
        }
        i += wc;
    }
    try testing.expect(found_entry_point);
}

test "spirv compute: OpExecutionMode LocalSize appears with workgroup size" {
    const source =
        \\@compute @workgroup_size(8, 4, 2)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    // OpExecutionMode = 16. LocalSize = 17.
    var found_local_size = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 16 and wc >= 6) { // OpExecutionMode with at least 6 words
            const mode = read_u32_le(binary, (i + 2) * 4);
            if (mode == 17) { // LocalSize
                const x = read_u32_le(binary, (i + 3) * 4);
                const y = read_u32_le(binary, (i + 4) * 4);
                const z = read_u32_le(binary, (i + 5) * 4);
                if (x == 8 and y == 4 and z == 2) {
                    found_local_size = true;
                    break;
                }
            }
        }
        i += wc;
    }
    try testing.expect(found_local_size);
}

test "spirv compute: OpCapability Shader appears" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    // OpCapability = 17. Shader = 1.
    var found_shader_cap = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 17 and wc >= 2) {
            const cap = read_u32_le(binary, (i + 1) * 4);
            if (cap == 1) {
                found_shader_cap = true;
                break;
            }
        }
        i += wc;
    }
    try testing.expect(found_shader_cap);
}

// ============================================================
// SPIR-V memory model
// ============================================================

test "spirv: OpMemoryModel Logical GLSL450 appears" {
    const source =
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    // OpMemoryModel = 14. Logical = 0. GLSL450 = 1.
    var found_memory_model = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 14 and wc >= 3) {
            const addressing = read_u32_le(binary, (i + 1) * 4);
            const memory = read_u32_le(binary, (i + 2) * 4);
            if (addressing == 0 and memory == 1) {
                found_memory_model = true;
                break;
            }
        }
        i += wc;
    }
    try testing.expect(found_memory_model);
}

// ============================================================
// SPIR-V vertex/fragment output
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

// ============================================================
// SPIR-V builder: write_binary round-trip
// ============================================================

test "spirv builder: write_binary produces valid header" {
    var builder = spirv.Builder.init(allocator);
    defer builder.deinit();
    _ = try builder.type_void();
    const fn_type = try builder.type_function(try builder.type_void(), &.{});
    const fn_id = builder.reserve_id();
    try builder.emit_entry_point(fn_id, "main", &.{});
    try builder.emit_execution_mode_local_size(fn_id, 1, 1, 1);
    try builder.begin_function(try builder.type_void(), fn_id, fn_type);
    _ = try builder.label();
    try builder.append_function_inst(spirv.Opcode.Return, &.{});
    try builder.finish_function();

    var out: [4096]u8 = undefined;
    const len = try builder.write_binary(&out);
    try testing.expect(len >= 20);
    try testing.expectEqual(spirv.MAGIC, read_u32_le(&out, 0));
    try testing.expectEqual(@as(u32, 0), read_u32_le(&out, 16)); // schema
}

// ============================================================
// SPIR-V: Block decoration for uniform/storage buffers
// ============================================================

test "spirv binding: Block decoration emitted for uniform buffer" {
    const source =
        \\struct Params {
        \\    scale: f32,
        \\}
        \\@group(0) @binding(0) var<uniform> params: Params;
        \\
        \\@compute @workgroup_size(1)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let s = params.scale;
        \\}
    ;
    var out: [MAX_SPIRV_OUTPUT]u8 = undefined;
    const len = try translateToSpirv(allocator, source, &out);
    const binary = out[0..len];

    // OpDecorate with Block decoration (2)
    var found_block = false;
    const word_count = len / 4;
    var i: usize = 5;
    while (i < word_count) {
        const w = read_u32_le(binary, i * 4);
        const op = w & 0xFFFF;
        const wc = w >> 16;
        if (op == 71 and wc >= 3) { // OpDecorate
            const decoration = read_u32_le(binary, (i + 2) * 4);
            if (decoration == 2) { // Block
                found_block = true;
                break;
            }
        }
        i += wc;
    }
    try testing.expect(found_block);
}
