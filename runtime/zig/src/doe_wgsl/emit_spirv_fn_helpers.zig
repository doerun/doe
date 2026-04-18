const ir = @import("ir.zig");

pub const ScalarKind = enum { bool, signed, unsigned, float };

pub fn scalar_construct_kind(scalar: ir.ScalarType) ScalarKind {
    return switch (scalar) {
        .bool => .bool,
        .u32 => .unsigned,
        .f16, .f32, .abstract_float => .float,
        else => .signed,
    };
}

pub fn assign_op_to_binary(op: ir.AssignOp) ir.BinaryOp {
    return switch (op) {
        .assign => .add,
        .add => .add,
        .sub => .sub,
        .mul => .mul,
        .div => .div,
        .rem => .rem,
        .bit_and => .bit_and,
        .bit_or => .bit_or,
        .bit_xor => .bit_xor,
    };
}

// Returns true if any `.assign` statement in the function has an lhs chain
// that roots at `param_ref(param_index)`. Used to decide whether a param is
// safe to SSA-promote (WGSL params are locally mutable by default).
pub fn param_is_assigned(function: *const ir.Function, param_index: u32) bool {
    for (function.stmts.items) |stmt| {
        switch (stmt) {
            .assign => |assign| {
                if (ref_chain_roots_at_param(function, assign.lhs, param_index)) return true;
            },
            else => {},
        }
    }
    return false;
}

fn ref_chain_roots_at_param(function: *const ir.Function, expr_id: ir.ExprId, param_index: u32) bool {
    var current = expr_id;
    while (true) {
        const expr = function.exprs.items[current];
        switch (expr.data) {
            .param_ref => |index| return index == param_index,
            .member => |m| current = m.base,
            .index => |idx| current = idx.base,
            .load => |inner| current = inner,
            else => return false,
        }
    }
}
