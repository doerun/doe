const std = @import("std");
const ir = @import("ir.zig");

pub fn emit_builtin(self: anytype, function: ir.Function, call: @FieldType(ir.Expr, "call")) !bool {
    if (std.mem.eql(u8, call.name, "textureLoad")) {
        if (call.args.len != 3) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".read(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureSample")) {
        if (call.args.len != 3) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureSampleLevel")) {
        if (call.args.len != 4) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", level(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write("))");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureStore")) {
        if (call.args.len != 3) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".write(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureDimensions")) {
        if (call.args.len < 1 or call.args.len > 2) return error.InvalidIr;
        const target_expr = function.expr_args.items[call.args.start];
        switch (function.exprs.items[target_expr].data) {
            .global_ref => |index| {
                const global = self.module.globals.items[index];
                switch (self.module.types.get(global.ty)) {
                    .texture_2d => {
                        if (call.args.len != 2) return error.InvalidIr;
                        try self.write("uint2(");
                        try self.write(global.name);
                        try self.write(".get_width(uint(");
                        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                        try self.write(")), ");
                        try self.write(global.name);
                        try self.write(".get_height(uint(");
                        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                        try self.write(")))");
                        return true;
                    },
                    .storage_texture_2d => {
                        if (call.args.len != 1) return error.InvalidIr;
                        try self.write("uint2(");
                        try self.write(global.name);
                        try self.write(".get_width(), ");
                        try self.write(global.name);
                        try self.write(".get_height())");
                        return true;
                    },
                    else => return error.InvalidIr,
                }
            },
            else => return error.InvalidIr,
        }
    }
    return false;
}
