// emit_csl_fused.zig — CSL PE program for fused GEMV + Q4K dequant.
//
// On-the-fly dequantization during matrix-vector multiply for decode.
// Each PE holds a slice of the quantized weight matrix, dequants and
// computes partial dot products, then fabric reduces to get the final
// output vector.
//
// Maps from Doppler's fused_matmul_q4.wgsl. Buffer names from IR.
//
// Manifest-scale blocker for `lm_head_gemv_stable` at Gemma 4 E2B
// (out_dim=1331, in_dim_per_pe=512, num_blocks_per_row=2, grid=197x1):
// The i16 overflow is `[out_dim * num_blocks_per_row * Q4K_BLOCK_BYTES_I16]u8
//  = 1331*2*144 = 383328` > 32767. Root cause: out_dim is NOT sharded —
// each PE stores the *full* vocab-sized weight. 1D reduce-width only shards
// `in_dim`, leaving `out_dim` fully duplicated per PE.
//
// Minimal viable fix (~2 days engineering + validation): add an
// `out_dim_per_pe` param and change the layout to 2D
// (width=in_dim_shard, height=out_dim_shard). Classifier sets
//   out_dim_per_pe = ceil(out_dim / height)
// At grid 197x84, out_dim_per_pe=ceil(1331/84)=16, weight per PE drops
// from 383 KiB to 16 * 2 * 144 = 4.6 KiB (fits).
// Per-row reduce-chain stays the same (east-west across width for the
// in_dim reduction); rows are independent output slices. Host D2H reads
// out_dim_per_pe floats from each row's sink PE and concatenates by row
// to reassemble [out_dim]f32.
//
// Touch points:
//   - this emitter: use `out_dim_per_pe` instead of `out_dim` in every
//     `var weight/output/partial/scratch_*` declaration and inner loop
//     bound.
//   - emit_csl_layout.zig `emitFusedGemvLayout`: add `height: i16` and
//     `out_dim_per_pe: i16` params, change `@set_rectangle(width, 1)` to
//     `@set_rectangle(width, height)`, wrap `emitReduceRowTileLoop` in
//     a height loop that sets a `row_id = pe_y` param per tile.
//   - emit_csl_classify.zig: plumb `out_dim_per_pe` + `height` through
//     FusedGemvDequantInfo from manifest-scale out_dim.
//   - host Python runner: concat D2H shards across pe_y.
//
// Partial fixes will compile but produce wrong results (each row would
// independently reduce against a wrong in_dim slice). Do not ship
// individually.

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

    try W.write(buf, pos, "param memcpy_params;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param reduce_color: color;\n\n");

    try W.write(buf, pos, "param out_dim: i16;\n");
    try W.write(buf, pos, "param in_dim_per_pe: i16;\n");
    try W.write(buf, pos, "param num_blocks_per_row: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    // Q4K constants
    // Expose i16 aliases for the byte-count constants so array
    // dimensions type-check (CSL array dims are i16). The u32 form is
    // still used for body byte-arithmetic. Same pattern as dequant.
    try W.write(buf, pos, "const QK_K: u32 = 256;\n");
    try W.write(buf, pos, "const QK_K_I16: i16 = 256;\n");
    try W.write(buf, pos, "const Q4K_BLOCK_BYTES: u32 = 144;\n");
    try W.write(buf, pos, "const Q4K_BLOCK_BYTES_I16: i16 = 144;\n\n");

    // Buffers
    try emitBuf(buf, pos, act, "[in_dim_per_pe]f32");
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, wgt);
    try W.write(buf, pos, ": [out_dim * num_blocks_per_row * Q4K_BLOCK_BYTES_I16]u8 = @zeros([out_dim * num_blocks_per_row * Q4K_BLOCK_BYTES_I16]u8);\n");
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

    // wse3 DSD-to-DSD async fabric: single-shot extent=out_dim drain
    // to avoid router-queue-remap conflicts when the task would
    // re-arm an async recv on the same color + queue. Iteration 33
    // tried the iterative [1]f32 re-arm pattern; sim errored with
    //   "P5.1 Attempt to remap input queue 1, from C22 to C4, but the
    //    router is holding wavelets"
    // because the first arm's wavelets were still in-flight when the
    // task's second arm tried to bind the same queue. Reading all
    // out_dim values in a single @mov32 avoids the lifecycle issue;
    // the task then processes scratch_in[0..out_dim) and (if not last
    // PE) forwards east via a matching single-shot send.
    try W.write(buf, pos, "var scratch_in: [out_dim]f32 = @zeros([out_dim]f32);\n");
    try W.write(buf, pos, "var scratch_out: [out_dim]f32 = @zeros([out_dim]f32);\n");
    try W.write(buf, pos, "const scratch_in_dsd = @get_dsd(mem1d_dsd, .{ .tensor_access = |i|{out_dim} -> scratch_in[i] });\n");
    try W.write(buf, pos, "const scratch_out_dsd = @get_dsd(mem1d_dsd, .{ .tensor_access = |i|{out_dim} -> scratch_out[i] });\n");
    // Queues 0-1 are typically reserved by the memcpy runtime for its
    // h2d/d2h handlers. Canonical SDK examples start user fabric
    // queues at id 2+ (gemv-checkerboard uses 2, 3, 4). Using id=1
    // here triggered a wse3 sim "Attempt to remap input queue 1, from
    // C22 to C4" — the router saw the memcpy color still bound to
    // queue 1 when our reduce_color tried to take it.
    try W.write(buf, pos, "const reduce_out_q = @get_output_queue(2);\n");
    try W.write(buf, pos, "const reduce_in_q = @get_input_queue(2);\n");
    try W.write(buf, pos, "const reduce_out = @get_dsd(fabout_dsd, .{ .extent = out_dim, .output_queue = reduce_out_q });\n");
    try W.write(buf, pos, "const reduce_in = @get_dsd(fabin_dsd, .{ .extent = out_dim, .input_queue = reduce_in_q });\n\n");
    try W.write(buf, pos, "const reduce_task_id: local_task_id = @get_local_task_id(10);\n");
    // send_done_id is bound to a task that's @block'd at comptime; the
    // @mov32 send below uses `.unblock = send_done_id` so the task only
    // fires once the async send has propagated. This defers
    // sys_mod.unblock_cmd_stream until the send is actually on the
    // wire, avoiding the memcpy-runtime-teardown stall seen when PE 0
    // unblocks before PE 1's armed recv has received anything.
    try W.write(buf, pos, "const send_done_id: local_task_id = @get_local_task_id(11);\n\n");

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

    // Single-shot allreduce with async-send completion gating:
    //   - PE 0 stages all partial sums, fires @mov32 send with
    //     `.unblock = send_done_id`. send_done_task is @block'd at
    //     comptime, so it only fires after the send propagates — at
    //     which point it calls sys_mod.unblock_cmd_stream.
    //   - Non-seed PEs arm @mov32 recv with `.activate = reduce_task_id`.
    //   - reduce_recv folds scratch_in into the output. Non-last PEs
    //     forward east using the same `.unblock = send_done_id` pattern.
    //     The last PE has nothing to send; it unblocks directly.
    try W.write(buf, pos, "    if (pe_id == 0) {\n");
    try W.write(buf, pos, "        for (@range(i16, out_dim)) |i| {\n");
    try W.write(buf, pos, "            scratch_out[@as(u32, i)] = partial[@as(u32, i)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        @mov32(reduce_out, scratch_out_dsd, .{ .async = true, .unblock = send_done_id });\n");
    try W.write(buf, pos, "    } else {\n");
    try W.write(buf, pos, "        @mov32(scratch_in_dsd, reduce_in, .{ .async = true, .activate = reduce_task_id });\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    // Phase 2: fold scratch_in into partial, write to output, forward east.
    try W.write(buf, pos, "task reduce_recv() void {\n");
    try W.write(buf, pos, "    for (@range(i16, out_dim)) |i| {\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, i)] = partial[@as(u32, i)] + scratch_in[@as(u32, i)];\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    if (pe_id != num_pes - 1) {\n");
    try W.write(buf, pos, "        for (@range(i16, out_dim)) |i| {\n");
    try W.write(buf, pos, "            scratch_out[@as(u32, i)] = ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, i)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        @mov32(reduce_out, scratch_out_dsd, .{ .async = true, .unblock = send_done_id });\n");
    try W.write(buf, pos, "    } else {\n");
    try W.write(buf, pos, "        sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    // send_done_task: fires when an async send completes, unblocks
    // cmd_stream so the memcpy runtime can proceed to d2h on this PE.
    try W.write(buf, pos, "task send_done_task() void {\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    // Drop @set_local_color_config (wse3 rejects it when the layout
    // configures the same color with routes). @bind_local_task alone
    // binds the recv task for the async @mov32 activate callback.
    // send_done_task is @block'd so it only fires via the @mov32
    // `.unblock` arg — the canonical wse3 async-send-completion gate.
    try W.write(buf, pos, "    @bind_local_task(reduce_recv, reduce_task_id);\n");
    try W.write(buf, pos, "    @bind_local_task(send_done_task, send_done_id);\n");
    try W.write(buf, pos, "    @block(send_done_id);\n");
    try W.write(buf, pos, "    if (@is_arch(\"wse3\")) {\n");
    try W.write(buf, pos, "        @initialize_queue(reduce_out_q, .{ .color = reduce_color });\n");
    try W.write(buf, pos, "        @initialize_queue(reduce_in_q, .{ .color = reduce_color });\n");
    try W.write(buf, pos, "    }\n");
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
