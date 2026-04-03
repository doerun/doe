// ir_transform_robustness_test.zig — tests for the robustness IR transform pass.
//
// Split from ir_transform_robustness.zig for line-limit compliance.

const std = @import("std");
const testing = std.testing;
const ir = @import("ir.zig");
const robustness = @import("ir_transform_robustness.zig");
const apply = robustness.apply;

fn make_test_module(allocator: std.mem.Allocator) !ir.Module {
    var module = ir.Module.init(allocator);
    errdefer module.deinit();

    // Intern base types: u32 and f32
    _ = try module.types.intern(.{ .scalar = .u32 });
    _ = try module.types.intern(.{ .scalar = .f32 });
    return module;
}

fn u32_type(module: *ir.Module) ir.TypeId {
    for (module.types.items.items, 0..) |item, idx| {
        if (item == .scalar and item.scalar == .u32) return @intCast(idx);
    }
    unreachable;
}

fn f32_type(module: *ir.Module) ir.TypeId {
    for (module.types.items.items, 0..) |item, idx| {
        if (item == .scalar and item.scalar == .f32) return @intCast(idx);
    }
    unreachable;
}

fn add_struct_type(
    module: *ir.Module,
    allocator: std.mem.Allocator,
    name: []const u8,
    fields: []const struct { name: []const u8, ty: ir.TypeId },
) !ir.TypeId {
    var struct_def = ir.StructDef{ .name = try ir.dup_string(allocator, name) };
    errdefer struct_def.deinit(allocator);
    for (fields) |field| {
        try struct_def.fields.append(allocator, .{
            .name = try ir.dup_string(allocator, field.name),
            .ty = field.ty,
        });
    }
    try module.structs.append(allocator, struct_def);
    const struct_id: ir.StructId = @intCast(module.structs.items.len - 1);
    return try module.types.intern(.{ .struct_ = struct_id });
}

test "robustness: sized array index is clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    // array<f32, 10>
    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = 10 } });
    const ref_arr_ty = try module.types.intern(.{ .ref = .{ .elem = arr_ty, .addr_space = .function, .access = .read_write } });

    // Add a global for the array
    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "data"),
        .ty = ref_arr_ty,
        .class = .var_,
        .addr_space = .function,
    });

    // Build a function with: data[idx]
    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // expr 0: global_ref(0) — the array
    const base_id = try function.append_expr(allocator, .{ .ty = ref_arr_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    // expr 1: int_lit(15) — intentionally out-of-bounds index
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 15 } });
    // expr 2: index { base, index }
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .ref, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);

    try apply(allocator, &module, .{});

    // The index expression should now reference a min() call, not the raw index.
    const transformed = module.functions.items[0].exprs.items[index_id];
    try testing.expect(transformed.data == .index);
    const new_index = transformed.data.index.index;
    // The new index should be a min() call appended after the original expressions.
    try testing.expect(new_index > index_id);

    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expect(min_expr.data == .call);
    try testing.expectEqualStrings("min", min_expr.data.call.name);
    try testing.expectEqual(@as(u32, 2), min_expr.data.call.args.len);
}

test "robustness: vector index is clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    // vec4<f32>
    const vec_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    try function.locals.append(allocator, .{ .name = try ir.dup_string(allocator, "v"), .ty = vec_ty, .mutable = false });

    // expr 0: local_ref(0) — the vector
    const base_id = try function.append_expr(allocator, .{ .ty = vec_ty, .category = .value, .data = .{ .local_ref = 0 } });
    // expr 1: int_lit(5) — out of bounds
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 5 } });
    // expr 2: index { base, index }
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .value, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    // The max value should be vec.len - 1 = 3
    const max_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_arg_id];
    try testing.expectEqual(@as(u64, 3), max_expr.data.int_lit);
}

test "robustness: struct member and nested array indices are clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    // array<array<f32, 4>, 3>
    const inner_arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = 4 } });
    const outer_arr_ty = try module.types.intern(.{ .array = .{ .elem = inner_arr_ty, .len = 3 } });
    const struct_ty = try add_struct_type(&module, allocator, "Wrapper", &.{
        .{ .name = "data", .ty = outer_arr_ty },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "wrapper"),
        .ty = struct_ty,
        .mutable = false,
    });

    const base_id = try function.append_expr(allocator, .{
        .ty = struct_ty,
        .category = .value,
        .data = .{ .local_ref = 0 },
    });
    const member_id = try function.append_expr(allocator, .{
        .ty = outer_arr_ty,
        .category = .value,
        .data = .{
            .member = .{
                .base = base_id,
                .field_name = try ir.dup_string(allocator, "data"),
                .field_index = 0,
            },
        },
    });
    const outer_idx_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 9 },
    });
    const outer_access_id = try function.append_expr(allocator, .{
        .ty = inner_arr_ty,
        .category = .value,
        .data = .{ .index = .{ .base = member_id, .index = outer_idx_id } },
    });
    const inner_idx_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 8 },
    });
    const inner_access_id = try function.append_expr(allocator, .{
        .ty = f32_ty,
        .category = .value,
        .data = .{ .index = .{ .base = outer_access_id, .index = inner_idx_id } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const outer_transformed = module.functions.items[0].exprs.items[outer_access_id];
    try testing.expect(outer_transformed.data == .index);
    const outer_min_id = outer_transformed.data.index.index;
    const outer_min_expr = module.functions.items[0].exprs.items[outer_min_id];
    try testing.expectEqualStrings("min", outer_min_expr.data.call.name);
    const outer_max_id = module.functions.items[0].expr_args.items[outer_min_expr.data.call.args.start + 1];
    const outer_max_expr = module.functions.items[0].exprs.items[outer_max_id];
    try testing.expectEqual(@as(u64, 2), outer_max_expr.data.int_lit);

    const inner_transformed = module.functions.items[0].exprs.items[inner_access_id];
    try testing.expect(inner_transformed.data == .index);
    const inner_min_id = inner_transformed.data.index.index;
    const inner_min_expr = module.functions.items[0].exprs.items[inner_min_id];
    try testing.expectEqualStrings("min", inner_min_expr.data.call.name);
    const inner_max_id = module.functions.items[0].expr_args.items[inner_min_expr.data.call.args.start + 1];
    const inner_max_expr = module.functions.items[0].exprs.items[inner_max_id];
    try testing.expectEqual(@as(u64, 3), inner_max_expr.data.int_lit);
}

test "robustness: nested refs to arrays are unwrapped for clamping" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = 5 } });
    const ref_ty = try module.types.intern(.{ .ref = .{
        .elem = arr_ty,
        .addr_space = .function,
        .access = .read_write,
    } });
    const nested_ref_ty = try module.types.intern(.{ .ref = .{
        .elem = ref_ty,
        .addr_space = .function,
        .access = .read_write,
    } });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    try function.locals.append(allocator, .{
        .name = try ir.dup_string(allocator, "data"),
        .ty = nested_ref_ty,
        .mutable = false,
    });

    const base_id = try function.append_expr(allocator, .{
        .ty = nested_ref_ty,
        .category = .value,
        .data = .{ .local_ref = 0 },
    });
    const idx_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 11 },
    });
    const index_id = try function.append_expr(allocator, .{
        .ty = f32_ty,
        .category = .value,
        .data = .{ .index = .{ .base = base_id, .index = idx_id } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    try testing.expect(transformed.data == .index);
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);
    const max_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_arg_id];
    try testing.expectEqual(@as(u64, 4), max_expr.data.int_lit);
}

test "robustness: runtime-sized array uses arrayLength" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = null } });
    const ref_arr_ty = try module.types.intern(.{ .ref = .{ .elem = arr_ty, .addr_space = .storage, .access = .read_write } });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "buf"),
        .ty = ref_arr_ty,
        .class = .var_,
        .addr_space = .storage,
        .access = .read_write,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const base_id = try function.append_expr(allocator, .{ .ty = ref_arr_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 100 } });
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .ref, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    const first_arg = module.functions.items[0].expr_args.items[min_expr.data.call.args.start];
    try testing.expectEqual(idx_id, first_arg);

    const second_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const sub_expr = module.functions.items[0].exprs.items[second_arg_id];
    try testing.expect(sub_expr.data == .binary);
    try testing.expectEqual(ir.BinaryOp.sub, sub_expr.data.binary.op);

    const al_expr = module.functions.items[0].exprs.items[sub_expr.data.binary.lhs];
    try testing.expect(al_expr.data == .call);
    try testing.expectEqualStrings("arrayLength", al_expr.data.call.name);
}

test "robustness: runtime-sized array member uses arrayLength" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = null } });
    const struct_ty = try add_struct_type(&module, allocator, "Wrapper", &.{
        .{ .name = "data", .ty = arr_ty },
    });
    const ref_struct_ty = try module.types.intern(.{ .ref = .{
        .elem = struct_ty,
        .addr_space = .storage,
        .access = .read_write,
    } });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "buf"),
        .ty = ref_struct_ty,
        .class = .var_,
        .addr_space = .storage,
        .access = .read_write,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };

    const root_id = try function.append_expr(allocator, .{
        .ty = ref_struct_ty,
        .category = .ref,
        .data = .{ .global_ref = 0 },
    });
    const member_id = try function.append_expr(allocator, .{
        .ty = arr_ty,
        .category = .ref,
        .data = .{ .member = .{
            .base = root_id,
            .field_name = try ir.dup_string(allocator, "data"),
            .field_index = 0,
        } },
    });
    const idx_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 9 },
    });
    const index_id = try function.append_expr(allocator, .{
        .ty = f32_ty,
        .category = .ref,
        .data = .{ .index = .{
            .base = member_id,
            .index = idx_id,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    const min_id = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[min_id];
    try testing.expectEqualStrings("min", min_expr.data.call.name);
    const second_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const second_arg_expr = module.functions.items[0].exprs.items[second_arg_id];
    try testing.expect(second_arg_expr.data == .binary);
    try testing.expectEqual(ir.BinaryOp.sub, second_arg_expr.data.binary.op);
    const array_length_expr = module.functions.items[0].exprs.items[second_arg_expr.data.binary.lhs];
    try testing.expect(array_length_expr.data == .call);
    try testing.expectEqualStrings("arrayLength", array_length_expr.data.call.name);
    const array_length_arg = module.functions.items[0].expr_args.items[array_length_expr.data.call.args.start];
    try testing.expectEqual(member_id, array_length_arg);
}

test "robustness: non-index expressions are unchanged" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const u32_ty = u32_type(&module);

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    _ = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 42 } });
    _ = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .binary = .{ .op = .add, .lhs = 0, .rhs = 0 } } });

    try module.functions.append(allocator, function);

    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

test "robustness: matrix column index is clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    const vec3_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 3 } });
    const mat_ty = try module.types.intern(.{ .matrix = .{ .elem = f32_ty, .columns = 3, .rows = 3 } });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    try function.locals.append(allocator, .{ .name = try ir.dup_string(allocator, "m"), .ty = mat_ty, .mutable = false });

    const base_id = try function.append_expr(allocator, .{ .ty = mat_ty, .category = .value, .data = .{ .local_ref = 0 } });
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 7 } });
    const index_id = try function.append_expr(allocator, .{ .ty = vec3_ty, .category = .value, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    const max_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_arg_id];
    try testing.expectEqual(@as(u64, 2), max_expr.data.int_lit);
}

// ---- Tests for texture coordinate clamping ----

test "robustness: textureLoad 2D coords are clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec2u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // expr 0: global_ref(0) — the texture
    const tex_id = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    // expr 1: vec2u coords
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .int_lit = 999 } });
    // expr 2: int_lit(0) — mip level
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    // expr 3: textureLoad(tex, coords, level)
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, level_id });
    const call_id = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    // The coordinate argument (index 1 in call args) should now be a clamp() call
    const transformed_call = module.functions.items[0].exprs.items[call_id];
    try testing.expect(transformed_call.data == .call);
    const new_coord_id = module.functions.items[0].expr_args.items[transformed_call.data.call.args.start + 1];
    // The new coord should be different from the original
    try testing.expect(new_coord_id != coord_id);

    const clamp_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expect(clamp_expr.data == .call);
    try testing.expectEqualStrings("clamp", clamp_expr.data.call.name);
    try testing.expectEqual(@as(u32, 3), clamp_expr.data.call.args.len);

    // First arg to clamp is the original coords
    const clamp_first = module.functions.items[0].expr_args.items[clamp_expr.data.call.args.start];
    try testing.expectEqual(coord_id, clamp_first);

    // Third arg (max) should be a sub(vec(textureDimensions), vec(1))
    const clamp_max_id = module.functions.items[0].expr_args.items[clamp_expr.data.call.args.start + 2];
    const max_expr = module.functions.items[0].exprs.items[clamp_max_id];
    try testing.expect(max_expr.data == .binary);
    try testing.expectEqual(ir.BinaryOp.sub, max_expr.data.binary.op);

    // lhs of the sub should be a constructor that casts textureDimensions to the coord type.
    const td_cast_expr = module.functions.items[0].exprs.items[max_expr.data.binary.lhs];
    try testing.expect(td_cast_expr.data == .construct);
    try testing.expectEqual(vec2u_ty, td_cast_expr.ty);
    try testing.expectEqual(@as(u32, 1), td_cast_expr.data.construct.args.len);

    const td_expr = module.functions.items[0].exprs.items[module.functions.items[0].expr_args.items[td_cast_expr.data.construct.args.start]];
    try testing.expect(td_expr.data == .call);
    try testing.expectEqualStrings("textureDimensions", td_expr.data.call.name);
    // textureDimensions should get 2 args for textureLoad (tex + level)
    try testing.expectEqual(@as(u32, 2), td_expr.data.call.args.len);
}

test "robustness: textureStore 2D coords are clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec2u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
    const void_ty = try module.types.intern(.{ .scalar = .void });
    const stor_tex_ty = try module.types.intern(.{ .storage_texture_2d = .{ .format = .rgba8unorm, .access = .write } });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "out_tex"),
        .ty = stor_tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const tex_id = try function.append_expr(allocator, .{ .ty = stor_tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .int_lit = 999 } });
    const value_id = try function.append_expr(allocator, .{ .ty = vec4f_ty, .category = .value, .data = .{ .float_lit = 1.0 } });
    // textureStore(tex, coords, value)
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, value_id });
    const call_id = try function.append_expr(allocator, .{
        .ty = void_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureStore"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed_call = module.functions.items[0].exprs.items[call_id];
    const new_coord_id = module.functions.items[0].expr_args.items[transformed_call.data.call.args.start + 1];
    try testing.expect(new_coord_id != coord_id);

    const clamp_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expect(clamp_expr.data == .call);
    try testing.expectEqualStrings("clamp", clamp_expr.data.call.name);

    // For textureStore, textureDimensions should get 1 arg (no level), then be cast to coord type.
    const clamp_max_id = module.functions.items[0].expr_args.items[clamp_expr.data.call.args.start + 2];
    const max_expr = module.functions.items[0].exprs.items[clamp_max_id];
    const td_cast_expr = module.functions.items[0].exprs.items[max_expr.data.binary.lhs];
    try testing.expect(td_cast_expr.data == .construct);
    try testing.expectEqual(vec2u_ty, td_cast_expr.ty);
    const td_expr = module.functions.items[0].exprs.items[module.functions.items[0].expr_args.items[td_cast_expr.data.construct.args.start]];
    try testing.expectEqualStrings("textureDimensions", td_expr.data.call.name);
    try testing.expectEqual(@as(u32, 1), td_expr.data.call.args.len);
}

test "robustness: textureLoad i32 coords remain signed" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const i32_ty = try module.types.intern(.{ .scalar = .i32 });
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec2i_ty = try module.types.intern(.{ .vector = .{ .elem = i32_ty, .len = 2 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const tex_id = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2i_ty, .category = .value, .data = .{ .int_lit = 7 } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, level_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const new_coord_id = module.functions.items[0].expr_args.items[call_args.start + 1];
    const clamp_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expectEqual(vec2i_ty, clamp_expr.ty);

    const clamp_max_id = module.functions.items[0].expr_args.items[clamp_expr.data.call.args.start + 2];
    const max_expr = module.functions.items[0].exprs.items[clamp_max_id];
    const td_cast_expr = module.functions.items[0].exprs.items[max_expr.data.binary.lhs];
    try testing.expect(td_cast_expr.data == .construct);
    try testing.expectEqual(vec2i_ty, td_cast_expr.ty);
}

test "robustness: guarded gid textureLoad skips injected clamp" {
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
        .name = try ir.dup_string(allocator, "limit"),
        .ty = u32_ty,
        .class = .const_,
        .initializer = .{ .int = 64 },
    });
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

    const gid_param_x = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_x, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const gid_load_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_x } });
    const limit_ref_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    const limit_load_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = limit_ref_x } });
    const guard_x = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .greater_equal, .lhs = gid_load_x, .rhs = limit_load_x } } });

    const gid_param_y = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_y, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });
    const gid_load_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_y } });
    const limit_ref_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    const limit_load_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = limit_ref_y } });
    const guard_y = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .greater_equal, .lhs = gid_load_y, .rhs = limit_load_y } } });
    const guard_or = try function.append_expr(allocator, .{ .ty = bool_ty, .category = .value, .data = .{ .binary = .{ .op = .logical_or, .lhs = guard_x, .rhs = guard_y } } });

    const return_stmt = try function.append_stmt(allocator, .{ .return_ = null });
    const then_children = try function.append_stmt_children(allocator, &.{return_stmt});
    const then_block = try function.append_stmt(allocator, .{ .block = then_children });
    const if_stmt = try function.append_stmt(allocator, .{ .if_ = .{ .cond = guard_or, .then_block = then_block, .else_block = null } });

    const tex_ref = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 1 } });
    const gid_param_coord_x = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_coord_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_coord_x, .field_name = try ir.dup_string(allocator, "x"), .field_index = 0 } } });
    const gid_load_coord_x = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_coord_x } });
    const gid_param_coord_y = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .ref, .data = .{ .param_ref = 0 } });
    const gid_member_coord_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .ref, .data = .{ .member = .{ .base = gid_param_coord_y, .field_name = try ir.dup_string(allocator, "y"), .field_index = 1 } } });
    const gid_load_coord_y = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .load = gid_member_coord_y } });
    const coord_args = try function.append_expr_args(allocator, &.{ gid_load_coord_x, gid_load_coord_y });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .construct = .{ .ty = vec2u_ty, .args = coord_args } } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
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

    const root_children = try function.append_stmt_children(allocator, &.{ if_stmt, expr_stmt });
    function.root_stmt = try function.append_stmt(allocator, .{ .block = root_children });

    try module.functions.append(allocator, function);
    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    const transformed_call = module.functions.items[0].exprs.items[call_id];
    const new_coord_id = module.functions.items[0].expr_args.items[transformed_call.data.call.args.start + 1];
    try testing.expectEqual(coord_id, new_coord_id);
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

test "robustness: textureLoad 3D coords produce vec3 clamp" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec3u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 3 } });
    const tex_3d_ty = try module.types.intern(.{ .texture_3d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "vol"),
        .ty = tex_3d_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const tex_id = try function.append_expr(allocator, .{ .ty = tex_3d_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec3u_ty, .category = .value, .data = .{ .int_lit = 999 } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, level_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    // The clamp result type should be vec3<u32>
    const new_coord_id = module.functions.items[0].expr_args.items[call_args.start + 1];
    const clamp_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expectEqualStrings("clamp", clamp_expr.data.call.name);

    // Verify the type of the clamped coord is vec3<u32>
    const clamp_ty = module.types.get(clamp_expr.ty);
    try testing.expect(clamp_ty == .vector);
    try testing.expectEqual(@as(u8, 3), clamp_ty.vector.len);
}

test "robustness: textureSample float coords are not clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec2f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 2 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });
    const sampler_ty = try module.types.intern(.{ .sampler = {} });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });
    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "samp"),
        .ty = sampler_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 1 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // textureSample(tex, samp, uv) — float coords, should not be clamped
    const tex_id = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const samp_id = try function.append_expr(allocator, .{ .ty = sampler_ty, .category = .value, .data = .{ .global_ref = 1 } });
    const uv_id = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const sample_args = try function.append_expr_args(allocator, &.{ tex_id, samp_id, uv_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSample"),
            .kind = .builtin,
            .args = sample_args,
        } },
    });

    // textureSampleLevel(tex, samp, uv, level) — float coords, should not be clamped
    const tex_id2 = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const samp_id2 = try function.append_expr(allocator, .{ .ty = sampler_ty, .category = .value, .data = .{ .global_ref = 1 } });
    const uv_id2 = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const level_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .value, .data = .{ .float_lit = 0.0 } });
    const sample_level_args = try function.append_expr_args(allocator, &.{ tex_id2, samp_id2, uv_id2, level_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSampleLevel"),
            .kind = .builtin,
            .args = sample_level_args,
        } },
    });

    // textureSampleOffset(tex, samp, uv, offset) — float coords + const int offset
    const tex_id3 = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const samp_id3 = try function.append_expr(allocator, .{ .ty = sampler_ty, .category = .value, .data = .{ .global_ref = 1 } });
    const uv_id3 = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const i32_ty = try module.types.intern(.{ .scalar = .i32 });
    const vec2i_ty = try module.types.intern(.{ .vector = .{ .elem = i32_ty, .len = 2 } });
    const offset_id = try function.append_expr(allocator, .{ .ty = vec2i_ty, .category = .value, .data = .{ .int_lit = 1 } });
    const sample_offset_args = try function.append_expr_args(allocator, &.{ tex_id3, samp_id3, uv_id3, offset_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSampleOffset"),
            .kind = .builtin,
            .args = sample_offset_args,
        } },
    });

    try module.functions.append(allocator, function);

    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    // No new expressions should have been appended — none of these use integer coords.
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

test "robustness: non-texture builtins are not clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const u32_ty = u32_type(&module);

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // min(a, b) — should not be modified
    const a_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 1 } });
    const b_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 2 } });
    const min_args = try function.append_expr_args(allocator, &.{ a_id, b_id });
    _ = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "min"),
            .kind = .builtin,
            .args = min_args,
        } },
    });

    try module.functions.append(allocator, function);

    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    // No new expressions should have been appended.
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

// ---- Tests for broader base-expression handling ----

test "robustness: runtime-sized array via load base uses arrayLength" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = null } });
    const ref_arr_ty = try module.types.intern(.{ .ref = .{ .elem = arr_ty, .addr_space = .storage, .access = .read_write } });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "buf"),
        .ty = ref_arr_ty,
        .class = .var_,
        .addr_space = .storage,
        .access = .read_write,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // Simulate a load of the array reference (pointer deref pattern)
    const global_id = try function.append_expr(allocator, .{ .ty = ref_arr_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    const load_id = try function.append_expr(allocator, .{ .ty = arr_ty, .category = .value, .data = .{ .load = global_id } });
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 50 } });
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .ref, .data = .{ .index = .{ .base = load_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    // Should have injected arrayLength-based clamping (load is now accepted)
    const transformed = module.functions.items[0].exprs.items[index_id];
    try testing.expect(transformed.data == .index);
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);
}

test "robustness: workgroup array index is clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    // var<workgroup> shared: array<f32, 256>
    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = 256 } });
    const ref_arr_ty = try module.types.intern(.{ .ref = .{
        .elem = arr_ty,
        .addr_space = .workgroup,
        .access = .read_write,
    } });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "shared"),
        .ty = ref_arr_ty,
        .class = .var_,
        .addr_space = .workgroup,
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const base_id = try function.append_expr(allocator, .{ .ty = ref_arr_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 300 } });
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .ref, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    try testing.expect(transformed.data == .index);
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    // Max should be 255
    const max_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_arg_id];
    try testing.expectEqual(@as(u64, 255), max_expr.data.int_lit);
}

test "robustness: storage buffer sized array index is clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    // @group(0) @binding(0) var<storage> buf: array<f32, 1024>
    const arr_ty = try module.types.intern(.{ .array = .{ .elem = f32_ty, .len = 1024 } });
    const ref_arr_ty = try module.types.intern(.{ .ref = .{
        .elem = arr_ty,
        .addr_space = .storage,
        .access = .read,
    } });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "buf"),
        .ty = ref_arr_ty,
        .class = .var_,
        .addr_space = .storage,
        .access = .read,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const base_id = try function.append_expr(allocator, .{ .ty = ref_arr_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 2000 } });
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .ref, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    const transformed = module.functions.items[0].exprs.items[index_id];
    try testing.expect(transformed.data == .index);
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    // Max should be 1023
    const max_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_arg_id];
    try testing.expectEqual(@as(u64, 1023), max_expr.data.int_lit);
}

// ---- texture_1d coordinate clamping ----

test "robustness: textureLoad 1D coord is clamped with min" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const tex_1d_ty = try module.types.intern(.{ .texture_1d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex1d"),
        .ty = tex_1d_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const tex_id = try function.append_expr(allocator, .{ .ty = tex_1d_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const coord_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 999 } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, level_id });
    const call_id = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    // 1D textures use scalar min(), not vector clamp()
    const new_coord_id = module.functions.items[0].expr_args.items[call_args.start + 1];
    try testing.expect(new_coord_id != coord_id);

    const min_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expect(min_expr.data == .call);
    try testing.expectEqualStrings("min", min_expr.data.call.name);
    try testing.expectEqual(@as(u32, 2), min_expr.data.call.args.len);

    // First arg to min is the original coord
    const min_first = module.functions.items[0].expr_args.items[min_expr.data.call.args.start];
    try testing.expectEqual(coord_id, min_first);

    // Second arg is textureDimensions(tex, level) - 1
    const max_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_id];
    try testing.expect(max_expr.data == .binary);
    try testing.expectEqual(ir.BinaryOp.sub, max_expr.data.binary.op);

    // lhs of the sub should be textureDimensions call with 2 args (tex + level)
    const td_expr = module.functions.items[0].exprs.items[max_expr.data.binary.lhs];
    try testing.expect(td_expr.data == .call);
    try testing.expectEqualStrings("textureDimensions", td_expr.data.call.name);
    try testing.expectEqual(@as(u32, 2), td_expr.data.call.args.len);

    // Verify the call expression is unchanged
    const transformed_call = module.functions.items[0].exprs.items[call_id];
    try testing.expect(transformed_call.data == .call);
    try testing.expectEqualStrings("textureLoad", transformed_call.data.call.name);
}

test "robustness: textureLoad 1D without level arg uses single-arg textureDimensions" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    // texture_multisampled_2d has no level, but use texture_1d with only 2 args
    // to test the textureStore path (no level param)
    const stor_tex_ty = try module.types.intern(.{ .storage_texture_2d = .{ .format = .rgba8unorm, .access = .write } });
    const vec2u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
    const void_ty = try module.types.intern(.{ .scalar = .void });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "out_tex"),
        .ty = stor_tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 1 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    const tex_id = try function.append_expr(allocator, .{ .ty = stor_tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const coord_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .int_lit = 42 } });
    const value_id = try function.append_expr(allocator, .{ .ty = vec4f_ty, .category = .value, .data = .{ .float_lit = 1.0 } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, value_id });
    _ = try function.append_expr(allocator, .{
        .ty = void_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureStore"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module, .{});

    // textureStore has no level — textureDimensions should get 1 arg
    const new_coord_id = module.functions.items[0].expr_args.items[call_args.start + 1];
    const clamp_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expectEqualStrings("clamp", clamp_expr.data.call.name);

    const clamp_max_id = module.functions.items[0].expr_args.items[clamp_expr.data.call.args.start + 2];
    const max_expr = module.functions.items[0].exprs.items[clamp_max_id];
    const td_cast_expr = module.functions.items[0].exprs.items[max_expr.data.binary.lhs];
    const td_expr = module.functions.items[0].exprs.items[module.functions.items[0].expr_args.items[td_cast_expr.data.construct.args.start]];
    try testing.expectEqualStrings("textureDimensions", td_expr.data.call.name);
    try testing.expectEqual(@as(u32, 1), td_expr.data.call.args.len);
}

// ---- textureSampleLevel integer coordinate edge cases ----

test "robustness: textureSampleLevel with integer-typed coords is not clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec2u_ty = try module.types.intern(.{ .vector = .{ .elem = u32_ty, .len = 2 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });
    const sampler_ty = try module.types.intern(.{ .sampler = {} });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });
    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "samp"),
        .ty = sampler_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 1 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // textureSampleLevel with integer coords (malformed but possible in IR)
    const tex_id = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const samp_id = try function.append_expr(allocator, .{ .ty = sampler_ty, .category = .value, .data = .{ .global_ref = 1 } });
    const int_uv_id = try function.append_expr(allocator, .{ .ty = vec2u_ty, .category = .value, .data = .{ .int_lit = 10 } });
    const level_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .value, .data = .{ .float_lit = 0.0 } });
    const args = try function.append_expr_args(allocator, &.{ tex_id, samp_id, int_uv_id, level_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSampleLevel"),
            .kind = .builtin,
            .args = args,
        } },
    });

    try module.functions.append(allocator, function);
    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    // textureSampleLevel is not textureLoad/textureStore — no clamping regardless of coord type
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

test "robustness: textureSampleGrad and textureSampleCompare are not clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const vec2f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 2 } });
    const tex_ty = try module.types.intern(.{ .texture_2d = f32_ty });
    const sampler_ty = try module.types.intern(.{ .sampler = {} });
    const depth_tex_ty = try module.types.intern(.{ .texture_depth_2d = {} });
    const sampler_cmp_ty = try module.types.intern(.{ .sampler_comparison = {} });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex"),
        .ty = tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 0 },
    });
    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "samp"),
        .ty = sampler_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 1 },
    });
    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "depth_tex"),
        .ty = depth_tex_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 2 },
    });
    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "samp_cmp"),
        .ty = sampler_cmp_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 3 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // textureSampleGrad(tex, samp, uv, ddx, ddy)
    const tex_id = try function.append_expr(allocator, .{ .ty = tex_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const samp_id = try function.append_expr(allocator, .{ .ty = sampler_ty, .category = .value, .data = .{ .global_ref = 1 } });
    const uv_id = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const ddx_id = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.01 } });
    const ddy_id = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.01 } });
    const grad_args = try function.append_expr_args(allocator, &.{ tex_id, samp_id, uv_id, ddx_id, ddy_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSampleGrad"),
            .kind = .builtin,
            .args = grad_args,
        } },
    });

    // textureSampleCompare(depth_tex, samp_cmp, uv, ref_value)
    const dtex_id = try function.append_expr(allocator, .{ .ty = depth_tex_ty, .category = .value, .data = .{ .global_ref = 2 } });
    const scmp_id = try function.append_expr(allocator, .{ .ty = sampler_cmp_ty, .category = .value, .data = .{ .global_ref = 3 } });
    const uv_id2 = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const ref_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const cmp_args = try function.append_expr_args(allocator, &.{ dtex_id, scmp_id, uv_id2, ref_id });
    _ = try function.append_expr(allocator, .{
        .ty = f32_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSampleCompare"),
            .kind = .builtin,
            .args = cmp_args,
        } },
    });

    // textureSampleCompareLevel(depth_tex, samp_cmp, uv, ref_value)
    const dtex_id2 = try function.append_expr(allocator, .{ .ty = depth_tex_ty, .category = .value, .data = .{ .global_ref = 2 } });
    const scmp_id2 = try function.append_expr(allocator, .{ .ty = sampler_cmp_ty, .category = .value, .data = .{ .global_ref = 3 } });
    const uv_id3 = try function.append_expr(allocator, .{ .ty = vec2f_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const ref_id2 = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .value, .data = .{ .float_lit = 0.5 } });
    const cmp_lvl_args = try function.append_expr_args(allocator, &.{ dtex_id2, scmp_id2, uv_id3, ref_id2 });
    _ = try function.append_expr(allocator, .{
        .ty = f32_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureSampleCompareLevel"),
            .kind = .builtin,
            .args = cmp_lvl_args,
        } },
    });

    try module.functions.append(allocator, function);
    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module, .{});

    // None of these should be clamped — all use float coordinates
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

// ---- Dispatch-fit texture precondition enforcement ----

test "robustness: texture_1d resolve_texture_binding matches" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);
    const vec4f_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 4 } });
    const tex_1d_ty = try module.types.intern(.{ .texture_1d = f32_ty });

    try module.globals.append(allocator, .{
        .name = try ir.dup_string(allocator, "tex1d"),
        .ty = tex_1d_ty,
        .class = .var_,
        .addr_space = .handle,
        .binding = .{ .group = 0, .binding = 5 },
    });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    // Build textureLoad(tex1d, coord, 0) to verify the 1D scalar clamp path
    // works end-to-end and resolve_texture_binding accepts texture_1d
    const tex_id = try function.append_expr(allocator, .{ .ty = tex_1d_ty, .category = .value, .data = .{ .global_ref = 0 } });
    const coord_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 100 } });
    const level_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 0 } });
    const call_args = try function.append_expr_args(allocator, &.{ tex_id, coord_id, level_id });
    _ = try function.append_expr(allocator, .{
        .ty = vec4f_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "textureLoad"),
            .kind = .builtin,
            .args = call_args,
        } },
    });

    try module.functions.append(allocator, function);

    // With dispatch-fit enabled, the 1D texture clamp should still be
    // injected (no lean proof available in test builds), proving
    // resolve_texture_binding accepts texture_1d and the scalar path works.
    try apply(allocator, &module, .{ .elide_proven_texture_bounds = true });

    const new_coord_id = module.functions.items[0].expr_args.items[call_args.start + 1];
    try testing.expect(new_coord_id != coord_id);
    const min_expr = module.functions.items[0].exprs.items[new_coord_id];
    try testing.expectEqualStrings("min", min_expr.data.call.name);
}
