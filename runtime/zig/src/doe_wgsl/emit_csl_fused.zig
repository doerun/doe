// emit_csl_fused.zig — CSL PE program for fused GEMV + Q4K dequant.
//
// On-the-fly dequantization during matrix-vector multiply for decode.
// Each PE holds a slice of the quantized weight matrix, dequants and
// computes partial dot products, then fabric reduces to get the final
// output vector.
//
// Maps from Doppler's fused_matmul_q4.wgsl. Buffer names from IR.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.FusedGemvDequantInfo,
) EmitError!void {
    const act = module.globals.items[info.activation_global].name;
    const wgt = module.globals.items[info.weight_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: fused GEMV + Q4K dequant (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Each PE dequants its weight slice and computes partial dot products.\n");
    try W.write(buf, pos, "// Fabric allreduce accumulates the final output vector.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param reduce_color: color;\n\n");

    try W.write(buf, pos, "param out_dim: i16;\n");
    try W.write(buf, pos, "param in_dim_per_pe: i16;\n");
    try W.write(buf, pos, "param num_blocks_per_row: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    // Q4K constants
    try W.write(buf, pos, "const QK_K: u32 = 256;\n");
    try W.write(buf, pos, "const Q4K_BLOCK_BYTES: u32 = 144;\n\n");

    // Buffers
    try emitBuf(buf, pos, act, "[in_dim_per_pe]f32");
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, ": [out_dim * num_blocks_per_row * Q4K_BLOCK_BYTES]u8 = @zeros([out_dim * num_blocks_per_row * Q4K_BLOCK_BYTES]u8);\n");
    try emitBuf(buf, pos, out, "[out_dim]f32");
    try W.write(buf, pos, "var partial: [out_dim]f32 = @zeros([out_dim]f32);\n\n");

    try emitPtr(buf, pos, act, "f32");
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, "_ptr: [*]u8 = &");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, ";\n");
    try emitPtr(buf, pos, out, "f32");
    try W.write(buf, pos, "\n");

    // Fabric DSDs
    try W.write(buf, pos, "const reduce_out = @get_dsd(fabout_dsd, .{ .extent = 1, .fabric_color = reduce_color });\n");
    try W.write(buf, pos, "const reduce_in = @get_dsd(fabin_dsd, .{ .extent = 1, .fabric_color = reduce_color });\n\n");
    try W.write(buf, pos, "const reduce_task_id: local_task_id = @get_local_task_id(10);\n");
    try W.write(buf, pos, "const done_task_id: local_task_id = @get_local_task_id(11);\n");
    try W.write(buf, pos, "var reduce_dim: i16 = 0;\n\n");

    // Phase 1: local partial dot products with on-the-fly dequant
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    for (@range(i16, out_dim)) |row| {\n");
    try W.write(buf, pos, "        var sum: f32 = 0.0;\n");
    try W.write(buf, pos, "        const row_base = @as(u32, row) * @as(u32, num_blocks_per_row) * Q4K_BLOCK_BYTES;\n\n");

    try W.write(buf, pos, "        for (@range(i16, num_blocks_per_row)) |blk| {\n");
    try W.write(buf, pos, "            const blk_base = row_base + @as(u32, blk) * Q4K_BLOCK_BYTES;\n");
    try W.write(buf, pos, "            const d_bits = @as(u16, ");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, "[blk_base]) | (@as(u16, ");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, "[blk_base + 1]) << 8);\n");
    try W.write(buf, pos, "            const d = @as(f32, @bitcast(f16, d_bits));\n");
    try W.write(buf, pos, "            const data_off = blk_base + 16;\n");
    try W.write(buf, pos, "            const act_off = @as(u32, blk) * QK_K;\n\n");

    try W.write(buf, pos, "            for (@range(u32, 128)) |i| {\n");
    try W.write(buf, pos, "                const byte = ");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, "[data_off + i];\n");
    try W.write(buf, pos, "                const lo = @as(f32, byte & 0x0F) * d;\n");
    try W.write(buf, pos, "                const hi = @as(f32, byte >> 4) * d;\n");
    try W.write(buf, pos, "                sum += lo * ");
    try W.write(buf, pos, act);
    try W.write(buf, pos, "[act_off + i * 2];\n");
    try W.write(buf, pos, "                sum += hi * ");
    try W.write(buf, pos, act);
    try W.write(buf, pos, "[act_off + i * 2 + 1];\n");
    try W.write(buf, pos, "            }\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        partial[@as(u32, row)] = sum;\n");
    try W.write(buf, pos, "    }\n\n");

    try W.write(buf, pos, "    reduce_dim = 0;\n");
    try W.write(buf, pos, "    @fmovs(reduce_out, partial[0]);\n");
    try W.write(buf, pos, "}\n\n");

    // Phase 2: fabric reduce partial sums
    try W.write(buf, pos, "task reduce_recv() void {\n");
    try W.write(buf, pos, "    var incoming: f32 = 0.0;\n");
    try W.write(buf, pos, "    @fmovs(incoming, reduce_in);\n");
    try W.write(buf, pos, "    ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, reduce_dim)] = partial[@as(u32, reduce_dim)] + incoming;\n\n");
    try W.write(buf, pos, "    reduce_dim += 1;\n");
    try W.write(buf, pos, "    if (reduce_dim < out_dim) {\n");
    try W.write(buf, pos, "        @fmovs(reduce_out, partial[@as(u32, reduce_dim)]);\n");
    try W.write(buf, pos, "    } else {\n");
    try W.write(buf, pos, "        if (pe_id == num_pes - 1) {\n");
    try W.write(buf, pos, "            sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    try W.write(buf, pos, "    @bind_local_task(reduce_recv, reduce_task_id);\n");
    try W.write(buf, pos, "    @set_local_color_config(reduce_color, .{ .recv_task = reduce_task_id });\n");
    try emitExport(buf, pos, act);
    try emitExportTyped(buf, pos, wgt);
    try emitExport(buf, pos, out);
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}

fn emitBuf(buf: []u8, pos: *usize, name: []const u8, ty: []const u8) EmitError!void {
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, name);
    try W.write(buf, pos, ": ");
    try W.write(buf, pos, ty);
    try W.write(buf, pos, " = @zeros(");
    try W.write(buf, pos, ty);
    try W.write(buf, pos, ");\n");
}

fn emitPtr(buf: []u8, pos: *usize, name: []const u8, elem: []const u8) EmitError!void {
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "_ptr: [*]");
    try W.write(buf, pos, elem);
    try W.write(buf, pos, " = &");
    try W.write(buf, pos, name);
    try W.write(buf, pos, ";\n");
}

fn emitExport(buf: []u8, pos: *usize, name: []const u8) EmitError!void {
    try W.write(buf, pos, "    @export_symbol(");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "_ptr, \"");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "\");\n");
}

fn emitExportTyped(buf: []u8, pos: *usize, name: []const u8) EmitError!void {
    try W.write(buf, pos, "    @export_symbol(");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "_ptr, \"");
    try W.write(buf, pos, name);
    try W.write(buf, pos, "\");\n");
}
