const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_hlsl_maps.zig");

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

    try emit_impl_function(self, function_index);
    try emit_output_struct(self, function, stage);
    try emit_wrapper_function(self, function_index, stage);
}

fn emit_impl_function(self: anytype, function_index: ir.FunctionId) !void {
    const function = self.module.functions.items[function_index];
    try self.write("\n");
    try self.emit_type_only(function.return_type);
    try self.write(" ");
    try self.write(function.name);
    try self.write("_impl(");
    for (function.params.items, 0..) |param, index| {
        if (index > 0) try self.write(", ");
        try self.emit_typed_name(param.ty, param.name);
    }
    try self.write(") {\n");
    self.indent += 4;
    try self.emit_stmt(function, function.root_stmt);
    self.indent -= 4;
    try self.write("}\n");
}

fn emit_output_struct(self: anytype, function: ir.Function, stage: ir.ShaderStage) !void {
    try self.write("\nstruct ");
    try self.write(function.name);
    try self.write("_stage_out {\n");
    self.indent += 4;
    try self.write_indent();
    try self.emit_typed_name(function.return_type, "value");
    try self.write(" : ");
    try write_output_semantic(self, stage, function.return_io.?);
    try self.write(";\n");
    self.indent -= 4;
    try self.write("};\n");
}

fn emit_wrapper_function(self: anytype, function_index: ir.FunctionId, stage: ir.ShaderStage) !void {
    _ = stage;
    const function = self.module.functions.items[function_index];
    try self.write("\n");
    try self.write(function.name);
    try self.write("_stage_out ");
    try self.write(function.name);
    try self.write("(");
    for (function.params.items, 0..) |param, index| {
        if (index > 0) try self.write(", ");
        try self.emit_typed_name(param.ty, param.name);
        try self.write(" : ");
        try write_input_semantic(self, param.io.?);
    }
    try self.write(") {\n");
    self.indent += 4;
    try self.write_indent();
    try self.write(function.name);
    try self.write("_stage_out out;\n");
    try self.write_indent();
    try self.write("out.value = ");
    try self.write(function.name);
    try self.write("_impl(");
    for (function.params.items, 0..) |param, index| {
        if (index > 0) try self.write(", ");
        try self.write(param.name);
    }
    try self.write(");\n");
    try self.write_indent();
    try self.write("return out;\n");
    self.indent -= 4;
    try self.write("}\n");
}

fn write_input_semantic(self: anytype, io: ir.IoAttr) !void {
    if (io.location) |loc| {
        try self.write("TEXCOORD");
        try self.write_u32(loc);
        return;
    }
    try self.write(maps.hlsl_builtin_name(io.builtin));
}

fn write_output_semantic(self: anytype, stage: ir.ShaderStage, io: ir.IoAttr) !void {
    if (io.location) |loc| {
        try self.write(if (stage == .fragment) "SV_Target" else "TEXCOORD");
        try self.write_u32(loc);
        return;
    }
    try self.write(maps.hlsl_builtin_name(io.builtin));
}
