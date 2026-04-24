// emit_csl_gather.zig — CSL PE program for embedding gather.
//
// Maps Doppler's gather_f16.wgsl pattern to CSL. The embedding table is
// distributed across PEs. Each PE holds a contiguous chunk of rows.
// Host sends token IDs; each PE checks if the target row is in its
// chunk and outputs the corresponding embedding vector.
//
// Buffer names are resolved from the IR module, not hardcoded.
//
// Manifest-scale blocker (2026-04-24, verified by direct cslc run):
// At Gemma 4 E2B (`num_tokens=32, hidden_size=1536, rows_per_pe=16, grid=197x84`),
// the surface error is the i16-overflow
//     `[num_tokens * hidden_size]f32 = [49152]f32`  (32*1536=49152 > 32767)
// but the root cause is per-PE memory. Even with the product split into a
// 2D `[num_tokens, hidden_size]f32` (verified to compile for i16 purposes),
// per-PE state at real shape is:
//     output  32 * 1536 * 4 =  192 KiB  (>> 63 KiB PE .data.hi budget)
//     table   16 * 1536 * 4 =   96 KiB  (>>    "                    )
//     indices 32 *    4     = 0.13 KiB
// and the linker fails `ran out of PE memory for data (section .data.hi)`
// because `.blocked_ut_ival` starts at 0xFC04 ≈ 63 KiB.
//
// Minimal viable fix (~1 day engineering, ~1 day validation):
//   1. Add params `tokens_per_chunk: i16`, `hidden_per_pe: i16`.
//      Keep `rows_per_pe` semantics unchanged.
//   2. Change layout to 2D (width=row_shard, height=hidden_shard). Each PE
//      holds table slice `[rows_per_pe, hidden_per_pe]f32` and output slice
//      `[tokens_per_chunk, hidden_per_pe]f32`.
//   3. Classifier picks `hidden_per_pe = hidden_size / height` and
//      `tokens_per_chunk` such that per-PE footprint ≤ 48 KiB:
//        (rows_per_pe + tokens_per_chunk) * hidden_per_pe * 4 ≤ 48 KiB
//      Verified-feasible region at hidden_size=1536, rows_per_pe=16:
//        height=8, hidden_per_pe=192, tokens_per_chunk=16 → 16*192*4+16*192*4
//        = 24 KiB (fits). See bench/out/cslc-embed-memory-probe.json once
//        landed.
//   4. Host Python runner dispatches `ceil(num_tokens / tokens_per_chunk)`
//      chunks, then concatenates per-column slices across height PEs to
//      reassemble `[num_tokens, hidden_size]f32`. Existing sum-across-width
//      pattern stays the same for column PEs with the same hidden shard.
//   5. operation-graph schema adds `hostIoLayout.embed.chunkedDispatch`
//      with `tokens_per_chunk` and `hidden_shardCount` keys.
//
// Partial fixes here will compile but silently drop output on non-first
// chunks; do not ship the emitter change without the host orchestration
// change.

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

    try W.write(buf, pos, "param memcpy_params;\n");
    // u16 for 2-D grids up to 65,535 total PEs (covers 31B 58,056 PE as
    // 246x236). See bench/out/layout-2d-needs/layout-2d-needs.json.
    try W.write(buf, pos, "param pe_id: u16;\n");
    try W.write(buf, pos, "param num_pes: u16;\n");
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
