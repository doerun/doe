// emit_kernel_body_linear_attention.zig — CSL emit body for
// SemanticBodyOp `linear_attention` (gated DeltaNet).
//
// Per-token recurrent state update + readout. Single-Q (decode-shape)
// canary surface; multi-Q prefill is a follow-up that reuses this body
// inside an outer query-row loop the same way attention_scores does.
//
// State buffer: linear_state has shape [value_dim * key_dim]f32 per
// head pair. The update reads + writes it. The bootstrap canary covers
// `norm_mode = .shared` (one A_log scalar per head pair, no dt_bias)
// because that's the simplest closed form to oracle. `.per_head` with
// time-varying dt_bias is an explicit `error.InvalidBodyContract` until
// the conv1d → A_log decay path lands as a separate composition.
//
// Math (shared-norm form):
//   alpha = 1 - exp(-A_log_shared)              // per-head scalar in (0, 1)
//   beta  = sigmoid(gate)                       // per-token gate
//   for each (vh, kh) head pair:
//     delta[d, k] = alpha * (q[d] - dot(state[d, :], k_in)) * k_in[k]
//     state[d, k] = (1 - alpha) * state[d, k] + delta[d, k]
//     output[d]   = sum_k state[d, k] * v[k] + beta * input[d]
//
// Bindings: query, key, value, gate (β stream), input (residual hint),
// linear_state (R/W), output. Body params declared on
// `LinearAttentionBody`. Single-PE; no fabric collectives.

const std = @import("std");
const schema = @import("schema.zig");
const body_emit = @import("emit_kernel_body.zig");

pub fn emitCslLinearAttention(
    writer: anytype,
    func: schema.SemanticFunction,
    config: *const body_emit.Config,
) body_emit.EmitError!void {
    const query = try body_emit.bindingForRole(func, .query);
    const key = try body_emit.bindingForRole(func, .key);
    const value = try body_emit.bindingForRole(func, .value);
    const gate = try body_emit.bindingForRole(func, .gate);
    const linear_state = try body_emit.bindingForRole(func, .linear_state);
    const output = try body_emit.bindingForRole(func, .output);
    try body_emit.requireElem(query, .f32);
    try body_emit.requireElem(key, .f32);
    try body_emit.requireElem(value, .f32);
    try body_emit.requireElem(gate, .f32);
    try body_emit.requireElem(linear_state, .f32);
    try body_emit.requireElem(output, .f32);
    if (!linear_state.read_write) return error.InvalidBodyContract;

    const body = func.body.linear_attention orelse return error.InvalidBodyContract;
    if (body.key_dim == 0 or body.value_dim == 0) return error.InvalidBodyContract;
    if (body.key_heads == 0 or body.value_heads == 0) return error.InvalidBodyContract;
    if (body.norm_mode != .shared) return error.InvalidBodyContract;
    if (body.has_dt_bias) return error.InvalidBodyContract;

    const p = config.var_prefix;
    try writer.writeAll("param memcpy_params;\n");
    try writer.print("const key_dim: i16 = {d};\n", .{body.key_dim});
    try writer.print("const value_dim: i16 = {d};\n", .{body.value_dim});
    try writer.writeAll("param a_log: f32;\n");
    try writer.writeAll("const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try writer.writeAll("const math = @import_module(\"<math>\");\n");
    try body_emit.writeCslBufferArray(writer, p, query.name, "value_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, key.name, "key_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, value.name, "key_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, gate.name, "value_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, linear_state.name, "value_dim * key_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, output.name, "value_dim", "f32");
    try body_emit.writeCslBufferPointer(writer, p, query.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, key.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, value.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, gate.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, linear_state.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, output.name, "f32");
    try writer.writeAll("\n");
    try writer.writeAll("fn compute() void {\n");
    // alpha = 1 - exp(-A_log) clamped to (0, 1) by the host's a_log >= 0
    // contract. exp(-A_log) is the per-step state retention; alpha is
    // the new-information weight in the SSM update.
    try writer.writeAll("    const alpha: f32 = 1.0 - math.exp(-a_log);\n");
    try writer.writeAll("    const decay: f32 = 1.0 - alpha;\n");
    // Pass 1: for each value-dim row d, compute scalar
    //   prev_dot = sum_k state[d, k] * k_in[k]
    // and the per-(d, k) delta and updated state.
    try writer.writeAll("    for (@range(i16, value_dim)) |d| {\n");
    try writer.writeAll("        var prev_dot: f32 = 0.0;\n");
    try writer.writeAll("        for (@range(i16, key_dim)) |k| {\n");
    try writer.print(
        "            prev_dot += {s}{s}[@as(u32, d) * @as(u32, key_dim) + @as(u32, k)] * {s}{s}[@as(u32, k)];\n",
        .{ p, linear_state.name, p, key.name },
    );
    try writer.writeAll("        }\n");
    try writer.print(
        "        const q_d: f32 = {s}{s}[@as(u32, d)];\n",
        .{ p, query.name },
    );
    try writer.writeAll("        const correction: f32 = q_d - prev_dot;\n");
    try writer.writeAll("        const scaled_correction: f32 = alpha * correction;\n");
    try writer.writeAll("        for (@range(i16, key_dim)) |k| {\n");
    try writer.print(
        "            const k_in: f32 = {s}{s}[@as(u32, k)];\n",
        .{ p, key.name },
    );
    try writer.print(
        "            const idx: u32 = @as(u32, d) * @as(u32, key_dim) + @as(u32, k);\n",
        .{},
    );
    try writer.print(
        "            const prev_state: f32 = {s}{s}[idx];\n",
        .{ p, linear_state.name },
    );
    try writer.writeAll("            const delta: f32 = scaled_correction * k_in;\n");
    try writer.print(
        "            {s}{s}[idx] = decay * prev_state + delta;\n",
        .{ p, linear_state.name },
    );
    try writer.writeAll("        }\n");
    try writer.writeAll("    }\n");
    // Pass 2: output[d] = sum_k state[d, k] * v[k] + sigmoid(gate[d]) * q[d].
    // The gate stream provides the residual mix-in; sigmoid here matches
    // the DeltaNet `attentionOutputGate=sigmoid` form. The query value
    // is the residual carrier (input to FFN if the SSM were a no-op).
    try writer.writeAll("    for (@range(i16, value_dim)) |d| {\n");
    try writer.writeAll("        var acc: f32 = 0.0;\n");
    try writer.writeAll("        for (@range(i16, key_dim)) |k| {\n");
    try writer.print(
        "            acc += {s}{s}[@as(u32, d) * @as(u32, key_dim) + @as(u32, k)] * {s}{s}[@as(u32, k)];\n",
        .{ p, linear_state.name, p, value.name },
    );
    try writer.writeAll("        }\n");
    try writer.print(
        "        const g: f32 = {s}{s}[@as(u32, d)];\n",
        .{ p, gate.name },
    );
    try writer.writeAll("        const sigmoid_g: f32 = 1.0 / (1.0 + math.exp(-g));\n");
    try writer.print(
        "        {s}{s}[@as(u32, d)] = acc + sigmoid_g * {s}{s}[@as(u32, d)];\n",
        .{ p, output.name, p, query.name },
    );
    try writer.writeAll("    }\n");
    try writer.writeAll("    sys_mod.unblock_cmd_stream();\n");
    try writer.writeAll("}\n\n");
    try writer.writeAll("comptime {\n");
    try body_emit.writeCslExportSymbol(writer, p, query.name);
    try body_emit.writeCslExportSymbol(writer, p, key.name);
    try body_emit.writeCslExportSymbol(writer, p, value.name);
    try body_emit.writeCslExportSymbol(writer, p, gate.name);
    try body_emit.writeCslExportSymbol(writer, p, linear_state.name);
    try body_emit.writeCslExportSymbol(writer, p, output.name);
    try writer.writeAll("    @export_symbol(compute);\n");
    try writer.writeAll("}\n");
}
