// emit_csl_gather.zig — CSL PE program for embedding gather.
//
// Maps Doppler's gather_f16.wgsl pattern to CSL. The embedding table is
// distributed across PEs. Each PE holds a contiguous chunk of rows.
// Host sends token IDs; each PE checks if the target row is in its
// chunk and outputs the corresponding embedding vector.
//
// Buffer names are resolved from the IR module, not hardcoded.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.GatherInfo,
) EmitError!void {
    const idx = module.globals.items[info.indices_global].name;
    const tbl = module.globals.items[info.table_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: embedding gather (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Each PE holds a chunk of the embedding table.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param hidden_size: i16;\n");
    try W.write(buf, pos, "param rows_per_pe: i16;\n");
    try W.write(buf, pos, "param num_tokens: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n\n");

    // Buffers — names derived from IR
    try emitBuf(buf, pos, idx, "[num_tokens]u32");
    try emitBuf(buf, pos, tbl, "[rows_per_pe * hidden_size]f32");
    try emitBuf(buf, pos, out, "[num_tokens * hidden_size]f32");
    try W.write(buf, pos, "\n");
    try emitPtr(buf, pos, idx, "u32");
    try emitPtr(buf, pos, tbl, "f32");
    try emitPtr(buf, pos, out, "f32");
    try W.write(buf, pos, "\n");

    // Compute: for each token, check if the row is in this PE's chunk
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    const row_start = @as(u32, pe_id) * @as(u32, rows_per_pe);\n");
    try W.write(buf, pos, "    const row_end = row_start + @as(u32, rows_per_pe);\n\n");
    try W.write(buf, pos, "    for (@range(i16, num_tokens)) |t| {\n");
    try W.write(buf, pos, "        const token_id = ");
    try W.write(buf, pos, idx);
    try W.write(buf, pos, "[@as(u32, t)];\n");
    try W.write(buf, pos, "        if (token_id >= row_start and token_id < row_end) {\n");
    try W.write(buf, pos, "            const local_row = token_id - row_start;\n");
    try W.write(buf, pos, "            for (@range(i16, hidden_size)) |d| {\n");
    try W.write(buf, pos, "                const src = local_row * @as(u32, hidden_size) + @as(u32, d);\n");
    try W.write(buf, pos, "                const dst = @as(u32, t) * @as(u32, hidden_size) + @as(u32, d);\n");
    try W.write(buf, pos, "                ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[dst] = ");
    try W.write(buf, pos, tbl);
    try W.write(buf, pos, "[src];\n");
    try W.write(buf, pos, "            }\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    try emitExport(buf, pos, idx);
    try emitExport(buf, pos, tbl);
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
