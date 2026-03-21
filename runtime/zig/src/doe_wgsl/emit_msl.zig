const emit_msl_ir = @import("emit_msl_ir.zig");
const ir = @import("ir.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
};

pub const MAX_OUTPUT: usize = emit_msl_ir.MAX_OUTPUT;

pub fn emit(module: *const ir.Module, out: []u8) EmitError!usize {
    return emit_msl_ir.emit(module, out) catch |err| switch (err) {
        error.OutputTooLarge => error.OutputTooLarge,
        error.InvalidIr => error.InvalidIr,
    };
}

pub fn moduleNeedsSizesParam(module_ir: *const ir.Module) bool {
    const std = @import("std");
    for (module_ir.globals.items) |global| {
        switch (module_ir.types.get(global.ty)) {
            .array => |arr| if (arr.len == null) return true,
            else => {},
        }
    }
    _ = std;
    return false;
}
