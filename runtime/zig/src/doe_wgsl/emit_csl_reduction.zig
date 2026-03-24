// emit_csl_reduction.zig — CSL PE program emitter for reduction kernels.
//
// Maps Doppler's reduction WGSL patterns (RMSNorm, LayerNorm, Softmax) to
// CSL PE programs. Single-PE mode: each PE holds one full token's hidden
// vector. Barriers become no-ops, shared memory becomes PE-local.

const std = @import("std");
const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");
const walk = W.Emit(.{ .skip_barriers = true, .runtime_array_size = "hidden_size" });

pub const EmitError = W.EmitError;

/// Emit a CSL PE program for a reduction kernel (single-PE mode).
pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.ReductionInfo,
) EmitError!void {
    _ = info;
    const function = &module.functions.items[entry.function];

    try W.write(buf, pos, "// PE program: reduction kernel (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Single-PE mode: each PE processes one full token.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param reduce_color: color;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    try walk.uniformParams(buf, pos, module);
    try walk.storageBuffers(buf, pos, module);
    try walk.workgroupBuffers(buf, pos, module);
    try walk.helperFunctions(buf, pos, module);
    try emitComputeFunction(buf, pos, module, function);

    // Reduction only exports storage (not uniform) in comptime block.
    try W.write(buf, pos, "comptime {\n");
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try W.write(buf, pos, "    @export_symbol(");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "_ptr, \"");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "\");\n");
    }
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}

fn emitComputeFunction(buf: []u8, pos: *usize, module: *const ir.Module, function: *const ir.Function) EmitError!void {
    try W.write(buf, pos, "fn compute() void {\n");
    if (function.stmts.items.len > 0) {
        // Walk root block, skipping barriers (handled by walk config).
        const root = function.stmts.items[function.root_stmt];
        switch (root) {
            .block => |range| {
                var i: u32 = 0;
                while (i < range.len) : (i += 1) {
                    const cid = function.stmt_children.items[range.start + i];
                    try walk.stmt(buf, pos, module, function, cid, 1);
                }
            },
            else => try walk.stmt(buf, pos, module, function, function.root_stmt, 1),
        }
    }
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");
}
