const std = @import("std");
const ast_mod = @import("ast.zig");
const ir = @import("ir.zig");
const sema = @import("sema.zig");
const token_mod = @import("token.zig");

const Ast = ast_mod.Ast;
const Node = ast_mod.Node;
const NULL_NODE = ast_mod.NULL_NODE;
const Tag = token_mod.Tag;

pub const BuildError = error{
    OutOfMemory,
    InvalidIr,
    UnsupportedConstruct,
};

pub fn build(allocator: std.mem.Allocator, tree: *const Ast, semantic: *const sema.SemanticModule) BuildError!ir.Module {
    var module = ir.Module.init(allocator);
    errdefer module.deinit();

    try module.types.items.appendSlice(allocator, semantic.types.items.items);
    try copy_structs(allocator, &module, semantic);
    try copy_globals(allocator, tree, &module, semantic);
    try copy_functions(allocator, tree, &module, semantic);
    return module;
}

fn copy_structs(allocator: std.mem.Allocator, module: *ir.Module, semantic: *const sema.SemanticModule) BuildError!void {
    for (semantic.structs.items) |struct_info| {
        var struct_def = ir.StructDef{ .name = try ir.dup_string(allocator, struct_info.name) };
        errdefer struct_def.deinit(allocator);
        for (struct_info.fields.items) |field| {
            try struct_def.fields.append(allocator, .{
                .name = try ir.dup_string(allocator, field.name),
                .ty = field.ty,
                .io = field.io,
            });
        }
        try module.structs.append(allocator, struct_def);
    }
}

fn copy_globals(allocator: std.mem.Allocator, tree: *const Ast, module: *ir.Module, semantic: *const sema.SemanticModule) BuildError!void {
    for (semantic.globals.items) |global_info| {
        const node = tree.nodes.items[global_info.node_idx];
        var initializer: ?ir.ConstantValue = null;
        switch (node.tag) {
            .global_var => {
                const init_node = tree.extra_data.items[node.data.rhs + 3];
                if (init_node != NULL_NODE) initializer = try scalar_constant_from_node(tree, init_node);
            },
            .const_decl, .override_decl => {
                if (node.data.rhs != NULL_NODE) initializer = try scalar_constant_from_node(tree, node.data.rhs);
            },
            else => {},
        }
        try module.globals.append(allocator, .{
            .name = try ir.dup_string(allocator, global_info.name),
            .ty = global_info.ty,
            .class = global_info.class,
            .addr_space = global_info.addr_space,
            .access = global_info.access,
            .binding = global_info.binding,
            .io = global_info.io,
            .initializer = initializer,
        });
    }
}

fn copy_functions(allocator: std.mem.Allocator, tree: *const Ast, module: *ir.Module, semantic: *const sema.SemanticModule) BuildError!void {
    for (semantic.functions.items, 0..) |function_info, function_index| {
        var function = ir.Function{
            .name = try ir.dup_string(allocator, function_info.name),
            .return_type = function_info.return_type,
            .stage = function_info.stage,
            .workgroup_size = function_info.workgroup_size,
        };
        errdefer function.deinit(allocator);

        for (function_info.params.items) |param| {
            try function.params.append(allocator, .{
                .name = try ir.dup_string(allocator, param.name),
                .ty = param.ty,
                .io = param.io,
            });
        }
        for (function_info.locals.items) |local| {
            try function.locals.append(allocator, .{
                .name = try ir.dup_string(allocator, local.name),
                .ty = local.ty,
                .mutable = local.mutable,
            });
        }

        var builder = FunctionBuilder{
            .allocator = allocator,
            .tree = tree,
            .semantic = semantic,
            .function = &function,
        };
        const fn_node = tree.nodes.items[function_info.node_idx];
        function.root_stmt = try builder.lower_stmt(fn_node.data.rhs);

        const new_index: ir.FunctionId = @intCast(module.functions.items.len);
        try module.functions.append(allocator, function);
        if (function_info.stage) |stage| {
            try module.entry_points.append(allocator, .{
                .function = new_index,
                .stage = stage,
                .workgroup_size = function_info.workgroup_size,
            });
        }
        _ = function_index;
    }
}

const FunctionBuilder = struct {
    allocator: std.mem.Allocator,
    tree: *const Ast,
    semantic: *const sema.SemanticModule,
    function: *ir.Function,
    next_local_index: u32 = 0,

    fn lower_stmt(self: *FunctionBuilder, node_idx: u32) BuildError!ir.StmtId {
        const node = self.tree.nodes.items[node_idx];
        return switch (node.tag) {
            .block => try self.lower_block(node),
            .var_stmt, .let_stmt, .const_stmt => try self.lower_local_decl(node),
            .return_stmt => try self.function.append_stmt(self.allocator, .{ .return_ = if (node.data.lhs != NULL_NODE) try self.lower_value_expr(node.data.lhs) else null }),
            .if_stmt => try self.lower_if_stmt(node),
            .for_stmt => try self.lower_for_stmt(node),
            .while_stmt => try self.function.append_stmt(self.allocator, .{ .loop_ = .{
                .kind = .while_loop,
                .init = null,
                .cond = try self.lower_value_expr(node.data.lhs),
                .continuing = null,
                .body = try self.lower_stmt(node.data.rhs),
            } }),
            .loop_stmt => try self.lower_loop_stmt(node),
            .break_stmt => try self.lower_break_stmt(node),
            .continue_stmt => try self.function.append_stmt(self.allocator, .continue_),
            .continuing_stmt => try self.lower_stmt(node.data.lhs),
            .discard_stmt => try self.function.append_stmt(self.allocator, .discard_),
            .expr_stmt => try self.function.append_stmt(self.allocator, .{ .expr = try self.lower_value_expr(node.data.lhs) }),
            .assign_stmt => try self.function.append_stmt(self.allocator, .{ .assign = .{
                .op = map_assign_op(self.tree.tokens.items[node.main_token].tag),
                .lhs = try self.lower_ref_expr(node.data.lhs),
                .rhs = try self.lower_value_expr(node.data.rhs),
            } }),
            .switch_stmt => try self.lower_switch_stmt(node),
            .switch_case, .else_clause => error.UnsupportedConstruct,
            else => error.UnsupportedConstruct,
        };
    }

    fn lower_if_stmt(self: *FunctionBuilder, node: Node) !ir.StmtId {
        const extra = self.tree.extra_data.items;
        const then_block = extra[node.data.rhs + 0];
        const else_block = extra[node.data.rhs + 1];
        return try self.function.append_stmt(self.allocator, .{ .if_ = .{
            .cond = try self.lower_value_expr(node.data.lhs),
            .then_block = try self.lower_stmt(then_block),
            .else_block = if (else_block != NULL_NODE) try self.lower_stmt(else_block) else null,
        } });
    }

    fn lower_block(self: *FunctionBuilder, node: Node) !ir.StmtId {
        var children = std.ArrayListUnmanaged(ir.StmtId){};
        defer children.deinit(self.allocator);
        var i: u32 = 0;
        while (i < node.data.rhs) : (i += 1) {
            try children.append(self.allocator, try self.lower_stmt(self.tree.extra_data.items[node.data.lhs + i]));
        }
        const range = try self.function.append_stmt_children(self.allocator, children.items);
        return try self.function.append_stmt(self.allocator, .{ .block = range });
    }

    fn lower_local_decl(self: *FunctionBuilder, node: Node) !ir.StmtId {
        const local_index = self.next_local_index;
        self.next_local_index += 1;
        const initializer = if (node.data.rhs != NULL_NODE) try self.lower_value_expr(node.data.rhs) else null;
        return try self.function.append_stmt(self.allocator, .{ .local_decl = .{
            .local = local_index,
            .initializer = initializer,
            .is_const = node.tag != .var_stmt,
        } });
    }

    fn lower_for_stmt(self: *FunctionBuilder, node: Node) !ir.StmtId {
        const extra = self.tree.extra_data.items;
        const base = node.data.lhs;
        return try self.function.append_stmt(self.allocator, .{ .loop_ = .{
            .kind = .for_loop,
            .init = if (extra[base + 0] != NULL_NODE) try self.lower_stmt(extra[base + 0]) else null,
            .cond = if (extra[base + 1] != NULL_NODE) try self.lower_value_expr(extra[base + 1]) else null,
            .continuing = if (extra[base + 2] != NULL_NODE) try self.lower_stmt(extra[base + 2]) else null,
            .body = try self.lower_stmt(node.data.rhs),
        } });
    }

    fn lower_loop_stmt(self: *FunctionBuilder, node: Node) !ir.StmtId {
        const parts = try self.lower_loop_body_parts(node.data.lhs);
        return try self.function.append_stmt(self.allocator, .{ .loop_ = .{
            .kind = .loop,
            .init = null,
            .cond = null,
            .continuing = parts.continuing,
            .body = parts.body,
        } });
    }

    fn lower_loop_body_parts(self: *FunctionBuilder, block_idx: u32) !struct { body: ir.StmtId, continuing: ?ir.StmtId } {
        const block = self.tree.nodes.items[block_idx];
        if (block.tag != .block or block.data.rhs == 0) {
            return .{ .body = try self.lower_stmt(block_idx), .continuing = null };
        }

        const last_stmt_idx = self.tree.extra_data.items[block.data.lhs + block.data.rhs - 1];
        const last_stmt = self.tree.nodes.items[last_stmt_idx];
        if (last_stmt.tag != .continuing_stmt) {
            return .{ .body = try self.lower_stmt(block_idx), .continuing = null };
        }

        var children = std.ArrayListUnmanaged(ir.StmtId){};
        defer children.deinit(self.allocator);
        var i: u32 = 0;
        while (i + 1 < block.data.rhs) : (i += 1) {
            try children.append(self.allocator, try self.lower_stmt(self.tree.extra_data.items[block.data.lhs + i]));
        }

        const range = try self.function.append_stmt_children(self.allocator, children.items);
        return .{
            .body = try self.function.append_stmt(self.allocator, .{ .block = range }),
            .continuing = try self.lower_stmt(last_stmt.data.lhs),
        };
    }

    fn lower_break_stmt(self: *FunctionBuilder, node: Node) !ir.StmtId {
        if (node.data.lhs == NULL_NODE) return try self.function.append_stmt(self.allocator, .break_);

        const break_stmt = try self.function.append_stmt(self.allocator, .break_);
        const range = try self.function.append_stmt_children(self.allocator, &.{break_stmt});
        const then_block = try self.function.append_stmt(self.allocator, .{ .block = range });
        return try self.function.append_stmt(self.allocator, .{ .if_ = .{
            .cond = try self.lower_value_expr(node.data.lhs),
            .then_block = then_block,
            .else_block = null,
        } });
    }

    fn lower_switch_stmt(self: *FunctionBuilder, node: Node) !ir.StmtId {
        const extra = self.tree.extra_data.items;
        const case_start = node.data.rhs & 0xFFFF;
        const case_count = node.data.rhs >> 16;
        const cases_range = ir.Range{
            .start = @intCast(self.function.switch_cases.items.len),
            .len = case_count,
        };

        var i: u32 = 0;
        while (i < case_count) : (i += 1) {
            const case_node = self.tree.nodes.items[extra[case_start + i]];
            const selector_start = case_node.data.rhs & 0xFFFF;
            const selector_count = case_node.data.rhs >> 16;
            var case_ir = ir.SwitchCase{
                .body = try self.lower_stmt(case_node.data.lhs),
                .is_default = self.tree.tokens.items[case_node.main_token].tag == .kw_default,
            };
            errdefer case_ir.deinit(self.allocator);

            var j: u32 = 0;
            while (j < selector_count) : (j += 1) {
                try case_ir.selectors.append(self.allocator, try self.lower_value_expr(extra[selector_start + j]));
            }
            try self.function.switch_cases.append(self.allocator, case_ir);
        }

        return try self.function.append_stmt(self.allocator, .{ .switch_ = .{
            .expr = try self.lower_value_expr(node.data.lhs),
            .cases = cases_range,
        } });
    }

    fn lower_expr(self: *FunctionBuilder, node_idx: u32) BuildError!ir.ExprId {
        const node = self.tree.nodes.items[node_idx];
        const ty = self.semantic.nodeType(node_idx);
        const category = self.semantic.nodeCategory(node_idx);
        const expr = switch (node.tag) {
            .bool_literal => ir.Expr{ .bool_lit = std.mem.eql(u8, self.tree.tokenSlice(node.main_token), "true") },
            .int_literal => ir.Expr{ .int_lit = std.fmt.parseInt(u64, self.tree.tokenSlice(node.main_token), 10) catch return error.InvalidIr },
            .float_literal => ir.Expr{ .float_lit = std.fmt.parseFloat(f64, self.tree.tokenSlice(node.main_token)) catch return error.InvalidIr },
            .ident_expr => try self.lower_ident(node_idx),
            .unary_expr => ir.Expr{ .unary = .{
                .op = map_unary_op(self.tree.tokens.items[node.main_token].tag),
                .operand = try self.lower_value_expr(node.data.lhs),
            } },
            .binary_expr => ir.Expr{ .binary = .{
                .op = map_binary_op(self.tree.tokens.items[node.main_token].tag),
                .lhs = try self.lower_value_expr(node.data.lhs),
                .rhs = try self.lower_value_expr(node.data.rhs),
            } },
            .call_expr => try self.lower_call(node_idx, node),
            .member_expr => ir.Expr{ .member = .{
                .base = if (category == .ref) try self.lower_ref_expr(node.data.lhs) else try self.lower_value_expr(node.data.lhs),
                .field_name = try ir.dup_string(self.allocator, self.tree.tokenSlice(node.data.rhs)),
                .field_index = try self.resolve_member_index(node.data.lhs, node.data.rhs),
            } },
            .index_expr => ir.Expr{ .index = .{
                .base = if (category == .ref) try self.lower_ref_expr(node.data.lhs) else try self.lower_value_expr(node.data.lhs),
                .index = try self.lower_value_expr(node.data.rhs),
            } },
            else => return error.UnsupportedConstruct,
        };
        return try self.function.append_expr(self.allocator, .{
            .ty = ty,
            .category = category,
            .data = expr,
        });
    }

    fn lower_ident(self: *FunctionBuilder, node_idx: u32) !ir.Expr {
        return switch (self.semantic.nodeSymbol(node_idx)) {
            .global => |index| .{ .global_ref = index },
            .param => |index| .{ .param_ref = index },
            .local => |index| .{ .local_ref = index },
            else => return error.InvalidIr,
        };
    }

    fn lower_call(self: *FunctionBuilder, node_idx: u32, node: Node) !ir.Expr {
        const name = self.tree.tokenSlice(node.main_token);
        var args = std.ArrayListUnmanaged(ir.ExprId){};
        defer args.deinit(self.allocator);

        const kind: ir.CallKind = if (self.semantic.function_map.get(name) != null) .user else .builtin;
        const is_constructor = self.semantic.tryResolveNamedType(name) != null;

        var i: u32 = 0;
        while (i < node.data.rhs) : (i += 1) {
            const arg_node = self.tree.extra_data.items[node.data.lhs + i];
            if (!is_constructor and kind == .builtin and i == 0 and (std.mem.startsWith(u8, name, "atomic") or std.mem.eql(u8, name, "arrayLength"))) {
                try args.append(self.allocator, try self.lower_ref_expr(arg_node));
            } else {
                try args.append(self.allocator, try self.lower_value_expr(arg_node));
            }
        }
        const range = try self.function.append_expr_args(self.allocator, args.items);
        if (is_constructor) {
            return .{ .construct = .{ .ty = self.semantic.nodeType(node_idx), .args = range } };
        }
        return .{ .call = .{ .name = try ir.dup_string(self.allocator, name), .kind = kind, .args = range } };
    }

    fn resolve_member_index(self: *FunctionBuilder, base_node_idx: u32, field_token: u32) !u32 {
        const field_name = self.tree.tokenSlice(field_token);
        var ty = self.semantic.nodeType(base_node_idx);
        while (true) {
            switch (self.semantic.types.get(ty)) {
                .ref => |ref_ty| ty = ref_ty.elem,
                .vector => {
                    if (field_name.len != 1) return error.InvalidIr;
                    return switch (field_name[0]) {
                        'x', 'r' => 0,
                        'y', 'g' => 1,
                        'z', 'b' => 2,
                        'w', 'a' => 3,
                        else => error.InvalidIr,
                    };
                },
                .struct_ => |struct_id| {
                    const struct_info = self.semantic.structs.items[struct_id];
                    for (struct_info.fields.items, 0..) |field, index| {
                        if (std.mem.eql(u8, field.name, field_name)) return @intCast(index);
                    }
                    return error.InvalidIr;
                },
                else => return error.InvalidIr,
            }
        }
    }

    fn lower_value_expr(self: *FunctionBuilder, node_idx: u32) !ir.ExprId {
        const expr_id = try self.lower_expr(node_idx);
        if (self.function.exprs.items[expr_id].category == .value) return expr_id;
        return try self.function.append_expr(self.allocator, .{
            .ty = self.function.exprs.items[expr_id].ty,
            .category = .value,
            .data = .{ .load = expr_id },
        });
    }

    fn lower_ref_expr(self: *FunctionBuilder, node_idx: u32) !ir.ExprId {
        const expr_id = try self.lower_expr(node_idx);
        if (self.function.exprs.items[expr_id].category != .ref) return error.InvalidIr;
        return expr_id;
    }
};

fn map_unary_op(tag: Tag) ir.UnaryOp {
    return switch (tag) {
        .@"-" => .neg,
        .@"!" => .not,
        .@"~" => .bit_not,
        else => .neg,
    };
}

fn map_binary_op(tag: Tag) ir.BinaryOp {
    return switch (tag) {
        .@"+" => .add,
        .@"-" => .sub,
        .@"*" => .mul,
        .@"/" => .div,
        .@"%" => .rem,
        .@"&" => .bit_and,
        .@"|" => .bit_or,
        .@"^" => .bit_xor,
        .shift_left => .shift_left,
        .shift_right => .shift_right,
        .eq_eq => .equal,
        .not_eq => .not_equal,
        .@"<" => .less,
        .lte => .less_equal,
        .@">" => .greater,
        .gte => .greater_equal,
        .and_and => .logical_and,
        .or_or => .logical_or,
        else => .add,
    };
}

fn map_assign_op(tag: Tag) ir.AssignOp {
    return switch (tag) {
        .@"=" => .assign,
        .plus_eq => .add,
        .minus_eq => .sub,
        .star_eq => .mul,
        .slash_eq => .div,
        .percent_eq => .rem,
        .amp_eq => .bit_and,
        .pipe_eq => .bit_or,
        .caret_eq => .bit_xor,
        else => .assign,
    };
}

fn scalar_constant_from_node(tree: *const Ast, node_idx: u32) BuildError!?ir.ConstantValue {
    const node = tree.nodes.items[node_idx];
    return switch (node.tag) {
        .bool_literal => ir.ConstantValue{ .bool = std.mem.eql(u8, tree.tokenSlice(node.main_token), "true") },
        .int_literal => ir.ConstantValue{ .int = std.fmt.parseInt(u64, tree.tokenSlice(node.main_token), 10) catch return error.InvalidIr },
        .float_literal => ir.ConstantValue{ .float = std.fmt.parseFloat(f64, tree.tokenSlice(node.main_token)) catch return error.InvalidIr },
        .unary_expr => switch (tree.tokens.items[node.main_token].tag) {
            .@"-" => blk: {
                const inner = try scalar_constant_from_node(tree, node.data.lhs) orelse return error.UnsupportedConstruct;
                switch (inner) {
                    .int => |value| break :blk ir.ConstantValue{ .int = (~value) +% 1 },
                    .float => |value| break :blk ir.ConstantValue{ .float = -value },
                    else => return error.UnsupportedConstruct,
                }
            },
            else => error.UnsupportedConstruct,
        },
        else => null,
    };
}
