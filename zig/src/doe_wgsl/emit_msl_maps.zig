const std = @import("std");
const ir = @import("ir.zig");

pub fn unary_op_text(op: ir.UnaryOp) []const u8 {
    return switch (op) {
        .neg => "-",
        .not => "!",
        .bit_not => "~",
    };
}

pub fn msl_function_name(name: []const u8, stage: ?ir.ShaderStage) []const u8 {
    if (stage != null and std.mem.eql(u8, name, "main")) return "main_kernel";
    return name;
}

pub fn msl_builtin_passthrough_name(name: []const u8) ?[]const u8 {
    const passthrough = [_][]const u8{
        "abs",
        "acos",
        "asin",
        "atan",
        "atan2",
        "ceil",
        "clamp",
        "cos",
        "cosh",
        "cross",
        "distance",
        "dot",
        "exp",
        "exp2",
        "fma",
        "floor",
        "fract",
        "ldexp",
        "length",
        "log",
        "log2",
        "max",
        "min",
        "mix",
        "normalize",
        "pow",
        "round",
        "sign",
        "sin",
        "sinh",
        "smoothstep",
        "sqrt",
        "step",
        "tan",
        "tanh",
        "trunc",
    };
    inline for (passthrough) |candidate| {
        if (std.mem.eql(u8, name, candidate)) return candidate;
    }
    return null;
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

pub fn msl_builtin_name(builtin: ir.Builtin) []const u8 {
    return switch (builtin) {
        .global_invocation_id => "thread_position_in_grid",
        .local_invocation_id => "thread_position_in_threadgroup",
        .local_invocation_index => "thread_index_in_threadgroup",
        .workgroup_id => "threadgroup_position_in_grid",
        else => "unsupported_builtin",
    };
}
