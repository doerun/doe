const std = @import("std");
const ir = @import("../../ir/ir.zig");
const spirv = @import("spirv_spec.zig");
const query = @import("../../ir/ir_query.zig");
const INDEPENDENCE_MAX_EXPR_DEPTH: u32 = 64;

/// Distinct local array elements have no reduction carried between iterations.
/// Unknown calls, aliases, index remapping and control flow keep the old hint.
pub fn independentIndexedLoop(module: *const ir.Module, function: *const ir.Function, loop: @FieldType(ir.Stmt, "loop_")) bool {
    const init = singleStatement(function, loop.init orelse return false);
    if (init != .local_decl) return false;
    const induction = init.local_decl.local;
    if (!ir.is_scalar(&module.types, function.locals.items[induction].ty, .u32)) return false;
    if ((fixedInt(module, function, init.local_decl.initializer orelse return false) orelse return false) != 0) return false;
    const cond = function.exprs.items[loop.cond orelse return false].data;
    if (cond != .binary or cond.binary.op != .less or !inductionRef(function, cond.binary.lhs, induction)) return false;
    const limit = fixedInt(module, function, cond.binary.rhs) orelse return false;
    if (limit == 0 or limit > std.math.maxInt(u32)) return false;
    const step = singleStatement(function, loop.continuing orelse return false);
    if (step != .assign or !inductionRef(function, step.assign.lhs, induction)) return false;
    if (step.assign.op == .add) {
        if ((fixedInt(module, function, step.assign.rhs) orelse return false) != 1) return false;
    } else if (step.assign.op == .assign) {
        const add = function.exprs.items[step.assign.rhs].data;
        if (add != .binary or add.binary.op != .add or !inductionRef(function, add.binary.lhs, induction)) return false;
        if ((fixedInt(module, function, add.binary.rhs) orelse return false) != 1) return false;
    } else return false;

    const body = function.stmts.items[loop.body];
    if (body != .block) return false;
    const children = function.stmt_children.items[body.block.start..][0..body.block.len];
    var target: ?u32 = null;
    for (children) |id| switch (function.stmts.items[id]) {
        .local_decl => |decl| if (!decl.is_const) return false,
        .assign => |assignment| {
            if (target != null) return false;
            const lhs = function.exprs.items[assignment.lhs].data;
            if (lhs != .index) return false;
            const base = function.exprs.items[lhs.index.base].data;
            if (base != .local_ref or base.local_ref == induction) return false;
            const ty = module.types.get(function.locals.items[base.local_ref].ty);
            if (ty != .array or limit > (ty.array.len orelse return false)) return false;
            if (!ir.is_scalar(&module.types, ty.array.elem, .f32)) return false;
            if (!isInductionIndex(module, function, lhs.index.index, induction, limit)) return false;
            target = base.local_ref;
        },
        else => return false,
    };
    const context = IndependentLoop{ .module = module, .function = function, .induction = induction, .limit = limit, .target = target orelse return false };
    for (children) |id| switch (function.stmts.items[id]) {
        .local_decl => |decl| {
            if (!context.readOnlyExpr(decl.initializer orelse return false, INDEPENDENCE_MAX_EXPR_DEPTH)) return false;
        },
        .assign => |assignment| if (!context.readOnlyExpr(assignment.rhs, INDEPENDENCE_MAX_EXPR_DEPTH)) return false,
        else => unreachable,
    };
    return true;
}

fn singleStatement(function: *const ir.Function, id: ir.StmtId) ir.Stmt {
    const statement = function.stmts.items[id];
    if (statement == .block and statement.block.len == 1) return singleStatement(function, function.stmt_children.items[statement.block.start]);
    return statement;
}

fn fixedInt(module: *const ir.Module, function: *const ir.Function, id: ir.ExprId) ?u64 {
    var current = id;
    for (0..INDEPENDENCE_MAX_EXPR_DEPTH) |_| {
        switch (function.exprs.items[current].data) {
            .int_lit => |value| return value,
            .load => |inner| current = inner,
            .local_ref => |local| current = query.resolveConstLocalInitializer(function, local) orelse return null,
            .global_ref => |index| {
                const global = module.globals.items[index];
                if (global.class != .const_ and global.class != .override_) return null;
                if (!ir.is_scalar(&module.types, global.ty, .u32)) return null;
                const initializer = global.initializer orelse return null;
                return if (initializer == .int) initializer.int else null;
            },
            else => return null,
        }
    }
    return null;
}

fn inductionRef(function: *const ir.Function, id: ir.ExprId, induction: u32) bool {
    var current = id;
    while (function.exprs.items[current].data == .load) current = function.exprs.items[current].data.load;
    const expr = function.exprs.items[current].data;
    // Numeric conversions are not aliases: float rounding can repeat indices.
    return expr == .local_ref and expr.local_ref == induction;
}

fn isInductionIndex(module: *const ir.Module, function: *const ir.Function, id: ir.ExprId, induction: u32, limit: u64) bool {
    if (inductionRef(function, id, induction)) return true;
    const expr = function.exprs.items[id].data;
    if (expr != .call or !expr.call.robustness_generated or !std.mem.eql(u8, expr.call.name, "min") or expr.call.args.len != 2) return false;
    const args = function.expr_args.items[expr.call.args.start..][0..2];
    return inductionRef(function, args[0], induction) and (fixedInt(module, function, args[1]) orelse return false) >= limit - 1;
}

const IndependentLoop = struct {
    module: *const ir.Module,
    function: *const ir.Function,
    induction: u32,
    limit: u64,
    target: ?u32,

    fn readOnlyExpr(self: IndependentLoop, id: ir.ExprId, depth: u32) bool {
        if (depth == 0) return false;
        return switch (self.function.exprs.items[id].data) {
            .bool_lit, .int_lit, .float_lit, .global_ref => true,
            .local_ref => |local| (self.target == null or local != self.target.?) and
                self.module.types.get(self.function.locals.items[local].ty) != .ref,
            .param_ref => |param| self.module.types.get(self.function.params.items[param].ty) != .ref,
            .load => |inner| self.readOnlyExpr(inner, depth - 1),
            .unary => |value| self.readOnlyExpr(value.operand, depth - 1),
            .binary => |value| self.readOnlyExpr(value.lhs, depth - 1) and self.readOnlyExpr(value.rhs, depth - 1),
            .member => |value| self.readOnlyExpr(value.base, depth - 1),
            .index => |value| blk: {
                const base = self.function.exprs.items[value.base].data;
                if (self.target != null and base == .local_ref and base.local_ref == self.target.?)
                    break :blk isInductionIndex(self.module, self.function, value.index, self.induction, self.limit);
                break :blk self.readOnlyExpr(value.base, depth - 1) and self.readOnlyExpr(value.index, depth - 1);
            },
            .construct => |value| self.readOnlyArgs(value.args, depth - 1),
            .call => |call| blk: {
                if (!self.readOnlyArgs(call.args, depth - 1)) break :blk false;
                if (call.kind == .builtin) break :blk std.mem.eql(u8, call.name, "dot") or std.mem.eql(u8, call.name, "min") or std.mem.eql(u8, call.name, "max") or std.mem.eql(u8, call.name, "clamp") or std.mem.eql(u8, call.name, "arrayLength");
                for (self.module.functions.items) |*callee| {
                    if (!std.mem.eql(u8, callee.name, call.name)) continue;
                    const context = IndependentLoop{ .module = self.module, .function = callee, .induction = 0, .limit = 0, .target = null };
                    break :blk context.readOnlyStatement(callee.root_stmt, depth - 1);
                }
                break :blk false;
            },
        };
    }

    fn readOnlyArgs(self: IndependentLoop, range: ir.Range, depth: u32) bool {
        for (self.function.expr_args.items[range.start..][0..range.len]) |arg| if (!self.readOnlyExpr(arg, depth)) return false;
        return true;
    }

    fn readOnlyStatement(self: IndependentLoop, id: ir.StmtId, depth: u32) bool {
        if (depth == 0) return false;
        return switch (self.function.stmts.items[id]) {
            .block => |range| blk: {
                for (self.function.stmt_children.items[range.start..][0..range.len]) |child| if (!self.readOnlyStatement(child, depth - 1)) break :blk false;
                break :blk true;
            },
            .local_decl => |decl| decl.is_const and self.readOnlyExpr(decl.initializer orelse return false, depth - 1),
            .return_ => |expr| self.readOnlyExpr(expr orelse return false, depth - 1),
            else => false,
        };
    }
};

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

pub const AccessChainEntry = struct {
    root_id: u32,
    ptr_type: u32,
    result_id: u32,
    indices: []u32,
};

pub const LoadCacheRoot = enum {
    local,
};

pub const LoadCacheEntry = struct {
    root: LoadCacheRoot,
    index: u32,
    value_id: u32,
};

pub const ResultInstEntry = struct {
    opcode: u16,
    result_type: u32,
    result_id: u32,
    operands: []u32,
};

pub fn clearResultInstEntries(allocator: std.mem.Allocator, entries: *std.ArrayListUnmanaged(ResultInstEntry)) void {
    for (entries.items) |entry| allocator.free(entry.operands);
    entries.clearRetainingCapacity();
}

pub fn findResultInstEntry(entries: []const ResultInstEntry, opcode: u16, result_type: u32, operands: []const u32) ?u32 {
    for (entries) |entry| {
        if (entry.opcode != opcode) continue;
        if (entry.result_type != result_type) continue;
        if (entry.operands.len != operands.len) continue;
        if (std.mem.eql(u32, entry.operands, operands)) return entry.result_id;
    }
    return null;
}

pub fn appendResultInstEntry(
    allocator: std.mem.Allocator,
    entries: *std.ArrayListUnmanaged(ResultInstEntry),
    opcode: u16,
    result_type: u32,
    result_id: u32,
    operands: []const u32,
) !void {
    const owned_operands = try allocator.dupe(u32, operands);
    errdefer allocator.free(owned_operands);
    try entries.append(allocator, .{
        .opcode = opcode,
        .result_type = result_type,
        .result_id = result_id,
        .operands = owned_operands,
    });
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

pub fn removeLoadCacheEntry(entries: *std.ArrayListUnmanaged(LoadCacheEntry), root: LoadCacheRoot, index: u32) void {
    var i: usize = 0;
    while (i < entries.items.len) {
        const entry = entries.items[i];
        if (entry.root == root and entry.index == index) {
            _ = entries.swapRemove(i);
            continue;
        }
        i += 1;
    }
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

pub fn ref_chain_roots_at_local(function: *const ir.Function, expr_id: ir.ExprId) ?u32 {
    var current = expr_id;
    while (true) {
        const expr = function.exprs.items[current];
        switch (expr.data) {
            .local_ref => |index| return index,
            .member => |m| current = m.base,
            .index => |idx| current = idx.base,
            .load => |inner| current = inner,
            else => return null,
        }
    }
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
