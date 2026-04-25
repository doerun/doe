// emit_csl_semantic_ops.zig — direct CSL for model-semantic scalar kernels.
//
// These kernels are small enough that lowering through a toy WGSL fixture
// loses the semantic contract. Emit them directly so the HostPlan source
// matches the reference interpreter formulas.

const std = @import("std");
const spec = @import("csl_spec.zig");

pub const EmitError = error{
    OutputTooLarge,
    UnsupportedPattern,
};

const RMS_EPS: []const u8 = "0.000001";

pub fn isSemanticPattern(pattern: []const u8) bool {
    return std.mem.eql(u8, pattern, "rms_norm") or
        std.mem.eql(u8, pattern, "residual_add") or
        std.mem.eql(u8, pattern, "gelu_gated");
}

pub fn emitLayout(buf: []u8, pos: *usize, pattern: []const u8) EmitError!void {
    if (std.mem.eql(u8, pattern, "rms_norm")) return emitRmsNormLayout(buf, pos);
    if (std.mem.eql(u8, pattern, "residual_add")) return emitElementwiseLayout(buf, pos, .residual);
    if (std.mem.eql(u8, pattern, "gelu_gated")) return emitElementwiseLayout(buf, pos, .gelu);
    return error.UnsupportedPattern;
}

pub fn emitPeProgram(buf: []u8, pos: *usize, pattern: []const u8) EmitError!void {
    if (std.mem.eql(u8, pattern, "rms_norm")) return emitRmsNormPe(buf, pos);
    if (std.mem.eql(u8, pattern, "residual_add")) return emitResidualPe(buf, pos);
    if (std.mem.eql(u8, pattern, "gelu_gated")) return emitGeluPe(buf, pos);
    return error.UnsupportedPattern;
}

fn emitRmsNormLayout(buf: []u8, pos: *usize) EmitError!void {
    try write(buf, pos, "// Layout: RMSNorm, one token per PE.\n\n");
    try write(buf, pos, "param width: i16;\n\n");
    try write(buf, pos, "const memcpy = @import_module(\"<memcpy/get_params>\", .{\n");
    try write(buf, pos, "    .width = width,\n");
    try write(buf, pos, "    .height = 1,\n");
    try write(buf, pos, "});\n\n");
    try write(buf, pos, "layout {\n");
    try write(buf, pos, "    @set_rectangle(width, 1);\n\n");
    try write(buf, pos, "    for (@range(i16, width)) |pe_x| {\n");
    try write(buf, pos, "        @set_tile_code(pe_x, 0, \"");
    try write(buf, pos, spec.PE_PROGRAM_FILENAME);
    try write(buf, pos, "\", .{\n");
    try write(buf, pos, "            .memcpy_params = memcpy.get_params(pe_x),\n");
    try write(buf, pos, "        });\n");
    try write(buf, pos, "    }\n\n");
    try write(buf, pos, "    @export_name(\"input\", [*]f32, true);\n");
    try write(buf, pos, "    @export_name(\"weight\", [*]f32, true);\n");
    try write(buf, pos, "    @export_name(\"output\", [*]f32, true);\n");
    try write(buf, pos, "    @export_name(\"compute\", fn()void);\n");
    try write(buf, pos, "}\n");
}

const ElementwiseKind = enum { residual, gelu };

fn emitElementwiseLayout(buf: []u8, pos: *usize, kind: ElementwiseKind) EmitError!void {
    const title = switch (kind) {
        .residual => "residual add",
        .gelu => "gated GELU",
    };
    try write(buf, pos, "// Layout: ");
    try write(buf, pos, title);
    try write(buf, pos, ", one activation vector per PE.\n\n");
    try write(buf, pos, "param width: u16;\n");
    try write(buf, pos, "param height: u16;\n\n");
    try write(buf, pos, "const memcpy = @import_module(\"<memcpy/get_params>\", .{\n");
    try write(buf, pos, "    .width = width,\n");
    try write(buf, pos, "    .height = height,\n");
    try write(buf, pos, "});\n\n");
    try write(buf, pos, "layout {\n");
    try write(buf, pos, "    @set_rectangle(width, height);\n\n");
    try write(buf, pos, "    for (@range(u16, height)) |pe_y| {\n");
    try write(buf, pos, "        for (@range(u16, width)) |pe_x| {\n");
    try write(buf, pos, "            @set_tile_code(pe_x, pe_y, \"");
    try write(buf, pos, spec.PE_PROGRAM_FILENAME);
    try write(buf, pos, "\", .{\n");
    try write(buf, pos, "                .memcpy_params = memcpy.get_params(pe_x),\n");
    try write(buf, pos, "            });\n");
    try write(buf, pos, "        }\n");
    try write(buf, pos, "    }\n\n");
    switch (kind) {
        .residual => {
            try write(buf, pos, "    @export_name(\"a\", [*]f32, true);\n");
            try write(buf, pos, "    @export_name(\"b\", [*]f32, true);\n");
        },
        .gelu => {
            try write(buf, pos, "    @export_name(\"input\", [*]f32, true);\n");
            try write(buf, pos, "    @export_name(\"gate\", [*]f32, true);\n");
        },
    }
    try write(buf, pos, "    @export_name(\"output\", [*]f32, true);\n");
    try write(buf, pos, "    @export_name(\"compute\", fn()void);\n");
    try write(buf, pos, "}\n");
}

fn emitRmsNormPe(buf: []u8, pos: *usize) EmitError!void {
    try write(buf, pos, "// PE program: RMSNorm, full hidden vector per token.\n\n");
    try write(buf, pos, "param memcpy_params;\n");
    try write(buf, pos, "param hidden_size: i16;\n\n");
    try write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try write(buf, pos, "const math = @import_module(\"<math>\");\n");
    try write(buf, pos, "const rms_eps: f32 = ");
    try write(buf, pos, RMS_EPS);
    try write(buf, pos, ";\n\n");
    try emitBuf(buf, pos, "input", "[hidden_size]f32");
    try emitBuf(buf, pos, "weight", "[hidden_size]f32");
    try emitBuf(buf, pos, "output", "[hidden_size]f32");
    try write(buf, pos, "\n");
    try emitPtr(buf, pos, "input", "f32");
    try emitPtr(buf, pos, "weight", "f32");
    try emitPtr(buf, pos, "output", "f32");
    try write(buf, pos, "\n");
    try write(buf, pos, "fn compute() void {\n");
    try write(buf, pos, "    var sum_sq: f32 = 0.0;\n");
    try write(buf, pos, "    for (@range(i16, hidden_size)) |i| {\n");
    try write(buf, pos, "        const idx = @as(u32, i);\n");
    try write(buf, pos, "        const x = input[idx];\n");
    try write(buf, pos, "        sum_sq += x * x;\n");
    try write(buf, pos, "    }\n\n");
    try write(buf, pos, "    const mean_sq = sum_sq / @as(f32, hidden_size);\n");
    try write(buf, pos, "    const inv_rms = 1.0 / math.sqrt(mean_sq + rms_eps);\n");
    try write(buf, pos, "    for (@range(i16, hidden_size)) |i| {\n");
    try write(buf, pos, "        const idx = @as(u32, i);\n");
    try write(buf, pos, "        output[idx] = input[idx] * inv_rms * (1.0 + weight[idx]);\n");
    try write(buf, pos, "    }\n");
    try write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try write(buf, pos, "}\n\n");
    const exports = [_][]const u8{ "input", "weight", "output" };
    try emitComptime(buf, pos, &exports);
}

fn emitResidualPe(buf: []u8, pos: *usize) EmitError!void {
    try write(buf, pos, "// PE program: residual add, full activation vector per PE.\n\n");
    try write(buf, pos, "param memcpy_params;\n");
    try write(buf, pos, "param chunk_size: i16;\n\n");
    try write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n\n");
    try emitBuf(buf, pos, "a", "[chunk_size]f32");
    try emitBuf(buf, pos, "b", "[chunk_size]f32");
    try emitBuf(buf, pos, "output", "[chunk_size]f32");
    try write(buf, pos, "\n");
    try emitPtr(buf, pos, "a", "f32");
    try emitPtr(buf, pos, "b", "f32");
    try emitPtr(buf, pos, "output", "f32");
    try write(buf, pos, "\n");
    try write(buf, pos, "fn compute() void {\n");
    try write(buf, pos, "    for (@range(i16, chunk_size)) |i| {\n");
    try write(buf, pos, "        const idx = @as(u32, i);\n");
    try write(buf, pos, "        output[idx] = a[idx] + b[idx];\n");
    try write(buf, pos, "    }\n");
    try write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try write(buf, pos, "}\n\n");
    const exports = [_][]const u8{ "a", "b", "output" };
    try emitComptime(buf, pos, &exports);
}

fn emitGeluPe(buf: []u8, pos: *usize) EmitError!void {
    try write(buf, pos, "// PE program: gated GELU, output = gelu(gate) * input.\n\n");
    try write(buf, pos, "param memcpy_params;\n");
    try write(buf, pos, "param chunk_size: i16;\n\n");
    try write(buf, pos, "const sys_mod = @import_module(\"<memcpy/memcpy>\", memcpy_params);\n");
    try write(buf, pos, "const math = @import_module(\"<math>\");\n");
    try write(buf, pos, "const GELU_A: f32 = 0.7978845608028654;\n");
    try write(buf, pos, "const GELU_B: f32 = 0.044715;\n\n");
    try emitBuf(buf, pos, "input", "[chunk_size]f32");
    try emitBuf(buf, pos, "gate", "[chunk_size]f32");
    try emitBuf(buf, pos, "output", "[chunk_size]f32");
    try write(buf, pos, "\n");
    try emitPtr(buf, pos, "input", "f32");
    try emitPtr(buf, pos, "gate", "f32");
    try emitPtr(buf, pos, "output", "f32");
    try write(buf, pos, "\n");
    try write(buf, pos, "fn gelu(x: f32) f32 {\n");
    try write(buf, pos, "    var inner = GELU_A * (x + GELU_B * x * x * x);\n");
    try write(buf, pos, "    if (inner < -15.0) inner = -15.0;\n");
    try write(buf, pos, "    if (inner > 15.0) inner = 15.0;\n");
    try write(buf, pos, "    return 0.5 * x * (1.0 + math.tanh(inner));\n");
    try write(buf, pos, "}\n\n");
    try write(buf, pos, "fn compute() void {\n");
    try write(buf, pos, "    for (@range(i16, chunk_size)) |i| {\n");
    try write(buf, pos, "        const idx = @as(u32, i);\n");
    try write(buf, pos, "        output[idx] = gelu(gate[idx]) * input[idx];\n");
    try write(buf, pos, "    }\n");
    try write(buf, pos, "    sys_mod.unblock_cmd_stream();\n");
    try write(buf, pos, "}\n\n");
    const exports = [_][]const u8{ "input", "gate", "output" };
    try emitComptime(buf, pos, &exports);
}

fn emitBuf(buf: []u8, pos: *usize, name: []const u8, ty: []const u8) EmitError!void {
    try write(buf, pos, "var ");
    try write(buf, pos, name);
    try write(buf, pos, ": ");
    try write(buf, pos, ty);
    try write(buf, pos, " = @zeros(");
    try write(buf, pos, ty);
    try write(buf, pos, ");\n");
}

fn emitPtr(buf: []u8, pos: *usize, name: []const u8, elem: []const u8) EmitError!void {
    try write(buf, pos, "var ");
    try write(buf, pos, name);
    try write(buf, pos, "_ptr: [*]");
    try write(buf, pos, elem);
    try write(buf, pos, " = &");
    try write(buf, pos, name);
    try write(buf, pos, ";\n");
}

fn emitComptime(buf: []u8, pos: *usize, names: []const []const u8) EmitError!void {
    try write(buf, pos, "comptime {\n");
    for (names) |name| {
        try write(buf, pos, "    @export_symbol(");
        try write(buf, pos, name);
        try write(buf, pos, "_ptr, \"");
        try write(buf, pos, name);
        try write(buf, pos, "\");\n");
    }
    try write(buf, pos, "    @export_symbol(compute);\n");
    try write(buf, pos, "}\n");
}

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}
