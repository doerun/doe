const std = @import("std");
const ir = @import("ir.zig");

pub fn unary_op_text(op: ir.UnaryOp) []const u8 {
    return switch (op) {
        .neg => "-",
        .not => "!",
        .bit_not => "~",
    };
}

pub fn binary_op_text(op: ir.BinaryOp) []const u8 {
    return switch (op) {
        .add => "+",
        .sub => "-",
        .mul => "*",
        .div => "/",
        .rem => "%",
        .bit_and => "&",
        .bit_or => "|",
        .bit_xor => "^",
        .shift_left => "<<",
        .shift_right => ">>",
        .equal => "==",
        .not_equal => "!=",
        .less => "<",
        .less_equal => "<=",
        .greater => ">",
        .greater_equal => ">=",
        .logical_and => "&&",
        .logical_or => "||",
    };
}

pub fn assign_op_text(op: ir.AssignOp) []const u8 {
    return switch (op) {
        .assign => "=",
        .add => "+=",
        .sub => "-=",
        .mul => "*=",
        .div => "/=",
        .rem => "%=",
        .bit_and => "&=",
        .bit_or => "|=",
        .bit_xor => "^=",
    };
}

pub fn hlsl_builtin_name(builtin: ir.Builtin) []const u8 {
    return switch (builtin) {
        .position => "SV_Position",
        .frag_depth => "SV_Depth",
        .front_facing => "SV_IsFrontFace",
        .global_invocation_id => "SV_DispatchThreadID",
        .local_invocation_id => "SV_GroupThreadID",
        .local_invocation_index => "SV_GroupIndex",
        .workgroup_id => "SV_GroupID",
        .num_workgroups => "SV_GroupID",
        .sample_index => "SV_SampleIndex",
        .sample_mask => "SV_Coverage",
        .vertex_index => "SV_VertexID",
        .instance_index => "SV_InstanceID",
        .subgroup_size, .subgroup_invocation_id => "UNSUPPORTED_BUILTIN",
        .clip_distances => "SV_ClipDistance",
        .primitive_index => "SV_PrimitiveID",
        else => "UNSUPPORTED_BUILTIN",
    };
}

/// Returns the HLSL intrinsic call for builtins that map to function calls
/// rather than entry-point parameter semantics, or null for standard semantics.
pub fn hlsl_intrinsic_builtin(builtin: ir.Builtin) ?[]const u8 {
    return switch (builtin) {
        .subgroup_size => "WaveGetLaneCount()",
        .subgroup_invocation_id => "WaveGetLaneIndex()",
        else => null,
    };
}

pub fn texture_component(sample_ty: ir.TypeId) []const u8 {
    _ = sample_ty;
    return "float";
}

pub fn hlsl_bitcast_fn(module: *const ir.Module, result_ty: ir.TypeId) []const u8 {
    const scalar = switch (module.types.get(result_ty)) {
        .scalar => |s| s,
        .vector => |v| switch (module.types.get(v.elem)) {
            .scalar => |s| s,
            else => return "asuint",
        },
        else => return "asuint",
    };
    return switch (scalar) {
        .f32, .abstract_float, .f16 => "asfloat",
        .i32, .abstract_int => "asint",
        else => "asuint",
    };
}

pub fn hlsl_renamed_builtin(name: []const u8) ?[]const u8 {
    if (std.mem.eql(u8, name, "fract")) return "frac";
    if (std.mem.eql(u8, name, "inverseSqrt")) return "rsqrt";
    if (std.mem.eql(u8, name, "mix")) return "lerp";
    if (std.mem.eql(u8, name, "atomicLoad")) return "doe_atomicLoad";
    if (std.mem.eql(u8, name, "atomicStore")) return "doe_atomicStore";
    if (std.mem.eql(u8, name, "atomicAdd")) return "doe_atomicAdd";
    if (std.mem.eql(u8, name, "atomicSub")) return "doe_atomicSub";
    if (std.mem.eql(u8, name, "atomicMin")) return "doe_atomicMin";
    if (std.mem.eql(u8, name, "atomicMax")) return "doe_atomicMax";
    if (std.mem.eql(u8, name, "atomicAnd")) return "doe_atomicAnd";
    if (std.mem.eql(u8, name, "atomicOr")) return "doe_atomicOr";
    if (std.mem.eql(u8, name, "atomicXor")) return "doe_atomicXor";
    if (std.mem.eql(u8, name, "atomicExchange")) return "doe_atomicExchange";
    if (std.mem.eql(u8, name, "unpack2x16float")) return "doe_unpack2x16float";
    if (std.mem.eql(u8, name, "pack2x16float")) return "doe_pack2x16float";
    if (std.mem.eql(u8, name, "unpack4x8unorm")) return "doe_unpack4x8unorm";
    if (std.mem.eql(u8, name, "unpack4x8snorm")) return "doe_unpack4x8snorm";
    if (std.mem.eql(u8, name, "pack4x8unorm")) return "doe_pack4x8unorm";
    if (std.mem.eql(u8, name, "pack4x8snorm")) return "doe_pack4x8snorm";
    if (std.mem.eql(u8, name, "subgroupAdd")) return "WaveActiveSum";
    if (std.mem.eql(u8, name, "subgroupExclusiveAdd")) return "WavePrefixSum";
    if (std.mem.eql(u8, name, "subgroupMin")) return "WaveActiveMin";
    if (std.mem.eql(u8, name, "subgroupMax")) return "WaveActiveMax";
    if (std.mem.eql(u8, name, "subgroupBroadcast")) return "WaveReadLaneAt";
    if (std.mem.eql(u8, name, "subgroupShuffle")) return "WaveReadLaneAt";
    return null;
}

pub fn hlsl_builtin_passthrough(name: []const u8) bool {
    const list = [_][]const u8{
        "abs",      "acos",  "asin",      "atan",       "atan2",
        "ceil",     "clamp", "cos",       "cosh",       "cross",
        "distance", "dot",   "exp",       "exp2",       "floor",
        "fma",      "ldexp", "length",    "log",        "log2",
        "max",      "min",   "normalize", "pow",        "round",
        "sign",     "sin",   "sinh",      "smoothstep", "sqrt",
        "step",     "tan",   "tanh",      "trunc",
    };
    inline for (list) |candidate| {
        if (std.mem.eql(u8, name, candidate)) return true;
    }
    return false;
}
