const std = @import("std");
const ir = @import("../../ir/ir.zig");
const spirv = @import("spirv_spec.zig");
pub fn multiDotLoopControl(body: []const u32) u32 {
    const multi_dot_minimum = 2;
    var dot_count: usize = 0;
    var offset: usize = 0;
    while (offset < body.len) {
        const word_count = body[offset] >> 16;
        const opcode: u16 = @truncate(body[offset]);
        std.debug.assert(word_count > 0 and word_count <= body.len - offset);
        if (opcode == spirv.Opcode.LoopMerge) return spirv.LoopControl.None;
        if (opcode == spirv.Opcode.Dot) dot_count += 1;
        offset += word_count;
    }
    return if (dot_count >= multi_dot_minimum) spirv.LoopControl.DontUnroll else spirv.LoopControl.None;
}

pub fn cacheableResultOpcode(opcode: u16) bool {
    return switch (opcode) {
        spirv.Opcode.SNegate,
        spirv.Opcode.FNegate,
        spirv.Opcode.Not,
        spirv.Opcode.IAdd,
        spirv.Opcode.FAdd,
        spirv.Opcode.ISub,
        spirv.Opcode.FSub,
        spirv.Opcode.IMul,
        spirv.Opcode.FMul,
        spirv.Opcode.UDiv,
        spirv.Opcode.SDiv,
        spirv.Opcode.FDiv,
        spirv.Opcode.UMod,
        spirv.Opcode.SRem,
        spirv.Opcode.FRem,
        spirv.Opcode.VectorTimesScalar,
        spirv.Opcode.MatrixTimesScalar,
        spirv.Opcode.VectorTimesMatrix,
        spirv.Opcode.MatrixTimesVector,
        spirv.Opcode.MatrixTimesMatrix,
        spirv.Opcode.BitwiseAnd,
        spirv.Opcode.BitwiseOr,
        spirv.Opcode.BitwiseXor,
        spirv.Opcode.ShiftLeftLogical,
        spirv.Opcode.ShiftRightLogical,
        spirv.Opcode.ShiftRightArithmetic,
        spirv.Opcode.LogicalEqual,
        spirv.Opcode.LogicalNotEqual,
        spirv.Opcode.IEqual,
        spirv.Opcode.INotEqual,
        spirv.Opcode.ULessThan,
        spirv.Opcode.ULessThanEqual,
        spirv.Opcode.UGreaterThan,
        spirv.Opcode.UGreaterThanEqual,
        spirv.Opcode.SLessThan,
        spirv.Opcode.SLessThanEqual,
        spirv.Opcode.SGreaterThan,
        spirv.Opcode.SGreaterThanEqual,
        spirv.Opcode.FOrdEqual,
        spirv.Opcode.FOrdNotEqual,
        spirv.Opcode.FOrdLessThan,
        spirv.Opcode.FOrdLessThanEqual,
        spirv.Opcode.FOrdGreaterThan,
        spirv.Opcode.FOrdGreaterThanEqual,
        spirv.Opcode.LogicalAnd,
        spirv.Opcode.LogicalOr,
        spirv.Opcode.Bitcast,
        spirv.Opcode.ConvertFToS,
        spirv.Opcode.ConvertFToU,
        spirv.Opcode.ConvertSToF,
        spirv.Opcode.ConvertUToF,
        spirv.Opcode.FConvert,
        spirv.Opcode.CompositeExtract,
        spirv.Opcode.VectorExtractDynamic,
        spirv.Opcode.Dot,
        => true,
        else => false,
    };
}

pub fn emitZeroValue(self: anytype, ty: ir.TypeId) !u32 {
    return switch (self.emitter.module.types.get(ty)) {
        .scalar => |scalar| switch (scalar) {
            .bool => try self.emitter.builder.const_bool(false),
            .i32, .abstract_int => try self.emitter.builder.const_i32_bits(0),
            .u32 => try self.emitter.builder.const_u32(0),
            .f16 => try self.emitter.builder.const_f16_bits(0),
            .f32, .abstract_float => try self.emitter.builder.const_f32_bits(0),
            .void => error.UnsupportedConstruct,
        },
        .vector => |vec| blk: {
            const zero = try emitZeroValue(self, vec.elem);
            var components = std.ArrayListUnmanaged(u32){};
            defer components.deinit(self.emitter.alloc);
            var i: u32 = 0;
            while (i < vec.len) : (i += 1) try components.append(self.emitter.alloc, zero);
            break :blk try self.emit_construct_from_operands(ty, components.items);
        },
        else => error.UnsupportedConstruct,
    };
}

pub const ScalarKind = enum { bool, signed, unsigned, float };

pub fn scalar_construct_kind(scalar: ir.ScalarType) ScalarKind {
    return switch (scalar) {
        .bool => .bool,
        .u32 => .unsigned,
        .f16, .f32, .abstract_float => .float,
        else => .signed,
    };
}

pub fn emitBoolScalarConstruct(
    self: anytype,
    target_ty: ir.TypeId,
    source_ty: ir.TypeId,
    target_scalar: ir.ScalarType,
    source_scalar: ir.ScalarType,
    source_id: u32,
) !?u32 {
    const target_kind = scalar_construct_kind(target_scalar);
    const source_kind = scalar_construct_kind(source_scalar);
    if (target_kind == .bool) {
        const opcode: u16 = switch (source_kind) {
            .bool => return source_id,
            .signed, .unsigned => spirv.Opcode.INotEqual,
            .float => spirv.Opcode.FOrdNotEqual,
        };
        return try self.emit_result_inst(
            opcode,
            try self.emitter.lower_type(target_ty),
            &.{ source_id, try emitZeroValue(self, source_ty) },
        );
    }
    if (source_kind != .bool) return null;
    const one = switch (target_scalar) {
        .i32, .abstract_int => try self.emitter.builder.const_i32_bits(1),
        .u32 => try self.emitter.builder.const_u32(1),
        .f16 => try self.emitter.builder.const_f16_bits(@as(u16, @bitCast(@as(f16, 1.0)))),
        .f32, .abstract_float => try self.emitter.builder.const_f32_bits(@as(u32, @bitCast(@as(f32, 1.0)))),
        .bool, .void => return error.UnsupportedConstruct,
    };
    return try self.emit_result_inst(
        spirv.Opcode.Select,
        try self.emitter.lower_type(target_ty),
        &.{ source_id, one, try emitZeroValue(self, target_ty) },
    );
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
        .shift_left => .shift_left,
        .shift_right => .shift_right,
    };
}
