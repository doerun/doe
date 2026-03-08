const ir = @import("ir.zig");

pub const ValidateError = error{
    InvalidIr,
};

pub fn validate(module: *const ir.Module) ValidateError!void {
    for (module.functions.items) |function| {
        if (function.root_stmt >= function.stmts.items.len) return error.InvalidIr;

        for (function.locals.items, 0..) |_, local_index| {
            _ = local_index;
        }

        for (function.exprs.items) |expr| {
            if (expr.ty == ir.INVALID_TYPE) return error.InvalidIr;
            switch (expr.data) {
                .param_ref => |index| if (index >= function.params.items.len) return error.InvalidIr,
                .local_ref => |index| if (index >= function.locals.items.len) return error.InvalidIr,
                .global_ref => |index| if (index >= module.globals.items.len) return error.InvalidIr,
                .load => |inner| if (inner >= function.exprs.items.len) return error.InvalidIr,
                .unary => |unary| if (unary.operand >= function.exprs.items.len) return error.InvalidIr,
                .binary => |binary| {
                    if (binary.lhs >= function.exprs.items.len or binary.rhs >= function.exprs.items.len) return error.InvalidIr;
                },
                .call => |call| {
                    if (call.args.start + call.args.len > function.expr_args.items.len) return error.InvalidIr;
                },
                .construct => |construct| {
                    if (construct.args.start + construct.args.len > function.expr_args.items.len) return error.InvalidIr;
                },
                .member => |member| if (member.base >= function.exprs.items.len) return error.InvalidIr,
                .index => |index| {
                    if (index.base >= function.exprs.items.len or index.index >= function.exprs.items.len) return error.InvalidIr;
                },
                else => {},
            }
        }

        for (function.stmts.items) |stmt| {
            switch (stmt) {
                .block => |range| if (range.start + range.len > function.stmt_children.items.len) return error.InvalidIr,
                .local_decl => |decl| {
                    if (decl.local >= function.locals.items.len) return error.InvalidIr;
                    if (decl.initializer) |expr_id| if (expr_id >= function.exprs.items.len) return error.InvalidIr;
                },
                .expr => |expr_id| if (expr_id >= function.exprs.items.len) return error.InvalidIr,
                .assign => |assign| {
                    if (assign.lhs >= function.exprs.items.len or assign.rhs >= function.exprs.items.len) return error.InvalidIr;
                },
                .return_ => |value| if (value) |expr_id| if (expr_id >= function.exprs.items.len) return error.InvalidIr,
                .if_ => |if_stmt| {
                    if (if_stmt.cond >= function.exprs.items.len) return error.InvalidIr;
                    if (if_stmt.then_block >= function.stmts.items.len) return error.InvalidIr;
                    if (if_stmt.else_block) |stmt_id| if (stmt_id >= function.stmts.items.len) return error.InvalidIr;
                },
                .loop_ => |loop_stmt| {
                    if (loop_stmt.init) |stmt_id| if (stmt_id >= function.stmts.items.len) return error.InvalidIr;
                    if (loop_stmt.cond) |expr_id| if (expr_id >= function.exprs.items.len) return error.InvalidIr;
                    if (loop_stmt.continuing) |stmt_id| if (stmt_id >= function.stmts.items.len) return error.InvalidIr;
                    if (loop_stmt.body >= function.stmts.items.len) return error.InvalidIr;
                },
                .switch_ => |switch_stmt| {
                    if (switch_stmt.expr >= function.exprs.items.len) return error.InvalidIr;
                    if (switch_stmt.cases.start + switch_stmt.cases.len > function.switch_cases.items.len) return error.InvalidIr;
                },
                else => {},
            }
        }

        for (function.switch_cases.items) |case_node| {
            if (case_node.body >= function.stmts.items.len) return error.InvalidIr;
            for (case_node.selectors.items) |expr_id| {
                if (expr_id >= function.exprs.items.len) return error.InvalidIr;
            }
        }
    }
}
