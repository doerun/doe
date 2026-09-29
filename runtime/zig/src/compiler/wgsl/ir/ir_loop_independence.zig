const std = @import("std");
const ir = @import("ir.zig");
const query = @import("ir_query.zig");

const INDEPENDENCE_MAX_EXPR_DEPTH: u32 = 64;

/// Distinct local array elements have no reduction carried between iterations.
/// Unknown calls, aliases, index remapping and control flow reject eligibility.
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
            .address_of, .deref => false,
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
