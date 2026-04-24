// emit_csl_gather.zig — CSL PE program for embedding gather.
//
// Maps Doppler's gather_f16.wgsl pattern to CSL on a 2-D PE grid:
//
//   * width  (pe_x) shards the embedding table by row  — `rows_per_pe` rows
//     per column PE, as in the pre-chunking 1-D kernel.
//   * height (pe_y) shards the hidden dimension         — `hidden_per_pe`
//     columns per row PE. Required to fit the Gemma 4 E2B embed output
//     (`[num_tokens, hidden_size]f32` = 192 KiB) inside the per-PE
//     `.data.hi` budget (~63 KiB). The classifier/host picks `height` such
//     that `(rows_per_pe + tokens_per_chunk) * hidden_per_pe * 4 ≤ 48 KiB`.
//
// Token dispatch is chunked: host broadcasts one `tokens_per_chunk`-sized
// slice of `indices` at a time. Each PE writes its hidden shard of that
// chunk into `[tokens_per_chunk, hidden_per_pe]f32`; host concatenates per
// chunk and across the height axis to reassemble the full
// `[num_tokens, hidden_size]f32` output.
//
// Defaults preserve today's 1-D single-chunk behavior: with `height=1`,
// `hidden_per_pe=hidden_size`, and `tokens_per_chunk=num_tokens` the
// compute loop is identical to the pre-chunking emitter. Real-shape E2B
// (num_tokens=32, hidden_size=1536) overrides via the layout params the
// host supplies; those overrides are what moves the compile out of the
// i16-coercion + `.data.hi` overflow regime.
//
// Buffer names are resolved from the IR module, not hardcoded.
//
// First-chunk-only silent-drop hazard (see emit_csl_gather.zig history,
// 2026-04-24 TODO): until the host runner implements chunked dispatch
// across all tokens, calling this kernel with `tokens_per_chunk <
// num_tokens` without the matching `ceil(num_tokens / tokens_per_chunk)`
// launch sequence produces only the first chunk of output. The emitter
// cannot detect this from inside the PE program; the contract is that
// host orchestration owns chunk iteration.

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
    try W.write(buf, pos, "// 2-D layout: pe_x shards rows, pe_y shards hidden. Host orchestrates\n");
    try W.write(buf, pos, "// chunked dispatch across tokens (see emit_csl_gather.zig header).\n\n");

    try W.write(buf, pos, "param memcpy_params;\n");
    // u16 for 2-D grids up to 65,535 total PEs (covers 31B 58,056 PE as
    // 246x236). See bench/out/layout-2d-needs/layout-2d-needs.json.
    try W.write(buf, pos, "param pe_id: u16;\n");
    try W.write(buf, pos, "param pe_x: u16;\n");
    try W.write(buf, pos, "param pe_y: u16;\n");
    try W.write(buf, pos, "param num_pes: u16;\n");
    // Row sharding (unchanged): `rows_per_pe` rows held by each column PE.
    try W.write(buf, pos, "param rows_per_pe: i16;\n");
    // Hidden sharding (new): `hidden_per_pe` columns held by each row PE.
    // With height=1 and hidden_per_pe=hidden_size, the kernel collapses to
    // today's 1-D shape; callers that set height>1 must also partition
    // weights and output on the host accordingly.
    try W.write(buf, pos, "param hidden_size: i16;\n");
    try W.write(buf, pos, "param hidden_per_pe: i16;\n");
    // Chunked token dispatch (new): indices/output sized to one chunk;
    // host iterates ceil(num_tokens / tokens_per_chunk) launches.
    try W.write(buf, pos, "param num_tokens: i16;\n");
    try W.write(buf, pos, "param tokens_per_chunk: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n\n");

    // Per-PE buffers:
    //   indices: one chunk of tokens (broadcast from host per-chunk)
    //   table:   this PE's (row shard × hidden shard) slice of the embedding table
    //   output:  this PE's hidden shard of the current chunk
    try emitBuf(buf, pos, idx, "[tokens_per_chunk]u32");
    try emitBuf(buf, pos, tbl, "[rows_per_pe * hidden_per_pe]f32");
    try emitBuf(buf, pos, out, "[tokens_per_chunk * hidden_per_pe]f32");
    try W.write(buf, pos, "\n");
    try emitPtr(buf, pos, idx, "u32");
    try emitPtr(buf, pos, tbl, "f32");
    try emitPtr(buf, pos, out, "f32");
    try W.write(buf, pos, "\n");

    // Compute: for each token in this chunk, check if the token's global
    // row is in this column-PE's row shard. If so, write this row's
    // hidden shard into the per-chunk output slice.
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    const row_start = @as(u32, pe_x) * @as(u32, rows_per_pe);\n");
    try W.write(buf, pos, "    const row_end = row_start + @as(u32, rows_per_pe);\n\n");
    try W.write(buf, pos, "    for (@range(i16, tokens_per_chunk)) |t| {\n");
    try W.write(buf, pos, "        const token_id = ");
    try W.write(buf, pos, idx);
    try W.write(buf, pos, "[@as(u32, t)];\n");
    try W.write(buf, pos, "        if (token_id >= row_start and token_id < row_end) {\n");
    try W.write(buf, pos, "            const local_row = token_id - row_start;\n");
    try W.write(buf, pos, "            for (@range(i16, hidden_per_pe)) |d| {\n");
    try W.write(buf, pos, "                const src = local_row * @as(u32, hidden_per_pe) + @as(u32, d);\n");
    try W.write(buf, pos, "                const dst = @as(u32, t) * @as(u32, hidden_per_pe) + @as(u32, d);\n");
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
