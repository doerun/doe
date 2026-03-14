const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_msl_maps.zig");

pub fn emit_stage_function(self: anytype, function_index: ir.FunctionId) !void {
    const function = self.module.functions.items[function_index];
    const stage = function.stage orelse return error.InvalidIr;
    if (stage == .compute or function.return_io == null) return error.InvalidIr;
    for (function.params.items) |param| {
        if (switch (self.module.types.get(param.ty)) {
            .struct_ => true,
            else => false,
        }) return error.InvalidIr;
    }

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

fn emit_stage_in_struct(self: anytype, function: ir.Function, stage: ir.ShaderStage) !void {
    if (!needs_stage_in(function)) return;
    try self.write("\nstruct ");
    try self.write(function.name);
    try self.write("_stage_in {\n");
    self.indent += 4;
    for (function.params.items, 0..) |param, index| {
        const io = param.io orelse continue;
        if (io.location == null and io.builtin != .position) continue;
        try self.write_indent();
        try self.emit_type(param.ty);
        try self.write(" p");
        try self.write_u32(@intCast(index));
        try self.write(" [[");
        if (io.location) |loc| {
            try self.write(if (stage == .vertex) "attribute(" else "user(loc");
            try self.write_u32(loc);
            try self.write(")");
        } else {
            try self.write(maps.msl_builtin_name(io.builtin));
        }
        try self.write("]];\n");
    }
    self.indent -= 4;
    try self.write("};\n");
}

fn emit_stage_out_struct(self: anytype, function: ir.Function, stage: ir.ShaderStage) !void {
    try self.write("\nstruct ");
    try self.write(function.name);
    try self.write("_stage_out {\n");
    self.indent += 4;
    try self.write_indent();
    try self.emit_type(function.return_type);
    try self.write(" value [[");
    const io = function.return_io.?;
    if (io.location) |loc| {
        try self.write(if (stage == .fragment) "color(" else "user(loc");
        try self.write_u32(loc);
        try self.write(")");
    } else {
        try self.write(maps.msl_builtin_name(io.builtin));
    }
    try self.write("]];\n");
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
    for (self.module.globals.items) |global| {
        if (global.binding == null) continue;
        if (need_comma) try self.write(", ");
        try self.emit_bound_global_param(global);
        need_comma = true;
    }
    if (needs_stage_in(function)) {
        if (need_comma) try self.write(", ");
        try self.write(function.name);
        try self.write("_stage_in in [[stage_in]]");
        need_comma = true;
    }
    for (function.params.items) |param| {
        const io = param.io orelse continue;
        if (io.location != null or io.builtin == .position) continue;
        if (need_comma) try self.write(", ");
        try self.emit_type(param.ty);
        try self.write(" ");
        try self.write(param.name);
        try self.write(" [[");
        try self.write(maps.msl_builtin_name(io.builtin));
        try self.write("]]");
        need_comma = true;
    }
    try self.write(") {\n");
    self.indent += 4;
    for (function.params.items, 0..) |param, index| {
        const io = param.io orelse continue;
        if (io.location == null and io.builtin != .position) continue;
        try self.write_indent();
        try self.write("const ");
        try self.emit_type(param.ty);
        try self.write(" ");
        try self.write(param.name);
        try self.write(" = in.p");
        try self.write_u32(@intCast(index));
        try self.write(";\n");
    }
    try self.write_indent();
    try self.write(function.name);
    try self.write("_stage_out out;\n");
    try self.write_indent();
    try self.write("out.value = ");
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
    try self.write_indent();
    try self.write("return out;\n");
    self.indent -= 4;
    try self.write("}\n");
}

fn needs_stage_in(function: ir.Function) bool {
    for (function.params.items) |param| {
        const io = param.io orelse continue;
        if (io.location != null or io.builtin == .position) return true;
    }
    return false;
}
