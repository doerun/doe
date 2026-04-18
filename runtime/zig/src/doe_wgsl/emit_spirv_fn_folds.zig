const ir = @import("ir.zig");
const emit_spirv_shared = @import("emit_spirv_shared.zig");
const ir_const_eval = @import("ir_const_eval.zig");

const EmitError = emit_spirv_shared.EmitError;

pub fn resolve_constant_int(self: anytype, expr_id: ir.ExprId) ?u64 {
    return ir_const_eval.resolve_constant_int(self.emitter.module, self.function, expr_id);
}

pub fn try_fold_identity_binary(
    self: anytype,
    binary: @FieldType(ir.Expr, "binary"),
    result_ty: ir.TypeId,
) EmitError!?u32 {
    const result_scalar = switch (self.emitter.module.types.get(result_ty)) {
        .scalar => |s| s,
        else => return null,
    };
    if (result_scalar != .u32 and result_scalar != .i32 and result_scalar != .abstract_int) return null;
    const lhs_const = resolve_constant_int(self, binary.lhs);
    const rhs_const = resolve_constant_int(self, binary.rhs);
    // Only fire when exactly one side is a known integer constant; the
    // both-constant case is handled by try_fold_const_binary.
    if ((lhs_const == null) == (rhs_const == null)) return null;
    const op = binary.op;
    if (lhs_const) |c| {
        const c32: u32 = @truncate(c);
        switch (op) {
            .add, .bit_or, .bit_xor => if (c32 == 0) return try self.emit_value_expr(binary.rhs),
            .mul => {
                if (c32 == 0) return try self.emitter.builder.const_u32(0);
                if (c32 == 1) return try self.emit_value_expr(binary.rhs);
            },
            .bit_and => if (c32 == 0) return try self.emitter.builder.const_u32(0),
            else => {},
        }
    }
    if (rhs_const) |c| {
        const c32: u32 = @truncate(c);
        switch (op) {
            .add, .sub, .bit_or, .bit_xor, .shift_left, .shift_right => {
                if (c32 == 0) return try self.emit_value_expr(binary.lhs);
            },
            .mul => {
                if (c32 == 0) return try self.emitter.builder.const_u32(0);
                if (c32 == 1) return try self.emit_value_expr(binary.lhs);
            },
            .div => if (c32 == 1) return try self.emit_value_expr(binary.lhs),
            .bit_and => if (c32 == 0) return try self.emitter.builder.const_u32(0),
            else => {},
        }
    }
    return null;
}

pub fn try_fold_const_binary(
    self: anytype,
    binary: @FieldType(ir.Expr, "binary"),
    result_ty: ir.TypeId,
) EmitError!?u32 {
    const a_raw = resolve_constant_int(self, binary.lhs) orelse return null;
    const b_raw = resolve_constant_int(self, binary.rhs) orelse return null;
    const result_scalar = switch (self.emitter.module.types.get(result_ty)) {
        .scalar => |s| s,
        else => return null,
    };
    if (result_scalar != .u32 and result_scalar != .i32 and result_scalar != .abstract_int) return null;
    const unsigned = result_scalar == .u32;
    const a_u32: u32 = @truncate(a_raw);
    const b_u32: u32 = @truncate(b_raw);
    const a_i32: i32 = @bitCast(a_u32);
    const b_i32: i32 = @bitCast(b_u32);
    const folded_u32: u32 = switch (binary.op) {
        .add => a_u32 +% b_u32,
        .sub => a_u32 -% b_u32,
        .mul => a_u32 *% b_u32,
        .div => if (b_u32 == 0) return null else if (unsigned) a_u32 / b_u32 else @bitCast(@divTrunc(a_i32, b_i32)),
        .rem => if (b_u32 == 0) return null else if (unsigned) a_u32 % b_u32 else @bitCast(@rem(a_i32, b_i32)),
        .bit_and => a_u32 & b_u32,
        .bit_or => a_u32 | b_u32,
        .bit_xor => a_u32 ^ b_u32,
        .shift_left => if (b_u32 >= 32) 0 else a_u32 << @intCast(b_u32),
        .shift_right => if (unsigned) (if (b_u32 >= 32) 0 else a_u32 >> @intCast(b_u32)) else @bitCast(if (b_u32 >= 32) @as(i32, if (a_i32 < 0) -1 else 0) else a_i32 >> @intCast(b_u32)),
        else => return null,
    };
    return switch (result_scalar) {
        .u32 => try self.emitter.builder.const_u32(folded_u32),
        .i32, .abstract_int => try self.emitter.builder.const_i32_bits(folded_u32),
        else => unreachable,
    };
}
