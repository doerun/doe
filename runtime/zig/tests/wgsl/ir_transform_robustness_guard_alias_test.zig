// ir_transform_robustness_guard_alias_test.zig - Guard alias robustness tests.

const support = @import("ir_transform_robustness_test_support.zig");
const testing = support.testing;
const ir = support.ir;
const apply = support.apply;
const make_test_module = support.make_test_module;
const u32_type = support.u32_type;
const f32_type = support.f32_type;

test "robustness: guarded const coord alias skips injected textureLoad clamp" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const bool_ty = try module.types.intern(.{ .scalar = .bool });
    const void_ty = try module.types.intern(.{ .scalar = .void });
    const vec2u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
    const vec3u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 3 } });
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{
        .name = try ir.dup_string(allocator, "main"),
        .return_type = void_ty,
    };
    errdefer function.deinit(allocator);

    try function.params.append(allocator, .{
        .name = try ir.dup_string(allocator, "gid"),
        .ty = vec3u_ty,
        .io = .{ .builtin = .global_invocation_id },
    });
    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "coords"),
        .ty = vec2u_ty,
        .mutable = false,
    });

    const tex_ref = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    const texture_dimensions_args = try function.append_expr_args(allocator, &.{ tex_ref, level_id });
    const texture_dimensions = try function.append_expr(allocator, .{
        .ty = vec2u_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureDimensions"),
            .kind = .builtin,
            .args = texture_dimensions_args,
        } },
    });
    const texture_width = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .member = .{ .base = texture_dimensions, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const texture_height = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .member = .{ .base = texture_dimensions, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });

    const gid_param_x = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_x, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const gid_load_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_x } });
    const guard_x = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .greater_equal, .lhs = gid_load_x, .rhs = texture_width } } });

    const gid_param_y = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_y, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });
    const gid_load_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_y } });
    const guard_y = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .greater_equal, .lhs = gid_load_y, .rhs = texture_height } } });
    const guard_or = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .logical_or, .lhs = guard_x, .rhs = guard_y } } });

    const return_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const then_children = try function.append_stmt_children(allocator, &.{return_stmt});
    const then_block = try function.append_stmt(allocator, .{ .block = then_children });
    const if_stmt = try function.append_stmt(allocator, .{ .if_ = .{ .cond = guard_or, .then_block = then_block, .else_block = null } });

    const gid_param_coord_x = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_coord_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_coord_x, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const gid_load_coord_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_coord_x } });
    const gid_param_coord_y = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_coord_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_coord_y, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });
    const gid_load_coord_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_coord_y } });
    const coord_args = try function.append_expr_args(allocator, &.{ gid_load_coord_x, gid_load_coord_y });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .construct = .{ .ty = vec2u_ty, .args = coord_args } } });
    const local_decl = try function.append_stmt(allocator, .{ .local_decl = .{ .local = 0, .initializer = coord_id, .is_const = true } });
    const coord_ref = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .local_ref = 0 } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_ref, coord_ref, level_id });
    const call_id = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });
    const expr_stmt = try function.append_stmt(allocator, .{ .expr = call_id });

    const root_children = try function.append_stmt_children(allocator, &.{ if_stmt, local_decl, expr_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = root_children });

    try module.functions.append(allocator, function);
    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    const transformed_call = module.functions.items[0].exprs.items[call_id];
    const new_coord_id = module.functions.items[0].expr_args.items[transformed_call.data.call.args.start + 1];
    try testing.expectEqual(coord_ref, new_coord_id);
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

test "robustness: const guard alias skips injected textureLoad clamp" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const bool_ty = try module.types.intern(.{ .scalar = .bool });
    const void_ty = try module.types.intern(.{ .scalar = .void });
    const vec2u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
    const vec3u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 3 } });
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{
        .name = try ir.dup_string(allocator, "main"),
        .return_type = void_ty,
    };
    errdefer function.deinit(allocator);

    try function.params.append(allocator, .{
        .name = try ir.dup_string(allocator, "gid"),
        .ty = vec3u_ty,
        .io = .{ .builtin = .global_invocation_id },
    });
    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "out_of_bounds"),
        .ty = bool_ty,
        .mutable = false,
    });

    const tex_ref = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    const texture_dimensions_args = try function.append_expr_args(allocator, &.{ tex_ref, level_id });
    const texture_dimensions = try function.append_expr(allocator, .{
        .ty = vec2u_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureDimensions"),
            .kind = .builtin,
            .args = texture_dimensions_args,
        } },
    });
    const texture_width = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .member = .{ .base = texture_dimensions, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const texture_height = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .member = .{ .base = texture_dimensions, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });

    const gid_param_x = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_x, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const gid_load_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_x } });
    const guard_x = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .greater_equal, .lhs = gid_load_x, .rhs = texture_width } } });

    const gid_param_y = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_y, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });
    const gid_load_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_y } });
    const guard_y = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .greater_equal, .lhs = gid_load_y, .rhs = texture_height } } });
    const guard_or = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .logical_or, .lhs = guard_x, .rhs = guard_y } } });
    const guard_decl = try function.append_stmt(allocator, .{ .local_decl = .{ .local = 0, .initializer = guard_or, .is_const = true } });
    const guard_ref = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .local_ref = 0 } });

    const return_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const then_children = try function.append_stmt_children(allocator, &.{return_stmt});
    const then_block = try function.append_stmt(allocator, .{ .block = then_children });
    const if_stmt = try function.append_stmt(allocator, .{ .if_ = .{ .cond = guard_ref, .then_block = then_block, .else_block = null } });

    const gid_param_coord_x = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_coord_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_coord_x, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const gid_load_coord_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_coord_x } });
    const gid_param_coord_y = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_coord_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_coord_y, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });
    const gid_load_coord_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_coord_y } });
    const coord_args = try function.append_expr_args(allocator, &.{ gid_load_coord_x, gid_load_coord_y });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .construct = .{ .ty = vec2u_ty, .args = coord_args } } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_ref, coord_id, level_id });
    const call_id = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });
    const expr_stmt = try function.append_stmt(allocator, .{ .expr = call_id });

    const root_children = try function.append_stmt_children(allocator, &.{ guard_decl, if_stmt, expr_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = root_children });

    try module.functions.append(allocator, function);
    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    const transformed_call = module.functions.items[0].exprs.items[call_id];
    const new_coord_id = module.functions.items[0].expr_args.items[transformed_call.data.call.args.start + 1];
    try testing.expectEqual(coord_id, new_coord_id);
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}
