// emit_csl_attention.zig — CSL PE program emitters for attention kernels.
//
// Three attention patterns mapped from Doppler's WGSL kernels:
//
//   streaming   — Per-PE sequential attention, no fabric (Qwen linear_attention)
//                 Each PE handles one (query_pos, head) pair.
//
//   decode      — Chunked KV with fabric reduction for online softmax
//                 KV distributed across PE row, fabric allreduce for max/sum.
//
//   tiled       — Flash Attention with K/V tile broadcasts for prefill
//                 P×P grid, tiles broadcast via collectives_2d.
//
// Buffer names are resolved from the IR module via the info struct.

const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const W = @import("emit_csl_ir_walk.zig");

pub const EmitError = W.EmitError;

// ---------------------------------------------------------------------------
// Streaming attention — per-PE, no fabric
// ---------------------------------------------------------------------------

pub fn emitStreaming(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.AttentionStreamingInfo,
) EmitError!void {
    const q = module.globals.items[info.q_global].name;
    const k = module.globals.items[info.k_global].name;
    const v = module.globals.items[info.v_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: streaming attention (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// Per-PE online softmax: each PE handles one (query, head) pair.\n");
    try W.write(buf, pos, "// No inter-PE communication — fully local.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n\n");
    try W.write(buf, pos, "param head_dim: i16;\n");
    try W.write(buf, pos, "param kv_len: i16;\n");
    try W.write(buf, pos, "param softcap: f32 = 0.0;\n");
    try W.write(buf, pos, "param scale: f32 = 0.125;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    try emitStoragePtrs(buf, pos, module);

    // Online softmax: 2-pass algorithm
    try W.write(buf, pos, "fn compute() void {\n");
    // Pass 1: find max score
    try W.write(buf, pos, "    var max_score: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "    for (@range(i16, kv_len)) |kv_i| {\n");
    try W.write(buf, pos, "        var score: f32 = 0.0;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            const qi = ");
    try W.write(buf, pos, q);
    try W.write(buf, pos, "[@as(u32, d)];\n");
    try W.write(buf, pos, "            const ki = ");
    try W.write(buf, pos, k);
    try W.write(buf, pos, "[@as(u32, kv_i) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "            score += qi * ki;\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        score *= scale;\n");
    try W.write(buf, pos, "        if (softcap != 0.0) {\n");
    try W.write(buf, pos, "            score = softcap * math.tanh(score / softcap);\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        if (score > max_score) max_score = score;\n");
    try W.write(buf, pos, "    }\n\n");

    // Pass 2: accumulate exp(score - max) * V
    try W.write(buf, pos, "    var sum_exp: f32 = 0.0;\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] = 0.0;\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    for (@range(i16, kv_len)) |kv_i| {\n");
    try W.write(buf, pos, "        var score: f32 = 0.0;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            score += ");
    try W.write(buf, pos, q);
    try W.write(buf, pos, "[@as(u32, d)] * ");
    try W.write(buf, pos, k);
    try W.write(buf, pos, "[@as(u32, kv_i) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        score *= scale;\n");
    try W.write(buf, pos, "        if (softcap != 0.0) score = softcap * math.tanh(score / softcap);\n");
    try W.write(buf, pos, "        const w = math.exp(score - max_score);\n");
    try W.write(buf, pos, "        sum_exp += w;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            const idx = @as(u32, d);\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[idx] += w * ");
    try W.write(buf, pos, v);
    try W.write(buf, pos, "[@as(u32, kv_i) * @as(u32, head_dim) + idx];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n\n");

    // Normalize
    try W.write(buf, pos, "    const inv_sum = 1.0 / sum_exp;\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "        ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] *= inv_sum;\n");
    try W.write(buf, pos, "    }\n\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try emitComptime(buf, pos, module);
}

// ---------------------------------------------------------------------------
// Decode attention — chunked KV, fabric reduction
// ---------------------------------------------------------------------------

pub fn emitDecode(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.AttentionDecodeInfo,
) EmitError!void {
    const q = module.globals.items[info.q_global].name;
    const k = module.globals.items[info.k_global].name;
    const v = module.globals.items[info.v_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: decode attention (auto-generated from WGSL)\n");
    try W.write(buf, pos, "// KV distributed across PE row, fabric allreduce for softmax.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param pe_id: i16;\n");
    try W.write(buf, pos, "param num_pes: i16;\n");
    try W.write(buf, pos, "param reduce_color: color;\n\n");
    try W.write(buf, pos, "param head_dim: i16;\n");
    try W.write(buf, pos, "param kv_chunk: i16;\n");
    try W.write(buf, pos, "param scale: f32 = 0.125;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    try emitStoragePtrs(buf, pos, module);

    // Local accumulators
    try W.write(buf, pos, "var local_max: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "var local_sum: f32 = 0.0;\n");
    try W.write(buf, pos, "var global_max: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "var global_sum: f32 = 0.0;\n\n");

    // Fabric DSDs
    try W.write(buf, pos, "const reduce_out = @get_dsd(fabout_dsd, .{ .extent = 1, .fabric_color = reduce_color });\n");
    try W.write(buf, pos, "const reduce_in = @get_dsd(fabin_dsd, .{ .extent = 1, .fabric_color = reduce_color });\n\n");
    try W.write(buf, pos, "const reduce_task_id: local_task_id = @get_local_task_id(10);\n");
    try W.write(buf, pos, "const norm_task_id: local_task_id = @get_local_task_id(11);\n\n");

    // Phase 1: local score computation
    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    local_max = -3.4028235e+38;\n");
    try W.write(buf, pos, "    local_sum = 0.0;\n");
    try emitScoreLoop(buf, pos, q, k, "kv_chunk");
    try W.write(buf, pos, "    @fmovs(reduce_out, local_max);\n");
    try W.write(buf, pos, "}\n\n");

    // Phase 2: reduce and normalize
    try W.write(buf, pos, "task reduce_recv() void {\n");
    try W.write(buf, pos, "    var incoming: f32 = 0.0;\n");
    try W.write(buf, pos, "    @fmovs(incoming, reduce_in);\n");
    try W.write(buf, pos, "    if (incoming > global_max) global_max = incoming;\n");
    try W.write(buf, pos, "    if (pe_id == num_pes - 1) @activate(norm_task_id);\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "task normalize() void {\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| { ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] = 0.0; }\n");
    try W.write(buf, pos, "    var sum_exp: f32 = 0.0;\n");
    try W.write(buf, pos, "    for (@range(i16, kv_chunk)) |kv_i| {\n");
    try W.write(buf, pos, "        var score: f32 = 0.0;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            score += ");
    try W.write(buf, pos, q);
    try W.write(buf, pos, "[@as(u32, d)] * ");
    try W.write(buf, pos, k);
    try W.write(buf, pos, "[@as(u32, kv_i) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        score *= scale;\n");
    try W.write(buf, pos, "        const w = math.exp(score - global_max);\n");
    try W.write(buf, pos, "        sum_exp += w;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] += w * ");
    try W.write(buf, pos, v);
    try W.write(buf, pos, "[@as(u32, kv_i) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "    }\n");
    try W.write(buf, pos, "    const inv = 1.0 / sum_exp;\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| { ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] *= inv; }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try W.write(buf, pos, "comptime {\n");
    try W.write(buf, pos, "    @bind_local_task(reduce_recv, reduce_task_id);\n");
    try W.write(buf, pos, "    @bind_local_task(normalize, norm_task_id);\n");
    try W.write(buf, pos, "    @set_local_color_config(reduce_color, .{ .recv_task = reduce_task_id });\n");
    try emitStorageExports(buf, pos, module);
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}

// ---------------------------------------------------------------------------
// Tiled attention — Flash Attention with tile broadcasts
// ---------------------------------------------------------------------------

pub fn emitTiled(
    buf: []u8,
    pos: *usize,
    module: *const ir.Module,
    info: classify.AttentionTiledInfo,
) EmitError!void {
    const q = module.globals.items[info.q_global].name;
    const k = module.globals.items[info.k_global].name;
    const v = module.globals.items[info.v_global].name;
    const out = module.globals.items[info.output_global].name;

    try W.write(buf, pos, "// PE program: tiled Flash Attention for prefill (auto-generated)\n");
    try W.write(buf, pos, "// KV tiles broadcast via collectives, online softmax accumulation.\n\n");

    try W.write(buf, pos, "param memcpy_params: comptime_struct;\n");
    try W.write(buf, pos, "param head_dim: i16;\n");
    try W.write(buf, pos, "param block_size: i16 = 32;\n");
    try W.write(buf, pos, "param kv_len: i16;\n");
    try W.write(buf, pos, "param q_len: i16;\n");
    try W.write(buf, pos, "param scale: f32 = 0.125;\n\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    try emitStoragePtrs(buf, pos, module);

    // K/V tile buffers
    try W.write(buf, pos, "var K_tile = @zeros([block_size * head_dim]f32);\n");
    try W.write(buf, pos, "var V_tile = @zeros([block_size * head_dim]f32);\n\n");

    // Online softmax state
    try W.write(buf, pos, "var m_i: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "var l_i: f32 = 0.0;\n\n");

    try W.write(buf, pos, "fn compute() void {\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| { ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] = 0.0; }\n");
    try W.write(buf, pos, "    m_i = -3.4028235e+38;\n");
    try W.write(buf, pos, "    l_i = 0.0;\n\n");

    try W.write(buf, pos, "    var kv_start: i16 = 0;\n");
    try W.write(buf, pos, "    while (kv_start < kv_len) : (kv_start += block_size) {\n");
    try W.write(buf, pos, "        const blk_end = math.min(i16, kv_start + block_size, kv_len);\n");
    try W.write(buf, pos, "        const blk_len = blk_end - kv_start;\n\n");

    // Load K/V tile
    try W.write(buf, pos, "        for (@range(i16, blk_len)) |bi| {\n");
    try W.write(buf, pos, "            for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "                const src = @as(u32, kv_start + bi) * @as(u32, head_dim) + @as(u32, d);\n");
    try W.write(buf, pos, "                const dst = @as(u32, bi) * @as(u32, head_dim) + @as(u32, d);\n");
    try W.write(buf, pos, "                K_tile[dst] = ");
    try W.write(buf, pos, k);
    try W.write(buf, pos, "[src];\n");
    try W.write(buf, pos, "                V_tile[dst] = ");
    try W.write(buf, pos, v);
    try W.write(buf, pos, "[src];\n");
    try W.write(buf, pos, "            }\n");
    try W.write(buf, pos, "        }\n\n");

    // Online softmax over this block
    try W.write(buf, pos, "        var blk_max: f32 = -3.4028235e+38;\n");
    try W.write(buf, pos, "        for (@range(i16, blk_len)) |bi| {\n");
    try W.write(buf, pos, "            var score: f32 = 0.0;\n");
    try W.write(buf, pos, "            for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "                score += ");
    try W.write(buf, pos, q);
    try W.write(buf, pos, "[@as(u32, d)] * K_tile[@as(u32, bi) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "            }\n");
    try W.write(buf, pos, "            score *= scale;\n");
    try W.write(buf, pos, "            if (score > blk_max) blk_max = score;\n");
    try W.write(buf, pos, "        }\n\n");

    // Update running max and rescale
    try W.write(buf, pos, "        const m_new = math.max(f32, m_i, blk_max);\n");
    try W.write(buf, pos, "        const rescale = math.exp(m_i - m_new);\n");
    try W.write(buf, pos, "        l_i *= rescale;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] *= rescale;\n");
    try W.write(buf, pos, "        }\n\n");

    // Accumulate weighted V
    try W.write(buf, pos, "        for (@range(i16, blk_len)) |bi| {\n");
    try W.write(buf, pos, "            var score: f32 = 0.0;\n");
    try W.write(buf, pos, "            for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "                score += ");
    try W.write(buf, pos, q);
    try W.write(buf, pos, "[@as(u32, d)] * K_tile[@as(u32, bi) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "            }\n");
    try W.write(buf, pos, "            const w = math.exp(score * scale - m_new);\n");
    try W.write(buf, pos, "            l_i += w;\n");
    try W.write(buf, pos, "            for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "                ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] += w * V_tile[@as(u32, bi) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "            }\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        m_i = m_new;\n");
    try W.write(buf, pos, "    }\n\n");

    // Final normalize
    try W.write(buf, pos, "    const inv = 1.0 / l_i;\n");
    try W.write(buf, pos, "    for (@range(i16, head_dim)) |d| { ");
    try W.write(buf, pos, out);
    try W.write(buf, pos, "[@as(u32, d)] *= inv; }\n");
    try W.write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try W.write(buf, pos, "}\n\n");

    try emitComptime(buf, pos, module);
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

fn emitScoreLoop(buf: []u8, pos: *usize, q: []const u8, k: []const u8, len_param: []const u8) EmitError!void {
    try W.write(buf, pos, "    for (@range(i16, ");
    try W.write(buf, pos, len_param);
    try W.write(buf, pos, ")) |kv_i| {\n");
    try W.write(buf, pos, "        var score: f32 = 0.0;\n");
    try W.write(buf, pos, "        for (@range(i16, head_dim)) |d| {\n");
    try W.write(buf, pos, "            score += ");
    try W.write(buf, pos, q);
    try W.write(buf, pos, "[@as(u32, d)] * ");
    try W.write(buf, pos, k);
    try W.write(buf, pos, "[@as(u32, kv_i) * @as(u32, head_dim) + @as(u32, d)];\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        score *= scale;\n");
    try W.write(buf, pos, "        if (score > local_max) {\n");
    try W.write(buf, pos, "            const rescale = math.exp(local_max - score);\n");
    try W.write(buf, pos, "            local_sum *= rescale;\n");
    try W.write(buf, pos, "            local_max = score;\n");
    try W.write(buf, pos, "        }\n");
    try W.write(buf, pos, "        local_sum += math.exp(score - local_max);\n");
    try W.write(buf, pos, "    }\n");
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

fn emitComptime(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
    try W.write(buf, pos, "comptime {\n");
    try emitStorageExports(buf, pos, module);
    try W.write(buf, pos, "    @export_symbol(compute);\n");
    try W.write(buf, pos, "}\n");
}
