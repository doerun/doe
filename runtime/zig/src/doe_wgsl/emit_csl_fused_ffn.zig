// emit_csl_fused_ffn.zig — CSL PE program for SiLU-gated FFN.
//
// Fuses gate_proj, up_proj, SiLU activation, and element-wise multiply:
//   output = silu(gate_proj(x)) * up_proj(x)
//
// Common in Qwen/Llama FFN blocks. Each PE holds a slice of the weight
// matrices and computes partial output rows. Fabric reduce accumulates.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

pub fn emit(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.FusedFfnInfo,
) EmitError!void {
    const inp = module.globals.items[info.input_global].name;
    const gate = module.globals.items[info.gate_weight_global].name;
    const up = module.globals.items[info.up_weight_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: fused SiLU-gated FFN (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// output = silu(gate(x)) * up(x), distributed across PEs.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param reduce_color: color;\n\n");
    try W.write(buf, pos, "param in_dim: i16;\n");
    try W.write(buf, pos, "param out_dim: i16;\n");
    try W.write(buf, pos, "param in_per_pe: i16;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    try emitStoragePtrs(buf, pos, module);

    try W.write(buf, pos, "var gate_partial: [out_dim]f32 = @zeros([out_dim]f32);\n");
    try W.write(buf, pos, "var up_partial: [out_dim]f32 = @zeros([out_dim]f32);\n\n");

    // Fabric DSDs
    try W.write(buf, pos, "const reduce_out = @get_dsd(fabout_dsd, .{ .extent = 1, .fabric_color = reduce_color });\n");
    try W.write(buf, pos, "const reduce_in = @get_dsd(fabin_dsd, .{ .extent = 1, .fabric_color = reduce_color });\n\n");
    try W.write(buf, pos, "const reduce_task_id: local_task_id = @get_local_task_id(10);\n");
    try W.write(buf, pos, "var reduce_dim: i16 = 0;\n\n");

    // SiLU: x * sigmoid(x) = x / (1 + exp(-x))
    try W.write(buf, pos, "fn silu(x: f32) f32 {\n");
    try W.write(buf, pos, "    return x / (1.0 + math.exp(-x));\n");
    try W.write(buf, pos, "}\n\n");

    // Phase 1: local matmul for gate and up projections
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    for (@range(i16, out_dim)) |row| {\n");
    try W.write(buf, pos, "        var gate_sum: f32 = 0.0;\n");
    try W.write(buf, pos, "        var up_sum: f32 = 0.0;\n");
    try W.write(buf, pos, "        for (@range(i16, in_per_pe)) |col| {\n");
    try W.write(buf, pos, "            const x = ");
    try W.write(buf, pos, inp);
    try W.write(buf, pos, "[@as(u32, col)];\n");
    try W.write(buf, pos, "            const widx = @as(u32, row) * @as(u32, in_per_pe) + @as(u32, col);\n");
    try W.write(buf, pos, "            gate_sum += x * ");
    try W.write(buf, pos, gate);
    try W.write(buf, pos, "[widx];\n");
    try W.write(buf, pos, "            up_sum += x * ");
    try W.write(buf, pos, up);
    try W.write(buf, pos, "[widx];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        gate_partial[@as(u32, row)] = gate_sum;\n");
    try W.write(buf, pos, "        up_partial[@as(u32, row)] = up_sum;\n");
    try W.write(buf, pos, "    }\n\n");

    try W.write(buf, pos, "    reduce_dim = 0;\n");
    try W.write(buf, pos, "    @fmovs(reduce_out, gate_partial[0]);\n");
    try W.write(buf, pos, "}\n\n");

    // Phase 2: reduce and apply SiLU gating
    try W.write(buf, pos, "task reduce_recv() void {\n");
    try W.write(buf, pos, "    var incoming: f32 = 0.0;\n");
    try W.write(buf, pos, "    @fmovs(incoming, reduce_in);\n");
    try W.write(buf, pos, "    const g = gate_partial[@as(u32, reduce_dim)] + incoming;\n");
    try W.write(buf, pos, "    ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, reduce_dim)] = silu(g) * up_partial[@as(u32, reduce_dim)];\n\n");
    try W.write(buf, pos, "    reduce_dim += 1;\n");
    try W.write(buf, pos, "    if (reduce_dim < out_dim) {\n");
    try W.write(buf, pos, "        @fmovs(reduce_out, gate_partial[@as(u32, reduce_dim)]);\n");
    try W.write(buf, pos, "    } else {\n");
    try W.write(buf, pos, "        if (pe_id == num_pes - 1) sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    try W.write(buf, pos, "    @bind_local_task(reduce_recv, reduce_task_id);\n");
    try W.write(buf, pos, "    @set_local_color_config(reduce_color, .{ .recv_task = reduce_task_id });\n");
    try emitStorageExports(buf, pos, module);
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}

fn emitStoragePtrs(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        try W.write(buf, pos, "var ");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, ": [*]f32 = undefined;\n");
        try W.write(buf, pos, "var ");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "_ptr: [*]f32 = &");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, ";\n");
    }
    try W.write(buf, pos, "\n");
}

fn emitStorageExports(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
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
}
