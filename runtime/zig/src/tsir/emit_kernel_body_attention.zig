// emit_kernel_body_attention.zig — CSL emit body for SemanticBodyOp
// `attention_scores`.
//
// Lifted out of `emit_kernel_body.zig` so the parent file stays under the
// 999-line repo limit. The dispatch in `emit_kernel_body.zig:emitCsl`
// forwards `.attention_scores` here; nothing else imports this module.
//
// Scope: bootstrap-canary surface only. Required body schema:
//   - softmax_mode = .two_pass_stable
//   - causal_mode = .none (causal / sliding_window are rejected)
//   - has_softcap = false
//   - scale_source = .literal_f32 (uniform scale not yet wired)
// Streaming softmax, causal masks, softcap, page-table KV, and uniform
// scale are explicit `error.InvalidBodyContract` so the canary lane fails
// loudly when an unsupported attention shape is requested. Manifest-shape
// attention with those features needs a separate emit body class.

const std = @import("std");
const schema = @import("schema.zig");
const body_emit = @import("emit_kernel_body.zig");

/// Emit a CSL `attention_scores` kernel body in two-pass-stable softmax form:
///
///   scores[k] = (sum_d Q[d] * K[k, d]) * scale
///   m         = max_k scores[k]
///   weights[k] = exp(scores[k] - m)        ; sum_e = sum_k weights[k]
///   O[d]      = sum_k V[k, d] * (weights[k] / sum_e)
pub fn emitCslAttentionScores(
    writer: anytype,
    func: schema.SemanticFunction,
    config: *const body_emit.Config,
) body_emit.EmitError!void {
    const query = try body_emit.bindingForRole(func, .query);
    const key = try body_emit.bindingForRole(func, .key);
    const value = try body_emit.bindingForRole(func, .value);
    const output = try body_emit.bindingForRole(func, .output);
    try body_emit.requireElem(query, .f32);
    try body_emit.requireElem(key, .f32);
    try body_emit.requireElem(value, .f32);
    try body_emit.requireElem(output, .f32);

    const attn = func.body.attention_scores orelse return error.InvalidBodyContract;
    if (attn.softmax_mode != .two_pass_stable) return error.InvalidBodyContract;
    if (attn.causal_mode != .none) return error.InvalidBodyContract;
    if (attn.has_softcap) return error.InvalidBodyContract;
    if (attn.scale_source != .literal_f32) return error.InvalidBodyContract;
    const scale = attn.scale_literal_f32 orelse return error.InvalidBodyContract;

    const p = config.var_prefix;

    try writer.writeAll("param memcpy_params;\n");
    try writer.print("const head_dim: i16 = {d};\n", .{attn.head_dim});
    try writer.writeAll("param kv_len: i16;\n");
    try writer.writeAll("const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try writer.writeAll("const math = @import_module(\"<math>\");\n");
    try writer.print("const attn_scale: f32 = {d};\n", .{scale});
    try body_emit.writeCslBufferArray(writer, p, query.name, "head_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, key.name, "kv_len * head_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, value.name, "kv_len * head_dim", "f32");
    try body_emit.writeCslBufferArray(writer, p, output.name, "head_dim", "f32");
    try writer.writeAll("var attn_scores: [kv_len]f32 = @zeros([kv_len]f32);\n");
    try body_emit.writeCslBufferPointer(writer, p, query.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, key.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, value.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, output.name, "f32");
    try writer.writeAll("\n");
    try writer.writeAll("fn compute() void {\n");
    try writer.writeAll("    var max_score: f32 = -1.0e30;\n");
    try writer.writeAll("    for (@range(i16, kv_len)) |k| {\n");
    try writer.writeAll("        var dot: f32 = 0.0;\n");
    try writer.writeAll("        for (@range(i16, head_dim)) |d| {\n");
    try writer.print(
        "            dot += {s}{s}[@as(u32, d)] * {s}{s}[@as(u32, k) * @as(u32, head_dim) + @as(u32, d)];\n",
        .{ p, query.name, p, key.name },
    );
    try writer.writeAll("        }\n");
    try writer.writeAll("        const sc = dot * attn_scale;\n");
    try writer.writeAll("        attn_scores[@as(u32, k)] = sc;\n");
    try writer.writeAll("        if (sc > max_score) {\n");
    try writer.writeAll("            max_score = sc;\n");
    try writer.writeAll("        }\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    var sum_exp: f32 = 0.0;\n");
    try writer.writeAll("    for (@range(i16, kv_len)) |k| {\n");
    try writer.writeAll("        const e = math.exp(attn_scores[@as(u32, k)] - max_score);\n");
    try writer.writeAll("        attn_scores[@as(u32, k)] = e;\n");
    try writer.writeAll("        sum_exp += e;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    for (@range(i16, head_dim)) |d| {\n");
    try writer.writeAll("        var acc: f32 = 0.0;\n");
    try writer.writeAll("        for (@range(i16, kv_len)) |k| {\n");
    try writer.print(
        "            acc += {s}{s}[@as(u32, k) * @as(u32, head_dim) + @as(u32, d)] * (attn_scores[@as(u32, k)] / sum_exp);\n",
        .{ p, value.name },
    );
    try writer.writeAll("        }\n");
    try writer.print(
        "        {s}{s}[@as(u32, d)] = acc;\n",
        .{ p, output.name },
    );
    try writer.writeAll("    }\n");
    try writer.writeAll("    sys_mod.unblock_cmd_stream();\n");
    try writer.writeAll("}\n\n");
    try writer.writeAll("comptime {\n");
    try body_emit.writeCslExportSymbol(writer, p, query.name);
    try body_emit.writeCslExportSymbol(writer, p, key.name);
    try body_emit.writeCslExportSymbol(writer, p, value.name);
    try body_emit.writeCslExportSymbol(writer, p, output.name);
    try writer.writeAll("    @export_symbol(compute);\n");
    try writer.writeAll("}\n");
}
