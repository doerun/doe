const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_msl_maps.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

pub const MAX_OUTPUT: usize = 128 * 1024;

pub fn emit(module: *const ir.Module, out: []u8) EmitError!usize {
    var emitter = Emitter{ .module = module, .buf = out };
    try emitter.emit_root();
    return emitter.pos;
}

const Emitter = struct {
    module: *const ir.Module,
    buf: []u8,
    pos: usize = 0,
    indent: usize = 0,

    fn emit_root(self: *Emitter) EmitError!void {
        try self.write("#include <metal_stdlib>\nusing namespace metal;\n");
        try self.emit_structs();
        try self.emit_globals();
        try self.emit_functions();
    }

    fn emit_structs(self: *Emitter) EmitError!void {
        for (self.module.structs.items) |struct_def| {
            try self.write("\nstruct ");
            try self.write(struct_def.name);
            try self.write(" {\n");
            self.indent += 4;
            for (struct_def.fields.items) |field| {
                try self.write_indent();
                try self.emit_type(field.ty);
                try self.write(" ");
                try self.write(field.name);
                try self.write(";\n");
            }
            self.indent -= 4;
            try self.write("};\n");
        }
    }

    fn emit_globals(self: *Emitter) EmitError!void {
        for (self.module.globals.items) |global| {
            if (global.binding != null) continue;
            switch (global.class) {
                .var_ => {
                    const addr_space = global.addr_space orelse continue;
                    switch (addr_space) {
                        .workgroup => try self.write("\nthreadgroup "),
                        .private => try self.write("\nthread "),
                        else => continue,
                    }
                    try self.emit_type(global.ty);
                    try self.write(" ");
                    try self.write(global.name);
                    if (global.initializer) |constant| {
                        try self.write(" = ");
                        try self.emit_constant(constant, global.ty);
                    }
                    try self.write(";\n");
                },
                .const_, .override_ => {
                    try self.write("\nconstant ");
                    try self.emit_type(global.ty);
                    try self.write(" ");
                    try self.write(global.name);
                    if (global.initializer) |constant| {
                        try self.write(" = ");
                        try self.emit_constant(constant, global.ty);
                    }
                    try self.write(";\n");
                },
                else => {},
            }
        }
    }

    fn emit_functions(self: *Emitter) EmitError!void {
        for (self.module.functions.items, 0..) |_, index| {
            try self.emit_function(@intCast(index));
        }
    }

    fn emit_function(self: *Emitter, function_index: ir.FunctionId) EmitError!void {
        const function = self.module.functions.items[function_index];
        const stage = if (function.stage) |stage| stage else null;
        if (stage != null and stage.? != .compute) return error.InvalidIr;

        try self.write("\n");
        if (stage != null) try self.write("[[kernel]]\n");
        try self.emit_type(function.return_type);
        try self.write(" ");
        try self.write(maps.msl_function_name(function.name, stage));
        try self.write("(");
        var need_comma = false;
        if (stage != null) {
            for (self.module.globals.items) |global| {
                if (global.binding == null) continue;
                if (need_comma) try self.write(", ");
                try self.emit_bound_global_param(global);
                need_comma = true;
            }
        }
        for (function.params.items) |param| {
            if (need_comma) try self.write(", ");
            try self.emit_param(param);
            need_comma = true;
        }
        try self.write(") {\n");
        self.indent += 4;
        try self.emit_stmt(function, function.root_stmt);
        self.indent -= 4;
        try self.write("}\n");
    }

    fn emit_bound_global_param(self: *Emitter, global: ir.Global) EmitError!void {
        const binding = global.binding orelse return error.InvalidIr;
        if (global.addr_space) |addr_space| switch (addr_space) {
            .uniform => {
                try self.write("constant ");
                try self.emit_type(global.ty);
                try self.write("& ");
                try self.write(global.name);
                try self.write(" [[buffer(");
                try self.write_u32(binding.binding);
                try self.write(")]]");
                return;
            },
            .storage => {
                const access = global.access orelse .read_write;
                if (access == .read) {
                    try self.write("const device ");
                } else {
                    try self.write("device ");
                }
                switch (self.module.types.get(global.ty)) {
                    .array => |arr| {
                        try self.emit_type(arr.elem);
                        try self.write("* ");
                    },
                    else => {
                        try self.emit_type(global.ty);
                        try self.write("& ");
                    },
                }
                try self.write(global.name);
                try self.write(" [[buffer(");
                try self.write_u32(binding.binding);
                try self.write(")]]");
                switch (self.module.types.get(global.ty)) {
                    .array => |arr| if (arr.len == null) {
                        try self.write(", uint ");
                        try self.write(global.name);
                        try self.write("_size [[buffer_size(");
                        try self.write_u32(binding.binding);
                        try self.write(")]]");
                    },
                    else => {},
                }
                return;
            },
            else => {},
        };
        switch (self.module.types.get(global.ty)) {
            .sampler => {
                try self.write("sampler ");
                try self.write(global.name);
                try self.write(" [[sampler(");
                try self.write_u32(binding.binding);
                try self.write(")]]");
            },
            .texture_2d, .storage_texture_2d => {
                try self.emit_type(global.ty);
                try self.write(" ");
                try self.write(global.name);
                try self.write(" [[texture(");
                try self.write_u32(binding.binding);
                try self.write(")]]");
            },
            else => return error.InvalidIr,
        }
    }

    fn emit_param(self: *Emitter, param: ir.Param) EmitError!void {
        try self.emit_type(param.ty);
        try self.write(" ");
        try self.write(param.name);
        if (param.io) |io_attr| {
            if (io_attr.builtin != .none) {
                try self.write(" [[");
                try self.write(maps.msl_builtin_name(io_attr.builtin));
                try self.write("]]" );
            } else if (io_attr.location != null) {
                return error.InvalidIr;
            }
        }
    }

    fn emit_stmt(self: *Emitter, function: ir.Function, stmt_id: ir.StmtId) EmitError!void {
        const stmt = function.stmts.items[stmt_id];
        switch (stmt) {
            .block => |range| {
                var i: u32 = 0;
                while (i < range.len) : (i += 1) {
                    try self.emit_stmt(function, function.stmt_children.items[range.start + i]);
                }
            },
            .local_decl => |decl| {
                const local = function.locals.items[decl.local];
                try self.write_indent();
                if (decl.is_const) {
                    try self.write("const ");
                }
                try self.emit_type(local.ty);
                try self.write(" ");
                try self.write(local.name);
                if (decl.initializer) |expr_id| {
                    try self.write(" = ");
                    try self.emit_expr(function, expr_id);
                }
                try self.write(";\n");
            },
            .expr => |expr_id| {
                try self.write_indent();
                try self.emit_expr(function, expr_id);
                try self.write(";\n");
            },
            .assign => |assign| {
                try self.write_indent();
                try self.emit_expr(function, assign.lhs);
                try self.write(" ");
                try self.write(maps.assign_op_text(assign.op));
                try self.write(" ");
                try self.emit_expr(function, assign.rhs);
                try self.write(";\n");
            },
            .return_ => |value| {
                try self.write_indent();
                try self.write("return");
                if (value) |expr_id| {
                    try self.write(" ");
                    try self.emit_expr(function, expr_id);
                }
                try self.write(";\n");
            },
            .if_ => |if_stmt| {
                try self.write_indent();
                try self.write("if (");
                try self.emit_expr(function, if_stmt.cond);
                try self.write(") {\n");
                self.indent += 4;
                try self.emit_stmt(function, if_stmt.then_block);
                self.indent -= 4;
                try self.write_indent();
                try self.write("}");
                if (if_stmt.else_block) |else_block| {
                    try self.write(" else {\n");
                    self.indent += 4;
                    try self.emit_stmt(function, else_block);
                    self.indent -= 4;
                    try self.write_indent();
                    try self.write("}\n");
                } else {
                    try self.write("\n");
                }
            },
            .loop_ => |loop_stmt| {
                if (loop_stmt.init) |init_stmt| try self.emit_stmt(function, init_stmt);
                try self.write_indent();
                switch (loop_stmt.kind) {
                    .while_loop, .for_loop => {
                        try self.write("while (");
                        if (loop_stmt.cond) |cond| {
                            try self.emit_expr(function, cond);
                        } else {
                            try self.write("true");
                        }
                        try self.write(") {\n");
                    },
                    .loop => try self.write("while (true) {\n"),
                }
                self.indent += 4;
                try self.emit_stmt(function, loop_stmt.body);
                if (loop_stmt.continuing) |continuing| try self.emit_stmt(function, continuing);
                self.indent -= 4;
                try self.write_indent();
                try self.write("}\n");
            },
            .switch_ => |switch_stmt| {
                try self.write_indent();
                try self.write("switch (");
                try self.emit_expr(function, switch_stmt.expr);
                try self.write(") {\n");
                self.indent += 4;
                var case_index: u32 = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = function.switch_cases.items[switch_stmt.cases.start + case_index];
                    if (case_node.is_default) {
                        try self.write_indent();
                        try self.write("default:\n");
                    } else {
                        var selector_index: usize = 0;
                        while (selector_index < case_node.selectors.items.len) : (selector_index += 1) {
                            try self.write_indent();
                            try self.write("case ");
                            try self.emit_expr(function, case_node.selectors.items[selector_index]);
                            try self.write(":\n");
                        }
                    }
                    self.indent += 4;
                    try self.emit_stmt(function, case_node.body);
                    try self.write_indent();
                    try self.write("break;\n");
                    self.indent -= 4;
                }
                self.indent -= 4;
                try self.write_indent();
                try self.write("}\n");
            },
            .break_ => {
                try self.write_indent();
                try self.write("break;\n");
            },
            .continue_ => {
                try self.write_indent();
                try self.write("continue;\n");
            },
            .discard_ => {
                try self.write_indent();
                try self.write("discard_fragment();\n");
            },
        }
    }

    fn emit_expr(self: *Emitter, function: ir.Function, expr_id: ir.ExprId) EmitError!void {
        const expr = function.exprs.items[expr_id];
        switch (expr.data) {
            .bool_lit => |value| try self.write(if (value) "true" else "false"),
            .int_lit => |value| try self.write_u64(value),
            .float_lit => |value| try self.write_float(value),
            .param_ref => |index| try self.write(function.params.items[index].name),
            .local_ref => |index| try self.write(function.locals.items[index].name),
            .global_ref => |index| try self.write(self.module.globals.items[index].name),
            .load => |inner| try self.emit_expr(function, inner),
            .unary => |unary| {
                try self.write("(");
                try self.write(maps.unary_op_text(unary.op));
                try self.emit_expr(function, unary.operand);
                try self.write(")");
            },
            .binary => |binary| {
                try self.write("(");
                try self.emit_expr(function, binary.lhs);
                try self.write(" ");
                try self.write(maps.binary_op_text(binary.op));
                try self.write(" ");
                try self.emit_expr(function, binary.rhs);
                try self.write(")");
            },
            .call => |call| try self.emit_call(function, expr.ty, call),
            .construct => |construct| {
                try self.emit_type(construct.ty);
                try self.write("(");
                try self.emit_expr_list(function, construct.args);
                try self.write(")");
            },
            .member => |member| {
                try self.emit_expr(function, member.base);
                try self.write(".");
                try self.write(member.field_name);
            },
            .index => |index| {
                try self.emit_expr(function, index.base);
                try self.write("[");
                try self.emit_expr(function, index.index);
                try self.write("]");
            },
        }
    }

    fn emit_call(self: *Emitter, function: ir.Function, result_ty: ir.TypeId, call: @FieldType(ir.Expr, "call")) EmitError!void {
        if (call.kind == .builtin) {
            if (std.mem.eql(u8, call.name, "workgroupBarrier")) {
                try self.write("threadgroup_barrier(mem_flags::mem_threadgroup)");
                return;
            }
            if (std.mem.eql(u8, call.name, "storageBarrier")) {
                try self.write("threadgroup_barrier(mem_flags::mem_device)");
                return;
            }
            if (std.mem.eql(u8, call.name, "bitcast")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("as_type<");
                try self.emit_type(result_ty);
                try self.write(">(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "unpack2x16float")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("float2(as_type<half2>(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write("))");
                return;
            }
            if (std.mem.eql(u8, call.name, "pack2x16float")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("as_type<uint>(half2(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write("))");
                return;
            }
            if (std.mem.eql(u8, call.name, "unpack4x8unorm")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("(float4(as_type<uchar4>(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")) / 255.0)");
                return;
            }
            if (std.mem.eql(u8, call.name, "unpack4x8snorm")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("clamp(float4(as_type<char4>(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")) / 127.0, -1.0, 1.0)");
                return;
            }
            if (std.mem.eql(u8, call.name, "pack4x8unorm")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("as_type<uint>(uchar4(round(clamp(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(", 0.0, 1.0) * 255.0)))");
                return;
            }
            if (std.mem.eql(u8, call.name, "pack4x8snorm")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("as_type<uint>(char4(round(clamp(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(", -1.0, 1.0) * 127.0)))");
                return;
            }
            if (std.mem.eql(u8, call.name, "textureLoad")) {
                if (call.args.len != 3) return error.InvalidIr;
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(".read(");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(", ");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "textureStore")) {
                if (call.args.len != 3) return error.InvalidIr;
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(".write(");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
                try self.write(", ");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicLoad")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("atomic_load_explicit(&(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write("), memory_order_relaxed)");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicStore")) {
                if (call.args.len != 2) return error.InvalidIr;
                try self.write("atomic_store_explicit(&(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write("), ");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(", memory_order_relaxed)");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicAdd")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_add_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicSub")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_sub_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicMax")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_max_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicMin")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_min_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicAnd")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_and_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicOr")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_or_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicXor")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_fetch_xor_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "atomicExchange")) {
                try self.emit_atomic_fetch_explicit(function, call, "atomic_exchange_explicit");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupAdd")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("simd_sum(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupExclusiveAdd")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("simd_prefix_exclusive_sum(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupMin")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("simd_min(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupMax")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("simd_max(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupBroadcast")) {
                if (call.args.len != 2) return error.InvalidIr;
                try self.write("simd_broadcast(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(", ");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupShuffle")) {
                if (call.args.len != 2) return error.InvalidIr;
                try self.write("simd_shuffle(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(", ");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "subgroupShuffleXor")) {
                if (call.args.len != 2) return error.InvalidIr;
                try self.write("simd_shuffle_xor(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(", ");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "inverseSqrt")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("rsqrt(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(")");
                return;
            }
            if (std.mem.eql(u8, call.name, "degrees")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(" * 57.29577951308232)");
                return;
            }
            if (std.mem.eql(u8, call.name, "radians")) {
                if (call.args.len != 1) return error.InvalidIr;
                try self.write("(");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write(" * 0.017453292519943295)");
                return;
            }
            if (std.mem.eql(u8, call.name, "arrayLength")) {
                if (call.args.len != 1) return error.InvalidIr;
                const target_expr = function.expr_args.items[call.args.start];
                switch (function.exprs.items[target_expr].data) {
                    .global_ref => |index| {
                        const global = self.module.globals.items[index];
                        switch (self.module.types.get(global.ty)) {
                            .array => |arr| {
                                if (arr.len != null) return error.InvalidIr;
                                try self.write("uint(");
                                try self.write(global.name);
                                try self.write("_size / sizeof(");
                                try self.emit_type(arr.elem);
                                try self.write("))");
                                return;
                            },
                            else => return error.InvalidIr,
                        }
                    },
                    else => return error.InvalidIr,
                }
            }
            if (std.mem.eql(u8, call.name, "select")) {
                if (call.args.len != 3) return error.InvalidIr;
                try self.write("((");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
                try self.write(") ? (");
                try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                try self.write(") : (");
                try self.emit_expr(function, function.expr_args.items[call.args.start]);
                try self.write("))");
                return;
            }
            if (maps.msl_builtin_passthrough_name(call.name)) |mapped_name| {
                try self.write(mapped_name);
                try self.write("(");
                try self.emit_expr_list(function, call.args);
                try self.write(")");
                return;
            }
            return error.InvalidIr;
        }
        try self.write(call.name);
        try self.write("(");
        try self.emit_expr_list(function, call.args);
        try self.write(")");
    }

    fn emit_atomic_fetch_explicit(self: *Emitter, function: ir.Function, call: @FieldType(ir.Expr, "call"), name: []const u8) EmitError!void {
        if (call.args.len != 2) return error.InvalidIr;
        try self.write(name);
        try self.write("(&(");
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write("), ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", memory_order_relaxed)");
    }

    fn emit_expr_list(self: *Emitter, function: ir.Function, range: ir.Range) EmitError!void {
        var i: u32 = 0;
        while (i < range.len) : (i += 1) {
            if (i > 0) try self.write(", ");
            try self.emit_expr(function, function.expr_args.items[range.start + i]);
        }
    }

    fn emit_constant(self: *Emitter, constant: ir.ConstantValue, ty: ir.TypeId) EmitError!void {
        _ = ty;
        switch (constant) {
            .bool => |value| try self.write(if (value) "true" else "false"),
            .int => |value| try self.write_u64(value),
            .float => |value| try self.write_float(value),
        }
    }

    fn emit_type(self: *Emitter, ty: ir.TypeId) EmitError!void {
        switch (self.module.types.get(ty)) {
            .scalar => |scalar| try self.write(switch (scalar) {
                .void => "void",
                .bool => "bool",
                .i32, .abstract_int => "int",
                .u32 => "uint",
                .f32, .abstract_float => "float",
                .f16 => "half",
            }),
            .vector => |vec| {
                const elem_name = switch (self.module.types.get(vec.elem)) {
                    .scalar => |scalar| switch (scalar) {
                        .bool => "bool",
                        .i32, .abstract_int => "int",
                        .u32 => "uint",
                        .f32, .abstract_float => "float",
                        .f16 => "half",
                        else => return error.InvalidIr,
                    },
                    else => return error.InvalidIr,
                };
                try self.write(elem_name);
                try self.write_u32(vec.len);
            },
            .matrix => |mat| {
                const elem_name = switch (self.module.types.get(mat.elem)) {
                    .scalar => |scalar| switch (scalar) {
                        .f32, .abstract_float => "float",
                        .f16 => "half",
                        else => return error.InvalidIr,
                    },
                    else => return error.InvalidIr,
                };
                try self.write(elem_name);
                try self.write_u32(mat.columns);
                try self.write("x");
                try self.write_u32(mat.rows);
            },
            .array => |arr| {
                if (arr.len == null) return error.InvalidIr;
                try self.write("array<");
                try self.emit_type(arr.elem);
                try self.write(", ");
                try self.write_u32(arr.len.?);
                try self.write(">");
            },
            .atomic => |inner| switch (self.module.types.get(inner)) {
                .scalar => |scalar| switch (scalar) {
                    .u32 => try self.write("atomic_uint"),
                    .i32, .abstract_int => try self.write("atomic_int"),
                    else => return error.InvalidIr,
                },
                else => return error.InvalidIr,
            },
            .struct_ => |struct_id| try self.write(self.module.structs.items[struct_id].name),
            .sampler => try self.write("sampler"),
            .texture_2d => |sample_ty| {
                try self.write("texture2d<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .storage_texture_2d => |storage_tex| {
                try self.write("texture2d<float, access::");
                try self.write(switch (storage_tex.access) {
                    .read => "read",
                    .write => "write",
                    .read_write => "read_write",
                });
                try self.write(">");
            },
            .ref => |ref_ty| try self.emit_type(ref_ty.elem),
        }
    }

    fn write(self: *Emitter, text: []const u8) EmitError!void {
        if (self.pos + text.len > self.buf.len) return error.OutputTooLarge;
        @memcpy(self.buf[self.pos .. self.pos + text.len], text);
        self.pos += text.len;
    }

    fn write_indent(self: *Emitter) EmitError!void {
        var i: usize = 0;
        while (i < self.indent) : (i += 1) try self.write(" ");
    }

    fn write_u32(self: *Emitter, value: u32) EmitError!void {
        var buf: [32]u8 = undefined;
        const text = std.fmt.bufPrint(&buf, "{}", .{value}) catch return error.OutputTooLarge;
        try self.write(text);
    }

    fn write_u64(self: *Emitter, value: u64) EmitError!void {
        var buf: [32]u8 = undefined;
        const text = std.fmt.bufPrint(&buf, "{}", .{value}) catch return error.OutputTooLarge;
        try self.write(text);
    }

    fn write_float(self: *Emitter, value: f64) EmitError!void {
        var buf: [64]u8 = undefined;
        const text = std.fmt.bufPrint(&buf, "{d}", .{value}) catch return error.OutputTooLarge;
        try self.write(text);
        if (std.mem.indexOfScalar(u8, text, '.') == null and std.mem.indexOfAny(u8, text, "eE") == null) {
            try self.write(".0");
        }
    }
};
