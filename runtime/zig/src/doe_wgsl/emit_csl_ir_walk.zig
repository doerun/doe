// emit_csl_ir_walk.zig — Shared IR walker for all CSL pattern emitters.
//
// Extracts the duplicated statement/expression walker from emit_csl_elementwise
// and emit_csl_reduction into a single parameterized module. Each consumer
// instantiates Emit(config) with the appropriate settings:
//   - skip_barriers: elide workgroupBarrier/storageBarrier (reduction mode)
//   - runtime_array_size: "chunk_size" (element-wise) or "hidden_size" (reduction)

const std = @import("std");
const ir = @import("ir.zig");
const spec = @import("csl_spec.zig");
const maps = @import("emit_csl_maps.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
    UnsupportedBuiltin,
    UnsupportedConstruct,
};

pub const WalkConfig = struct {
    skip_barriers: bool = false,
    runtime_array_size: []const u8 = "chunk_size",
};

// ---------------------------------------------------------------------------
// Config-independent utilities
// ---------------------------------------------------------------------------

pub fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}

pub fn writeIndent(buf: []u8, pos: *usize, level: usize) EmitError!void {
    var i: usize = 0;
    while (i < level) : (i += 1) try write(buf, pos, "    ");
}

pub fn writeInt(buf: []u8, pos: *usize, value: anytype) EmitError!void {
    var tmp: [20]u8 = undefined;
    const slice = std.fmt.bufPrint(&tmp, "{d}", .{value}) catch return error.OutputTooLarge;
    try write(buf, pos, slice);
}

pub fn isBarrierName(name: []const u8) bool {
    return std.mem.eql(u8, name, "workgroupBarrier") or
        std.mem.eql(u8, name, "storageBarrier") or
        std.mem.eql(u8, name, "textureBarrier");
}

pub fn isBarrierExpr(function: *const ir.Function, expr_id: ir.ExprId) bool {
    if (expr_id >= function.exprs.items.len) return false;
    return switch (function.exprs.items[expr_id].data) {
        .call => |c| c.kind == .builtin and isBarrierName(c.name),
        else => false,
    };
}

pub fn isBarrierStmt(function: *const ir.Function, stmt_id: ir.StmtId) bool {
    if (stmt_id >= function.stmts.items.len) return false;
    return switch (function.stmts.items[stmt_id]) {
        .expr => |eid| isBarrierExpr(function, eid),
        else => false,
    };
}

pub fn isUniformGlobalBase(module: *const ir.Module, function: *const ir.Function, expr_id: ir.ExprId) bool {
    if (expr_id >= function.exprs.items.len) return false;
    return switch (function.exprs.items[expr_id].data) {
        .global_ref => |idx| blk: {
            if (idx >= module.globals.items.len) break :blk false;
            break :blk (module.globals.items[idx].addr_space orelse break :blk false) == .uniform;
        },
        .load => |inner| isUniformGlobalBase(module, function, inner),
        else => false,
    };
}

pub fn arrayElemType(module: *const ir.Module, ty: ir.TypeId) ir.TypeId {
    return switch (module.types.get(ty)) {
        .array => |arr| arr.elem,
        else => ty,
    };
}

// ---------------------------------------------------------------------------
// Config-dependent walker
// ---------------------------------------------------------------------------

pub fn Emit(comptime cfg: WalkConfig) type {
    return struct {
        pub fn stmt(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function, stmt_id: ir.StmtId, indent: usize) EmitError!void {
            if (stmt_id >= function.stmts.items.len) return;
            switch (function.stmts.items[stmt_id]) {
                .block => |range| {
                    var i: u32 = 0;
                    while (i < range.len) : (i += 1) {
                        const cid = function.stmt_children.items[range.start + i];
                        if (cfg.skip_barriers and isBarrierStmt(function, cid)) continue;
                        try stmt(buf, pos, module, function, cid, indent);
                    }
                },
                .local_decl => |decl| {
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, if (decl.is_const) "const " else "var ");
                    const local = function.locals.items[decl.local];
                    try write(buf, pos, local.name);
                    try write(buf, pos, ": ");
                    try writeType(buf, pos, module, local.ty);
                    if (decl.initializer) |init_expr| {
                        try write(buf, pos, " = ");
                        try expr(buf, pos, module, function, init_expr);
                    }
                    try write(buf, pos, ";\n");
                },
                .assign => |assign| {
                    try writeIndent(buf, pos, indent);
                    try expr(buf, pos, module, function, assign.lhs);
                    try write(buf, pos, " ");
                    try write(buf, pos, maps.assignOpText(assign.op));
                    try write(buf, pos, " ");
                    try expr(buf, pos, module, function, assign.rhs);
                    try write(buf, pos, ";\n");
                },
                .return_ => |maybe_expr| {
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "return");
                    if (maybe_expr) |eid| {
                        try write(buf, pos, " ");
                        try expr(buf, pos, module, function, eid);
                    }
                    try write(buf, pos, ";\n");
                },
                .if_ => |if_stmt| {
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "if (");
                    try expr(buf, pos, module, function, if_stmt.cond);
                    try write(buf, pos, ") {\n");
                    try stmt(buf, pos, module, function, if_stmt.then_block, indent + 1);
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "}");
                    if (if_stmt.else_block) |else_id| {
                        try write(buf, pos, " else {\n");
                        try stmt(buf, pos, module, function, else_id, indent + 1);
                        try writeIndent(buf, pos, indent);
                        try write(buf, pos, "}");
                    }
                    try write(buf, pos, "\n");
                },
                .loop_ => |loop_stmt| {
                    try writeIndent(buf, pos, indent);
                    if (loop_stmt.init) |init_id| try stmt(buf, pos, module, function, init_id, indent);
                    try write(buf, pos, "while (");
                    if (loop_stmt.cond) |cond| {
                        try expr(buf, pos, module, function, cond);
                    } else {
                        try write(buf, pos, "true");
                    }
                    try write(buf, pos, ") ");
                    if (loop_stmt.continuing) |cont_id| {
                        try write(buf, pos, ": (");
                        try stmt(buf, pos, module, function, cont_id, 0);
                        try write(buf, pos, ") ");
                    }
                    try write(buf, pos, "{\n");
                    try stmt(buf, pos, module, function, loop_stmt.body, indent + 1);
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "}\n");
                },
                .expr => |eid| {
                    if (cfg.skip_barriers and isBarrierExpr(function, eid)) return;
                    try writeIndent(buf, pos, indent);
                    try expr(buf, pos, module, function, eid);
                    try write(buf, pos, ";\n");
                },
                .break_ => {
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "break;\n");
                },
                .continue_ => {
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "continue;\n");
                },
                .switch_ => {
                    try writeIndent(buf, pos, indent);
                    try write(buf, pos, "// switch (unsupported)\n");
                },
                .discard_ => {},
            }
        }

        pub fn expr(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function, expr_id: ir.ExprId) EmitError!void {
            if (expr_id >= function.exprs.items.len) return;
            switch (function.exprs.items[expr_id].data) {
                .bool_lit => |v| try write(buf, pos, if (v) "true" else "false"),
                .int_lit => |v| {
                    var t: [20]u8 = undefined;
                    try write(buf, pos, std.fmt.bufPrint(&t, "{d}", .{v}) catch return error.OutputTooLarge);
                },
                .float_lit => |v| {
                    var t: [32]u8 = undefined;
                    const s = std.fmt.bufPrint(&t, "{d}", .{v}) catch return error.OutputTooLarge;
                    try write(buf, pos, s);
                    // Ensure CSL sees a `comptime_float`, not a `comptime_int`,
                    // when the value has no fractional part. Zig's `{d}` format
                    // drops trailing zeros ("2.0" → "2"), and cslc rejects
                    // `f32_var * 2` with "expected type 'f32', got: 'comptime_int'".
                    if (std.mem.indexOfAny(u8, s, ".eE") == null) {
                        try write(buf, pos, ".0");
                    }
                },
                .param_ref => |idx| {
                    if (idx < function.params.items.len) try write(buf, pos, function.params.items[idx].name);
                },
                .local_ref => |idx| {
                    if (idx < function.locals.items.len) try write(buf, pos, function.locals.items[idx].name);
                },
                .global_ref => |idx| {
                    if (idx < module.globals.items.len) try write(buf, pos, module.globals.items[idx].name);
                },
                .load => |inner| try expr(buf, pos, module, function, inner),
                .unary => |u| {
                    try write(buf, pos, maps.unaryOpText(u.op));
                    try write(buf, pos, "(");
                    try expr(buf, pos, module, function, u.operand);
                    try write(buf, pos, ")");
                },
                .binary => |b| {
                    try write(buf, pos, "(");
                    try expr(buf, pos, module, function, b.lhs);
                    try write(buf, pos, " ");
                    try write(buf, pos, maps.binaryOpText(b.op));
                    try write(buf, pos, " ");
                    try expr(buf, pos, module, function, b.rhs);
                    try write(buf, pos, ")");
                },
                .call => |call| {
                    if (cfg.skip_barriers and call.kind == .builtin and isBarrierName(call.name)) return;
                    // WGSL `arrayLength(&buf)` becomes the CSL static per-PE
                    // size since the CSL declaration is `var buf: [chunk_size]T`.
                    // Emitting a literal `arrayLength(...)` call would fail at
                    // cslc parse time — CSL has no arrayLength builtin. The
                    // runtime_array_size config names the declared per-PE
                    // length (default `chunk_size` for element-wise mode).
                    // Wrap the size name in `@as(u32, ...)` because CSL's
                    // param is `param chunk_size: i16` and downstream uses
                    // compare/subtract against u32-typed indices (`gid.x`).
                    // Without the cast cslc errors with
                    //   "expected type 'u32', got: 'i16'".
                    if (call.kind == .builtin and std.mem.eql(u8, call.name, "arrayLength")) {
                        try write(buf, pos, "@as(u32, ");
                        try write(buf, pos, cfg.runtime_array_size);
                        try write(buf, pos, ")");
                        return;
                    }
                    if (call.kind == .builtin) {
                        if (maps.cslMathBuiltin(call.name)) |csl_name| {
                            try write(buf, pos, csl_name);
                        } else if (maps.needsInlineExpansion(call.name)) {
                            try inlineBuiltin(buf, pos, module, function, call.name, call.args, expr_id);
                            return;
                        } else {
                            try write(buf, pos, call.name);
                        }
                    } else {
                        try write(buf, pos, call.name);
                    }
                    try write(buf, pos, "(");
                    var i: u32 = 0;
                    while (i < call.args.len) : (i += 1) {
                        if (i > 0) try write(buf, pos, ", ");
                        try expr(buf, pos, module, function, function.expr_args.items[call.args.start + i]);
                    }
                    try write(buf, pos, ")");
                },
                .construct => |c| {
                    switch (module.types.get(c.ty)) {
                        .scalar => |s| {
                            try write(buf, pos, "@as(");
                            try write(buf, pos, spec.scalarTypeName(s));
                            try write(buf, pos, ", ");
                            if (c.args.len > 0) try expr(buf, pos, module, function, function.expr_args.items[c.args.start]);
                            try write(buf, pos, ")");
                        },
                        else => try write(buf, pos, "/* construct */ 0"),
                    }
                },
                .member => |m| {
                    if (isUniformGlobalBase(module, function, m.base)) {
                        try write(buf, pos, m.field_name);
                    } else {
                        try expr(buf, pos, module, function, m.base);
                        try write(buf, pos, ".");
                        try write(buf, pos, m.field_name);
                    }
                },
                .index => |idx| {
                    try expr(buf, pos, module, function, idx.base);
                    try write(buf, pos, "[");
                    try expr(buf, pos, module, function, idx.index);
                    try write(buf, pos, "]");
                },
            }
        }

        pub fn inlineBuiltin(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function, name: []const u8, args: ir.Range, call_expr_id: ir.ExprId) EmitError!void {
            _ = call_expr_id;
            const a = function.expr_args.items;
            // CSL v1.4 has no `math.min(T, a, b)` / `math.max(T, a, b)` form.
            // SDK 1.4 canonical examples (gemv-checkerboard, conjugate-gradient,
            // wide-multiplication) use either user-defined `fn min(a, b)` helpers
            // or inline conditional expressions. Inline ternaries generalize to
            // any element type without requiring an external utility module,
            // so emit `(if (a < b) a else b)` / `(if (a > b) a else b)` directly.
            // For `clamp(x, lo, hi)` expand to nested min(max(x, lo), hi).
            if (std.mem.eql(u8, name, "clamp")) {
                if (args.len >= 3) {
                    // min( max(x, lo), hi ) → if (<if (x > lo) x else lo> < hi) ... else hi
                    try write(buf, pos, "(if ((if (");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " > ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ") ");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " else ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ") < ");
                    try expr(buf, pos, module, function, a[args.start + 2]);
                    try write(buf, pos, ") (if (");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " > ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ") ");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " else ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ") else ");
                    try expr(buf, pos, module, function, a[args.start + 2]);
                    try write(buf, pos, ")");
                }
            } else if (std.mem.eql(u8, name, "min")) {
                if (args.len >= 2) {
                    try write(buf, pos, "(if (");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " < ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ") ");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " else ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ")");
                }
            } else if (std.mem.eql(u8, name, "max")) {
                if (args.len >= 2) {
                    try write(buf, pos, "(if (");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " > ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ") ");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " else ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, ")");
                }
            } else if (std.mem.eql(u8, name, "fma")) {
                if (args.len >= 3) {
                    try write(buf, pos, "(");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " * ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, " + ");
                    try expr(buf, pos, module, function, a[args.start + 2]);
                    try write(buf, pos, ")");
                }
            } else if (std.mem.eql(u8, name, "select")) {
                if (args.len >= 3) {
                    try write(buf, pos, "if (");
                    try expr(buf, pos, module, function, a[args.start + 2]);
                    try write(buf, pos, ") ");
                    try expr(buf, pos, module, function, a[args.start + 1]);
                    try write(buf, pos, " else ");
                    try expr(buf, pos, module, function, a[args.start]);
                }
            } else if (std.mem.eql(u8, name, "fract")) {
                if (args.len >= 1) {
                    try write(buf, pos, "(");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, " - math.floor(");
                    try expr(buf, pos, module, function, a[args.start]);
                    try write(buf, pos, "))");
                }
            } else {
                try write(buf, pos, "/* unsupported: ");
                try write(buf, pos, name);
                try write(buf, pos, " */ 0");
            }
        }

        pub fn functionBody(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function) EmitError!void {
            if (function.stmts.items.len == 0) return;
            try stmt(buf, pos, module, function, function.root_stmt, 1);
        }

        pub fn writeType(buf: []u8, pos: *usize, module: *const ir.Module, ty: ir.TypeId) EmitError!void {
            switch (module.types.get(ty)) {
                .scalar => |s| try write(buf, pos, spec.scalarTypeName(s)),
                .vector => |vec| {
                    try write(buf, pos, "[");
                    try writeInt(buf, pos, vec.len);
                    try write(buf, pos, "]");
                    try writeType(buf, pos, module, vec.elem);
                },
                .array => |arr| {
                    // SDK v1.4 rejects `[N][M]T` (double-bracket) array-of-vector
                    // types. Canonical shape across all in-tree SDK examples
                    // (gemv-01, gemv-05, checkerboard benchmark) is flat
                    // `[N * M]scalar` with row-major indexing. Our IR walker
                    // already emits 1D computed-index accesses, so flattening
                    // here preserves access semantics while satisfying v1.4.
                    switch (module.types.get(arr.elem)) {
                        .vector => |vec| {
                            try write(buf, pos, "[");
                            if (arr.len) |al| {
                                try writeInt(buf, pos, al);
                                try write(buf, pos, " * ");
                                try writeInt(buf, pos, vec.len);
                            } else {
                                try write(buf, pos, cfg.runtime_array_size);
                                try write(buf, pos, " * ");
                                try writeInt(buf, pos, vec.len);
                            }
                            try write(buf, pos, "]");
                            try writeType(buf, pos, module, vec.elem);
                        },
                        else => {
                            try write(buf, pos, "[");
                            if (arr.len) |al| {
                                try writeInt(buf, pos, al);
                            } else {
                                try write(buf, pos, cfg.runtime_array_size);
                            }
                            try write(buf, pos, "]");
                            try writeType(buf, pos, module, arr.elem);
                        },
                    }
                },
                .struct_ => |sid| try write(buf, pos, module.structs.items[sid].name),
                else => try write(buf, pos, "u32"),
            }
        }

        pub fn writeZeroInit(buf: []u8, pos: *usize, module: *const ir.Module, ty: ir.TypeId) EmitError!void {
            switch (module.types.get(ty)) {
                .array => |arr| {
                    // Mirror the flattening in writeType: `@zeros([N * M]T)`
                    // for v1.4 compatibility, matching the declaration type.
                    try write(buf, pos, "@zeros(");
                    try writeType(buf, pos, module, ty);
                    try write(buf, pos, ")");
                    _ = arr;
                },
                else => try write(buf, pos, "0"),
            }
        }

        // Returns the CSL scalar-type name for an expression, unwrapping
        // vectors to their element type so WGSL-polymorphic builtins like
        // min/max/clamp can emit the correct `math.<op>(<type>, ...)` form.
        // Falls back to "f32" when the IR type is not scalar/vector — the
        // SDK's `math.min` / `math.max` require an explicit type argument
        // and mismatched types generate "Unexpected character" parse errors
        // at the invocation site.
        fn exprScalarTypeName(module: *const ir.Module, function: *const ir.Function, expr_id: ir.ExprId) []const u8 {
            if (expr_id >= function.exprs.items.len) return "f32";
            const ty = function.exprs.items[expr_id].ty;
            return scalarTypeOf(module, ty);
        }

        fn scalarTypeOf(module: *const ir.Module, ty: ir.TypeId) []const u8 {
            return switch (module.types.get(ty)) {
                .scalar => |s| spec.scalarTypeName(s),
                .vector => |vec| scalarTypeOf(module, vec.elem),
                .ref => |r| scalarTypeOf(module, r.elem),
                else => "f32",
            };
        }

        // Section emitters
        pub fn uniformParams(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
            for (module.globals.items) |global| {
                const space = global.addr_space orelse continue;
                if (space != .uniform) continue;
                switch (module.types.get(global.ty)) {
                    .struct_ => |struct_id| {
                        const sd = module.structs.items[struct_id];
                        try write(buf, pos, "// Uniforms (loaded from host before compute): a single\n");
                        try write(buf, pos, "// [N]u32 buffer rather than per-field vars so `&<uniform>`\n");
                        try write(buf, pos, "// yields `[*]u32` that matches `layout.csl @export_name(..., [*]u32)`.\n");
                        try write(buf, pos, "// Earlier per-field emission produced `&size: *u32` which cslc\n");
                        try write(buf, pos, "// rejected as a pointer-element-count mismatch. Per-field access\n");
                        try write(buf, pos, "// in the body is handled by the IR walker's `.member` case,\n");
                        try write(buf, pos, "// which maps struct field names to array indices via the field\n");
                        try write(buf, pos, "// index stored on the IR member expression.\n");
                        try write(buf, pos, "var ");
                        try write(buf, pos, global.name);
                        try write(buf, pos, ": [");
                        try writeInt(buf, pos, sd.fields.items.len);
                        try write(buf, pos, "]u32 = @zeros([");
                        try writeInt(buf, pos, sd.fields.items.len);
                        try write(buf, pos, "]u32);\n");
                        try write(buf, pos, "var ");
                        try write(buf, pos, global.name);
                        try write(buf, pos, "_ptr: [*]u32 = &");
                        try write(buf, pos, global.name);
                        try write(buf, pos, ";\n\n");
                    },
                    else => {},
                }
            }
        }

        fn writeRuntimeStorageType(buf: []u8, pos: *usize, module: *const ir.Module, elem_ty: ir.TypeId) EmitError!void {
            try write(buf, pos, "[");
            try write(buf, pos, cfg.runtime_array_size);
            switch (module.types.get(elem_ty)) {
                .vector => |vec| {
                    try write(buf, pos, " * ");
                    try writeInt(buf, pos, vec.len);
                    try write(buf, pos, "]");
                    try writeType(buf, pos, module, vec.elem);
                },
                else => {
                    try write(buf, pos, "]");
                    try writeType(buf, pos, module, elem_ty);
                },
            }
        }

        fn writeRuntimeStoragePointerElemType(buf: []u8, pos: *usize, module: *const ir.Module, elem_ty: ir.TypeId) EmitError!void {
            switch (module.types.get(elem_ty)) {
                .vector => |vec| try writeType(buf, pos, module, vec.elem),
                else => try writeType(buf, pos, module, elem_ty),
            }
        }

        pub fn storageBuffers(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
            try write(buf, pos, "// Storage buffers — each PE holds its local data.\n");
            try write(buf, pos, "param ");
            try write(buf, pos, cfg.runtime_array_size);
            try write(buf, pos, ": i16 = 1024;\n\n");
            for (module.globals.items) |global| {
                if (global.binding == null) continue;
                const space = global.addr_space orelse continue;
                if (space != .storage) continue;
                const et = arrayElemType(module, global.ty);
                try write(buf, pos, "var ");
                try write(buf, pos, global.name);
                try write(buf, pos, ": ");
                try writeRuntimeStorageType(buf, pos, module, et);
                try write(buf, pos, " = @zeros(");
                try writeRuntimeStorageType(buf, pos, module, et);
                try write(buf, pos, ");\n");
                try write(buf, pos, "var ");
                try write(buf, pos, global.name);
                try write(buf, pos, "_ptr: [*]");
                try writeRuntimeStoragePointerElemType(buf, pos, module, et);
                try write(buf, pos, " = &");
                try write(buf, pos, global.name);
                try write(buf, pos, ";\n");
            }
            try write(buf, pos, "\n");
        }

        pub fn workgroupBuffers(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
            var has_wg = false;
            for (module.globals.items) |global| {
                const space = global.addr_space orelse continue;
                if (space != .workgroup) continue;
                if (!has_wg) {
                    try write(buf, pos, "// Workgroup shared → PE-local in single-PE mode.\n");
                    has_wg = true;
                }
                try write(buf, pos, "var ");
                try write(buf, pos, global.name);
                try write(buf, pos, ": ");
                try writeType(buf, pos, module, global.ty);
                try write(buf, pos, " = ");
                try writeZeroInit(buf, pos, module, global.ty);
                try write(buf, pos, ";\n");
            }
            if (has_wg) try write(buf, pos, "\n");
        }

        pub fn helperFunctions(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
            for (module.functions.items) |func| {
                if (func.stage != null) continue;
                try write(buf, pos, "fn ");
                try write(buf, pos, func.name);
                try write(buf, pos, "(");
                for (func.params.items, 0..) |param, i| {
                    if (i > 0) try write(buf, pos, ", ");
                    try write(buf, pos, param.name);
                    try write(buf, pos, ": ");
                    try writeType(buf, pos, module, param.ty);
                }
                try write(buf, pos, ") ");
                try writeType(buf, pos, module, func.return_type);
                try write(buf, pos, " {\n");
                try functionBody(buf, pos, module, &func);
                try write(buf, pos, "}\n\n");
            }
        }

        pub fn comptimeExports(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
            try write(buf, pos, "comptime {\n");
            for (module.globals.items) |global| {
                if (global.binding == null) continue;
                const space = global.addr_space orelse continue;
                if (space != .storage and space != .uniform) continue;
                try write(buf, pos, "    @export_symbol(");
                try write(buf, pos, global.name);
                try write(buf, pos, "_ptr, \"");
                try write(buf, pos, global.name);
                try write(buf, pos, "\");\n");
            }
            try write(buf, pos, "    @export_symbol(compute);\n");
            try write(buf, pos, "}\n");
        }
    };
}
