// emit_csl_elementwise.zig — CSL PE program template for element-wise kernels.
//
// Maps Doppler's element-wise WGSL pattern (GELU, SiLU, scale, bias_add,
// embed) to a CSL PE program where each PE processes a contiguous chunk of
// the input/output arrays with no inter-PE communication.
//
// WGSL model:  256 threads, each does output[gid.x] = f(input[gid.x])
// CSL model:   N PEs, each does output[i] = f(input[i]) for i in local chunk

const std = @import("std");
const ir = @import("ir.zig");
const spec = @import("csl_spec.zig");
const maps = @import("emit_csl_maps.zig");
const classify = @import("emit_csl_classify.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
    UnsupportedBuiltin,
    UnsupportedConstruct,
};

/// Emit a complete CSL PE program for an element-wise kernel.
pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.ElementWiseInfo,
) EmitError!void {
    _ = info;
    const function = &module.functions.items[entry.function];

    // Header
    try write(buf, pos, "// PE program: element-wise kernel (auto-generated from WGSL)\n");
    try write(buf, pos, "// Each PE processes chunk_size elements with no fabric routing.\n\n");

    // Params from layout
    try write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try write(buf, pos, "param pe_id: i16;\n");
    try write(buf, pos, "param num_pes: i16;\n\n");

    // Memcpy + math imports
    try write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    // Emit uniform struct as comptime params
    try emitUniformParams(buf, pos, module);

    // Emit storage buffer declarations as PE-local arrays
    try emitStorageBuffers(buf, pos, module);

    // Emit helper functions (the actual math — gelu, silu, etc.)
    try emitHelperFunctions(buf, pos, module, function);

    // Emit the main compute function
    try emitComputeFunction(buf, pos, module, function);

    // Comptime block: symbol exports
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

// ---------------------------------------------------------------------------
// Section emitters
// ---------------------------------------------------------------------------

fn emitUniformParams(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
    // Find the uniform buffer and emit its struct fields as module-level vars.
    for (module.globals.items) |global| {
        const space = global.addr_space orelse continue;
        if (space != .uniform) continue;
        // Uniform struct fields become PE-local vars loaded from host.
        const ty = module.types.get(global.ty);
        switch (ty) {
            .struct_ => |struct_id| {
                const struct_def = module.structs.items[struct_id];
                try write(buf, pos, "// Uniforms (loaded from host before compute)\n");
                for (struct_def.fields.items) |field| {
                    try write(buf, pos, "var ");
                    try write(buf, pos, field.name);
                    try write(buf, pos, ": ");
                    try writeType(buf, pos, module, field.ty);
                    try write(buf, pos, " = 0;\n");
                }
                try write(buf, pos, "\n");
            },
            else => {},
        }
    }
}

fn emitStorageBuffers(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
    try write(buf, pos, "// Storage buffers — each PE holds its local chunk.\n");
    try write(buf, pos, "// Chunk size is total_size / num_pes, set by host before launch.\n");
    try write(buf, pos, "param chunk_size: i16 = 1024;\n\n");

    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;

        const elem_type = arrayElemType(module, global.ty);
        try write(buf, pos, "var ");
        try write(buf, pos, global.name);
        try write(buf, pos, ": [chunk_size]");
        try writeType(buf, pos, module, elem_type);
        try write(buf, pos, " = @zeros([chunk_size]");
        try writeType(buf, pos, module, elem_type);
        try write(buf, pos, ");\n");

        // Pointer for export
        try write(buf, pos, "var ");
        try write(buf, pos, global.name);
        try write(buf, pos, "_ptr: [*]");
        try writeType(buf, pos, module, elem_type);
        try write(buf, pos, " = &");
        try write(buf, pos, global.name);
        try write(buf, pos, ";\n");
    }
    try write(buf, pos, "\n");
}

fn emitHelperFunctions(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function) EmitError!void {
    // Scan for user-defined helper functions (non-entry functions) and emit them.
    for (module.functions.items) |func| {
        if (func.stage != null) continue; // Skip entry points.
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
        try emitFunctionBody(buf, pos, module, &func);
        try write(buf, pos, "}\n\n");
    }
    _ = function;
}

fn emitComputeFunction(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function) EmitError!void {
    try write(buf, pos, "fn compute() void {\n");

    // Element-wise loop: iterate over local chunk.
    try write(buf, pos, "    for (@range(i16, chunk_size)) |_idx| {\n");
    try write(buf, pos, "        const idx = @as(u32, _idx);\n");

    // Emit the kernel body, translating global_invocation_id.x → idx.
    // For now, emit a simplified version that calls the helper function
    // on each element.
    try emitElementWiseBody(buf, pos, module, function);

    try write(buf, pos, "    }\n");
    try write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try write(buf, pos, "}\n\n");
}

/// Emit the element-wise loop body by walking the IR function body and
/// translating WGSL constructs to CSL scalar operations.
fn emitElementWiseBody(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function) EmitError!void {
    // Walk statements looking for the core assignment pattern:
    //   output[idx] = f(input[idx]);
    // For the initial implementation, we look for the main assignment
    // and emit it directly. Complex control flow (if/else on override
    // constants) is emitted as CSL if/else.
    _ = module;
    _ = function;

    // TODO: Full IR-walking implementation. For now emit a placeholder
    // that shows the structure is correct.
    try write(buf, pos, "        // TODO: IR-driven body emission\n");
    try write(buf, pos, "        // Kernel body will be translated from WGSL IR here.\n");
}

/// Emit a function body by walking its IR statements.
fn emitFunctionBody(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function) EmitError!void {
    if (function.stmts.items.len == 0) return;
    try emitStmt(buf, pos, module, function, function.root_stmt, 1);
}

fn emitStmt(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function, stmt_id: ir.StmtId, indent: usize) EmitError!void {
    if (stmt_id >= function.stmts.items.len) return;
    const stmt = function.stmts.items[stmt_id];
    switch (stmt) {
        .block => |range| {
            var i: u32 = 0;
            while (i < range.len) : (i += 1) {
                const child_id = function.stmt_children.items[range.start + i];
                try emitStmt(buf, pos, module, function, child_id, indent);
            }
        },
        .local_decl => |decl| {
            try writeIndent(buf, pos, indent);
            if (decl.is_const) {
                try write(buf, pos, "const ");
            } else {
                try write(buf, pos, "var ");
            }
            const local = function.locals.items[decl.local];
            try write(buf, pos, local.name);
            try write(buf, pos, ": ");
            try writeType(buf, pos, module, local.ty);
            if (decl.initializer) |init_expr| {
                try write(buf, pos, " = ");
                try emitExpr(buf, pos, module, function, init_expr);
            }
            try write(buf, pos, ";\n");
        },
        .assign => |assign| {
            try writeIndent(buf, pos, indent);
            try emitExpr(buf, pos, module, function, assign.lhs);
            try write(buf, pos, " ");
            try write(buf, pos, maps.assignOpText(assign.op));
            try write(buf, pos, " ");
            try emitExpr(buf, pos, module, function, assign.rhs);
            try write(buf, pos, ";\n");
        },
        .return_ => |maybe_expr| {
            try writeIndent(buf, pos, indent);
            try write(buf, pos, "return");
            if (maybe_expr) |expr_id| {
                try write(buf, pos, " ");
                try emitExpr(buf, pos, module, function, expr_id);
            }
            try write(buf, pos, ";\n");
        },
        .if_ => |if_stmt| {
            try writeIndent(buf, pos, indent);
            try write(buf, pos, "if (");
            try emitExpr(buf, pos, module, function, if_stmt.cond);
            try write(buf, pos, ") {\n");
            try emitStmt(buf, pos, module, function, if_stmt.then_block, indent + 1);
            try writeIndent(buf, pos, indent);
            try write(buf, pos, "}");
            if (if_stmt.else_block) |else_id| {
                try write(buf, pos, " else {\n");
                try emitStmt(buf, pos, module, function, else_id, indent + 1);
                try writeIndent(buf, pos, indent);
                try write(buf, pos, "}");
            }
            try write(buf, pos, "\n");
        },
        .loop_ => |loop_stmt| {
            try writeIndent(buf, pos, indent);
            // CSL uses while/for; emit as while loop for generality.
            try write(buf, pos, "while (");
            if (loop_stmt.cond) |cond| {
                try emitExpr(buf, pos, module, function, cond);
            } else {
                try write(buf, pos, "true");
            }
            try write(buf, pos, ") {\n");
            try emitStmt(buf, pos, module, function, loop_stmt.body, indent + 1);
            try writeIndent(buf, pos, indent);
            try write(buf, pos, "}\n");
        },
        .expr => |expr_id| {
            try writeIndent(buf, pos, indent);
            try emitExpr(buf, pos, module, function, expr_id);
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
            try write(buf, pos, "// TODO: switch statement\n");
        },
        .discard_ => {
            // No equivalent in CSL compute — skip.
        },
    }
}

fn emitExpr(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function, expr_id: ir.ExprId) EmitError!void {
    if (expr_id >= function.exprs.items.len) return;
    const expr = function.exprs.items[expr_id];
    switch (expr.data) {
        .bool_lit => |val| try write(buf, pos, if (val) "true" else "false"),
        .int_lit => |val| {
            var tmp: [20]u8 = undefined;
            const slice = std.fmt.bufPrint(&tmp, "{d}", .{val}) catch return error.OutputTooLarge;
            try write(buf, pos, slice);
        },
        .float_lit => |val| {
            var tmp: [32]u8 = undefined;
            const len = std.fmt.bufPrint(&tmp, "{d}", .{val}) catch return error.OutputTooLarge;
            try write(buf, pos, len);
        },
        .param_ref => |idx| {
            if (idx < function.params.items.len) {
                try write(buf, pos, function.params.items[idx].name);
            }
        },
        .local_ref => |idx| {
            if (idx < function.locals.items.len) {
                try write(buf, pos, function.locals.items[idx].name);
            }
        },
        .global_ref => |idx| {
            if (idx < module.globals.items.len) {
                try write(buf, pos, module.globals.items[idx].name);
            }
        },
        .load => |inner| try emitExpr(buf, pos, module, function, inner),
        .unary => |unary| {
            try write(buf, pos, maps.unaryOpText(unary.op));
            try write(buf, pos, "(");
            try emitExpr(buf, pos, module, function, unary.operand);
            try write(buf, pos, ")");
        },
        .binary => |binary| {
            try write(buf, pos, "(");
            try emitExpr(buf, pos, module, function, binary.lhs);
            try write(buf, pos, " ");
            try write(buf, pos, maps.binaryOpText(binary.op));
            try write(buf, pos, " ");
            try emitExpr(buf, pos, module, function, binary.rhs);
            try write(buf, pos, ")");
        },
        .call => |call| {
            // Map WGSL builtins to CSL equivalents.
            if (call.kind == .builtin) {
                if (maps.cslMathBuiltin(call.name)) |csl_name| {
                    try write(buf, pos, csl_name);
                } else if (maps.needsInlineExpansion(call.name)) {
                    try emitInlineBuiltin(buf, pos, module, function, call.name, call.args);
                    return;
                } else {
                    // Passthrough or unsupported — emit as-is for now.
                    try write(buf, pos, call.name);
                }
            } else {
                try write(buf, pos, call.name);
            }
            try write(buf, pos, "(");
            var i: u32 = 0;
            while (i < call.args.len) : (i += 1) {
                if (i > 0) try write(buf, pos, ", ");
                const arg_id = function.expr_args.items[call.args.start + i];
                try emitExpr(buf, pos, module, function, arg_id);
            }
            try write(buf, pos, ")");
        },
        .construct => |construct| {
            // CSL has no vector constructors. Emit as array literal or cast.
            const ty = module.types.get(construct.ty);
            switch (ty) {
                .scalar => |s| {
                    // Type cast: f32(x) → @as(f32, x)
                    try write(buf, pos, "@as(");
                    try write(buf, pos, spec.scalarTypeName(s));
                    try write(buf, pos, ", ");
                    if (construct.args.len > 0) {
                        const arg_id = function.expr_args.items[construct.args.start];
                        try emitExpr(buf, pos, module, function, arg_id);
                    }
                    try write(buf, pos, ")");
                },
                else => {
                    try write(buf, pos, "/* construct */");
                    try write(buf, pos, "0");
                },
            }
        },
        .member => |member| {
            try emitExpr(buf, pos, module, function, member.base);
            try write(buf, pos, ".");
            try write(buf, pos, member.field_name);
        },
        .index => |idx| {
            try emitExpr(buf, pos, module, function, idx.base);
            try write(buf, pos, "[");
            try emitExpr(buf, pos, module, function, idx.index);
            try write(buf, pos, "]");
        },
    }
}

fn emitInlineBuiltin(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function, name: []const u8, args: ir.Range) EmitError!void {
    if (std.mem.eql(u8, name, "clamp")) {
        // clamp(x, lo, hi) → min(max(x, lo), hi)
        // CSL: use scalar comparisons
        if (args.len >= 3) {
            try write(buf, pos, "math.min(f32, math.max(f32, ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start]);
            try write(buf, pos, ", ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 1]);
            try write(buf, pos, "), ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 2]);
            try write(buf, pos, ")");
        }
    } else if (std.mem.eql(u8, name, "min")) {
        if (args.len >= 2) {
            try write(buf, pos, "math.min(f32, ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start]);
            try write(buf, pos, ", ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 1]);
            try write(buf, pos, ")");
        }
    } else if (std.mem.eql(u8, name, "max")) {
        if (args.len >= 2) {
            try write(buf, pos, "math.max(f32, ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start]);
            try write(buf, pos, ", ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 1]);
            try write(buf, pos, ")");
        }
    } else if (std.mem.eql(u8, name, "fma")) {
        // fma(a, b, c) → a * b + c
        if (args.len >= 3) {
            try write(buf, pos, "(");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start]);
            try write(buf, pos, " * ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 1]);
            try write(buf, pos, " + ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 2]);
            try write(buf, pos, ")");
        }
    } else if (std.mem.eql(u8, name, "select")) {
        // select(f, t, cond) → if (cond) t else f
        if (args.len >= 3) {
            try write(buf, pos, "if (");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 2]);
            try write(buf, pos, ") ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start + 1]);
            try write(buf, pos, " else ");
            try emitExpr(buf, pos, module, function, function.expr_args.items[args.start]);
        }
    } else if (std.mem.eql(u8, name, "fract")) {
        // fract(x) → x - floor(x)
        if (args.len >= 1) {
            const arg = function.expr_args.items[args.start];
            try write(buf, pos, "(");
            try emitExpr(buf, pos, module, function, arg);
            try write(buf, pos, " - math.floor(");
            try emitExpr(buf, pos, module, function, arg);
            try write(buf, pos, "))");
        }
    } else {
        // Fallback: emit as comment + zero
        try write(buf, pos, "/* unsupported: ");
        try write(buf, pos, name);
        try write(buf, pos, " */ 0");
    }
}

// ---------------------------------------------------------------------------
// Write helpers
// ---------------------------------------------------------------------------

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}

fn writeIndent(buf: []u8, pos: *usize, level: usize) EmitError!void {
    var i: usize = 0;
    while (i < level) : (i += 1) {
        try write(buf, pos, "    ");
    }
}

fn writeType(buf: []u8, pos: *usize, module: *const ir.Module, ty: ir.TypeId) EmitError!void {
    const resolved = module.types.get(ty);
    switch (resolved) {
        .scalar => |s| try write(buf, pos, spec.scalarTypeName(s)),
        .vector => |vec| {
            // CSL has no vector types — emit as array.
            try write(buf, pos, "[");
            var tmp: [4]u8 = undefined;
            const slice = std.fmt.bufPrint(&tmp, "{d}", .{vec.len}) catch return error.OutputTooLarge;
            try write(buf, pos, slice);
            try write(buf, pos, "]");
            try writeType(buf, pos, module, vec.elem);
        },
        .array => |arr| {
            try write(buf, pos, "[");
            if (arr.len) |array_len| {
                var tmp: [12]u8 = undefined;
                const slice = std.fmt.bufPrint(&tmp, "{d}", .{array_len}) catch return error.OutputTooLarge;
                try write(buf, pos, slice);
            } else {
                try write(buf, pos, "chunk_size");
            }
            try write(buf, pos, "]");
            try writeType(buf, pos, module, arr.elem);
        },
        .struct_ => |struct_id| {
            try write(buf, pos, module.structs.items[struct_id].name);
        },
        else => try write(buf, pos, "u32"), // fallback
    }
}

fn arrayElemType(module: *const ir.Module, ty: ir.TypeId) ir.TypeId {
    return switch (module.types.get(ty)) {
        .array => |arr| arr.elem,
        else => ty,
    };
}
