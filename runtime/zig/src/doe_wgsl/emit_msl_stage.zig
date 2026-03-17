const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_msl_maps.zig");

pub fn emit_stage_function(self: anytype, function_index: ir.FunctionId) !void {
    const function = self.module.functions.items[function_index];
    const stage = function.stage orelse return error.InvalidIr;
    if (stage == .compute) return error.InvalidIr;
    // Need either scalar return with IO attr, or struct return with IO fields.
    if (function.return_io == null and !is_io_struct(self, function.return_type)) return error.InvalidIr;

    try emit_stage_in_struct(self, function, stage);
    try emit_stage_out_struct(self, function, stage);
    try emit_impl_function(self, function_index);
    try emit_wrapper_function(self, function_index, stage);
}

pub fn runtime_array_needs_size_param(self: anytype, global_name: []const u8) bool {
    for (self.module.functions.items) |function| {
        for (function.exprs.items) |expr| {
            if (expr.data != .call) continue;
            const call = expr.data.call;
            if (call.kind != .builtin or !std.mem.eql(u8, call.name, "arrayLength") or call.args.len != 1) continue;
            const target_expr = function.expr_args.items[call.args.start];
            switch (function.exprs.items[target_expr].data) {
                .global_ref => |index| if (std.mem.eql(u8, self.module.globals.items[index].name, global_name)) return true,
                else => {},
            }
        }
    }
    return false;
}

// Returns true if an IO attribute designates a stage_in field (location or position builtin).
fn is_stage_in_io(io: ir.IoAttr) bool {
    return io.location != null or io.builtin == .position;
}

fn is_io_struct(self: anytype, ty: ir.TypeId) bool {
    return switch (self.module.types.get(ty)) {
        .struct_ => |struct_id| {
            const struct_def = self.module.structs.items[struct_id];
            for (struct_def.fields.items) |field| {
                if (field.io != null) return true;
            }
            return false;
        },
        else => false,
    };
}

fn get_struct_def(self: anytype, ty: ir.TypeId) ?*const ir.StructDef {
    return switch (self.module.types.get(ty)) {
        .struct_ => |struct_id| &self.module.structs.items[struct_id],
        else => null,
    };
}

fn needs_stage_in(self: anytype, function: ir.Function) bool {
    for (function.params.items) |param| {
        if (get_struct_def(self, param.ty)) |struct_def| {
            for (struct_def.fields.items) |field| {
                const io = field.io orelse continue;
                if (is_stage_in_io(io)) return true;
            }
        } else {
            const io = param.io orelse continue;
            if (is_stage_in_io(io)) return true;
        }
    }
    return false;
}

fn emit_input_io_attr(self: anytype, io: ir.IoAttr, stage: ir.ShaderStage) !void {
    if (io.location) |loc| {
        try self.write(if (stage == .vertex) "attribute(" else "user(loc");
        try self.write_u32(loc);
        try self.write(")");
    } else {
        try self.write(maps.msl_builtin_name(io.builtin));
    }
}

fn emit_output_io_attr(self: anytype, io: ir.IoAttr, stage: ir.ShaderStage) !void {
    if (io.blend_src) |src_index| {
        try self.write("color(0), index(");
        try self.write_u32(src_index);
        try self.write(")");
    } else if (io.location) |loc| {
        try self.write(if (stage == .fragment) "color(" else "user(loc");
        try self.write_u32(loc);
        try self.write(")");
    } else {
        try self.write(maps.msl_builtin_name(io.builtin));
    }
}

fn emit_stage_in_struct(self: anytype, function: ir.Function, stage: ir.ShaderStage) !void {
    if (!needs_stage_in(self, function)) return;
    try self.write("\nstruct ");
    try self.write(function.name);
    try self.write("_stage_in {\n");
    self.indent += 4;
    var flat_index: u32 = 0;
    for (function.params.items) |param| {
        if (get_struct_def(self, param.ty)) |struct_def| {
            for (struct_def.fields.items) |field| {
                const io = field.io orelse continue;
                if (!is_stage_in_io(io)) continue;
                try self.write_indent();
                try self.emit_type(field.ty);
                try self.write(" p");
                try self.write_u32(flat_index);
                try self.write(" [[");
                try emit_input_io_attr(self, io, stage);
                try self.write("]];\n");
                flat_index += 1;
            }
        } else {
            const io = param.io orelse continue;
            if (!is_stage_in_io(io)) continue;
            try self.write_indent();
            try self.emit_type(param.ty);
            try self.write(" p");
            try self.write_u32(flat_index);
            try self.write(" [[");
            try emit_input_io_attr(self, io, stage);
            try self.write("]];\n");
            flat_index += 1;
        }
    }
    self.indent -= 4;
    try self.write("};\n");
}

fn emit_stage_out_struct(self: anytype, function: ir.Function, stage: ir.ShaderStage) !void {
    try self.write("\nstruct ");
    try self.write(function.name);
    try self.write("_stage_out {\n");
    self.indent += 4;
    if (function.return_io) |io| {
        try self.write_indent();
        if (io.builtin == .clip_distances) {
            const arr_len = switch (self.module.types.get(function.return_type)) {
                .array => |arr| arr.len orelse 8,
                else => 8,
            };
            try self.write("float value [[clip_distance]] [");
            try self.write_u32(arr_len);
            try self.write("];\n");
        } else {
            try self.emit_type(function.return_type);
            try self.write(" value [[");
            try emit_output_io_attr(self, io, stage);
            try self.write("]];\n");
        }
    } else if (get_struct_def(self, function.return_type)) |struct_def| {
        for (struct_def.fields.items) |field| {
            const io = field.io orelse continue;
            try self.write_indent();
            try self.emit_type(field.ty);
            try self.write(" ");
            try self.write(field.name);
            try self.write(" [[");
            try emit_output_io_attr(self, io, stage);
            try self.write("]];\n");
        }
    }
    self.indent -= 4;
    try self.write("};\n");
}

fn emit_impl_function(self: anytype, function_index: ir.FunctionId) !void {
    const function = self.module.functions.items[function_index];
    try self.write("\n");
    try self.emit_type(function.return_type);
    try self.write(" ");
    try self.write(function.name);
    try self.write("_impl(");
    var need_comma = false;
    for (self.module.globals.items) |global| {
        if (global.binding == null) continue;
        if (need_comma) try self.write(", ");
        try self.emit_bound_global_param(global);
        need_comma = true;
    }
    for (function.params.items) |param| {
        if (need_comma) try self.write(", ");
        try self.emit_type(param.ty);
        try self.write(" ");
        try self.write(param.name);
        need_comma = true;
    }
    try self.write(") {\n");
    self.indent += 4;
    try self.emit_stmt(function, function.root_stmt);
    self.indent -= 4;
    try self.write("}\n");
}

fn emit_wrapper_function(self: anytype, function_index: ir.FunctionId, stage: ir.ShaderStage) !void {
    const function = self.module.functions.items[function_index];
    try self.write("\n");
    try self.write(switch (stage) {
        .vertex => "vertex ",
        .fragment => "fragment ",
        .compute => return error.InvalidIr,
    });
    try self.write(function.name);
    try self.write("_stage_out ");
    try self.write(maps.msl_function_name(function.name, stage));
    try self.write("(");
    var need_comma = false;
    // Bound globals (textures, buffers, etc.)
    for (self.module.globals.items) |global| {
        if (global.binding == null) continue;
        if (need_comma) try self.write(", ");
        try self.emit_bound_global_param(global);
        need_comma = true;
    }
    // Stage-in struct
    if (needs_stage_in(self, function)) {
        if (need_comma) try self.write(", ");
        try self.write(function.name);
        try self.write("_stage_in in [[stage_in]]");
        need_comma = true;
    }
    // Non-stage-in builtin params (passed directly with [[builtin]] attribute)
    for (function.params.items) |param| {
        if (get_struct_def(self, param.ty)) |struct_def| {
            for (struct_def.fields.items) |field| {
                const io = field.io orelse continue;
                if (is_stage_in_io(io)) continue;
                if (need_comma) try self.write(", ");
                try self.emit_type(field.ty);
                try self.write(" _blt_");
                try self.write(field.name);
                try self.write(" [[");
                try self.write(maps.msl_builtin_name(io.builtin));
                try self.write("]]");
                need_comma = true;
            }
        } else {
            const io = param.io orelse continue;
            if (is_stage_in_io(io)) continue;
            if (need_comma) try self.write(", ");
            try self.emit_type(param.ty);
            try self.write(" ");
            try self.write(param.name);
            try self.write(" [[");
            try self.write(maps.msl_builtin_name(io.builtin));
            try self.write("]]");
            need_comma = true;
        }
    }
    try self.write(") {\n");
    self.indent += 4;

    // Body: extract stage_in values and construct params
    var flat_index: u32 = 0;
    for (function.params.items) |param| {
        if (get_struct_def(self, param.ty)) |struct_def| {
            // Struct param: create local, assign fields from stage_in and builtins
            try self.write_indent();
            try self.emit_type(param.ty);
            try self.write(" ");
            try self.write(param.name);
            try self.write(";\n");
            for (struct_def.fields.items) |field| {
                const io = field.io orelse continue;
                try self.write_indent();
                try self.write(param.name);
                try self.write(".");
                try self.write(field.name);
                try self.write(" = ");
                if (is_stage_in_io(io)) {
                    try self.write("in.p");
                    try self.write_u32(flat_index);
                    flat_index += 1;
                } else {
                    try self.write("_blt_");
                    try self.write(field.name);
                }
                try self.write(";\n");
            }
        } else {
            const io = param.io orelse continue;
            if (!is_stage_in_io(io)) continue;
            try self.write_indent();
            try self.write("const ");
            try self.emit_type(param.ty);
            try self.write(" ");
            try self.write(param.name);
            try self.write(" = in.p");
            try self.write_u32(flat_index);
            try self.write(";\n");
            flat_index += 1;
        }
    }

    // Call impl and handle return
    try self.write_indent();
    try self.write(function.name);
    try self.write("_stage_out out;\n");

    const is_struct_return = function.return_io == null and get_struct_def(self, function.return_type) != null;
    if (is_struct_return) {
        try self.write_indent();
        try self.emit_type(function.return_type);
        try self.write(" _result = ");
    } else {
        try self.write_indent();
        try self.write("out.value = ");
    }
    try self.write(function.name);
    try self.write("_impl(");
    need_comma = false;
    for (self.module.globals.items) |global| {
        if (global.binding == null) continue;
        if (need_comma) try self.write(", ");
        try self.write(global.name);
        need_comma = true;
        switch (self.module.types.get(global.ty)) {
            .array => |arr| if (arr.len == null and runtime_array_needs_size_param(self, global.name)) {
                try self.write(", ");
                try self.write(global.name);
                try self.write("_size");
            },
            else => {},
        }
    }
    for (function.params.items) |param| {
        if (need_comma) try self.write(", ");
        try self.write(param.name);
        need_comma = true;
    }
    try self.write(");\n");

    // For struct return, copy fields from result to stage_out
    if (is_struct_return) {
        if (get_struct_def(self, function.return_type)) |struct_def| {
            for (struct_def.fields.items) |field| {
                if (field.io == null) continue;
                try self.write_indent();
                try self.write("out.");
                try self.write(field.name);
                try self.write(" = _result.");
                try self.write(field.name);
                try self.write(";\n");
            }
        }
    }

    try self.write_indent();
    try self.write("return out;\n");
    self.indent -= 4;
    try self.write("}\n");
}
