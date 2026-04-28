// emit_csl_sample.zig — CSL PE program for token sampling.
//
// Maps Doppler's sample.wgsl pattern to CSL. Three phases:
//   1. Distributed top-k: each PE finds local max in its logit chunk
//   2. Fabric reduce to find global top-k candidates
//   3. Single PE performs softmax + multinomial sampling
//
// Buffer names are resolved from the IR module.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.SampleInfo,
) EmitError!void {
    const logits = module.globals.items[info.logits_global].name;
    const tokens = module.globals.items[info.tokens_global].name;

    try W.write(buf, pos, "// PE program: token sampling (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Phase 1: local argmax over logit chunk.\n");
    try W.write(buf, pos, "// Phase 2: fabric reduce for global argmax.\n");
    try W.write(buf, pos, "// Phase 3: last PE outputs sampled token.\n\n");

    try W.write(buf, pos, "param memcpy_params;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param chunk_size: i16;\n");
    try W.write(buf, pos, "param reduce_color: color;\n");
    try W.write(buf, pos, "param temperature: f32 = 1.0;\n");
    try W.write(buf, pos, "param softcap: f32 = 0.0;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    // Buffers
    try emitBuf(buf, pos, logits, "[chunk_size]f32");
    try W.write(buf, pos, "var output_token: [1]u32 = @zeros([1]u32);\n\n");
    try emitPtr(buf, pos, logits, "f32");
    try W.write(buf, pos, "var ");
    try W.write(buf, pos, tokens);
    try W.write(buf, pos, "_ptr: [*]u32 = &output_token;\n\n");

    // State
    try W.write(buf, pos, "var local_max_val: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "var local_max_idx: u32 = 0;\n");
    try W.write(buf, pos, "var global_max_val: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "var global_max_idx: u32 = 0;\n\n");

    // wse3 DSD-to-DSD async fabric pattern with PAIRED VALUE+INDEX
    // reduction. Reference: csl-extras .../row-col-broadcast/src/sync/pe.csl.
    // The wse2-era `@fmovs(f32_var, fabin_dsd)` synchronous form is
    // rejected on wse3. The canonical replacement stages values through
    // a mem1d_dsd over a multi-element scratch buffer and uses
    // `@mov32(dst_dsd, src_dsd, .{.async=true, [.activate=task]})`.
    //
    // Sample's reduction must propagate BOTH the running max value AND
    // the index of the PE that produced it; a value-only reduction
    // would let the last PE in the chain unconditionally claim the
    // output token even when its local max was not the global max.
    // The 2-element scratch ([0]=val, [1]=idx-as-f32-bitcast) lets the
    // single fabric color carry both halves in one wavelet.
    try W.write(buf, pos, "var scratch_in: [2]f32 = @zeros([2]f32);\n");
    try W.write(buf, pos, "var scratch_out: [2]f32 = @zeros([2]f32);\n");
    try W.write(buf, pos, "const scratch_in_dsd = @get_dsd(mem1d_dsd, .{ .tensor_access = |i|{2} -> scratch_in[i] });\n");
    try W.write(buf, pos, "const scratch_out_dsd = @get_dsd(mem1d_dsd, .{ .tensor_access = |i|{2} -> scratch_out[i] });\n");
    // Queues 0-1 are reserved by the memcpy runtime; use id=2 to avoid
    // the wse3 router remap conflict (see emit_csl_fused for details).
    try W.write(buf, pos, "const reduce_out_q = @get_output_queue(2);\n");
    try W.write(buf, pos, "const reduce_in_q = @get_input_queue(2);\n");
    try W.write(buf, pos, "const reduce_out = @get_dsd(fabout_dsd, .{ .extent = 2, .output_queue = reduce_out_q });\n");
    try W.write(buf, pos, "const reduce_in = @get_dsd(fabin_dsd, .{ .extent = 2, .input_queue = reduce_in_q });\n\n");
    try W.write(buf, pos, "const reduce_task_id: local_task_id = @get_local_task_id(10);\n\n");

    // Phase 1: local argmax. Then seed-vs-non-seed split:
    //   PE 0  : stages local_max_val into scratch_out and fires the
    //           send east. No recv to arm (no west neighbor).
    //   others: arms an async recv that activates reduce_recv when the
    //           next wavelet arrives from the west. The task then
    //           combines with local state and (if not last PE) sends
    //           the running max east.
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    local_max_val = -3.4028235e+38;\n");
    try W.write(buf, pos, "    local_max_idx = 0;\n");
    try W.write(buf, pos, "    const offset = @as(u32, pe_id) * @as(u32, chunk_size);\n\n");
    try W.write(buf, pos, "    for (@range(i16, chunk_size)) |i| {\n");
    try W.write(buf, pos, "        var val = ");
    try W.write(buf, pos, logits);
    try W.write(buf, pos, "[@as(u32, i)];\n");
    try W.write(buf, pos, "        if (softcap != 0.0) val = softcap * math.tanh(val / softcap);\n");
    try W.write(buf, pos, "        val /= temperature;\n");
    try W.write(buf, pos, "        if (val > local_max_val) {\n");
    try W.write(buf, pos, "            local_max_val = val;\n");
    try W.write(buf, pos, "            local_max_idx = offset + @as(u32, i);\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n\n");
    try W.write(buf, pos, "    if (pe_id == 0) {\n");
    try W.write(buf, pos, "        scratch_out[0] = local_max_val;\n");
    try W.write(buf, pos, "        scratch_out[1] = @bitcast(f32, local_max_idx);\n");
    try W.write(buf, pos, "        @mov32(reduce_out, scratch_out_dsd, .{ .async = true });\n");
    try W.write(buf, pos, "        sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "    } else {\n");
    try W.write(buf, pos, "        @mov32(scratch_in_dsd, reduce_in, .{ .async = true, .activate = reduce_task_id });\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    // Phase 2: task fires on async recv completion. scratch_in carries
    // the running (max_val, max_idx) from the west. Combine with local
    // state; forward east on non-last PEs or write output on the last
    // PE. The pair propagates both halves so the last PE writes the
    // GLOBAL argmax index, not just its own local index.
    try W.write(buf, pos, "task reduce_recv() void {\n");
    try W.write(buf, pos, "    const incoming_val = scratch_in[0];\n");
    try W.write(buf, pos, "    const incoming_idx = @bitcast(u32, scratch_in[1]);\n");
    try W.write(buf, pos, "    if (incoming_val > global_max_val) {\n");
    try W.write(buf, pos, "        global_max_val = incoming_val;\n");
    try W.write(buf, pos, "        global_max_idx = incoming_idx;\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    const best_val = (if (local_max_val > global_max_val) local_max_val else global_max_val);\n");
    try W.write(buf, pos, "    const best_idx = (if (local_max_val > global_max_val) local_max_idx else global_max_idx);\n");
    try W.write(buf, pos, "    if (pe_id != num_pes - 1) {\n");
    try W.write(buf, pos, "        scratch_out[0] = best_val;\n");
    try W.write(buf, pos, "        scratch_out[1] = @bitcast(f32, best_idx);\n");
    try W.write(buf, pos, "        @mov32(reduce_out, scratch_out_dsd, .{ .async = true });\n");
    try W.write(buf, pos, "    } else {\n");
    try W.write(buf, pos, "        output_token[0] = best_idx;\n");
    try W.write(buf, pos, "        sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    // The reduce task is bound so it can fire when a wavelet arrives on
    // reduce_color. We do NOT emit
    //   @set_local_color_config(reduce_color, .{ .recv_task = reduce_task_id });
    // here because wse3 cslc rejects it — the layout already configured
    // reduce_color's routes via @set_color_config, and wse3 treats the
    // PE-local config as a duplicate. Task binding alone is sufficient
    // for the recv-task wiring; alternative canonical patterns use pure
    // blocking @fmovs(fabin_dsd) in the compute function, which is
    // already how the non-task receive path in emit_csl_reduce_dist.zig
    // currently reads from reduce_in.
    try W.write(buf, pos, "    @bind_local_task(reduce_recv, reduce_task_id);\n");
    try W.write(buf, pos, "    if (@is_arch(\"wse3\")) {\n");
    try W.write(buf, pos, "        @initialize_queue(reduce_out_q, .{ .color = reduce_color });\n");
    try W.write(buf, pos, "        @initialize_queue(reduce_in_q, .{ .color = reduce_color });\n");
    try W.write(buf, pos, "    }\n");
    try emitExport(buf, pos, logits);
    try W.write(buf, pos, "    @export_symbol(");
    try W.write(buf, pos, tokens);
    try W.write(buf, pos, "_ptr, \"");
    try W.write(buf, pos, tokens);
    try W.write(buf, pos, "\");\n");
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
