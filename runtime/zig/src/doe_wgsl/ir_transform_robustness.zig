// ir_transform_robustness.zig — WebGPU robustness injection IR transform pass.
//
// Clamps all array, vector, and matrix index operations to prevent out-of-bounds
// access, as required by the WebGPU specification for shader robustness.
//
// Sized containers:        index = min(index, length - 1)
// Runtime-sized arrays:    index = min(index, arrayLength(&buf) - 1)
//
// This is the first IR transform pass in the Doe shader compiler. It runs after
// IR building and validation, before emission to any backend (MSL, HLSL, SPIR-V).

const std = @import("std");
const ir = @import("ir.zig");

pub const TransformError = error{
    OutOfMemory,
};

/// Apply robustness clamping to all index expressions in the module.
pub fn apply(allocator: std.mem.Allocator, module: *ir.Module) TransformError!void {
    for (module.functions.items) |*function| {
        try transform_function(allocator, module, function);
    }
}

fn transform_function(allocator: std.mem.Allocator, module: *ir.Module, function: *ir.Function) TransformError!void {
    // Snapshot the expression count — we only transform pre-existing expressions.
    // New expressions appended by the transform are helper nodes and need not be
    // re-examined (they cannot themselves be index operations).
    const expr_count: u32 = @intCast(function.exprs.items.len);
    var i: u32 = 0;
    while (i < expr_count) : (i += 1) {
        const expr_node = function.exprs.items[i];
        switch (expr_node.data) {
            .index => |index_data| {
                const base_ty = resolve_indexable_type(&module.types, function.exprs.items[index_data.base].ty);
                switch (module.types.get(base_ty)) {
                    .array => |arr| {
                        if (arr.len) |len| {
                            if (len > 0) try clamp_sized(allocator, module, function, i, len);
                        } else {
                            try clamp_runtime_sized(allocator, module, function, i);
                        }
                    },
                    .vector => |vec| {
                        if (vec.len > 0) try clamp_sized(allocator, module, function, i, vec.len);
                    },
                    .matrix => |mat| {
                        if (mat.columns > 0) try clamp_sized(allocator, module, function, i, mat.columns);
                    },
                    else => {},
                }
            },
            else => {},
        }
    }
}

/// Resolve through ref types to get the indexable element type.
fn resolve_indexable_type(types: *const ir.TypeStore, ty: ir.TypeId) ir.TypeId {
    var current = ty;
    while (true) {
        switch (types.get(current)) {
            .ref => |ref_ty| current = ref_ty.elem,
            else => return current,
        }
    }
}

/// Intern the u32 scalar type, creating it if it does not already exist.
fn ensure_u32_type(module: *ir.Module) TransformError!ir.TypeId {
    return module.types.intern(.{ .scalar = .u32 }) catch return error.OutOfMemory;
}

/// Clamp index for a sized container: min(index, length - 1)
fn clamp_sized(
    allocator: std.mem.Allocator,
    module: *ir.Module,
    function: *ir.Function,
    expr_idx: u32,
    length: u32,
) TransformError!void {
    const u32_ty = try ensure_u32_type(module);
    const index_data = function.exprs.items[expr_idx].data.index;
    const original_index = index_data.index;

    // int_lit(length - 1)
    const max_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = length - 1 },
    });

    // min(index, length - 1)
    const args = try function.append_expr_args(allocator, &.{ original_index, max_id });
    const min_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "min"),
            .kind = .builtin,
            .args = args,
        } },
    });

    // Replace the original index with the clamped version.
    function.exprs.items[expr_idx].data = .{ .index = .{
        .base = index_data.base,
        .index = min_id,
    } };
}

/// Clamp index for a runtime-sized array: min(index, arrayLength(&buf) - 1)
///
/// Applies to direct globals and member-shaped bases rooted in the IR. The
/// transform keeps the base expression intact and relies on backend emission to
/// lower `arrayLength` for that base shape.
fn clamp_runtime_sized(
    allocator: std.mem.Allocator,
    module: *ir.Module,
    function: *ir.Function,
    expr_idx: u32,
) TransformError!void {
    const index_data = function.exprs.items[expr_idx].data.index;

    switch (function.exprs.items[index_data.base].data) {
        .global_ref, .member => {},
        else => return,
    }

    const u32_ty = try ensure_u32_type(module);
    const original_index = index_data.index;
    const base_ref = index_data.base;

    // arrayLength(&base)
    const al_args = try function.append_expr_args(allocator, &.{base_ref});
    const array_length_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "arrayLength"),
            .kind = .builtin,
            .args = al_args,
        } },
    });

    // int_lit(1)
    const one_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 1 },
    });

    // arrayLength(&base) - 1
    const sub_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .binary = .{
            .op = .sub,
            .lhs = array_length_id,
            .rhs = one_id,
        } },
    });

    // min(index, arrayLength(&base) - 1)
    const min_args = try function.append_expr_args(allocator, &.{ original_index, sub_id });
    const min_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .call = .{
            .name = try ir.dup_string(allocator, "min"),
            .kind = .builtin,
            .args = min_args,
        } },
    });

    // Replace the original index with the clamped version.
    function.exprs.items[expr_idx].data = .{ .index = .{
        .base = base_ref,
        .index = min_id,
    } };
}

// ============================================================
// Tests
// ============================================================

const testing = std.testing;

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

    try apply(allocator, &module);

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
    try apply(allocator, &module);

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

    // expr 0: local_ref(0) — the struct wrapper
    const base_id = try function.append_expr(allocator, .{
        .ty = struct_ty,
        .category = .value,
        .data = .{ .local_ref = 0 },
    });
    // expr 1: member { base, data } — array<array<f32, 4>, 3>
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
    // expr 2: int_lit(9) — out of bounds for the outer array
    const outer_idx_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 9 },
    });
    // expr 3: index { member, outer_idx } — inner array< f32, 4 >
    const outer_access_id = try function.append_expr(allocator, .{
        .ty = inner_arr_ty,
        .category = .value,
        .data = .{ .index = .{ .base = member_id, .index = outer_idx_id } },
    });
    // expr 4: int_lit(8) — out of bounds for the inner array
    const inner_idx_id = try function.append_expr(allocator, .{
        .ty = u32_ty,
        .category = .value,
        .data = .{ .int_lit = 8 },
    });
    // expr 5: index { outer_access, inner_idx } — final f32 element
    const inner_access_id = try function.append_expr(allocator, .{
        .ty = f32_ty,
        .category = .value,
        .data = .{ .index = .{ .base = outer_access_id, .index = inner_idx_id } },
    });

    try module.functions.append(allocator, function);
    try apply(allocator, &module);

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

    // array<f32, 5> wrapped in two ref layers.
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
    try apply(allocator, &module);

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

    // array<f32> (runtime-sized)
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

    // expr 0: global_ref(0) — the runtime-sized array
    const base_id = try function.append_expr(allocator, .{ .ty = ref_arr_ty, .category = .ref, .data = .{ .global_ref = 0 } });
    // expr 1: int_lit(100)
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 100 } });
    // expr 2: index { base, index }
    const index_id = try function.append_expr(allocator, .{ .ty = f32_ty, .category = .ref, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module);

    const transformed = module.functions.items[0].exprs.items[index_id];
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    // First arg to min should be the original index (expr 1)
    const first_arg = module.functions.items[0].expr_args.items[min_expr.data.call.args.start];
    try testing.expectEqual(idx_id, first_arg);

    // Second arg should be a binary sub (arrayLength - 1)
    const second_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const sub_expr = module.functions.items[0].exprs.items[second_arg_id];
    try testing.expect(sub_expr.data == .binary);
    try testing.expectEqual(ir.BinaryOp.sub, sub_expr.data.binary.op);

    // The lhs of the sub should be an arrayLength call
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
    try apply(allocator, &module);

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

    // expr 0: int_lit(42) — no index, should not be modified
    _ = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 42 } });
    // expr 1: binary add
    _ = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .binary = .{ .op = .add, .lhs = 0, .rhs = 0 } } });

    try module.functions.append(allocator, function);

    const original_count = module.functions.items[0].exprs.items.len;
    try apply(allocator, &module);

    // No new expressions should have been appended.
    try testing.expectEqual(original_count, module.functions.items[0].exprs.items.len);
}

test "robustness: matrix column index is clamped" {
    const allocator = testing.allocator;
    var module = try make_test_module(allocator);
    defer module.deinit();

    const f32_ty = f32_type(&module);
    const u32_ty = u32_type(&module);

    // mat3x3<f32>
    const vec3_ty = try module.types.intern(.{ .vector = .{ .elem = f32_ty, .len = 3 } });
    const mat_ty = try module.types.intern(.{ .matrix = .{ .elem = f32_ty, .columns = 3, .rows = 3 } });

    var function = ir.Function{ .name = try ir.dup_string(allocator, "main"), .return_type = ir.INVALID_TYPE };
    errdefer function.deinit(allocator);

    try function.locals.append(allocator, .{ .name = try ir.dup_string(allocator, "m"), .ty = mat_ty, .mutable = false });

    const base_id = try function.append_expr(allocator, .{ .ty = mat_ty, .category = .value, .data = .{ .local_ref = 0 } });
    const idx_id = try function.append_expr(allocator, .{ .ty = u32_ty, .category = .value, .data = .{ .int_lit = 7 } });
    const index_id = try function.append_expr(allocator, .{ .ty = vec3_ty, .category = .value, .data = .{ .index = .{ .base = base_id, .index = idx_id } } });

    try module.functions.append(allocator, function);
    try apply(allocator, &module);

    const transformed = module.functions.items[0].exprs.items[index_id];
    const new_index = transformed.data.index.index;
    const min_expr = module.functions.items[0].exprs.items[new_index];
    try testing.expectEqualStrings("min", min_expr.data.call.name);

    // Max should be columns - 1 = 2
    const max_arg_id = module.functions.items[0].expr_args.items[min_expr.data.call.args.start + 1];
    const max_expr = module.functions.items[0].exprs.items[max_arg_id];
    try testing.expectEqual(@as(u64, 2), max_expr.data.int_lit);
}
