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
