const std = @import("std");
const ir = @import("ir.zig");
const sema_helpers = @import("sema_helpers.zig");
const spirv = @import("spirv_builder.zig");
const emit_spirv = @import("emit_spirv.zig");
const emit_spirv_builtins = @import("emit_spirv_builtins.zig");

const Emitter = emit_spirv.Emitter;
const EmitError = emit_spirv.EmitError;

pub const FunctionState = struct {
    emitter: *Emitter,
    function: *const ir.Function,
    param_ptr_ids: []u32,
    local_ptr_ids: []u32,
    break_targets: std.ArrayListUnmanaged(u32) = .{},
    continue_targets: std.ArrayListUnmanaged(u32) = .{},

    pub fn init(emitter: *Emitter, function_index: ir.FunctionId) EmitError!FunctionState {
        const function = &emitter.module.functions.items[function_index];
        const param_ptr_ids = try emitter.alloc.alloc(u32, function.params.items.len);
        errdefer emitter.alloc.free(param_ptr_ids);
        @memset(param_ptr_ids, 0);
        const local_ptr_ids = try emitter.alloc.alloc(u32, function.locals.items.len);
        errdefer emitter.alloc.free(local_ptr_ids);
        @memset(local_ptr_ids, 0);
        return .{
            .emitter = emitter,
            .function = function,
            .param_ptr_ids = param_ptr_ids,
            .local_ptr_ids = local_ptr_ids,
        };
    }

    pub fn deinit(self: *FunctionState) void {
        self.break_targets.deinit(self.emitter.alloc);
        self.continue_targets.deinit(self.emitter.alloc);
        self.emitter.alloc.free(self.local_ptr_ids);
        self.emitter.alloc.free(self.param_ptr_ids);
    }

    pub fn emit_stmt(self: *FunctionState, stmt_id: ir.StmtId) EmitError!bool {
        const stmt = self.function.stmts.items[stmt_id];
        switch (stmt) {
            .block => |range| {
                var i: u32 = 0;
                while (i < range.len) : (i += 1) {
                    if (try self.emit_stmt(self.function.stmt_children.items[range.start + i])) return true;
                }
                return false;
            },
            .local_decl => |decl| {
                if (decl.initializer) |expr_id| {
                    try self.emitter.emit_store(self.local_ptr_ids[decl.local], try self.emit_value_expr(expr_id));
                }
                return false;
            },
            .expr => |expr_id| {
                _ = try self.emit_value_expr(expr_id);
                return false;
            },
            .assign => |assign| {
                const ptr_id = try self.emit_ref_expr(assign.lhs);
                var value_id = try self.emit_value_expr(assign.rhs);
                if (assign.op != .assign) {
                    const current = try self.emit_load_from_ref(assign.lhs);
                    value_id = try self.emit_binary(
                        assign_op_to_binary(assign.op),
                        current,
                        value_id,
                        self.function.exprs.items[assign.lhs].ty,
                        self.function.exprs.items[assign.lhs].ty,
                    );
                }
                try self.emitter.emit_store(ptr_id, value_id);
                return false;
            },
            .return_ => |value| {
                if (value) |expr_id| {
                    try self.emitter.builder.append_function_inst(spirv.Opcode.ReturnValue, &.{try self.emit_value_expr(expr_id)});
                } else {
                    try self.emitter.builder.append_function_inst(spirv.Opcode.Return, &.{});
                }
                return true;
            },
            .if_ => |if_stmt| {
                const cond_id = try self.emit_value_expr(if_stmt.cond);
                const then_label = self.emitter.builder.reserve_id();
                const else_label = if (if_stmt.else_block != null) self.emitter.builder.reserve_id() else 0;
                const merge_label = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(spirv.Opcode.SelectionMerge, &.{ merge_label, spirv.SelectionControl.None });
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.BranchConditional,
                    &.{ cond_id, then_label, if (else_label != 0) else_label else merge_label },
                );

                try self.emit_label(then_label);
                const then_terminated = try self.emit_stmt(if_stmt.then_block);
                if (!then_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{merge_label});

                if (if_stmt.else_block) |else_block| {
                    try self.emit_label(else_label);
                    const else_terminated = try self.emit_stmt(else_block);
                    if (!else_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{merge_label});
                }

                try self.emit_label(merge_label);
                return false;
            },
            .loop_ => |loop_stmt| {
                if (loop_stmt.init) |init_stmt| _ = try self.emit_stmt(init_stmt);

                const header_label = self.emitter.builder.reserve_id();
                const body_label = self.emitter.builder.reserve_id();
                const continue_label = self.emitter.builder.reserve_id();
                const merge_label = self.emitter.builder.reserve_id();

                try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{header_label});
                try self.emit_label(header_label);
                try self.emitter.builder.append_function_inst(spirv.Opcode.LoopMerge, &.{ merge_label, continue_label, spirv.LoopControl.None });
                if (loop_stmt.cond) |cond| {
                    try self.emitter.builder.append_function_inst(
                        spirv.Opcode.BranchConditional,
                        &.{ try self.emit_value_expr(cond), body_label, merge_label },
                    );
                } else {
                    try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{body_label});
                }

                try self.break_targets.append(self.emitter.alloc, merge_label);
                try self.continue_targets.append(self.emitter.alloc, continue_label);

                try self.emit_label(body_label);
                const body_terminated = try self.emit_stmt(loop_stmt.body);
                if (!body_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{continue_label});

                try self.emit_label(continue_label);
                const continuing_terminated = if (loop_stmt.continuing) |cont| try self.emit_stmt(cont) else false;
                if (!continuing_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{header_label});

                _ = self.break_targets.pop();
                _ = self.continue_targets.pop();

                try self.emit_label(merge_label);
                return false;
            },
            .switch_ => |switch_stmt| {
                const selector_id = try self.emit_value_expr(switch_stmt.expr);
                const merge_label = self.emitter.builder.reserve_id();
                var labels = try self.emitter.alloc.alloc(u32, switch_stmt.cases.len);
                defer self.emitter.alloc.free(labels);
                @memset(labels, 0);

                var default_label = merge_label;
                var case_index: u32 = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = self.function.switch_cases.items[switch_stmt.cases.start + case_index];
                    labels[case_index] = self.emitter.builder.reserve_id();
                    if (case_node.is_default) default_label = labels[case_index];
                }

                var operands = std.ArrayListUnmanaged(u32){};
                defer operands.deinit(self.emitter.alloc);
                try operands.append(self.emitter.alloc, selector_id);
                try operands.append(self.emitter.alloc, default_label);
                case_index = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = self.function.switch_cases.items[switch_stmt.cases.start + case_index];
                    if (case_node.is_default) continue;
                    for (case_node.selectors.items) |selector_expr| {
                        try operands.append(self.emitter.alloc, try self.switch_selector_literal(selector_expr));
                        try operands.append(self.emitter.alloc, labels[case_index]);
                    }
                }

                try self.emitter.builder.append_function_inst(spirv.Opcode.SelectionMerge, &.{ merge_label, spirv.SelectionControl.None });
                try self.emitter.builder.append_function_inst(spirv.Opcode.Switch, operands.items);

                try self.break_targets.append(self.emitter.alloc, merge_label);
                case_index = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = self.function.switch_cases.items[switch_stmt.cases.start + case_index];
                    try self.emit_label(labels[case_index]);
                    const terminated = try self.emit_stmt(case_node.body);
                    if (!terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{merge_label});
                }
                _ = self.break_targets.pop();

                try self.emit_label(merge_label);
                return false;
            },
            .break_ => {
                if (self.break_targets.items.len == 0) return error.InvalidIr;
                try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{self.break_targets.items[self.break_targets.items.len - 1]});
                return true;
            },
            .continue_ => {
                if (self.continue_targets.items.len == 0) return error.InvalidIr;
                try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{self.continue_targets.items[self.continue_targets.items.len - 1]});
                return true;
            },
            .discard_ => {
                try self.emitter.builder.append_function_inst(spirv.Opcode.Kill, &.{});
                return true;
            },
        }
    }

    fn emit_label(self: *FunctionState, label_id: u32) EmitError!void {
        try self.emitter.builder.append_function_inst(spirv.Opcode.Label, &.{label_id});
    }

    pub fn emit_value_expr(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .bool_lit => |value| try self.emitter.builder.const_bool(value),
            .int_lit => |value| switch (self.emitter.module.types.get(expr.ty)) {
                .scalar => |scalar| switch (scalar) {
                    .u32 => try self.emitter.builder.const_u32(@truncate(value)),
                    .i32, .abstract_int => try self.emitter.builder.const_i32_bits(@truncate(value)),
                    else => return error.InvalidIr,
                },
                else => return error.InvalidIr,
            },
            .float_lit => |value| switch (self.emitter.module.types.get(expr.ty)) {
                .scalar => |scalar| switch (scalar) {
                    .f16 => try self.emitter.builder.const_f16_bits(@as(u16, @bitCast(@as(f16, @floatCast(value))))),
                    else => try self.emitter.builder.const_f32_bits(@bitCast(@as(f32, @floatCast(value)))),
                },
                else => try self.emitter.builder.const_f32_bits(@bitCast(@as(f32, @floatCast(value)))),
            },
            .param_ref, .local_ref => return error.InvalidIr,
            .global_ref => |index| blk: {
                const global = self.emitter.module.globals.items[index];
                switch (self.emitter.module.types.get(global.ty)) {
                    .texture_2d, .storage_texture_2d => {
                        break :blk try self.emitter.emit_function_load(
                            try self.emitter.lower_type(expr.ty),
                            self.emitter.global_ids[index],
                        );
                    },
                    else => return error.InvalidIr,
                }
            },
            .load => |inner| try self.emit_load_from_ref(inner),
            .unary => |unary| try self.emit_unary(unary.op, try self.emit_value_expr(unary.operand), expr.ty),
            .binary => |binary| try self.emit_binary(
                binary.op,
                try self.emit_value_expr(binary.lhs),
                try self.emit_value_expr(binary.rhs),
                self.function.exprs.items[binary.lhs].ty,
                expr.ty,
            ),
            .call => |call| try self.emit_call(call, expr.ty),
            .construct => |construct| try self.emit_construct(construct.ty, construct.args),
            .member => |member| if (expr.category == .ref)
                return error.InvalidIr
            else
                try self.emit_member_value(member, expr.ty),
            .index => |index| if (expr.category == .ref)
                return error.InvalidIr
            else
                try self.emit_composite_extract(try self.emit_value_expr(index.base), expr.ty, try self.literal_index(index.index)),
        };
    }

    pub fn emit_ref_expr(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .param_ref => |index| self.param_ptr_ids[index],
            .local_ref => |index| self.local_ptr_ids[index],
            .global_ref => |index| blk: {
                if (!self.emitter.global_buffer_wrapped[index]) break :blk self.emitter.global_ids[index];
                const global = self.emitter.module.globals.items[index];
                const ptr_type = try self.emitter.builder.type_pointer(
                    try self.emitter.global_storage_class(global),
                    try self.emitter.lower_type(expr.ty),
                );
                const result_id = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.AccessChain,
                    &.{ ptr_type, result_id, self.emitter.global_ids[index], try self.emitter.builder.const_u32(0) },
                );
                break :blk result_id;
            },
            .member => |member| blk: {
                const base_ptr = try self.emit_ref_expr(member.base);
                const ptr_type = try self.emitter.builder.type_pointer(try self.ref_storage_class(member.base), try self.emitter.lower_type(expr.ty));
                const result_id = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.AccessChain,
                    &.{ ptr_type, result_id, base_ptr, try self.emitter.builder.const_u32(member.field_index) },
                );
                break :blk result_id;
            },
            .index => |index| blk: {
                const base_ptr = try self.emit_ref_expr(index.base);
                const ptr_type = try self.emitter.builder.type_pointer(try self.ref_storage_class(index.base), try self.emitter.lower_type(expr.ty));
                const result_id = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.AccessChain,
                    &.{ ptr_type, result_id, base_ptr, try self.emit_value_expr(index.index) },
                );
                break :blk result_id;
            },
            else => return error.InvalidIr,
        };
    }

    fn emit_load_from_ref(self: *FunctionState, ref_expr_id: ir.ExprId) EmitError!u32 {
        const ref_expr = self.function.exprs.items[ref_expr_id];
        return try self.emitter.emit_function_load(try self.emitter.lower_type(ref_expr.ty), try self.emit_ref_expr(ref_expr_id));
    }

    fn emit_member_value(self: *FunctionState, member: @FieldType(ir.Expr, "member"), result_ty: ir.TypeId) EmitError!u32 {
        if (member.field_name.len == 1) {
            return try self.emit_composite_extract(try self.emit_value_expr(member.base), result_ty, member.field_index);
        }

        const base_id = try self.emit_value_expr(member.base);
        const base_ty = self.function.exprs.items[member.base].ty;
        const vec = switch (self.emitter.module.types.get(base_ty)) {
            .vector => |vector| vector,
            else => return error.InvalidIr,
        };
        const swizzle = sema_helpers.parse_vector_swizzle(member.field_name, vec.len) catch return error.InvalidIr;

        var operands = std.ArrayListUnmanaged(u32){};
        defer operands.deinit(self.emitter.alloc);
        var i: usize = 0;
        while (i < swizzle.len) : (i += 1) {
            try operands.append(self.emitter.alloc, try self.emit_composite_extract(base_id, vec.elem, swizzle.indices[i]));
        }
        return try self.emit_construct_from_operands(result_ty, operands.items);
    }

    fn emit_unary(self: *FunctionState, op: ir.UnaryOp, operand_id: u32, result_ty: ir.TypeId) EmitError!u32 {
        const opcode: u16 = switch (op) {
            .neg => switch (self.scalar_kind(result_ty)) {
                .signed => spirv.Opcode.SNegate,
                .float => spirv.Opcode.FNegate,
                else => return error.UnsupportedConstruct,
            },
            .not => spirv.Opcode.LogicalNot,
            .bit_not => spirv.Opcode.Not,
        };
        return try self.emit_result_inst(opcode, try self.emitter.lower_type(result_ty), &.{operand_id});
    }

    fn emit_binary(self: *FunctionState, op: ir.BinaryOp, lhs_id: u32, rhs_id: u32, operand_ty: ir.TypeId, result_ty: ir.TypeId) EmitError!u32 {
        const opcode: u16 = switch (op) {
            .add => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FAdd,
                else => spirv.Opcode.IAdd,
            },
            .sub => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FSub,
                else => spirv.Opcode.ISub,
            },
            .mul => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FMul,
                else => spirv.Opcode.IMul,
            },
            .div => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FDiv,
                .unsigned => spirv.Opcode.UDiv,
                .signed => spirv.Opcode.SDiv,
                else => return error.UnsupportedConstruct,
            },
            .rem => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FRem,
                .unsigned => spirv.Opcode.UMod,
                .signed => spirv.Opcode.SRem,
                else => return error.UnsupportedConstruct,
            },
            .bit_and => spirv.Opcode.BitwiseAnd,
            .bit_or => spirv.Opcode.BitwiseOr,
            .bit_xor => spirv.Opcode.BitwiseXor,
            .shift_left => spirv.Opcode.ShiftLeftLogical,
            .shift_right => switch (self.scalar_kind(operand_ty)) {
                .unsigned => spirv.Opcode.ShiftRightLogical,
                else => spirv.Opcode.ShiftRightArithmetic,
            },
            .equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .not_equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .less => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .less_equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .greater => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .greater_equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .logical_and => spirv.Opcode.LogicalAnd,
            .logical_or => spirv.Opcode.LogicalOr,
        };
        return try self.emit_result_inst(opcode, try self.emitter.lower_type(result_ty), &.{ lhs_id, rhs_id });
    }

    fn emit_compare(self: *FunctionState, op: ir.BinaryOp, lhs_id: u32, rhs_id: u32, operand_ty: ir.TypeId) EmitError!u32 {
        const opcode: u16 = switch (self.scalar_kind(operand_ty)) {
            .bool => switch (op) {
                .equal => spirv.Opcode.LogicalEqual,
                .not_equal => spirv.Opcode.LogicalNotEqual,
                else => return error.UnsupportedConstruct,
            },
            .unsigned => switch (op) {
                .equal => spirv.Opcode.IEqual,
                .not_equal => spirv.Opcode.INotEqual,
                .less => spirv.Opcode.ULessThan,
                .less_equal => spirv.Opcode.ULessThanEqual,
                .greater => spirv.Opcode.UGreaterThan,
                .greater_equal => spirv.Opcode.UGreaterThanEqual,
                else => return error.UnsupportedConstruct,
            },
            .signed => switch (op) {
                .equal => spirv.Opcode.IEqual,
                .not_equal => spirv.Opcode.INotEqual,
                .less => spirv.Opcode.SLessThan,
                .less_equal => spirv.Opcode.SLessThanEqual,
                .greater => spirv.Opcode.SGreaterThan,
                .greater_equal => spirv.Opcode.SGreaterThanEqual,
                else => return error.UnsupportedConstruct,
            },
            .float => switch (op) {
                .equal => spirv.Opcode.FOrdEqual,
                .not_equal => spirv.Opcode.FOrdNotEqual,
                .less => spirv.Opcode.FOrdLessThan,
                .less_equal => spirv.Opcode.FOrdLessThanEqual,
                .greater => spirv.Opcode.FOrdGreaterThan,
                .greater_equal => spirv.Opcode.FOrdGreaterThanEqual,
                else => return error.UnsupportedConstruct,
            },
        };
        return try self.emit_result_inst(opcode, try self.emitter.builder.type_bool(), &.{ lhs_id, rhs_id });
    }

    fn emit_call(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        if (call.kind == .builtin) return try self.emit_builtin_call(call, result_ty);
        const fn_id = self.emitter.function_id_by_name(call.name) orelse return error.InvalidIr;
        var args = std.ArrayListUnmanaged(u32){};
        defer args.deinit(self.emitter.alloc);
        var i: u32 = 0;
        while (i < call.args.len) : (i += 1) {
            try args.append(self.emitter.alloc, try self.emit_value_expr(self.function.expr_args.items[call.args.start + i]));
        }
        return try self.emitter.emit_function_call(try self.emitter.lower_type(result_ty), fn_id, args.items);
    }

    fn emit_builtin_call(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        return (try emit_spirv_builtins.emit_builtin(self, call, result_ty)) orelse return error.UnsupportedConstruct;
    }

    fn emit_construct(self: *FunctionState, ty: ir.TypeId, range: ir.Range) EmitError!u32 {
        var operands = std.ArrayListUnmanaged(u32){};
        defer operands.deinit(self.emitter.alloc);
        var i: u32 = 0;
        while (i < range.len) : (i += 1) {
            try operands.append(self.emitter.alloc, try self.emit_value_expr(self.function.expr_args.items[range.start + i]));
        }
        return try self.emit_construct_from_operands(ty, operands.items);
    }

    pub fn emit_construct_from_operands(self: *FunctionState, ty: ir.TypeId, operands: []const u32) EmitError!u32 {
        var full = std.ArrayListUnmanaged(u32){};
        defer full.deinit(self.emitter.alloc);
        const result_ty = try self.emitter.lower_type(ty);
        const result_id = self.emitter.builder.reserve_id();
        try full.append(self.emitter.alloc, result_ty);
        try full.append(self.emitter.alloc, result_id);
        try full.appendSlice(self.emitter.alloc, operands);
        try self.emitter.builder.append_function_inst(spirv.Opcode.CompositeConstruct, full.items);
        return result_id;
    }

    pub fn emit_composite_extract(self: *FunctionState, composite_id: u32, result_ty: ir.TypeId, index: u32) EmitError!u32 {
        return try self.emit_result_inst(spirv.Opcode.CompositeExtract, try self.emitter.lower_type(result_ty), &.{ composite_id, index });
    }

    pub fn emit_result_inst(self: *FunctionState, opcode: u16, result_type: u32, operands: []const u32) EmitError!u32 {
        var full = std.ArrayListUnmanaged(u32){};
        defer full.deinit(self.emitter.alloc);
        const result_id = self.emitter.builder.reserve_id();
        try full.append(self.emitter.alloc, result_type);
        try full.append(self.emitter.alloc, result_id);
        try full.appendSlice(self.emitter.alloc, operands);
        try self.emitter.builder.append_function_inst(opcode, full.items);
        return result_id;
    }

    pub fn ref_storage_class(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .param_ref, .local_ref => spirv.StorageClass.Function,
            .global_ref => |index| try self.emitter.global_storage_class(self.emitter.module.globals.items[index]),
            .member => |member| try self.ref_storage_class(member.base),
            .index => |index| try self.ref_storage_class(index.base),
            else => error.InvalidIr,
        };
    }

    fn literal_index(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .int_lit => |value| @truncate(value),
            else => error.UnsupportedConstruct,
        };
    }

    fn switch_selector_literal(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .int_lit => |value| @truncate(value),
            .bool_lit => |value| if (value) 1 else 0,
            .unary => |unary| if (unary.op == .neg) blk: {
                const inner = self.function.exprs.items[unary.operand];
                switch (inner.data) {
                    .int_lit => |value| break :blk @as(u32, @bitCast(-@as(i32, @intCast(value)))),
                    else => return error.UnsupportedConstruct,
                }
            } else error.UnsupportedConstruct,
            else => error.UnsupportedConstruct,
        };
    }

    const ScalarKind = enum { bool, signed, unsigned, float };

    pub fn scalar_kind(self: *FunctionState, ty: ir.TypeId) ScalarKind {
        return switch (self.emitter.module.types.get(ty)) {
            .scalar => |scalar| switch (scalar) {
                .bool => .bool,
                .u32 => .unsigned,
                .f16, .f32, .abstract_float => .float,
                else => .signed,
            },
            .vector => |vec| switch (self.emitter.module.types.get(vec.elem)) {
                .scalar => |scalar| switch (scalar) {
                    .bool => .bool,
                    .u32 => .unsigned,
                    .f16, .f32, .abstract_float => .float,
                    else => .signed,
                },
                else => .signed,
            },
            else => .signed,
        };
    }
};

fn assign_op_to_binary(op: ir.AssignOp) ir.BinaryOp {
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
