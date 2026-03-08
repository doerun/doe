const ast_mod = @import("ast.zig");
const emit_msl_ir = @import("emit_msl_ir.zig");
const ir_builder = @import("ir_builder.zig");
const sema = @import("sema.zig");

const Ast = ast_mod.Ast;

pub const EmitError = error{
    OutputTooLarge,
    InvalidAst,
};

pub const MAX_OUTPUT: usize = emit_msl_ir.MAX_OUTPUT;

pub fn emit(tree: *const Ast, out: []u8) EmitError!usize {
    var semantic = sema.analyze(tree.allocator, tree) catch return error.InvalidAst;
    defer semantic.deinit();

    var module = ir_builder.build(tree.allocator, tree, &semantic) catch return error.InvalidAst;
    defer module.deinit();

    return emit_msl_ir.emit(&module, out) catch |err| switch (err) {
        error.OutputTooLarge => error.OutputTooLarge,
        error.InvalidIr => error.InvalidAst,
    };
}
