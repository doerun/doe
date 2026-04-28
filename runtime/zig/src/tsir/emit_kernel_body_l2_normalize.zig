// emit_kernel_body_l2_normalize.zig — CSL emit body for SemanticBodyOp
// `l2_normalize`.
//
// DeltaNet applies L2 normalization to Q and K rows before the
// linear-attention state update so the SSM gain remains scale-invariant
// across token magnitudes.
//
// Math:
//   sq = sum_d input[d] * input[d]
//   inv = 1 / sqrt(sq + eps)
//   output[d] = input[d] * inv
//
// Two-pass body. f32 accumulator. Reduction is `algorithm_exact` over
// the hidden axis (associativity declared at the realization level).

const std = @import("std");
const schema = @import("schema.zig");
const body_emit = @import("emit_kernel_body.zig");

pub fn emitCslL2Normalize(
    writer: anytype,
    func: schema.SemanticFunction,
    config: *const body_emit.Config,
) body_emit.EmitError!void {
    const input = try body_emit.bindingForRole(func, .input);
    const output = try body_emit.bindingForRole(func, .output);
    try body_emit.requireElem(input, .f32);
    try body_emit.requireElem(output, .f32);

    const body = func.body.l2_normalize orelse return error.InvalidBodyContract;
    if (body.hidden == 0) return error.InvalidBodyContract;
    if (body.eps < 0) return error.InvalidBodyContract;

    const p = config.var_prefix;
    try writer.writeAll("param memcpy_params;\n");
    try writer.print("const hidden_size: i16 = {d};\n", .{body.hidden});
    try writer.writeAll("const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try writer.writeAll("const math = @import_module(\"<math>\");\n");
    try writer.print("const l2_eps: f32 = {e};\n", .{body.eps});
    try body_emit.writeCslBufferArray(writer, p, input.name, "hidden_size", "f32");
    try body_emit.writeCslBufferArray(writer, p, output.name, "hidden_size", "f32");
    try body_emit.writeCslBufferPointer(writer, p, input.name, "f32");
    try body_emit.writeCslBufferPointer(writer, p, output.name, "f32");
    try writer.writeAll("\n");
    try writer.writeAll("fn compute() void {\n");
    try writer.writeAll("    var sq: f32 = 0.0;\n");
    try writer.writeAll("    for (@range(i16, hidden_size)) |d| {\n");
    try writer.print(
        "        const v = {s}{s}[@as(u32, d)];\n",
        .{ p, input.name },
    );
    try writer.writeAll("        sq += v * v;\n");
    try writer.writeAll("    }\n");
    try writer.writeAll("    const inv_norm = 1.0 / math.sqrt(sq + l2_eps);\n");
    try writer.writeAll("    for (@range(i16, hidden_size)) |d| {\n");
    try writer.print(
        "        {s}{s}[@as(u32, d)] = {s}{s}[@as(u32, d)] * inv_norm;\n",
        .{ p, output.name, p, input.name },
    );
    try writer.writeAll("    }\n");
    try writer.writeAll("    sys_mod.unblock_cmd_stream();\n");
    try writer.writeAll("}\n\n");
    try writer.writeAll("comptime {\n");
    try body_emit.writeCslExportSymbol(writer, p, input.name);
    try body_emit.writeCslExportSymbol(writer, p, output.name);
    try writer.writeAll("    @export_symbol(compute);\n");
    try writer.writeAll("}\n");
}
