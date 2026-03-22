const std = @import("std");
const ir = @import("ir.zig");

pub fn emit_builtin(self: anytype, function: ir.Function, call: @FieldType(ir.Expr, "call")) !bool {
    if (std.mem.eql(u8, call.name, "textureLoad")) {
        if (call.args.len != 3) return error.InvalidIr;
        const texture_expr = function.expr_args.items[call.args.start];
        const coord_expr = function.expr_args.items[call.args.start + 1];
        const level_expr = function.expr_args.items[call.args.start + 2];
        if (is_texture_2d(self.module, function, texture_expr)) {
            try self.write("((all(int2(");
            try self.emit_expr(function, coord_expr);
            try self.write(") >= int2(0)) && all(uint2(int2(");
            try self.emit_expr(function, coord_expr);
            try self.write(")) < uint2(");
            try self.emit_expr(function, texture_expr);
            try self.write(".get_width(uint(");
            try self.emit_expr(function, level_expr);
            try self.write(")), ");
            try self.emit_expr(function, texture_expr);
            try self.write(".get_height(uint(");
            try self.emit_expr(function, level_expr);
            try self.write("))))) ? ");
            try self.emit_expr(function, texture_expr);
            try self.write(".read(uint2(int2(");
            try self.emit_expr(function, coord_expr);
            try self.write(")), uint(");
            try self.emit_expr(function, level_expr);
            try self.write(")) : float4(0.0))");
        } else {
            try self.emit_expr(function, texture_expr);
            try self.write(".read(");
            try self.emit_expr(function, coord_expr);
            try self.write(", ");
            try self.emit_expr(function, level_expr);
            try self.write(")");
        }
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
    if (std.mem.eql(u8, call.name, "textureSampleCompare")) {
        if (call.args.len != 4) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample_compare(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureSampleCompareLevel")) {
        if (call.args.len != 4) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample_compare(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write(", level(0))");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureGather")) {
        if (call.args.len != 4) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(".gather(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write(", component::");
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureGatherCompare")) {
        if (call.args.len != 4) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".gather_compare(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureSampleGrad")) {
        if (call.args.len != 5) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", gradient2d(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 4]);
        try self.write("))");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureSampleOffset")) {
        if (call.args.len != 4) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureSampleLevelOffset")) {
        if (call.args.len != 5) return error.InvalidIr;
        try self.emit_expr(function, function.expr_args.items[call.args.start]);
        try self.write(".sample(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
        try self.write(", ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 2]);
        try self.write(", level(");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 3]);
        try self.write("), ");
        try self.emit_expr(function, function.expr_args.items[call.args.start + 4]);
        try self.write(")");
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureStore")) {
        if (call.args.len != 3) return error.InvalidIr;
        const texture_expr = function.expr_args.items[call.args.start];
        const coord_expr = function.expr_args.items[call.args.start + 1];
        const value_expr = function.expr_args.items[call.args.start + 2];
        if (is_storage_texture_2d(self.module, function, texture_expr)) {
            try self.write("((all(int2(");
            try self.emit_expr(function, coord_expr);
            try self.write(") >= int2(0)) && all(uint2(int2(");
            try self.emit_expr(function, coord_expr);
            try self.write(")) < uint2(");
            try self.emit_expr(function, texture_expr);
            try self.write(".get_width(), ");
            try self.emit_expr(function, texture_expr);
            try self.write(".get_height()))) ? (");
            try self.emit_expr(function, texture_expr);
            try self.write(".write(");
            try self.emit_expr(function, value_expr);
            try self.write(", uint2(int2(");
            try self.emit_expr(function, coord_expr);
            try self.write("))), 0) : 0)");
        } else {
            try self.emit_expr(function, texture_expr);
            try self.write(".write(");
            try self.emit_expr(function, value_expr);
            try self.write(", ");
            try self.emit_expr(function, coord_expr);
            try self.write(")");
        }
        return true;
    }
    if (std.mem.eql(u8, call.name, "textureDimensions")) {
        if (call.args.len < 1 or call.args.len > 2) return error.InvalidIr;
        const target_expr = function.expr_args.items[call.args.start];
        switch (function.exprs.items[target_expr].data) {
            .global_ref => |index| {
                const global = self.module.globals.items[index];
                switch (self.module.types.get(global.ty)) {
                    .texture_1d => {
                        if (call.args.len != 2) return error.InvalidIr;
                        try self.write(global.name);
                        try self.write(".get_width(uint(");
                        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                        try self.write("))");
                        return true;
                    },
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
                    .texture_3d => {
                        if (call.args.len != 2) return error.InvalidIr;
                        try self.write("uint3(");
                        try self.write(global.name);
                        try self.write(".get_width(uint(");
                        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                        try self.write(")), ");
                        try self.write(global.name);
                        try self.write(".get_height(uint(");
                        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                        try self.write(")), ");
                        try self.write(global.name);
                        try self.write(".get_depth(uint(");
                        try self.emit_expr(function, function.expr_args.items[call.args.start + 1]);
                        try self.write(")))");
                        return true;
                    },
                    .texture_cube, .texture_depth_cube => {
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
                    .texture_2d_array => {
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

fn is_texture_2d(module: *const ir.Module, function: ir.Function, expr_id: ir.ExprId) bool {
    return switch (module.types.get(function.exprs.items[expr_id].ty)) {
        .texture_2d => true,
        else => false,
    };
}

fn is_storage_texture_2d(module: *const ir.Module, function: ir.Function, expr_id: ir.ExprId) bool {
    return switch (module.types.get(function.exprs.items[expr_id].ty)) {
        .storage_texture_2d => true,
        else => false,
    };
}
