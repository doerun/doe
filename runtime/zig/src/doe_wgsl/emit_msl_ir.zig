const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_msl_maps.zig");
const stage_render = @import("emit_msl_stage.zig");
const subgroups = @import("emit_msl_subgroups.zig");
const call_builtins = @import("emit_msl_ir_builtins.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

pub const MAX_OUTPUT: usize = 128 * 1024;
const BINDINGS_PER_GROUP: u32 = 16;
// Reserved Metal buffer slot for the runtime array sizes buffer (_doe_sizes).
// Must match MSL_SIZES_SLOT in doe_queue_submit_native.zig.
pub const MSL_SIZES_SLOT: u32 = 30;

pub fn emit(module: *const ir.Module, out: []u8) EmitError!usize {
    var emitter = Emitter{ .module = module, .buf = out };
    try emitter.emit_root();
    return emitter.pos;
}

pub fn moduleNeedsSizesParam(module: *const ir.Module) bool {
    var emitter = Emitter{
        .module = module,
        .buf = &.{},
    };
    return emitter.module_needs_sizes_param();
}

const Emitter = struct {
    module: *const ir.Module,
    buf: []u8,
    pos: usize = 0,
    indent: usize = 0,

    pub fn msl_binding_slot(_: *Emitter, binding: ir.BindingPoint) u32 {
        return binding.group * BINDINGS_PER_GROUP + binding.binding;
    }

    // Returns true if any global runtime array uses arrayLength — signals that
    // _doe_sizes [[buffer(MSL_SIZES_SLOT)]] must be added to the kernel signature.
    fn module_needs_sizes_param(self: *Emitter) bool {
        for (self.module.globals.items) |global| {
            switch (self.module.types.get(global.ty)) {
                .array => |arr| if (arr.len == null and stage_render.runtime_array_needs_size_param(self, global.name)) return true,
                .struct_ => |struct_id| {
                    // Check if a struct-typed storage global has a runtime-sized
                    // array field accessed via arrayLength(&buf.field).
                    if (struct_has_runtime_array_with_array_length(self, struct_id, global.name)) return true;
                },
                else => {},
            }
        }
        return false;
    }

    /// Check if any function calls arrayLength on a member of a struct-typed
    /// storage global (e.g. arrayLength(&buf.data)).
    fn struct_has_runtime_array_with_array_length(self: *Emitter, struct_id: ir.StructId, global_name: []const u8) bool {
        const struct_def = self.module.structs.items[struct_id];
        // First check the struct actually has a runtime-sized array field.
        var has_rta = false;
        for (struct_def.fields.items) |field| {
            switch (self.module.types.get(field.ty)) {
                .array => |arr| if (arr.len == null) {
                    has_rta = true;
                    break;
                },
                else => {},
            }
        }
        if (!has_rta) return false;
        // Scan expressions for arrayLength calls targeting this global's member.
        for (self.module.functions.items) |function| {
            for (function.exprs.items) |expr| {
                if (expr.data != .call) continue;
                const call = expr.data.call;
                if (call.kind != .builtin or !std.mem.eql(u8, call.name, "arrayLength") or call.args.len != 1) continue;
                const target_expr = function.expr_args.items[call.args.start];
                switch (function.exprs.items[target_expr].data) {
                    .member => |member| {
                        // Walk up to find the global ref.
                        var base = member.base;
                        while (true) {
                            switch (function.exprs.items[base].data) {
                                .global_ref => |idx| {
                                    if (std.mem.eql(u8, self.module.globals.items[idx].name, global_name)) return true;
                                    break;
                                },
                                .load => |inner| base = inner,
                                else => break,
                            }
                        }
                    },
                    else => {},
                }
            }
        }
        return false;
    }

    fn emit_root(self: *Emitter) EmitError!void {
        try self.write("#include <metal_stdlib>\nusing namespace metal;\n");
        // Simdgroup header only needed when subgroup builtins are present.
        if (subgroups.module_uses_subgroups(self.module)) try self.write(subgroups.SIMDGROUP_INCLUDE);
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
                // Runtime-sized array field: emit as elem_type name[1] (flexible member).
                switch (self.module.types.get(field.ty)) {
                    .array => |arr| if (arr.len == null) {
                        try self.emit_type(arr.elem);
                        try self.write(" ");
                        try self.write(field.name);
                        try self.write("[1];\n");
                        continue;
                    },
                    else => {},
                }
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
        if (stage != null and stage.? != .compute) return stage_render.emit_stage_function(self, function_index);

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
            // Add _doe_sizes buffer for runtime array length queries (arrayLength).
            if (stage.? == .compute and self.module_needs_sizes_param()) {
                if (need_comma) try self.write(", ");
                try self.write("constant uint* _doe_sizes [[buffer(");
                try self.write_u32(MSL_SIZES_SLOT);
                try self.write(")]]");
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

    pub fn emit_bound_global_param(self: *Emitter, global: ir.Global) EmitError!void {
        const binding = global.binding orelse return error.InvalidIr;
        if (global.addr_space) |addr_space| switch (addr_space) {
            .uniform => {
                try self.write("constant ");
                try self.emit_type(global.ty);
                try self.write("& ");
                try self.write(global.name);
                try self.write(" [[buffer(");
                try self.write_u32(self.msl_binding_slot(binding));
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
                try self.write_u32(self.msl_binding_slot(binding));
                try self.write(")]]");
                return;
            },
            else => {},
        };
        switch (self.module.types.get(global.ty)) {
            .sampler, .sampler_comparison => {
                try self.write("sampler ");
                try self.write(global.name);
                try self.write(" [[sampler(");
                try self.write_u32(self.msl_binding_slot(binding));
                try self.write(")]]");
            },
            .texture_1d, .texture_2d, .texture_2d_array, .texture_cube, .texture_multisampled_2d, .texture_depth_2d, .texture_depth_cube, .texture_3d, .storage_texture_2d => {
                try self.emit_type(global.ty);
                try self.write(" ");
                try self.write(global.name);
                try self.write(" [[texture(");
                try self.write_u32(self.msl_binding_slot(binding));
                try self.write(")]]");
            },
            else => return error.InvalidIr,
        }
    }

    fn emit_param(self: *Emitter, param: ir.Param) EmitError!void {
        switch (self.module.types.get(param.ty)) {
            .ref => |ref_ty| try self.emit_ref_param(ref_ty, param.name),
            else => {
                try self.emit_type(param.ty);
                try self.write(" ");
                try self.write(param.name);
            },
        }
        if (param.io) |io_attr| {
            if (io_attr.builtin != .none) {
                try self.write(" [[");
                // Subgroup builtins use simdgroup attribute strings; others fall through to maps.
                if (subgroups.msl_subgroup_attribute(io_attr.builtin)) |attr| {
                    try self.write(attr);
                } else {
                    try self.write(maps.msl_builtin_name(io_attr.builtin));
                }
                try self.write("]]");
            } else if (io_attr.location != null) {
                return error.InvalidIr;
            }
        }
    }

    fn emit_ref_param(self: *Emitter, ref_ty: @FieldType(ir.Type, "ref"), name: []const u8) EmitError!void {
        switch (ref_ty.addr_space) {
            .storage => {
                if (ref_ty.access == .read) {
                    try self.write("const device ");
                } else {
                    try self.write("device ");
                }
                switch (self.module.types.get(ref_ty.elem)) {
                    .array => |arr| {
                        try self.emit_type(arr.elem);
                        try self.write("* ");
                    },
                    else => {
                        try self.emit_type(ref_ty.elem);
                        try self.write("& ");
                    },
                }
            },
            .uniform => {
                try self.write("constant ");
                try self.emit_type(ref_ty.elem);
                try self.write("& ");
            },
            .workgroup => {
                try self.write("threadgroup ");
                try self.emit_type(ref_ty.elem);
                try self.write("& ");
            },
            .function, .private => {
                try self.write("thread ");
                try self.emit_type(ref_ty.elem);
                try self.write("& ");
            },
            .handle => return error.InvalidIr,
        }
        try self.write(name);
    }

    pub fn emit_stmt(self: *Emitter, function: ir.Function, stmt_id: ir.StmtId) EmitError!void {
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

    pub fn emit_expr(self: *Emitter, function: ir.Function, expr_id: ir.ExprId) EmitError!void {
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
            .call => |call| try call_builtins.emit_call(self, function, expr.ty, call),
            .construct => |construct| {
                switch (self.module.types.get(construct.ty)) {
                    .array => {
                        // MSL array aggregate init: {a, b, c} — no constructor function syntax.
                        try self.write("{");
                        try self.emit_expr_list(function, construct.args);
                        try self.write("}");
                    },
                    else => {
                        try self.emit_type(construct.ty);
                        try self.write("(");
                        try self.emit_expr_list(function, construct.args);
                        try self.write(")");
                    },
                }
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

    pub fn emit_expr_list(self: *Emitter, function: ir.Function, range: ir.Range) EmitError!void {
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

    pub fn emit_type(self: *Emitter, ty: ir.TypeId) EmitError!void {
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
            .sampler_comparison => try self.write("sampler"),
            .texture_1d => |sample_ty| {
                try self.write("texture1d<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .texture_2d => |sample_ty| {
                try self.write("texture2d<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .texture_2d_array => |sample_ty| {
                try self.write("texture2d_array<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .texture_cube => |sample_ty| {
                try self.write("texturecube<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .texture_multisampled_2d => |sample_ty| {
                try self.write("texture2d_ms<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .texture_depth_2d => try self.write("depth2d<float>"),
            .texture_depth_cube => try self.write("depthcube<float>"),
            .texture_3d => |sample_ty| {
                try self.write("texture3d<");
                try self.emit_type(sample_ty);
                try self.write(">");
            },
            .storage_texture_2d => |storage_tex| {
                try self.write("texture2d<");
                try self.write(maps.msl_storage_texture_elem(storage_tex.format));
                try self.write(", access::");
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

    pub fn write(self: *Emitter, text: []const u8) EmitError!void {
        if (self.pos + text.len > self.buf.len) return error.OutputTooLarge;
        @memcpy(self.buf[self.pos .. self.pos + text.len], text);
        self.pos += text.len;
    }

    pub fn write_indent(self: *Emitter) EmitError!void {
        var i: usize = 0;
        while (i < self.indent) : (i += 1) try self.write(" ");
    }

    pub fn write_u32(self: *Emitter, value: u32) EmitError!void {
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
