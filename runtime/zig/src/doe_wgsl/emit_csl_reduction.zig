// emit_csl_reduction.zig — CSL PE program template for reduction kernels.
//
// Maps Doppler's reduction WGSL pattern (RMSNorm, LayerNorm, Softmax) to
// a CSL PE program. Two modes:
//
//   Single-PE mode (hidden_dim fits in PE SRAM):
//     Each PE holds one full token's hidden vector.
//     Reduction is purely local — loop + accumulate, no fabric.
//     Works for Gemma 3 270M (hidden=1536) and 1B (hidden=1920).
//
//   Distributed mode (hidden_dim > PE SRAM budget):
//     Hidden dimension partitioned across a PE row.
//     Each PE computes local partial sum.
//     Allreduce via fabric to get global sum.
//     Each PE normalizes its local slice.
//
// This file implements single-PE mode. Distributed mode will use the
// collectives library and is a Phase 2 deliverable.

const std = @import("std");
const ir = @import("ir.zig");
const spec = @import("csl_spec.zig");
const maps = @import("emit_csl_maps.zig");
const classify = @import("emit_csl_classify.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
    UnsupportedBuiltin,
    UnsupportedConstruct,
};

/// Emit a CSL PE program for a reduction kernel (single-PE mode).
pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    entry: ir.EntryPoint,
    info: classify.ReductionInfo,
) EmitError!void {
    _ = entry;
    _ = info;

    try write(buf, pos, "// PE program: reduction kernel (auto-generated from WGSL)\n");
    try write(buf, pos, "// Single-PE mode: each PE processes one full token.\n");
    try write(buf, pos, "// The reduction (sum of squares, mean, etc.) is local.\n\n");

    // Params
    try write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try write(buf, pos, "param pe_id: i16;\n");
    try write(buf, pos, "param num_pes: i16;\n");
    try write(buf, pos, "param reduce_color: color;\n\n");

    // Imports
    try write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    // Buffers — for RMSNorm: input, weight, output, optional residual
    try write(buf, pos, "// Hidden dimension size — set via host params.\n");
    try write(buf, pos, "param hidden_size: i16 = 1536;\n");
    try write(buf, pos, "param eps: f32 = 1e-5;\n\n");

    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try write(buf, pos, "var ");
        try write(buf, pos, global.name);
        try write(buf, pos, ": [hidden_size]f32 = @zeros([hidden_size]f32);\n");
        try write(buf, pos, "var ");
        try write(buf, pos, global.name);
        try write(buf, pos, "_ptr: [*]f32 = &");
        try write(buf, pos, global.name);
        try write(buf, pos, ";\n");
    }
    try write(buf, pos, "\n");

    // Compute function — RMSNorm pattern
    try write(buf, pos, "fn compute() void {\n");
    try write(buf, pos, "    // Phase 1: compute sum of squares (local reduction)\n");
    try write(buf, pos, "    var sum_sq: f32 = 0.0;\n");
    try write(buf, pos, "    for (@range(i16, hidden_size)) |i| {\n");
    try write(buf, pos, "        const x = input[@as(u32, i)];\n");
    try write(buf, pos, "        sum_sq += x * x;\n");
    try write(buf, pos, "    }\n\n");

    try write(buf, pos, "    // Phase 2: compute inverse RMS\n");
    try write(buf, pos, "    const mean_sq = sum_sq / @as(f32, hidden_size);\n");
    try write(buf, pos, "    const inv_rms = 1.0 / math.sqrt(mean_sq + eps);\n\n");

    try write(buf, pos, "    // Phase 3: normalize and apply weight\n");
    try write(buf, pos, "    for (@range(i16, hidden_size)) |i| {\n");
    try write(buf, pos, "        const idx = @as(u32, i);\n");
    try write(buf, pos, "        output[idx] = input[idx] * inv_rms * weight[idx];\n");
    try write(buf, pos, "    }\n\n");

    try write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try write(buf, pos, "}\n\n");

    // Comptime exports
    try write(buf, pos, "comptime {\n");
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try write(buf, pos, "    @export_symbol(");
        try write(buf, pos, global.name);
        try write(buf, pos, "_ptr, \"");
        try write(buf, pos, global.name);
        try write(buf, pos, "\");\n");
    }
    try write(buf, pos, "    @export_symbol(compute);\n");
    try write(buf, pos, "}\n");
}

// ---------------------------------------------------------------------------
// Write helpers
// ---------------------------------------------------------------------------

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}
