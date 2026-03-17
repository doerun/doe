const std = @import("std");
const ir = @import("ir.zig");
const maps = @import("emit_hlsl_maps.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

/// Try to emit an HLSL texture builtin call. Returns true if the call was
/// handled, false if it is not a texture builtin and the caller should
/// continue matching other builtins.
pub fn emit_texture_builtin(
    module: *const ir.Module,
    buf: []u8,
    pos: *usize,
    function: ir.Function,
    call_name: []const u8,
    args: ir.Range,
) EmitError!bool {
    var ctx = WriteCtx{ .module = module, .buf = buf, .pos = pos };

    if (std.mem.eql(u8, call_name, "textureLoad")) {
        if (args.len != 3) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".Load(int3(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write("))");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSample")) {
        if (args.len != 3) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".Sample(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSampleLevel")) {
        if (args.len != 4) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".SampleLevel(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSampleCompare")) {
        if (args.len != 4) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".SampleCmp(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSampleCompareLevel")) {
        if (args.len != 4) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".SampleCmpLevelZero(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureGather")) {
        if (args.len != 4) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(".GatherRed(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureGatherCompare")) {
        if (args.len != 4) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".GatherCmp(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSampleGrad")) {
        if (args.len != 5) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".SampleGrad(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 4]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSampleOffset")) {
        if (args.len != 4) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".Sample(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureSampleLevelOffset")) {
        if (args.len != 5) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write(".SampleLevel(");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 3]);
        try ctx.write(", ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 4]);
        try ctx.write(")");
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureStore")) {
        if (args.len != 3) return error.InvalidIr;
        try ctx.emit_expr(function, function.expr_args.items[args.start]);
        try ctx.write("[");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
        try ctx.write("] = ");
        try ctx.emit_expr(function, function.expr_args.items[args.start + 2]);
        return true;
    }
    if (std.mem.eql(u8, call_name, "textureDimensions")) {
        if (args.len < 1 or args.len > 2) return error.InvalidIr;
        const target_expr = function.expr_args.items[args.start];
        switch (function.exprs.items[target_expr].data) {
            .global_ref => |index| {
                const global = module.globals.items[index];
                try ctx.write("doe_textureDimensions_");
                try ctx.write(global.name);
                switch (module.types.get(global.ty)) {
                    .texture_2d => {
                        if (args.len != 2) return error.InvalidIr;
                        try ctx.write("(uint(");
                        try ctx.emit_expr(function, function.expr_args.items[args.start + 1]);
                        try ctx.write("))");
                        return true;
                    },
                    .storage_texture_2d => {
                        if (args.len != 1) return error.InvalidIr;
                        try ctx.write("()");
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

/// Lightweight write context that shares the Emitter's buffer and position.
const WriteCtx = struct {
    module: *const ir.Module,
    buf: []u8,
    pos: *usize,

    fn write(self: *WriteCtx, text: []const u8) EmitError!void {
        if (self.pos.* + text.len > self.buf.len) return error.OutputTooLarge;
        @memcpy(self.buf[self.pos.* .. self.pos.* + text.len], text);
        self.pos.* += text.len;
    }

    fn emit_expr(self: *WriteCtx, function: ir.Function, expr_id: ir.ExprId) EmitError!void {
        const expr = function.exprs.items[expr_id];
        switch (expr.data) {
            .int_lit => |value| {
                var buf_local: [32]u8 = undefined;
                const text = std.fmt.bufPrint(&buf_local, "{}", .{value}) catch return error.OutputTooLarge;
                try self.write(text);
            },
            .float_lit => |value| {
                var buf_local: [64]u8 = undefined;
                const text = std.fmt.bufPrint(&buf_local, "{d}", .{value}) catch return error.OutputTooLarge;
                try self.write(text);
                if (std.mem.indexOfScalar(u8, text, '.') == null and std.mem.indexOfAny(u8, text, "eE") == null) {
                    try self.write(".0");
                }
            },
            .global_ref => |index| try self.write(self.module.globals.items[index].name),
            .local_ref => |index| try self.write(function.locals.items[index].name),
            .call => |call| {
                try self.write(call.name);
                try self.write("(");
                var i: u32 = 0;
                while (i < call.args.len) : (i += 1) {
                    if (i > 0) try self.write(", ");
                    try self.emit_expr(function, function.expr_args.items[call.args.start + i]);
                }
                try self.write(")");
            },
            .member => |member| {
                try self.emit_expr(function, member.base);
                try self.write(".");
                try self.write(member.field_name);
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
            .construct => |construct| {
                const module = self.module;
                switch (module.types.get(construct.ty)) {
                    .vector => |vec| {
                        const prefix = switch (module.types.get(vec.elem)) {
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
                        try self.write(prefix);
                        var buf_local: [32]u8 = undefined;
                        const len_text = std.fmt.bufPrint(&buf_local, "{}", .{vec.len}) catch return error.OutputTooLarge;
                        try self.write(len_text);
                    },
                    else => return error.InvalidIr,
                }
                try self.write("(");
                var i: u32 = 0;
                while (i < construct.args.len) : (i += 1) {
                    if (i > 0) try self.write(", ");
                    try self.emit_expr(function, function.expr_args.items[construct.args.start + i]);
                }
                try self.write(")");
            },
            .index => |index| {
                try self.emit_expr(function, index.base);
                try self.write("[");
                try self.emit_expr(function, index.index);
                try self.write("]");
            },
            else => return error.InvalidIr,
        }
    }
};
