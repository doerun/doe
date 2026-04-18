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

const std = @import("std");
const ir = @import("ir.zig");
const classify = @import("emit_csl_classify.zig");
const spec = @import("csl_spec.zig");
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
    try W.write(buf, pos, "param scale: f32 = 0.125;\n");
    try W.write(buf, pos, "\n");

    try W.write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try W.write(buf, pos, "const math = @import_module(\"<math>\");\n\n");

    try emitStoragePtrs(buf, pos, module);
    try emitDecodeRuntimeState(buf, pos);

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
    try emitSlidingWindowGuard(buf, pos, "        ", "kv_i");
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
    try emitDecodeRuntimeExports(buf, pos);
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
    // SDK v1.4 removed the 3-arg `math.min(T, a, b)` form; use inline
    // ternary. Same pattern the element_wise emitter uses.
    try W.write(buf, pos, "        const blk_end = (if ((kv_start + block_size) < kv_len) (kv_start + block_size) else kv_len);\n");
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
    try W.write(buf, pos, "        const m_new = (if (m_i > blk_max) m_i else blk_max);\n");
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
    try emitSlidingWindowGuard(buf, pos, "        ", "kv_i");
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

fn emitSlidingWindowGuard(buf: []u8, pos: *usize, indent: []const u8, loop_var: []const u8) EmitError!void {
    try W.write(buf, pos, indent);
    try W.write(buf, pos, "if (decode_sliding_window[0] > 0) {\n");
    try W.write(buf, pos, indent);
    try W.write(buf, pos, "    const current_pos = @as(i32, @intCast(decode_position[0]));\n");
    try W.write(buf, pos, indent);
    try W.write(buf, pos, "    const sliding_window = @as(i32, @intCast(decode_sliding_window[0]));\n");
    try W.write(buf, pos, indent);
    try W.write(buf, pos, "    const abs_key = @as(i32, pe_id) * @as(i32, kv_chunk) + @as(i32, ");
    try W.write(buf, pos, loop_var);
    try W.write(buf, pos, ");\n");
    try W.write(buf, pos, indent);
    try W.write(buf, pos, "    if (current_pos >= sliding_window and abs_key < current_pos - sliding_window + 1) continue;\n");
    try W.write(buf, pos, indent);
    try W.write(buf, pos, "}\n");
}

fn emitDecodeRuntimeState(buf: []u8, pos: *usize) EmitError!void {
    try W.write(buf, pos, "var decode_position: [1]u32 = @zeros([1]u32);\n");
    try W.write(buf, pos, "var decode_position_ptr: [*]u32 = &decode_position;\n");
    try W.write(buf, pos, "var decode_sliding_window: [1]u32 = @zeros([1]u32);\n");
    try W.write(buf, pos, "var decode_sliding_window_ptr: [*]u32 = &decode_sliding_window;\n\n");
}

fn emitDecodeRuntimeExports(buf: []u8, pos: *usize) EmitError!void {
    try W.write(buf, pos, "    @export_symbol(decode_position_ptr, \"position\");\n");
    try W.write(buf, pos, "    @export_symbol(decode_sliding_window_ptr, \"sliding_window\");\n");
}

fn emitStoragePtrs(buf: []u8, pos: *usize, module: *const ir.Module) EmitError!void {
    // CSL rejects `var x: [*]f32 = undefined;` (and `&x` on a pointer
    // yields a pointer-to-pointer, not [*]f32). Use the sized-array +
    // aliased-pointer pattern the elementwise / rope / gather /
    // linear-attn emitters use. Size heuristic by name:
    //   K / V names   → [kv_len * head_dim]f32     (full KV matrix)
    //   Q / O names   → [q_len * head_dim]f32      (query / output rows)
    //   fallback      → [q_len * head_dim]f32      (safe upper bound)
    // The access patterns in emitTiled / emitStreaming stay in-bounds
    // for these sizes.
    for (module.globals.items) |global| {
        if (global.binding == null) continue;
        const space = global.addr_space orelse continue;
        if (space != .storage) continue;
        const size_expr: []const u8 = if (isKvStorageName(global.name))
            "kv_len * head_dim"
        else
            "q_len * head_dim";
        try W.write(buf, pos, "var ");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, ": [");
        try W.write(buf, pos, size_expr);
        try W.write(buf, pos, "]f32 = @zeros([");
        try W.write(buf, pos, size_expr);
        try W.write(buf, pos, "]f32);\n");
        try W.write(buf, pos, "var ");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, "_ptr: [*]");
        try writeScalarType(buf, pos, module, global.ty);
        try W.write(buf, pos, " = &");
        try W.write(buf, pos, global.name);
        try W.write(buf, pos, ";\n");
    }
    try W.write(buf, pos, "\n");
}

fn isKvStorageName(name: []const u8) bool {
    // A kernel's K and V buffers hold the full kv_len rows. Q and O
    // only hold q_len rows. Conservative: default to q_len sizing when
    // unrecognized, since kv_len is typically >= q_len in decode.
    return std.mem.indexOf(u8, name, "K") != null or
        std.mem.indexOf(u8, name, "V") != null or
        std.mem.indexOf(u8, name, "key") != null or
        std.mem.indexOf(u8, name, "val") != null or
        std.mem.indexOf(u8, name, "_k") != null or
        std.mem.indexOf(u8, name, "_v") != null;
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

fn writeScalarType(buf: []u8, pos: *usize, module: *const ir.Module, ty: ir.TypeId) EmitError!void {
    const resolved = module.types.get(ty);
    switch (resolved) {
        .scalar => |scalar| try W.write(buf, pos, spec.scalarTypeName(scalar)),
        .array => |array| try writeScalarType(buf, pos, module, array.elem),
        else => try W.write(buf, pos, "u32"),
    }
}
