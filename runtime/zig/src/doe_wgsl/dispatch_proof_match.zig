const ir = @import("ir.zig");
const layout_utils = @import("layout_utils.zig");
const lean_proof = @import("../lean_proof.zig");

pub fn try_elide_storage_index(
    module: *const ir.Module,
    function: *const ir.Function,
    function_id: ir.FunctionId,
    index_data: @FieldType(ir.Expr, "index"),
) ?ir.DispatchPrecondition {
    const binding = resolve_storage_binding(module, function, index_data.base) orelse return null;
    const element_stride_bytes = resolve_runtime_array_element_stride(module, function, index_data.base) orelse return null;

    if (lean_proof.boundsProven(.gid_1d_storage_buffer)) {
        if (classify_builtin_component(function, index_data.index, .global_invocation_id)) |gid_axis| {
            return .{
                .kind = .gid_component,
                .gid_axis = gid_axis,
                .storage_binding = binding,
                .element_stride_bytes = element_stride_bytes,
            };
        }
    }

    if (lean_proof.boundsProven(.gid_2d_flat_storage_buffer) and
        match_flat_index_2d_dispatch_x(module, function, function_id, index_data.index))
    {
        return .{
            .kind = .flat_index_2d_dispatch_x,
            .gid_axis = 0,
            .storage_binding = binding,
            .element_stride_bytes = element_stride_bytes,
        };
    }

    return null;
}

fn resolve_indexable_type(types: *const ir.TypeStore, ty: ir.TypeId) ir.TypeId {
    var current = ty;
    while (true) {
        switch (types.get(current)) {
            .ref => |ref_ty| current = ref_ty.elem,
            else => return current,
        }
    }
}

fn resolve_runtime_array_element_stride(
    module: *const ir.Module,
    function: *const ir.Function,
    base_id: ir.ExprId,
) ?u64 {
    const base_ty = resolve_indexable_type(&module.types, function.exprs.items[base_id].ty);
    const arr = switch (module.types.get(base_ty)) {
        .array => |value| value,
        else => return null,
    };
    if (arr.len != null) return null;
    const elem_size = layout_utils.type_size(module, arr.elem);
    const elem_align = layout_utils.type_alignment(module, arr.elem);
    return layout_utils.round_up(elem_size, elem_align);
}

fn resolve_storage_binding(
    module: *const ir.Module,
    function: *const ir.Function,
    expr_id: ir.ExprId,
) ?ir.BindingPoint {
    const current_id = resolve_value_alias(function, expr_id);
    const expr = function.exprs.items[current_id];
    switch (expr.data) {
        .global_ref => |global_idx| {
            if (global_idx >= module.globals.items.len) return null;
            const global = module.globals.items[global_idx];
            if (global.addr_space != .storage) return null;
            return global.binding;
        },
        .member => |member| return resolve_storage_binding(module, function, member.base),
        .index => |index| return resolve_storage_binding(module, function, index.base),
        else => return null,
    }
}

fn match_flat_index_2d_dispatch_x(
    module: *const ir.Module,
    function: *const ir.Function,
    function_id: ir.FunctionId,
    expr_id: ir.ExprId,
) bool {
    const canonical = resolve_value_alias(function, expr_id);
    const expr = function.exprs.items[canonical];
    const binary = switch (expr.data) {
        .binary => |value| value,
        else => return false,
    };
    if (binary.op != .add) return false;

    return (classify_builtin_component(function, binary.lhs, .global_invocation_id) == 0 and
        match_gid_y_times_dispatch_width(module, function, function_id, binary.rhs)) or
        (classify_builtin_component(function, binary.rhs, .global_invocation_id) == 0 and
            match_gid_y_times_dispatch_width(module, function, function_id, binary.lhs));
}

fn match_gid_y_times_dispatch_width(
    module: *const ir.Module,
    function: *const ir.Function,
    function_id: ir.FunctionId,
    expr_id: ir.ExprId,
) bool {
    const canonical = resolve_value_alias(function, expr_id);
    const expr = function.exprs.items[canonical];
    const binary = switch (expr.data) {
        .binary => |value| value,
        else => return false,
    };
    if (binary.op != .mul) return false;

    return (classify_builtin_component(function, binary.lhs, .global_invocation_id) == 1 and
        match_dispatch_width(module, function, function_id, binary.rhs)) or
        (classify_builtin_component(function, binary.rhs, .global_invocation_id) == 1 and
            match_dispatch_width(module, function, function_id, binary.lhs));
}

fn match_dispatch_width(
    module: *const ir.Module,
    function: *const ir.Function,
    function_id: ir.FunctionId,
    expr_id: ir.ExprId,
) bool {
    const workgroup_size = workgroup_size_for_function(module, function_id);
    if (classify_builtin_component(function, expr_id, .num_workgroups) == 0) {
        return workgroup_size[0] == 1;
    }

    const canonical = resolve_value_alias(function, expr_id);
    const expr = function.exprs.items[canonical];
    const binary = switch (expr.data) {
        .binary => |value| value,
        else => return false,
    };
    if (binary.op != .mul) return false;

    return (classify_builtin_component(function, binary.lhs, .num_workgroups) == 0 and
        match_u32_literal(function, binary.rhs, workgroup_size[0])) or
        (classify_builtin_component(function, binary.rhs, .num_workgroups) == 0 and
            match_u32_literal(function, binary.lhs, workgroup_size[0]));
}

fn workgroup_size_for_function(module: *const ir.Module, function_id: ir.FunctionId) [3]u32 {
    for (module.entry_points.items) |entry| {
        if (entry.function == function_id) return entry.workgroup_size;
    }
    return .{ 1, 1, 1 };
}

fn match_u32_literal(function: *const ir.Function, expr_id: ir.ExprId, expected: u32) bool {
    const expr = function.exprs.items[resolve_value_alias(function, expr_id)];
    return switch (expr.data) {
        .int_lit => |value| value == expected,
        else => false,
    };
}

fn classify_builtin_component(
    function: *const ir.Function,
    expr_id: ir.ExprId,
    builtin: ir.Builtin,
) ?u8 {
    const expr = function.exprs.items[resolve_value_alias(function, expr_id)];
    const member = switch (expr.data) {
        .member => |value| value,
        else => return null,
    };
    const base = function.exprs.items[resolve_value_alias(function, member.base)];
    const param_idx = switch (base.data) {
        .param_ref => |value| value,
        else => return null,
    };
    if (param_idx >= function.params.items.len) return null;
    const io = function.params.items[param_idx].io orelse return null;
    if (io.builtin != builtin) return null;
    if (std.mem.eql(u8, member.field_name, "x")) return 0;
    if (std.mem.eql(u8, member.field_name, "y")) return 1;
    if (std.mem.eql(u8, member.field_name, "z")) return 2;
    return null;
}

fn resolve_value_alias(function: *const ir.Function, expr_id: ir.ExprId) ir.ExprId {
    var current = expr_id;
    while (true) {
        const expr = function.exprs.items[current];
        switch (expr.data) {
            .load => |inner| current = inner,
            .construct => |construct| {
                if (construct.args.len != 1) return current;
                current = function.expr_args.items[construct.args.start];
            },
            .local_ref => |local_idx| {
                current = resolve_const_local_initializer(function, local_idx) orelse return current;
            },
            else => return current,
        }
    }
}

fn resolve_const_local_initializer(function: *const ir.Function, local_idx: u32) ?ir.ExprId {
    for (function.stmts.items) |stmt| {
        switch (stmt) {
            .local_decl => |decl| {
                if (decl.local == local_idx and decl.is_const) return decl.initializer;
            },
            else => {},
        }
    }
    return null;
}

const std = @import("std");
